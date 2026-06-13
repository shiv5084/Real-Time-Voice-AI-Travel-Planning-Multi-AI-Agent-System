"""Unit tests for Groq Whisper STT (app/voice/stt.py).

Strategy
--------
All HTTP calls to the Groq API are intercepted with ``respx`` so tests run
without a real API key or network access.  Each test covers a distinct
behaviour:
- Constructor validation (model name)
- ``transcribe`` — happy path, empty audio, oversized audio, API errors
- ``atranscribe`` — async path
- ``_normalise_input`` — bytes / Path / file-like object handling
- ``build_editable_response`` helper
- ``STTError`` raised on bad inputs and API failures
"""

from __future__ import annotations

import asyncio
import io
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from app.voice.stt import (
    GroqSTT,
    STTError,
    TranscriptResult,
    VALID_GROQ_WHISPER_MODELS,
    _GROQ_TRANSCRIPTION_URL,
    _MAX_AUDIO_BYTES,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _minimal_wav(n_samples: int = 1600) -> bytes:
    """Return a minimal valid 16-bit 16 kHz mono WAV."""
    sample_rate = 16000
    data = b"\x00" * (n_samples * 2)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE",
        b"fmt ", 16, 1, 1,
        sample_rate, sample_rate * 2, 2, 16,
        b"data", len(data),
    )
    return header + data


@pytest.fixture
def stt():
    """GroqSTT instance with a fake API key (no settings mock needed)."""
    with patch("app.voice.stt.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(groq_api_key="fake-groq-key")
        return GroqSTT(api_key="fake-groq-key")


@pytest.fixture
def stt_no_key():
    """GroqSTT instance with no API key."""
    with patch("app.voice.stt.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(groq_api_key=None)
        return GroqSTT(api_key=None)


# ── Constructor validation ────────────────────────────────────────────────────

class TestGroqSTTConstructor:
    def test_valid_defaults(self):
        with patch("app.voice.stt.get_settings") as ms:
            ms.return_value = MagicMock(groq_api_key="k")
            s = GroqSTT(api_key="k")
        assert s.model == "whisper-large-v3-turbo"
        assert s.language == "en"
        assert s.temperature == 0.0

    def test_invalid_model_raises(self):
        with pytest.raises(STTError, match="model"):
            GroqSTT(model="gpt-4o-audio", api_key="k")

    @pytest.mark.parametrize("model", sorted(VALID_GROQ_WHISPER_MODELS))
    def test_all_valid_models_accepted(self, model):
        with patch("app.voice.stt.get_settings") as ms:
            ms.return_value = MagicMock(groq_api_key="k")
            s = GroqSTT(api_key="k", model=model)
        assert s.model == model

    def test_api_key_from_settings_fallback(self):
        with patch("app.voice.stt.get_settings") as ms:
            ms.return_value = MagicMock(groq_api_key="settings-key")
            s = GroqSTT()
        assert s._api_key == "settings-key"


# ── transcribe (sync) ─────────────────────────────────────────────────────────

class TestTranscribeSync:
    @respx.mock
    def test_happy_path_returns_transcript(self, stt):
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "Plan a trip to Tokyo", "language": "en"})
        )
        result = stt.transcribe(_minimal_wav())
        assert result.text == "Plan a trip to Tokyo"
        assert result.language == "en"
        assert result.latency_ms >= 0

    @respx.mock
    def test_transcribes_path_object(self, stt, tmp_path):
        f = tmp_path / "audio.wav"
        f.write_bytes(_minimal_wav())
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "I want to visit Paris", "language": "en"})
        )
        result = stt.transcribe(f)
        assert result.text == "I want to visit Paris"

    @respx.mock
    def test_transcribes_str_path(self, stt, tmp_path):
        f = tmp_path / "audio.wav"
        f.write_bytes(_minimal_wav())
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "5 days in Berlin"})
        )
        result = stt.transcribe(str(f))
        assert "Berlin" in result.text

    @respx.mock
    def test_transcribes_file_like(self, stt):
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "Weekend in Rome", "language": "en"})
        )
        result = stt.transcribe(io.BytesIO(_minimal_wav()))
        assert "Rome" in result.text

    def test_missing_api_key_raises(self, stt_no_key):
        with pytest.raises(STTError, match="GROQ_API_KEY"):
            stt_no_key.transcribe(_minimal_wav())

    def test_empty_audio_raises(self, stt):
        with pytest.raises(STTError, match="empty"):
            stt.transcribe(b"")

    def test_oversized_audio_raises(self, stt):
        big = b"\x00" * (_MAX_AUDIO_BYTES + 1)
        with pytest.raises(STTError, match="20 MB"):
            stt.transcribe(big)

    @respx.mock
    def test_api_401_raises_stt_error(self, stt):
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(401, json={"error": "Unauthorized"})
        )
        with pytest.raises(STTError, match="401"):
            stt.transcribe(_minimal_wav())

    @respx.mock
    def test_api_429_raises_stt_error(self, stt):
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(429, json={"error": "rate limit"})
        )
        with pytest.raises(STTError, match="rate limit"):
            stt.transcribe(_minimal_wav())

    @respx.mock
    def test_api_500_raises_stt_error(self, stt):
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(STTError):
            stt.transcribe(_minimal_wav())

    @respx.mock
    def test_confidence_always_1(self, stt):
        """Groq does not return per-word confidence; result is always 1.0."""
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "test"})
        )
        result = stt.transcribe(_minimal_wav())
        assert result.confidence == 1.0

    @respx.mock
    def test_is_empty_for_blank_text(self, stt):
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "   "})
        )
        result = stt.transcribe(_minimal_wav())
        assert result.is_empty

    @respx.mock
    def test_segments_list_always_empty(self, stt):
        """Groq basic transcription has no segment breakdown."""
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "hello"})
        )
        result = stt.transcribe(_minimal_wav())
        assert result.segments == []


