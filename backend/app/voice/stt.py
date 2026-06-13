"""Groq Whisper API Speech-to-Text integration.

Converts audio buffers or file bytes into text transcripts by calling the
Groq Whisper API — no local model weights, no GPU memory, no CUDA required.

Architecture
------------
- Sends audio bytes to ``https://api.groq.com/openai/v1/audio/transcriptions``
  using a multipart/form-data POST (OpenAI-compatible endpoint).
- Reuses the project's existing ``GROQ_API_KEY`` — no new key needed.
- Supports WebM, MP3, MP4, M4A, WAV, OGG, FLAC (server-side decoding).
- VAD (``webrtcvad``) is applied upstream before calling this; the API also
  runs its own internal VAD so double-filtering is harmless.
- Returns a ``TranscriptResult`` dataclass with text, detected language,
  confidence, and processing latency.
- Both synchronous and async interfaces are provided.
- Falls back gracefully when ``GROQ_API_KEY`` is absent (raises ``STTError``
  only at call-time with a clear message).

Supported Groq Whisper models
------------------------------
- ``whisper-large-v3-turbo``  — fastest, best latency (default)
- ``whisper-large-v3``        — highest accuracy
- ``distil-whisper-large-v3-en`` — English-only, ultra-fast
"""

from __future__ import annotations

import asyncio
import io
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Union

import httpx

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

AudioInput = Union[bytes, BinaryIO, Path, str]

# Groq audio transcription endpoint (OpenAI-compatible)
_GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# Supported Groq Whisper model names
VALID_GROQ_WHISPER_MODELS = {
    "whisper-large-v3-turbo",
    "whisper-large-v3",
    "distil-whisper-large-v3-en",
}

# Groq free-tier limit: 20 MB per audio file, 7200 seconds/day
_MAX_AUDIO_BYTES = 20 * 1024 * 1024  # 20 MB


