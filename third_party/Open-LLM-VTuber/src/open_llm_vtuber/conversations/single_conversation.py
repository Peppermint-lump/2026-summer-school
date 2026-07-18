from typing import Union, List, Dict, Any, Optional
import asyncio
import json
from loguru import logger
import numpy as np

from .conversation_utils import (
    create_batch_input,
    process_agent_output,
    send_conversation_start_signals,
    process_user_input,
    finalize_conversation_turn,
    cleanup_conversation,
    EMOJI_LIST,
)
from .types import WebSocketSend
from .tts_manager import TTSTaskManager
from ..chat_history_manager import store_message
from ..service_context import ServiceContext
from ..emotion_middleware_client import (
    EmotionMiddlewareClient,
    EmotionMiddlewareResult,
)

# Import necessary types from agent outputs
from ..agent.output_types import SentenceOutput, AudioOutput


async def process_single_conversation(
    context: ServiceContext,
    websocket_send: WebSocketSend,
    client_uid: str,
    user_input: Union[str, np.ndarray],
    images: Optional[List[Dict[str, Any]]] = None,
    session_emoji: str = np.random.choice(EMOJI_LIST),
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Process a single-user conversation turn

    Args:
        context: Service context containing all configurations and engines
        websocket_send: WebSocket send function
        client_uid: Client unique identifier
        user_input: Text or audio input from user
        images: Optional list of image data
        session_emoji: Emoji identifier for the conversation
        metadata: Optional metadata for special processing flags

    Returns:
        str: Complete response text
    """
    # Create TTSTaskManager for this conversation
    tts_manager = TTSTaskManager()
    full_response = ""  # Initialize full_response here
    emotion_result: Optional[EmotionMiddlewareResult] = None
    emotion_action_applied = False

    try:
        # Send initial signals
        await send_conversation_start_signals(websocket_send)
        logger.info(f"New Conversation Chain {session_emoji} started!")

        # Preserve raw audio only long enough to call the independent audio observer.
        raw_audio = user_input.copy() if isinstance(user_input, np.ndarray) else None

        # Process user input
        input_text = await process_user_input(
            user_input, context.asr_engine, websocket_send
        )

        emotion_client = EmotionMiddlewareClient.from_environment()
        if emotion_client is not None:
            emotion_result = await emotion_client.analyze(
                session_id=client_uid,
                transcript=input_text,
                raw_audio=raw_audio,
            )
        raw_audio = None
        if emotion_result is not None:
            avatar_expression_indices = context.live2d_model.extract_emotion(
                f"[{emotion_result.expression}]"
            )[:1]
            metadata = dict(metadata or {})
            metadata["emotion_companion_context"] = emotion_result.companion_context
            metadata["authoritative_expression"] = emotion_result.expression
            metadata["authoritative_motion"] = emotion_result.motion
            logger.info(
                "Emotion middleware completed turn={} expression={} motion={} trace={}",
                emotion_result.turn_id,
                emotion_result.expression,
                emotion_result.motion,
                emotion_result.trace_directory or "disabled",
            )
            await websocket_send(
                json.dumps(
                    {
                        "type": "emotion-analysis",
                        "turn_id": emotion_result.turn_id,
                        "analysis": emotion_result.payload.get("analysis"),
                        "avatar_state": emotion_result.payload.get("avatar_state"),
                        "trace_directory": emotion_result.trace_directory,
                    },
                    ensure_ascii=False,
                )
            )
            await websocket_send(
                json.dumps(
                    {
                        "type": "avatar-state",
                        "turn_id": emotion_result.turn_id,
                        "expression": emotion_result.expression,
                        "expression_index": (
                            avatar_expression_indices[0]
                            if avatar_expression_indices
                            else None
                        ),
                        "motion": emotion_result.motion,
                    }
                )
            )

        # Create batch input
        batch_input = create_batch_input(
            input_text=input_text,
            images=images,
            from_name=context.character_config.human_name,
            metadata=metadata,
        )

        # Store user message (check if we should skip storing to history)
        skip_history = metadata and metadata.get("skip_history", False)
        if context.history_uid and not skip_history:
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="human",
                content=input_text,
                name=context.character_config.human_name,
            )

        if skip_history:
            logger.debug("Skipping storing user input to history (proactive speak)")

        logger.info(f"User input: {input_text}")
        if images:
            logger.info(f"With {len(images)} images")

        try:
            # agent.chat yields Union[SentenceOutput, Dict[str, Any]]
            agent_output_stream = context.agent_engine.chat(batch_input)

            async for output_item in agent_output_stream:
                if (
                    isinstance(output_item, dict)
                    and output_item.get("type") == "tool_call_status"
                ):
                    # Handle tool status event: send WebSocket message
                    output_item["name"] = context.character_config.character_name
                    logger.debug(f"Sending tool status update: {output_item}")

                    await websocket_send(json.dumps(output_item))

                elif isinstance(output_item, (SentenceOutput, AudioOutput)):
                    if emotion_result is not None:
                        output_item.actions.expressions = None
                        if not emotion_action_applied:
                            expressions = context.live2d_model.extract_emotion(
                                f"[{emotion_result.expression}]"
                            )
                            if expressions:
                                output_item.actions.expressions = expressions[:1]
                            emotion_action_applied = True
                    # Handle SentenceOutput or AudioOutput
                    response_part = await process_agent_output(
                        output=output_item,
                        character_config=context.character_config,
                        live2d_model=context.live2d_model,
                        tts_engine=context.tts_engine,
                        websocket_send=websocket_send,  # Pass websocket_send for audio/tts messages
                        tts_manager=tts_manager,
                        translate_engine=context.translate_engine,
                    )
                    # Ensure response_part is treated as a string before concatenation
                    response_part_str = (
                        str(response_part) if response_part is not None else ""
                    )
                    full_response += response_part_str  # Accumulate text response
                else:
                    logger.warning(
                        f"Received unexpected item type from agent chat stream: {type(output_item)}"
                    )
                    logger.debug(f"Unexpected item content: {output_item}")

        except Exception as e:
            logger.exception(
                f"Error processing agent response stream: {e}"
            )  # Log with stack trace
            await websocket_send(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error processing agent response: {str(e)}",
                    }
                )
            )
            # full_response will contain partial response before error
        # --- End processing agent response ---

        # Wait for any pending TTS tasks
        if tts_manager.task_list:
            await asyncio.gather(*tts_manager.task_list)
            await websocket_send(json.dumps({"type": "backend-synth-complete"}))

        await finalize_conversation_turn(
            tts_manager=tts_manager,
            websocket_send=websocket_send,
            client_uid=client_uid,
        )

        if context.history_uid and full_response:  # Check full_response before storing
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="ai",
                content=full_response,
                name=context.character_config.character_name,
                avatar=context.character_config.avatar,
            )
            logger.info(f"AI response: {full_response}")

        return full_response  # Return accumulated full_response

    except asyncio.CancelledError:
        logger.info(f"🤡👍 Conversation {session_emoji} cancelled because interrupted.")
        raise
    except Exception as e:
        logger.error(f"Error in conversation chain: {e}")
        await websocket_send(
            json.dumps({"type": "error", "message": f"Conversation error: {str(e)}"})
        )
        raise
    finally:
        cleanup_conversation(tts_manager, session_emoji)
