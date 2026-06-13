"""Text-to-Speech integration with ElevenLabs and Gemini Live TTS.

Converts a text summary into a spoken-word audio file (MP3 / PCM).
The TTS layer is designed for generating concise trip summaries (30–45 sec)
rather than reading out full itineraries.

Architecture
------------
- Thin async wrapper around ElevenLabs REST API (``/v1/text-to-speech``).
- Fallback to Google Gemini Live TTS API when ElevenLabs is unavailable.
- All network calls are made with ``httpx.AsyncClient``.
- Returns a ``TTSResult`` dataclass with audio bytes, format, duration, and
  latency.
- A synchronous helper is provided for testing contexts.
- Falls back gracefully when ``ELEVENLABS_API_KEY`` is absent (useful for
  local testing without credentials).
- Redis caching for common phrases to reduce API calls.
- Request throttling for Gemini TTS to prevent quota exhaustion.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import struct
import time
from dataclasses import dataclass, field
from typing import Optional

import google.genai as genai
from google.genai import types
import httpx

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ElevenLabs REST endpoint
_ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"

# Default voice — "Jessica"
# Override via ELEVENLABS_VOICE_ID env var (DEC-021)
_DEFAULT_VOICE_ID = "cgSgspJ2msm6clMCkdW9"

# Gemini Live TTS endpoint
_GEMINI_LIVE_TTS_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Supported output formats
_SUPPORTED_FORMATS = {"mp3_44100_128", "mp3_22050_32", "pcm_16000", "pcm_22050", "pcm_24000", "wav"}

# Word-per-minute estimate for duration calculation (~150 wpm for clear speech)
_WORDS_PER_MINUTE = 150

# Redis cache TTL for TTS responses (24 hours)
_TTS_CACHE_TTL = 86400

# Gemini TTS request throttling (max 1 request per 2 seconds to stay within quota)
_GEMINI_TTS_THROTTLE_SECONDS = 2.0

# Throttling state for Gemini TTS
_gemini_last_request_time = 0.0
_gemini_request_lock = asyncio.Lock()


# ── Audio Format Helpers ──────────────────────────────────────────────────────

def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap raw 16-bit PCM mono data in a WAV container."""
    num_channels = 1
    bits_per_sample = 16
    block_align = num_channels * (bits_per_sample // 8)
    byte_rate = sample_rate * block_align
    subchunk2_size = len(pcm_data)
    chunk_size = 36 + subchunk2_size
    
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        chunk_size,
        b'WAVE',
        b'fmt ',
        16,                # Subchunk1Size
        1,                 # AudioFormat (1 = PCM)
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        subchunk2_size
    )
    return header + pcm_data



# ── Cache helpers ─────────────────────────────────────────────────────────────

def _get_cache_key(text: str, provider: str, voice_id: str, model: str = "") -> str:
    """Generate a cache key for TTS results."""
    key_data = f"{provider}:{voice_id}:{model}:{text}"
    return f"tts_cache:{hashlib.sha256(key_data.encode()).hexdigest()}"


async def _get_cached_tts(cache_key: str) -> Optional[TTSResult]:
    """Retrieve cached TTS result from Redis."""
    try:
        from app.services.redis_client import get_redis
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            audio_bytes = base64.b64decode(data["audio_bytes"])
            audio_format = data["audio_format"]
            
            # Retroactively wrap cached raw PCM audio in WAV so the browser can play it natively
            if audio_format == "pcm_24000":
                audio_bytes = pcm_to_wav(audio_bytes, sample_rate=24000)
                audio_format = "wav"
            elif audio_format == "pcm_22050":
                audio_bytes = pcm_to_wav(audio_bytes, sample_rate=22050)
                audio_format = "wav"
            elif audio_format == "pcm_16000":
                audio_bytes = pcm_to_wav(audio_bytes, sample_rate=16000)
                audio_format = "wav"
                
            return TTSResult(
                audio_bytes=audio_bytes,
                audio_format=audio_format,
                estimated_duration_sec=data["estimated_duration_sec"],
                latency_ms=0,  # Cached results have no latency
                voice_id=data["voice_id"],
                character_count=data["character_count"],
            )
    except Exception as exc:
        logger.warning(
            "Failed to retrieve cached TTS result",
            extra={"event": {"cache_key": cache_key, "error": str(exc)}},
        )
    return None


