"""Narrow adapters that connect first-party services to the conversation lifecycle."""

from .video_emotion_middleware import VideoEmotionMiddleware

__all__ = ["VideoEmotionMiddleware"]
from .emotion_middleware import EmotionMiddleware

__all__ = ["EmotionMiddleware"]
