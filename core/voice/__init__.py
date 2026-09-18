"""Voice subsystem for JARVIS OS."""

from core.voice.audio import AudioInput, AudioOutput, create_wav_pcm
from core.voice.service import VoiceService
from core.voice.stt import BaseSTTProvider, DeterministicSTTProvider
from core.voice.tts import BaseTTSProvider, DeterministicTTSProvider

__all__ = [
    "AudioInput",
    "AudioOutput",
    "create_wav_pcm",
    "BaseSTTProvider",
    "DeterministicSTTProvider",
    "BaseTTSProvider",
    "DeterministicTTSProvider",
    "VoiceService",
]