async def _cache_tts_result(cache_key: str, result: TTSResult) -> None:
    """Cache TTS result in Redis."""
    try:
        from app.services.redis_client import get_redis
        redis = await get_redis()
        data = {
            "audio_bytes": base64.b64encode(result.audio_bytes).decode(),
            "audio_format": result.audio_format,
            "estimated_duration_sec": result.estimated_duration_sec,
            "voice_id": result.voice_id,
            "character_count": result.character_count,
        }
        await redis.set(cache_key, json.dumps(data), ex=_TTS_CACHE_TTL)
        logger.info(
            "TTS result cached",
            extra={"event": {"cache_key": cache_key, "audio_format": result.audio_format}},
        )
    except Exception as exc:
        logger.warning(
            "Failed to cache TTS result",
            extra={"event": {"cache_key": cache_key, "error": str(exc)}},
        )


async def _throttle_gemini_request() -> None:
    """Throttle Gemini TTS requests to prevent quota exhaustion."""
    global _gemini_last_request_time
    async with _gemini_request_lock:
        now = time.perf_counter()
        time_since_last = now - _gemini_last_request_time
        if time_since_last < _GEMINI_TTS_THROTTLE_SECONDS:
            wait_time = _GEMINI_TTS_THROTTLE_SECONDS - time_since_last
            logger.info(
                "Throttling Gemini TTS request",
                extra={"event": {"wait_seconds": wait_time}},
            )
            await asyncio.sleep(wait_time)
        _gemini_last_request_time = time.perf_counter()

# Target summary length: 30–45 seconds → roughly 75–113 words at 150 wpm
SUMMARY_MIN_WORDS = 75
SUMMARY_MAX_WORDS = 112
SUMMARY_TARGET_DURATION_SEC = (30, 45)


@dataclass
class TTSResult:
    """Holds the result of a TTS synthesis operation."""

    audio_bytes: bytes
    audio_format: str
    estimated_duration_sec: float
    latency_ms: float
    voice_id: str
    character_count: int = 0


class TTSError(RuntimeError):
    """Raised when TTS synthesis fails."""


