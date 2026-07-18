# Upstream patches

## Open-LLM-VTuber v1.2.1

- Upstream path: `third_party/Open-LLM-VTuber/`
- Upstream repository: `https://github.com/Open-LLM-VTuber/Open-LLM-VTuber.git`
- Pinned version: `v1.2.1`
- Pinned commit currently checked out locally: `3afa41014b4548a0842e9ee2f576f4b164b48886`

### Local model registry entry

- Reason: register the locally purchased Xiaohudie Live2D runtime copy for development.
- Upstream file: `model_dict.json`
- Expected behavior: Open-LLM-VTuber can resolve `live2d_model_name: xiaohudie` to `/live2d-models/xiaohudie/runtime/xiaohudie.model3.json`.
- Validation: `xiaohudie.model3.json` parses successfully, all referenced runtime files exist, and `conf.yaml` validates with `live2d_model_name: xiaohudie`.

### Xiaohudie runtime asset adaptation

- Reason: VTube Studio expressions and hotkey motions were toggle-style and could remain active or overlap in Open-LLM-VTuber.
- Runtime files: `live2d-models/xiaohudie/runtime/`
- Expected behavior:
  - expression index `0` is a neutral reset expression;
  - expressions use loader-compatible `Add` blend values and clear sibling expression parameters;
  - non-idle motions remain non-looping and retain their authored curves;
  - lip sync uses `ParamMouthOpenY`.
- Resource adaptation: `scripts/prepare_xiaohudie_one_shot_motions.py` changes only `Meta.Loop` to `false` for Greeting, CatchButterfly, and HoldBear. Their authored curves and durations remain unchanged; parameter restoration belongs to the frontend lifecycle controller.
- Validation: `xiaohudie.model3.json` parses successfully, all referenced runtime files exist, expressions cover the expected toggle parameters, and non-idle motions have `Loop: false`.

Apart from the narrowly scoped silent-TTS patch documented below, no other upstream Python source patches have been applied.

Project-specific behavior should be added through adapters under `apps/backend/app/integration/` unless a narrow upstream patch is unavoidable.

### Silent-TTS expression dispatch

- Reason: the bundled frontend only applies `actions.expressions` in its audio-playback branch. When Edge TTS is unavailable, upstream sends an `audio: null` payload and valid Live2D expression actions are ignored.
- Upstream file and function: `src/open_llm_vtuber/utils/stream_audio.py`, `prepare_audio_payload`.
- Expected behavior: a TTS failure sends a 1.5 second silent WAV payload with zero volumes, so the frontend still executes the existing expression path long enough for the 250 ms expression fade-in to be visible while the reply remains text-only.
- Validation: start with a deliberately unavailable TTS provider, send an assistant reply beginning with `[heart]`, and confirm an audio payload contains base64 WAV data plus `actions.expressions`.

### Local Piper TTS adapter

- Reason: Edge TTS depends on an external Bing WebSocket that is blocked in the target environment. The MVP needs an offline Windows TTS path.
- Upstream files: `src/open_llm_vtuber/tts/piper_tts.py`; `src/open_llm_vtuber/tts/tts_factory.py`; `src/open_llm_vtuber/config_manager/tts.py`; `pyproject.toml`; TTS configuration templates.
- Expected behavior: `tts_model: piper_tts` invokes `python -X utf8 -m piper` from the active virtual environment and generates a local WAV using the configured `.onnx` voice model. UTF-8 mode is required for Chinese text on Windows.
- Validation: confirm config parsing, then synthesize a Chinese sentence and verify that the generated WAV is nonempty.

### Xiaohudie companion expression and tap-motion mapping

