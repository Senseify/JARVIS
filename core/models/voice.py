"""Structured data models for JARVIS OS Voice Foundation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AudioFormat(str, Enum):
    """Supported audio container formats."""

    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"
    PCM = "pcm"


class VoiceInput(BaseModel):
    """Audio input payload for speech recognition."""

    model_config = ConfigDict(extra="forbid")

    audio_base64: str = Field(..., min_length=1, description="Base64-encoded audio payload")
    format: AudioFormat = Field(default=AudioFormat.WAV, description="Audio container format")
    sample_rate: int = Field(default=16000, gt=0, le=96000, description="Sample rate in Hertz")
    channels: int = Field(default=1, ge=1, le=2, description="Channel count (1=mono, 2=stereo)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Contextual audio metadata")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("audio_base64")
    @classmethod
    def validate_audio_base64(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("audio_base64 cannot be empty.")
        return cleaned


class SpeechRecognitionResult(BaseModel):
    """Structured transcription output returned by STT providers."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Recognized speech text")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    language: str = Field(default="en-US", description="Detected or requested language code")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Estimated or processed audio duration")
    is_final: bool = Field(default=True, description="Whether transcription is finalized")
    provider: str = Field(default="deterministic", description="Identifier of the executing STT provider")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific transcription metadata")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SpeechSynthesisRequest(BaseModel):
    """Parameters requesting text-to-speech synthesis."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=5000, description="Text to synthesize into spoken audio")
    voice_id: Optional[str] = Field(default=None, max_length=64, description="Target voice identifier")
    language: str = Field(default="en-US", max_length=16, description="Synthesis language code")
    speed: float = Field(default=1.0, gt=0.0, le=3.0, description="Speech playback speed multiplier")
    pitch: float = Field(default=1.0, gt=0.0, le=3.0, description="Voice pitch multiplier")
    format: AudioFormat = Field(default=AudioFormat.WAV, description="Desired audio output format")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom synthesis metadata")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Synthesis text cannot be empty or whitespace only.")
        return cleaned


class SpeechSynthesisResult(BaseModel):
    """Structured audio synthesis output returned by TTS providers."""

    model_config = ConfigDict(extra="forbid")

    audio_base64: str = Field(..., min_length=1, description="Base64-encoded synthesized audio payload")
    audio_bytes_length: int = Field(..., ge=1, description="Length of decoded audio payload in bytes")
    format: AudioFormat = Field(default=AudioFormat.WAV, description="Audio container format")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Duration of synthesized audio")
    sample_rate: int = Field(default=16000, gt=0, description="Audio sample rate in Hertz")
    provider: str = Field(default="deterministic", description="Identifier of the executing TTS provider")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific synthesis metadata")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VoiceState(BaseModel):
    """Runtime status of the voice subsystem."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ready", description="Status: 'ready', 'listening', 'transcribing', 'synthesizing', 'error'")
    is_listening: bool = False
    is_speaking: bool = False
    current_stt_provider: str = "deterministic"
    current_tts_provider: str = "deterministic"
    last_transcription: Optional[str] = None
    last_synthesized_text: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