class ElevenLabsTTS:
    """ElevenLabs TTS client for voice summary generation.

    Parameters
    ----------
    api_key:
        ElevenLabs API key.  Falls back to ``ELEVENLABS_API_KEY`` env var.
    voice_id:
        ElevenLabs voice ID.  Falls back to ``ELEVENLABS_VOICE_ID`` env var,
        then to ``_DEFAULT_VOICE_ID`` (Rachel).
    model_id:
        TTS model.  ``"eleven_multilingual_v2"`` is the default.
    output_format:
        Audio encoding.  Defaults to ``"mp3_44100_128"``.
    stability:
        Voice stability (0–1).  Higher values are more consistent.
    similarity_boost:
        Voice similarity enhancement (0–1).
    style:
        Speaking style intensity (0–1, 0 = neutral).
    use_speaker_boost:
        Apply speaker boost post-processing.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "mp3_44100_128",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or getattr(settings, "elevenlabs_api_key", None)
        self._voice_id = (
            voice_id
            or getattr(settings, "elevenlabs_voice_id", None)
            or _DEFAULT_VOICE_ID
        )

        if output_format not in _SUPPORTED_FORMATS:
            raise TTSError(
                f"output_format must be one of {_SUPPORTED_FORMATS}, got '{output_format}'"
            )

        self.model_id = model_id
        self.output_format = output_format
        self.stability = stability
        self.similarity_boost = similarity_boost
        self.style = style
        self.use_speaker_boost = use_speaker_boost

        logger.info(
            "ElevenLabsTTS configured",
            extra={
                "event": {
                    "voice_id": self._voice_id,
                    "model_id": model_id,
                    "output_format": output_format,
                    "api_key_set": bool(self._api_key),
                }
            },
        )

    # ── Public async API ─────────────────────────────────────────────────────

    async def synthesise(self, text: str) -> TTSResult:
        """Convert ``text`` to speech and return a ``TTSResult``.

        Parameters
        ----------
        text:
            Text to synthesise.  Should be a concise trip summary targeting
            30–45 seconds of audio.

        Returns
        -------
        TTSResult
            Contains ``.audio_bytes``, ``.estimated_duration_sec``,
            ``.latency_ms``.

        Raises
        ------
        TTSError
            If the API key is missing or the API call fails.
        """
        if not text or not text.strip():
            raise TTSError("Cannot synthesise empty text.")

        if not self._api_key:
            raise TTSError(
                "ElevenLabs API key not set. "
                "Set ELEVENLABS_API_KEY in your .env file."
            )

        # Check cache first
        cache_key = _get_cache_key(text, "elevenlabs", self._voice_id, self.model_id)
        cached_result = await _get_cached_tts(cache_key)
        if cached_result:
            logger.info(
                "ElevenLabs TTS cache hit",
                extra={"event": {"cache_key": cache_key, "text_length": len(text)}},
            )
            return cached_result

        url = f"{_ELEVENLABS_BASE_URL}/text-to-speech/{self._voice_id}"
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text.strip(),
            "model_id": self.model_id,
            "output_format": self.output_format,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "style": self.style,
                "use_speaker_boost": self.use_speaker_boost,
            },
        }

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                audio_bytes = response.content
        except httpx.HTTPStatusError as exc:
            raise TTSError(
                f"ElevenLabs API error {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise TTSError(f"ElevenLabs network error: {exc}") from exc

        latency_ms = (time.perf_counter() - t0) * 1000
        word_count = len(text.split())
        estimated_duration_sec = (word_count / _WORDS_PER_MINUTE) * 60

        result = TTSResult(
            audio_bytes=audio_bytes,
            audio_format=self.output_format,
            estimated_duration_sec=estimated_duration_sec,
            latency_ms=latency_ms,
            voice_id=self._voice_id,
            character_count=len(text),
        )

        # Cache the result
        await _cache_tts_result(cache_key, result)

        logger.info(
            "ElevenLabs TTS synthesis complete",
            extra={
                "event": {
                    "char_count": len(text),
                    "word_count": word_count,
                    "estimated_duration_sec": round(estimated_duration_sec, 1),
                    "audio_bytes": len(audio_bytes),
                    "latency_ms": round(latency_ms, 1),
                }
            },
        )
        return result

    # ── Synchronous wrapper ──────────────────────────────────────────────────

    def synthesise_sync(self, text: str) -> TTSResult:
        """Blocking wrapper around ``synthesise`` (useful in tests)."""
        return asyncio.run(self.synthesise(text))

    # ── Summary builder ──────────────────────────────────────────────────────

    @staticmethod
    def trim_to_target_length(text: str, max_words: int = SUMMARY_MAX_WORDS) -> str:
        """Truncate ``text`` to at most ``max_words`` words.

        Appends an ellipsis if truncation occurs.  Ensures the voice summary
        stays within the 30–45 second target window (DEC-022).
        """
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words]) + "…"

    @staticmethod
    def estimate_duration_sec(text: str) -> float:
        """Estimate spoken duration of ``text`` in seconds."""
        word_count = len(text.split())
        return (word_count / _WORDS_PER_MINUTE) * 60

    @staticmethod
    def is_duration_within_target(text: str) -> bool:
        """Return True if estimated duration falls in the 30–45 sec window."""
        lo, hi = SUMMARY_TARGET_DURATION_SEC
        duration = ElevenLabsTTS.estimate_duration_sec(text)
        return lo <= duration <= hi


class GeminiTTS:
    """Gemini Native TTS client for voice summary generation.

    Uses Google GenAI SDK for Gemini Native TTS as a fallback to ElevenLabs.
    Uses the same GEMINI_API_KEY as other Gemini API calls.

    Parameters
    ----------
    api_key:
        Gemini API key.  Falls back to ``GEMINI_API_KEY`` env var.
    model:
        Gemini TTS model.  ``"models/gemini-2.5-flash-preview-tts"`` is the default.
    voice_name:
        Voice name.  ``"Zephyr"`` is the default.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "models/gemini-2.5-flash-preview-tts",
        voice_name: str = "Zephyr",
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or getattr(settings, "gemini_api_key", None)
        # Ensure model name includes "models/" prefix
        model_config = model or getattr(settings, "gemini_tts_model", "gemini-2.5-flash-preview-tts")
        self.model = model_config if model_config.startswith("models/") else f"models/{model_config}"
        self.voice_name = voice_name or getattr(settings, "gemini_tts_voice", "Zephyr")

        # Initialize the GenAI client
        if self._api_key:
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(
                    timeout=10000,  # 10s timeout (in milliseconds)
                    retry_options=types.HttpRetryOptions(
                        attempts=1  # Only 1 attempt (fail fast without retrying)
                    )
                )
            )
        else:
            self._client = None

        logger.info(
            "GeminiTTS configured",
            extra={
                "event": {
                    "model": self.model,
                    "voice_name": self.voice_name,
                    "api_key_set": bool(self._api_key),
                }
            },
        )

    # ── Public async API ─────────────────────────────────────────────────────

    async def synthesise(self, text: str) -> TTSResult:
        """Convert ``text`` to speech and return a ``TTSResult``.

        Parameters
        ----------
        text:
            Text to synthesise.  Should be a concise trip summary targeting
            30–45 seconds of audio.

        Returns
        -------
        TTSResult
            Contains ``.audio_bytes``, ``.estimated_duration_sec``,
            ``.latency_ms``.

        Raises
        ------
        TTSError
            If the API key is missing or the API call fails.
        """
        if not text or not text.strip():
            raise TTSError("Cannot synthesise empty text.")

        if not self._api_key or not self._client:
            raise TTSError(
                "Gemini API key not set. "
                "Set GEMINI_API_KEY in your .env file."
            )

        # Check cache first
        cache_key = _get_cache_key(text, "gemini", self.voice_name, self.model)
        cached_result = await _get_cached_tts(cache_key)
        if cached_result:
            logger.info(
                "Gemini TTS cache hit",
                extra={"event": {"cache_key": cache_key, "text_length": len(text)}},
            )
            return cached_result

        # Apply throttling to prevent quota exhaustion
        await _throttle_gemini_request()

        # Use Gemini Native TTS via SDK
        t0 = time.perf_counter()
        try:
            # Generate content with audio response
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self.model,
                contents=text.strip(),
                config={
                    "response_modalities": ["AUDIO"]
                }
            )

            # Extract audio bytes from response
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            # Gemini returns PCM audio (L16) at 24000 Hz. Wrap it in a WAV container so the browser can play it natively.
                            audio_bytes = pcm_to_wav(part.inline_data.data, sample_rate=24000)
                            audio_format = "wav"
                            break
                    else:
                        raise TTSError("No audio data found in Gemini Native TTS response")
                else:
                    raise TTSError("Invalid Gemini Native TTS response structure")
            else:
                raise TTSError("No candidates in Gemini Native TTS response")
        except Exception as exc:
            raise TTSError(f"Gemini Native TTS error: {exc}") from exc

        latency_ms = (time.perf_counter() - t0) * 1000
        word_count = len(text.split())
        estimated_duration_sec = (word_count / _WORDS_PER_MINUTE) * 60

        result = TTSResult(
            audio_bytes=audio_bytes,
            audio_format=audio_format,
            estimated_duration_sec=estimated_duration_sec,
            latency_ms=latency_ms,
            voice_id=self.voice_name,
            character_count=len(text),
        )

        # Cache the result
        await _cache_tts_result(cache_key, result)

        logger.info(
            "Gemini Native TTS synthesis complete",
            extra={
                "event": {
                    "char_count": len(text),
                    "word_count": word_count,
                    "estimated_duration_sec": round(estimated_duration_sec, 1),
                    "audio_bytes": len(audio_bytes),
                    "latency_ms": round(latency_ms, 1),
                }
            },
        )
        return result

    # ── Synchronous wrapper ──────────────────────────────────────────────────

    def synthesise_sync(self, text: str) -> TTSResult:
        """Blocking wrapper around ``synthesise`` (useful in tests)."""
        return asyncio.run(self.synthesise(text))