- Reason: map the purchased model's named visual effects to the companion safety policy and expose its three non-looping poses without overlapping toggle states.
- Upstream files: `model_dict.json`; `prompts/utils/live2d_expression_prompt.txt`.
- Expected behavior: normal, uncertain, and low-affect contexts remain neutral; positive content selects star, heart, or butterfly; compliments use blush; sleepy and cry are restricted to the documented contexts. Named head and body hit areas let taps reliably select Greeting or CatchButterfly from the head and HoldBear from the body.
- Validation: confirm `Live2dModel('xiaohudie').extract_emotion('[heart] hi') == [5]`, verify all mapped indices are within the eight registered expressions, confirm every non-idle motion has `Loop: false`, then click each hit area after model load.

### Xiaohudie special-motion lifecycle controller

- Reason: Cubism restarts the `Idle` group after a one-shot motion finishes, but the Xiaohudie Idle resource controls only three parameters and none of the 11, 6, and 203 parameters touched by Greeting, CatchButterfly, and HoldBear. Saved special-motion values therefore survive the Idle restart.
- Upstream files: `frontend/index.html`; `frontend/avatar-motion-controller.js`; `src/open_llm_vtuber/agent/transformers.py`.
- Expected behavior: tap motions are routed through one controller. It captures a pre-motion parameter/part-opacity baseline and waits on the exact queue handle returned by `startMotion` using `CubismMotionQueueManager.isFinishedByHandle`. Greeting, CatchButterfly, and HoldBear remain visible for at least 5, 6, and 3 seconds respectively; an early SDK completion holds the final pose until that presentation window ends. A replacement request cancels the old request, cancels its animation-frame poll, calls the SDK's `stopAllMotions`, restores the baseline, and starts only the newest special motion. Natural completion interpolates parameters and part opacity back to the baseline over 500 ms, applies `neutral`, and then starts `Idle`. Backend expression extraction emits at most one legal expression index and never uses implicit motion indices.
- Debugging: set `localStorage.live2dDebug = "true"` and reload to log controller attachment, model count, motion group/index, timing, completion source, token/state, restored values, and Idle restart. No per-frame logging is added.
- Validation: test Idle -> each special motion -> Idle, the ordered three-motion sequence, and rapid Greeting -> HoldBear. Confirm one model instance, stale callback suppression, restored props/pose, and continued TTS/lip sync.

### Adaptive video backgrounds

- Reason: use the locally selected daytime and nighttime scene videos as a responsive background that follows the user's local clock.
- Upstream files: `frontend/index.html`; `frontend/adaptive-background.js`; `src/open_llm_vtuber/config_manager/utils.py`; private runtime files under `backgrounds/`.
- Expected behavior: the background component renders MP4/WebM sources as muted, looping, inline video with `object-fit: cover`; it selects daytime from `06:00` through `16:59` and nighttime otherwise, checking once per minute.
- Validation: verify both runtime videos return HTTP 200, force each time branch in browser developer tools, and confirm the video fills the viewport without stretching while Live2D remains interactive above it.

## Felix selectable character

- Upstream files: `model_dict.json`, `characters/felix.yaml`, `frontend/avatar-motion-controller.js`.
- Local runtime files: `live2d-models/felix/runtime/` (private and Git-ignored).
- Reason: register the locally supplied Felix model as a second selectable character while keeping Xiaohudie as the default.
- Adaptation: the runtime `wd66.model3.json` registers the supplied expression presets and `ParamMouthOpenY`; only emotion-safe presets are exposed through `emotionMap`. Outfit, prop, and pose toggles remain available to the model but are not selected by the LLM.
- Persona and voice isolation: `felix_001` contains Felix's identity and speaking style and selects the local `zh_CN-chaowen-medium` Piper male voice; it does not alter the base Xiaohudie persona or `zh_CN-huayan-medium` voice.
- Controller boundary: the Xiaohudie special-motion lifecycle patch now activates only for models that provide `Greeting`, `CatchButterfly`, and `HoldBear`, so switching to Felix preserves its native expression behavior.
- Validation: parse both JSON files, validate `felix.yaml`, verify every referenced Felix runtime file and both Piper voice files exist, synthesize a Chinese smoke-test sentence, and switch between `xiaohudie_001` and `felix_001` in the frontend.
