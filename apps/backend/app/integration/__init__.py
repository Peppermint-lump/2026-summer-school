"""Narrow adapters that connect first-party services to the conversation lifecycle."""

from .emotion_middleware import EmotionMiddleware
from .video_emotion_middleware import VideoEmotionMiddleware

__all__ = ["EmotionMiddleware", "VideoEmotionMiddleware"]