class GoogleTranslateTTS:
    """Google Translate TTS client as a free, reliable fallback.
    
    Requires no API keys and has high rate limits under normal usage.
    """

    def __init__(self, *, output_format: str = "mp3_44100_128") -> None:
        self.output_format = output_format
        self.voice_name = "google_default"
        self.model = "google_translate"

        logger.info(
            "GoogleTranslateTTS configured",
            extra={
                "event": {
                    "model": self.model,
                    "voice_name": self.voice_name,
                    "output_format": self.output_format,
                }
            },
        )

    @staticmethod
    def _split_text(text: str, max_chars: int = 200) -> list[str]:
        text = text.strip()
        if len(text) <= max_chars:
            return [text]
            
        chunks = []
        while text:
            if len(text) <= max_chars:
                chunks.append(text)
                break
                
            sub = text[:max_chars]
            split_idx = -1
            for char in ['. ', '! ', '? ']:
                idx = sub.rfind(char)
                if idx > split_idx:
                    split_idx = idx + 1
                    
            if split_idx == -1:
                for char in [', ', '; ']:
                    idx = sub.rfind(char)
                    if idx > split_idx:
                        split_idx = idx + 1
                        
            if split_idx == -1:
                idx = sub.rfind(' ')
                if idx > 0:
                    split_idx = idx
                    
            if split_idx == -1:
                split_idx = max_chars
                
            chunks.append(text[:split_idx].strip())
            text = text[split_idx:].strip()
            
        return [c for c in chunks if c]

    async def synthesise(self, text: str) -> TTSResult:
        """Convert ``text`` to speech and return a ``TTSResult``."""
        if not text or not text.strip():
            raise TTSError("Cannot synthesise empty text.")

        # Clean text: replace Unicode dashes with standard hyphen or space for TTS compatibility
        cleaned_text = text.replace("—", " - ").replace("–", " - ").strip()

        # Check cache first
        cache_key = _get_cache_key(cleaned_text, "google", self.voice_name, self.model)
        cached_result = await _get_cached_tts(cache_key)
        if cached_result:
            logger.info(
                "Google Translate TTS cache hit",
                extra={"event": {"cache_key": cache_key, "text_length": len(cleaned_text)}},
            )
            return cached_result

        chunks = self._split_text(cleaned_text)
        url = "https://translate.google.com/translate_tts"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        t0 = time.perf_counter()
        audio_bytes = b""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for chunk in chunks:
                    params = {
                        "ie": "UTF-8",
                        "q": chunk,
                        "tl": "en",
                        "client": "tw-ob"
                    }
                    response = await client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    
                    # Verify content type to prevent caching and serving Google CAPTCHA HTML pages
                    content_type = response.headers.get("content-type", "").lower()
                    if "audio" not in content_type:
                        raise TTSError(
                            f"Google Translate returned non-audio response: {content_type}. "
                            f"Response starts with: {response.text[:200]}"
                        )
                    
                    audio_bytes += response.content
        except Exception as exc:
            raise TTSError(f"Google Translate TTS error: {exc}") from exc

        latency_ms = (time.perf_counter() - t0) * 1000
        word_count = len(cleaned_text.split())
        estimated_duration_sec = (word_count / _WORDS_PER_MINUTE) * 60

        result = TTSResult(
            audio_bytes=audio_bytes,
            audio_format=self.output_format,
            estimated_duration_sec=estimated_duration_sec,
            latency_ms=latency_ms,
            voice_id=self.voice_name,
            character_count=len(cleaned_text),
        )

        # Cache the result
        await _cache_tts_result(cache_key, result)

        logger.info(
            "Google Translate TTS synthesis complete",
            extra={
                "event": {
                    "char_count": len(cleaned_text),
                    "word_count": word_count,
                    "estimated_duration_sec": round(estimated_duration_sec, 1),
                    "audio_bytes": len(audio_bytes),
                    "latency_ms": round(latency_ms, 1),
                }
            },
        )
        return result

    def synthesise_sync(self, text: str) -> TTSResult:
        """Blocking wrapper around ``synthesise``."""
        return asyncio.run(self.synthesise(text))