# ── atranscribe (async) ───────────────────────────────────────────────────────

class TestAtranscribeAsync:
    @pytest.mark.asyncio
    @respx.mock
    async def test_async_returns_transcript_result(self, stt):
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "I want to plan a trip to Tokyo", "language": "en"})
        )
        result = await stt.atranscribe(_minimal_wav())
        assert isinstance(result, TranscriptResult)
        assert result.text == "I want to plan a trip to Tokyo"

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_not_empty(self, stt):
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "Plan a trip to Spain"})
        )
        result = await stt.atranscribe(_minimal_wav())
        assert not result.is_empty

    @pytest.mark.asyncio
    async def test_async_missing_key_raises(self, stt_no_key):
        with pytest.raises(STTError, match="GROQ_API_KEY"):
            await stt_no_key.atranscribe(_minimal_wav())

    @pytest.mark.asyncio
    async def test_async_empty_audio_raises(self, stt):
        with pytest.raises(STTError, match="empty"):
            await stt.atranscribe(b"")

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_language_detected(self, stt):
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "Planen Sie eine Reise", "language": "de"})
        )
        result = await stt.atranscribe(_minimal_wav())
        assert result.language == "de"


# ── _normalise_input ──────────────────────────────────────────────────────────

class TestNormaliseInput:
    def test_bytes_returns_audio_wav(self):
        name, data = GroqSTT._normalise_input(b"\x00" * 100)
        assert name == "audio.wav"
        assert data == b"\x00" * 100

    def test_path_object_returns_filename_and_bytes(self, tmp_path):
        f = tmp_path / "clip.mp3"
        f.write_bytes(b"\xff\xfb")
        name, data = GroqSTT._normalise_input(f)
        assert name == "clip.mp3"
        assert data == b"\xff\xfb"

    def test_str_path_returns_filename_and_bytes(self, tmp_path):
        f = tmp_path / "test.ogg"
        f.write_bytes(b"\x4f\x67\x67")
        name, data = GroqSTT._normalise_input(str(f))
        assert name == "test.ogg"
        assert data == b"\x4f\x67\x67"

    def test_file_like_object(self):
        buf = io.BytesIO(b"\xAB\xCD")
        buf.name = "/tmp/recording.wav"
        name, data = GroqSTT._normalise_input(buf)
        assert name == "recording.wav"
        assert data == b"\xAB\xCD"

    def test_file_like_without_name_attr(self):
        buf = io.BytesIO(b"\x01\x02")
        name, data = GroqSTT._normalise_input(buf)
        assert name == "audio.wav"
        assert data == b"\x01\x02"


# ── build_editable_response ───────────────────────────────────────────────────

class TestBuildEditableResponse:
    def test_editable_flag_true(self):
        result = TranscriptResult(text="Plan a trip to Tokyo", language="en", confidence=1.0)
        editable = GroqSTT.build_editable_response(result)
        assert editable["editable"] is True
        assert editable["requires_confirmation"] is True

    def test_transcript_matches(self):
        result = TranscriptResult(text="I want to visit Rome", language="en", confidence=1.0)
        editable = GroqSTT.build_editable_response(result)
        assert editable["transcript"] == "I want to visit Rome"

    def test_confidence_rounded(self):
        result = TranscriptResult(text="hello", confidence=0.987654)
        editable = GroqSTT.build_editable_response(result)
        assert editable["confidence"] == round(0.987654, 3)

    def test_language_included(self):
        result = TranscriptResult(text="Bonjour", language="fr", confidence=1.0)
        editable = GroqSTT.build_editable_response(result)
        assert editable["language"] == "fr"


# ── TranscriptResult helpers ──────────────────────────────────────────────────

class TestTranscriptResult:
    def test_is_empty_true_for_whitespace(self):
        r = TranscriptResult(text="   ")
        assert r.is_empty

    def test_is_empty_false_for_content(self):
        r = TranscriptResult(text="Paris")
        assert not r.is_empty

    def test_is_empty_true_for_blank(self):
        r = TranscriptResult(text="")
        assert r.is_empty


# ── Backwards-compat alias ────────────────────────────────────────────────────

class TestBackwardsCompatAlias:
    def test_whisper_stt_is_groq_stt(self):
        from app.voice.stt import WhisperSTT
        assert WhisperSTT is GroqSTT