@dataclass
class TranscriptResult:
    """Holds the result of a transcription operation."""

    text: str
    language: str = "en"
    confidence: float = 1.0
    latency_ms: float = 0.0
    segments: list[dict] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True if the transcript is blank or whitespace only."""
        return not self.text.strip()


class STTError(RuntimeError):
    """Raised when speech-to-text transcription fails."""


class GroqSTT:
    """Groq Whisper API Speech-to-Text client.

    Uses the Groq cloud API — zero local memory footprint, no GPU required.
    Reuses ``GROQ_API_KEY`` already present in the project for LLM calls.

    Parameters
    ----------
    api_key:
        Groq API key.  Falls back to ``GROQ_API_KEY`` env var.
    model:
        Groq Whisper model variant.  Defaults to ``"whisper-large-v3-turbo"``
        (best speed/accuracy balance for travel voice queries).
        Accepted values: ``whisper-large-v3-turbo``, ``whisper-large-v3``,
        ``distil-whisper-large-v3-en``.
    language:
        ISO 639-1 language hint (e.g. ``"en"``).  ``None`` enables
        auto-detection.  Providing the correct language improves accuracy
        and reduces latency slightly.
    temperature:
        Sampling temperature (0–1).  ``0`` is deterministic; higher values
        allow more creative transcription (not recommended for travel queries).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "whisper-large-v3-turbo",
        language: str | None = "en",
        temperature: float = 0.0,
    ) -> None:
        if model not in VALID_GROQ_WHISPER_MODELS:
            raise STTError(
                f"model must be one of {VALID_GROQ_WHISPER_MODELS}, got '{model}'"
            )

        settings = get_settings()
        self._api_key = api_key or getattr(settings, "groq_api_key", None)
        self.model = model
        self.language = language
        self.temperature = temperature

        logger.info(
            "GroqSTT configured",
            extra={
                "event": {
                    "model": model,
                    "language": language,
                    "api_key_set": bool(self._api_key),
                }
            },
        )

    # ── Synchronous transcription ────────────────────────────────────────────

    def transcribe(self, audio_input: AudioInput, filename: str | None = None) -> TranscriptResult:
        """Transcribe audio by calling the Groq Whisper API.

        Parameters
        ----------
        audio_input:
            One of:
            - ``bytes``: raw audio bytes (WAV, MP3, OGG, WebM, FLAC, M4A).
            - File-like object with a ``read()`` method.
            - ``pathlib.Path`` or ``str`` path to an audio file on disk.
        filename:
            Original audio filename with extension to aid decoding.

        Returns
        -------
        TranscriptResult
            Contains ``.text``, ``.language``, ``.confidence``, ``.latency_ms``.

        Raises
        ------
        STTError
            If the API key is missing, audio is too large, or the API call fails.
        """
        if not self._api_key:
            raise STTError(
                "Groq API key not set. Set GROQ_API_KEY in your .env file."
            )

        # Normalise input to (filename, bytes) tuple
        filename, audio_bytes = self._normalise_input(audio_input, filename)

        if len(audio_bytes) == 0:
            raise STTError("Audio input is empty.")

        if len(audio_bytes) > _MAX_AUDIO_BYTES:
            raise STTError(
                f"Audio file exceeds Groq's 20 MB limit "
                f"({len(audio_bytes) / 1024 / 1024:.1f} MB)."
            )

        t0 = time.perf_counter()
        try:
            response_data = self._call_api_sync(filename, audio_bytes)
        except STTError:
            raise
        except Exception as exc:
            raise STTError(f"Groq Whisper API call failed: {exc}") from exc

        latency_ms = (time.perf_counter() - t0) * 1000

        text = (response_data.get("text") or "").strip()
        language = response_data.get("language") or self.language or "en"

        logger.info(
            "GroqSTT transcription complete",
            extra={
                "event": {
                    "text_length": len(text),
                    "language": language,
                    "latency_ms": round(latency_ms, 1),
                    "model": self.model,
                }
            },
        )

        return TranscriptResult(
            text=text,
            language=language,
            confidence=1.0,    # Groq API does not return per-word confidence
            latency_ms=latency_ms,
            segments=[],       # Groq basic transcription returns flat text
        )

    # ── Async transcription ──────────────────────────────────────────────────

    async def atranscribe(self, audio_input: AudioInput, filename: str | None = None) -> TranscriptResult:
        """Async transcription — calls the Groq API with an async HTTP client."""
        if not self._api_key:
            raise STTError(
                "Groq API key not set. Set GROQ_API_KEY in your .env file."
            )

        filename, audio_bytes = self._normalise_input(audio_input, filename)

        if len(audio_bytes) == 0:
            raise STTError("Audio input is empty.")

        if len(audio_bytes) > _MAX_AUDIO_BYTES:
            raise STTError(
                f"Audio file exceeds Groq's 20 MB limit "
                f"({len(audio_bytes) / 1024 / 1024:.1f} MB)."
            )

        t0 = time.perf_counter()
        try:
            response_data = await self._call_api_async(filename, audio_bytes)
        except STTError:
            raise
        except Exception as exc:
            raise STTError(f"Groq Whisper API call failed: {exc}") from exc

        latency_ms = (time.perf_counter() - t0) * 1000
        text = (response_data.get("text") or "").strip()
        language = response_data.get("language") or self.language or "en"

        logger.info(
            "GroqSTT async transcription complete",
            extra={
                "event": {
                    "text_length": len(text),
                    "language": language,
                    "latency_ms": round(latency_ms, 1),
                }
            },
        )

        return TranscriptResult(
            text=text,
            language=language,
            confidence=1.0,
            latency_ms=latency_ms,
            segments=[],
        )

    # ── HTTP helpers ─────────────────────────────────────────────────────────

    def _call_api_sync(self, filename: str, audio_bytes: bytes) -> dict:
        """Synchronous HTTP call to Groq transcription endpoint."""
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Map file extension to MIME type
        content_type = "audio/wav"
        filename_lower = filename.lower()
        if filename_lower.endswith(".mp4") or filename_lower.endswith(".m4a"):
            content_type = "audio/mp4"
        elif filename_lower.endswith(".webm"):
            content_type = "audio/webm"
        elif filename_lower.endswith(".mp3"):
            content_type = "audio/mpeg"
        elif filename_lower.endswith(".ogg"):
            content_type = "audio/ogg"

        files = {"file": (filename, io.BytesIO(audio_bytes), content_type)}
        data = {"model": self.model, "response_format": "json"}
        if self.language:
            data["language"] = self.language
        if self.temperature != 0.0:
            data["temperature"] = str(self.temperature)

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                _GROQ_TRANSCRIPTION_URL,
                headers=headers,
                files=files,
                data=data,
            )
        self._raise_for_status(resp)
        return resp.json()

    async def _call_api_async(self, filename: str, audio_bytes: bytes) -> dict:
        """Asynchronous HTTP call to Groq transcription endpoint."""
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Map file extension to MIME type
        content_type = "audio/wav"
        filename_lower = filename.lower()
        if filename_lower.endswith(".mp4") or filename_lower.endswith(".m4a"):
            content_type = "audio/mp4"
        elif filename_lower.endswith(".webm"):
            content_type = "audio/webm"
        elif filename_lower.endswith(".mp3"):
            content_type = "audio/mpeg"
        elif filename_lower.endswith(".ogg"):
            content_type = "audio/ogg"

        files = {"file": (filename, io.BytesIO(audio_bytes), content_type)}
        data = {"model": self.model, "response_format": "json"}
        if self.language:
            data["language"] = self.language
        if self.temperature != 0.0:
            data["temperature"] = str(self.temperature)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _GROQ_TRANSCRIPTION_URL,
                headers=headers,
                files=files,
                data=data,
            )
        self._raise_for_status(resp)
        return resp.json()

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        """Convert HTTP error responses to STTError."""
        if resp.status_code == 401:
            raise STTError("Groq API key invalid or missing (401 Unauthorized).")
        if resp.status_code == 413:
            raise STTError("Audio file too large for Groq API (413).")
        if resp.status_code == 429:
            raise STTError("Groq API rate limit exceeded (429). Retry later.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            raise STTError(
                f"Groq API error {exc.response.status_code}: {body}"
            ) from exc

    # ── Input normalisation ──────────────────────────────────────────────────

    @staticmethod
    def _normalise_input(audio_input: AudioInput, filename: str | None = None) -> tuple[str, bytes]:
        """Return (filename, bytes) from any supported input type."""
        if filename:
            if isinstance(audio_input, (str, Path)):
                return filename, Path(audio_input).read_bytes()
            if isinstance(audio_input, bytes):
                return filename, audio_input
            return filename, audio_input.read()

        if isinstance(audio_input, (str, Path)):
            p = Path(audio_input)
            return p.name, p.read_bytes()
        if isinstance(audio_input, bytes):
            return "audio.wav", audio_input
        # File-like object
        name = getattr(audio_input, "name", "audio.wav")
        return Path(name).name, audio_input.read()

    # ── Editable transcript helpers ──────────────────────────────────────────

    @staticmethod
    def build_editable_response(result: TranscriptResult) -> dict:
        """Return a dict suitable for sending to the frontend for confirmation.

        The frontend displays ``transcript`` to the user who can edit it before
        it is submitted to the planning pipeline.
        """
        return {
            "transcript": result.text,
            "language": result.language,
            "confidence": round(result.confidence, 3),
            "editable": True,
            "requires_confirmation": True,
        }


def create_stt_from_settings() -> GroqSTT:
    """Factory that reads STT configuration from app Settings."""
    settings = get_settings()
    model = getattr(settings, "groq_whisper_model", "whisper-large-v3-turbo")
    api_key = getattr(settings, "groq_api_key", None)
    return GroqSTT(api_key=api_key, model=model)


# ---------------------------------------------------------------------------
# Backwards-compat alias so any code still referencing ``WhisperSTT`` works
# until it is updated to use ``GroqSTT`` directly.
# ---------------------------------------------------------------------------
WhisperSTT = GroqSTT