class FallbackTTS:
    """TTS client that tries ElevenLabs first, then Gemini, then Google Translate.

    This provides a robust fallback mechanism for TTS synthesis.
    """

    def __init__(
        self,
        *,
        elevenlabs_api_key: str | None = None,
        elevenlabs_voice_id: str | None = None,
        gemini_api_key: str | None = None,
        gemini_model: str = "models/gemini-2.5-flash-preview-tts",
        gemini_voice_name: str = "Zephyr",
    ) -> None:
        settings = get_settings()
        self._elevenlabs = ElevenLabsTTS(
            api_key=elevenlabs_api_key or getattr(settings, "elevenlabs_api_key", None),
            voice_id=elevenlabs_voice_id or getattr(settings, "elevenlabs_voice_id", None),
        )
        self._gemini = GeminiTTS(
            api_key=gemini_api_key or getattr(settings, "gemini_api_key", None),
            model=gemini_model or getattr(settings, "gemini_tts_model", "models/gemini-2.5-flash-preview-tts"),
            voice_name=gemini_voice_name or getattr(settings, "gemini_tts_voice", "Zephyr"),
        )
        self._google = GoogleTranslateTTS()

        logger.info(
            "FallbackTTS configured",
            extra={
                "event": {
                    "elevenlabs_available": bool(self._elevenlabs._api_key),
                    "gemini_available": bool(self._gemini._api_key),
                }
            },
        )

    async def synthesise(self, text: str) -> TTSResult:
        """Convert ``text`` to speech, trying ElevenLabs first, then Gemini, then Google Translate.

        Parameters
        ----------
        text:
            Text to synthesise.

        Returns
        -------
        TTSResult
            Contains ``.audio_bytes``, ``.estimated_duration_sec``,
            ``.latency_ms``.

        Raises
        ------
        TTSError
            If all providers fail.
        """
        if not text or not text.strip():
            raise TTSError("Cannot synthesise empty text.")

        # Try ElevenLabs first
        if self._elevenlabs._api_key:
            try:
                logger.info(
                    "Primary TTS started",
                    extra={"event": {"provider": "elevenlabs", "text_length": len(text)}},
                )
                result = await self._elevenlabs.synthesise(text)
                logger.info(
                    "Primary TTS succeeded",
                    extra={
                        "event": {
                            "provider": "elevenlabs",
                            "audio_format": result.audio_format,
                            "audio_bytes": len(result.audio_bytes),
                        }
                    },
                )
                return result
            except Exception as exc:
                logger.warning(
                    "Primary TTS failed, attempting fallback",
                    extra={
                        "event": {
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                            "provider": "elevenlabs",
                        }
                    },
                )
        else:
            logger.info("Primary TTS API key not set, skipping to fallback")

        # Fall back to Gemini
        gemini_error = None
        if self._gemini._api_key:
            try:
                logger.info(
                    "Fallback TTS (Gemini) started",
                    extra={"event": {"provider": "gemini", "text_length": len(text)}},
                )
                result = await self._gemini.synthesise(text)
                logger.info(
                    "Fallback TTS (Gemini) succeeded",
                    extra={
                        "event": {
                            "provider": "gemini",
                            "audio_format": result.audio_format,
                            "audio_bytes": len(result.audio_bytes),
                        }
                    },
                )
                return result
            except Exception as exc:
                gemini_error = str(exc)
                logger.warning(
                    "Fallback TTS (Gemini) failed, attempting tertiary fallback",
                    extra={
                        "event": {
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                            "provider": "gemini",
                        }
                    },
                )
        else:
            logger.info("Fallback TTS (Gemini) API key not set, skipping to Google Translate")

        # Fall back to Google Translate
        try:
            logger.info(
                "Tertiary TTS (Google Translate) started",
                extra={"event": {"provider": "google", "text_length": len(text)}},
            )
            result = await self._google.synthesise(text)
            logger.info(
                "Tertiary TTS (Google Translate) succeeded",
                extra={
                    "event": {
                        "provider": "google",
                        "audio_format": result.audio_format,
                        "audio_bytes": len(result.audio_bytes),
                    }
                },
            )
            return result
        except Exception as exc:
            logger.error(
                "Tertiary TTS (Google Translate) failed",
                extra={
                    "event": {
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "provider": "google",
                    }
                },
                exc_info=True,
            )
            raise TTSError(
                f"All TTS providers failed. Gemini error: {gemini_error or 'Not tried'}. Google error: {exc}"
            ) from exc

    def synthesise_sync(self, text: str) -> TTSResult:
        """Blocking wrapper around ``synthesise`` (useful in tests)."""
        return asyncio.run(self.synthesise(text))


def create_tts_from_settings() -> FallbackTTS:
    """Factory that reads TTS configuration from app Settings and returns FallbackTTS."""
    settings = get_settings()
    return FallbackTTS(
        elevenlabs_api_key=getattr(settings, "elevenlabs_api_key", None),
        elevenlabs_voice_id=getattr(settings, "elevenlabs_voice_id", None),
        gemini_api_key=getattr(settings, "gemini_api_key", None),
        gemini_model=getattr(settings, "gemini_tts_model", "models/gemini-2.5-flash-preview-tts"),
        gemini_voice_name=getattr(settings, "gemini_tts_voice", "Zephyr"),
    )

