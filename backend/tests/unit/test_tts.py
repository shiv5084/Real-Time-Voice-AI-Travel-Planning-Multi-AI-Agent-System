"""Unit tests for ElevenLabs TTS (app/voice/tts.py).

Strategy
--------
All HTTP calls to the ElevenLabs API are mocked with ``respx`` (already a
project dependency) so tests run without real API keys.

Each test covers:
- Constructor validation (output_format, api_key_set flag)
- ``synthesise`` — happy path (mocked HTTP), missing key, empty text
- ``synthesise_sync`` — synchronous wrapper
- ``trim_to_target_length`` — word truncation
- ``estimate_duration_sec`` — duration calculation
- ``is_duration_within_target`` — 30–45 sec window check
- ``TTSResult`` dataclass fields
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
import httpx

from app.voice.tts import (
    ElevenLabsTTS,
    TTSError,
    TTSResult,
    SUMMARY_MIN_WORDS,
    SUMMARY_MAX_WORDS,
    SUMMARY_TARGET_DURATION_SEC,
    _WORDS_PER_MINUTE,
    _ELEVENLABS_BASE_URL,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tts_no_key():
    """ElevenLabsTTS instance with no API key."""
    with patch("app.voice.tts.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            elevenlabs_api_key=None,
            elevenlabs_voice_id=None,
        )
        return ElevenLabsTTS(api_key=None)


@pytest.fixture
def tts_with_key():
    """ElevenLabsTTS instance with a fake API key."""
    with patch("app.voice.tts.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            elevenlabs_api_key="fake-key-1234",
            elevenlabs_voice_id="cgSgspJ2msm6clMCkdW9",
        )
        return ElevenLabsTTS(api_key="fake-key-1234")


# ── Constructor ──────────────────────────────────────────────────────────────

class TestConstructor:
    def test_invalid_output_format_raises(self):
        with pytest.raises(TTSError, match="output_format"):
            ElevenLabsTTS(output_format="ogg_vorbis")

    def test_valid_output_format_accepted(self):
        tts = ElevenLabsTTS(output_format="mp3_44100_128", api_key="k")
        assert tts.output_format == "mp3_44100_128"

    def test_all_valid_formats_accepted(self):
        for fmt in ("mp3_44100_128", "mp3_22050_32", "pcm_16000", "pcm_22050", "pcm_24000"):
            tts = ElevenLabsTTS(output_format=fmt, api_key="k")
            assert tts.output_format == fmt


# ── synthesise ───────────────────────────────────────────────────────────────

class TestSynthesise:
    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self, tts_no_key):
        with pytest.raises(TTSError, match="API key"):
            await tts_no_key.synthesise("Hello world")

    @pytest.mark.asyncio
    async def test_empty_text_raises(self, tts_with_key):
        with pytest.raises(TTSError, match="empty"):
            await tts_with_key.synthesise("")

    @pytest.mark.asyncio
    async def test_whitespace_only_raises(self, tts_with_key):
        with pytest.raises(TTSError, match="empty"):
            await tts_with_key.synthesise("   ")

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_synthesis_returns_result(self, tts_with_key):
        fake_audio = b"FAKE_MP3_DATA_1234"
        voice_id = tts_with_key._voice_id
        url = f"{_ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}"
        respx.post(url).mock(
            return_value=httpx.Response(200, content=fake_audio)
        )
        result = await tts_with_key.synthesise("Plan a 5-day trip to Japan.")
        assert isinstance(result, TTSResult)
        assert result.audio_bytes == fake_audio
        assert result.latency_ms >= 0
        assert result.estimated_duration_sec > 0
        assert result.character_count > 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_4xx_raises_tts_error(self, tts_with_key):
        voice_id = tts_with_key._voice_id
        url = f"{_ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}"
        respx.post(url).mock(
            return_value=httpx.Response(401, json={"detail": "Unauthorized"})
        )
        with pytest.raises(TTSError, match="401"):
            await tts_with_key.synthesise("Hello")

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_5xx_raises_tts_error(self, tts_with_key):
        voice_id = tts_with_key._voice_id
        url = f"{_ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}"
        respx.post(url).mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        with pytest.raises(TTSError, match="503"):
            await tts_with_key.synthesise("Hello")

    @pytest.mark.asyncio
    @respx.mock
    async def test_audio_bytes_are_returned(self, tts_with_key):
        fake_audio = b"\xff\xfb\x90\x00" * 100  # fake MP3 header pattern
        voice_id = tts_with_key._voice_id
        url = f"{_ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}"
        respx.post(url).mock(
            return_value=httpx.Response(200, content=fake_audio)
        )
        result = await tts_with_key.synthesise("Your trip is ready!")
        assert len(result.audio_bytes) == len(fake_audio)


# ── synthesise_sync ───────────────────────────────────────────────────────────

class TestSynthesiseSync:
    @respx.mock
    def test_sync_wrapper_returns_tts_result(self, tts_with_key):
        fake_audio = b"SYNC_AUDIO"
        voice_id = tts_with_key._voice_id
        url = f"{_ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}"
        respx.post(url).mock(
            return_value=httpx.Response(200, content=fake_audio)
        )
        result = tts_with_key.synthesise_sync("A short summary.")
        assert isinstance(result, TTSResult)
        assert result.audio_bytes == fake_audio


# ── trim_to_target_length ─────────────────────────────────────────────────────

class TestTrimToTargetLength:
    def test_short_text_unchanged(self):
        text = "Hello world"
        result = ElevenLabsTTS.trim_to_target_length(text, max_words=20)
        assert result == text

    def test_long_text_truncated(self):
        words = ["word"] * 200
        text = " ".join(words)
        result = ElevenLabsTTS.trim_to_target_length(text, max_words=SUMMARY_MAX_WORDS)
        assert len(result.split()) <= SUMMARY_MAX_WORDS + 1  # +1 for ellipsis word

    def test_truncated_text_ends_with_ellipsis(self):
        words = ["word"] * 200
        text = " ".join(words)
        result = ElevenLabsTTS.trim_to_target_length(text, max_words=50)
        assert result.endswith("…")

    def test_exact_max_words_not_truncated(self):
        text = " ".join(["x"] * SUMMARY_MAX_WORDS)
        result = ElevenLabsTTS.trim_to_target_length(text)
        assert not result.endswith("…")


# ── estimate_duration_sec ─────────────────────────────────────────────────────

class TestEstimateDurationSec:
    def test_150_words_equals_60_seconds(self):
        text = " ".join(["word"] * _WORDS_PER_MINUTE)
        assert ElevenLabsTTS.estimate_duration_sec(text) == pytest.approx(60.0)

    def test_75_words_equals_30_seconds(self):
        text = " ".join(["word"] * 75)
        assert ElevenLabsTTS.estimate_duration_sec(text) == pytest.approx(30.0)

    def test_single_word_nonzero(self):
        assert ElevenLabsTTS.estimate_duration_sec("hello") > 0

    def test_empty_string_returns_zero(self):
        assert ElevenLabsTTS.estimate_duration_sec("") == pytest.approx(0.0)


# ── is_duration_within_target ─────────────────────────────────────────────────

class TestIsDurationWithinTarget:
    def test_90_words_is_within_target(self):
        """~36 seconds — should be within 30–45 sec window."""
        text = " ".join(["word"] * 90)
        assert ElevenLabsTTS.is_duration_within_target(text) is True

    def test_10_words_is_too_short(self):
        text = " ".join(["word"] * 10)
        assert ElevenLabsTTS.is_duration_within_target(text) is False

    def test_200_words_is_too_long(self):
        text = " ".join(["word"] * 200)
        assert ElevenLabsTTS.is_duration_within_target(text) is False

    def test_boundary_30_sec_included(self):
        """Exactly 30 sec worth of words should return True."""
        text = " ".join(["word"] * SUMMARY_MIN_WORDS)
        assert ElevenLabsTTS.is_duration_within_target(text) is True

    def test_boundary_45_sec_included(self):
        """Exactly 45 sec worth of words should return True."""
        text = " ".join(["word"] * SUMMARY_MAX_WORDS)
        assert ElevenLabsTTS.is_duration_within_target(text) is True

# ── GeminiTTS and FallbackTTS Tests ──────────────────────────────────────────

from app.voice.tts import GeminiTTS, FallbackTTS, GoogleTranslateTTS

class TestGeminiTTS:
    def test_gemini_client_http_options(self):
        """Verify GeminiTTS sets the fail-fast http_options correctly."""
        with patch("app.voice.tts.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                gemini_api_key="fake-gemini-key",
                gemini_tts_model="gemini-2.5-flash-preview-tts",
                gemini_tts_voice="Zephyr",
            )
            
            with patch("google.genai.Client") as mock_client_cls:
                tts = GeminiTTS(api_key="fake-gemini-key")
                mock_client_cls.assert_called_once()
                args, kwargs = mock_client_cls.call_args
                
                # Check that http_options were passed and configured correctly
                assert "http_options" in kwargs
                options = kwargs["http_options"]
                assert options.timeout == 10000
                assert options.retry_options is not None
                assert options.retry_options.attempts == 1


class TestFallbackTTS:
    @pytest.mark.asyncio
    async def test_fallback_flow_gemini_to_google(self):
        """Verify that if ElevenLabs is not configured, Gemini starts but if it fails, it falls back to Google."""
        with patch("app.voice.tts.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                elevenlabs_api_key=None,
                gemini_api_key="fake-gemini-key",
            )
            
            with patch("app.voice.tts.ElevenLabsTTS") as mock_elevenlabs_cls,                  patch("app.voice.tts.GeminiTTS") as mock_gemini_cls,                  patch("app.voice.tts.GoogleTranslateTTS") as mock_google_cls:
                
                # Setup ElevenLabs mock
                mock_elevenlabs = mock_elevenlabs_cls.return_value
                mock_elevenlabs._api_key = None
                
                # Setup Gemini mock to fail
                mock_gemini = mock_gemini_cls.return_value
                mock_gemini._api_key = "fake-gemini-key"
                mock_gemini.synthesise = AsyncMock(side_effect=Exception("Gemini quota exhausted"))
                
                # Setup Google mock to succeed
                mock_google = mock_google_cls.return_value
                expected_result = TTSResult(
                    audio_bytes=b"google_audio",
                    audio_format="mp3_44100_128",
                    estimated_duration_sec=5.0,
                    latency_ms=100.0,
                    voice_id="google_default"
                )
                mock_google.synthesise = AsyncMock(return_value=expected_result)
                
                fallback_tts = FallbackTTS()
                result = await fallback_tts.synthesise("Test fallback text")
                
                # Assertions
                assert result == expected_result
                mock_gemini.synthesise.assert_called_once_with("Test fallback text")
                mock_google.synthesise.assert_called_once_with("Test fallback text")
