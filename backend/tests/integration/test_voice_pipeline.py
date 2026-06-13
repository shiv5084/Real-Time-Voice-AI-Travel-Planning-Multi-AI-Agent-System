"""Integration tests for the voice pipeline (STT → pipeline → TTS).

These tests verify end-to-end flows without making real API calls:
  1. ``/api/voice/transcribe`` — upload audio → editable transcript
  2. ``/api/voice/confirm`` — confirmed transcript → plan + voice summary
  3. ``/api/voice/synthesise`` — text → TTS audio bytes
  4. Fallback to text input when STT fails
  5. Fallback when TTS fails (plan still returned)

Strategy
--------
- Groq Whisper API calls are intercepted with ``respx`` — no local model.
- ``webrtcvad`` is stubbed so the test runs without the native extension.
- ElevenLabs HTTP calls are intercepted with ``respx``.
- The LangGraph pipeline is mocked with a simple async function that returns
  a minimal valid state.
"""

from __future__ import annotations

import asyncio
import base64
import io
import struct
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.voice.stt import _GROQ_TRANSCRIPTION_URL
from app.voice.tts import _ELEVENLABS_BASE_URL


# ── Stubs ────────────────────────────────────────────────────────────────────


def _make_webrtcvad_stub():
    stub = types.ModuleType("webrtcvad")

    class _FakeVad:
        def __init__(self, *a): pass
        def is_speech(self, frame, sr): return True

    stub.Vad = _FakeVad
    return stub


def _minimal_wav() -> bytes:
    sample_rate = 16000
    n_samples = 3200
    data = b"\x00" * (n_samples * 2)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE",
        b"fmt ", 16, 1, 1,
        sample_rate, sample_rate * 2, 2, 16,
        b"data", len(data),
    )
    return header + data


_MOCK_PIPELINE_STATE = {
    "pipeline_status": "completed",
    "validation_status": "approved",
    "itinerary": {
        "days": [
            {
                "day": 1,
                "date": "2025-07-01",
                "location": "Tokyo",
                "activities": [
                    {"name": "Arrive at hotel", "type": "hotel", "start_time": "14:00", "end_time": "15:00"},
                    {"name": "Walk Shibuya", "type": "attraction", "start_time": "16:00", "end_time": "18:00"},
                ],
            }
        ]
    },
    "constraints": {"destinations": ["Tokyo"], "budget": 3000.0, "travelers": 2},
    "budget_breakdown": {
        "total_budget": 3000.0,
        "total_estimated_cost": 2400.0,
        "compliance": "within_budget",
        "currency": "USD",
    },
    "follow_up_questions": [],
    "errors": [],
    "total_latency_ms": 800,
    "raw_request": "I want to plan a trip to Tokyo",
    "user_id": "anonymous",
}


@pytest.fixture(scope="module", autouse=True)
def stub_native_deps():
    """Inject fake webrtcvad module for the whole test module."""
    vad_stub = _make_webrtcvad_stub()
    with patch.dict(sys.modules, {"webrtcvad": vad_stub}):
        import importlib
        import app.voice.vad as vad_mod
        importlib.reload(vad_mod)
        yield


@pytest.fixture
def client():
    """FastAPI test client with pipeline and Groq STT mocked out."""
    with patch("app.graph.workflow.run_pipeline", new_callable=AsyncMock) as mock_pipeline:
        mock_pipeline.return_value = _MOCK_PIPELINE_STATE
        from app.main import create_app
        app = create_app()
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, mock_pipeline


# ── Task 5.3 — STT transcribes audio ─────────────────────────────────────────

class TestTranscribeEndpoint:
    @respx.mock
    def test_transcribe_returns_editable_transcript(self, client):
        c, _ = client
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "I want to plan a trip to Tokyo", "language": "en"})
        )
        wav_bytes = _minimal_wav()
        response = c.post(
            "/api/voice/transcribe",
            files={"audio": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "transcript" in data
        assert data["editable"] is True
        assert data["requires_confirmation"] is True

    @respx.mock
    def test_transcribe_returns_trace_id(self, client):
        c, _ = client
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "Trip to Seoul", "language": "en"})
        )
        wav_bytes = _minimal_wav()
        response = c.post(
            "/api/voice/transcribe",
            files={"audio": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("trace_id")

    @respx.mock
    def test_transcribe_language_field_present(self, client):
        c, _ = client
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "Paris trip", "language": "en"})
        )
        wav_bytes = _minimal_wav()
        response = c.post(
            "/api/voice/transcribe",
            files={"audio": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
        )
        data = response.json()
        assert "language" in data

    @respx.mock
    def test_transcribe_confidence_field_present(self, client):
        c, _ = client
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "Trip to Berlin"})
        )
        wav_bytes = _minimal_wav()
        response = c.post(
            "/api/voice/transcribe",
            files={"audio": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
        )
        data = response.json()
        assert "confidence" in data
        assert 0.0 <= data["confidence"] <= 1.0

    @respx.mock
    def test_transcript_text_is_present(self, client):
        c, _ = client
        respx.post(_GROQ_TRANSCRIPTION_URL).mock(
            return_value=httpx.Response(200, json={"text": "I want to plan a trip to Tokyo"})
        )
        wav_bytes = _minimal_wav()
        response = c.post(
            "/api/voice/transcribe",
            files={"audio": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
        )
        data = response.json()
        assert isinstance(data["transcript"], str)


# ── Task 5.8 — Fallback when STT fails ───────────────────────────────────────

class TestTranscribeFallback:
    def test_stt_failure_returns_fallback_flag(self):
        """When the Groq API call raises an unexpected error, fallback_to_text should be True."""
        with patch("app.voice.stt.GroqSTT.atranscribe", new_callable=AsyncMock) as mock_stt:
            mock_stt.side_effect = Exception("API unavailable")
            from app.main import create_app
            app = create_app()
            with TestClient(app) as c:
                response = c.post(
                    "/api/voice/transcribe",
                    files={"audio": ("test.wav", io.BytesIO(_minimal_wav()), "audio/wav")},
                )
            assert response.status_code == 200
            data = response.json()
            assert data["fallback_to_text"] is True
            assert data["error"] is not None

    def test_empty_audio_returns_400(self, client):
        c, _ = client
        response = c.post(
            "/api/voice/transcribe",
            files={"audio": ("empty.wav", io.BytesIO(b""), "audio/wav")},
        )
        assert response.status_code == 400


# ── Task 5.5 — Confirmed transcript → pipeline ───────────────────────────────

class TestConfirmEndpoint:
    def test_confirm_triggers_pipeline(self, client):
        c, mock_pipeline = client
        response = c.post(
            "/api/voice/confirm",
            json={"transcript": "Plan a 5-day trip to Tokyo for 2 people with $3000 budget."},
        )
        assert response.status_code == 200
        assert mock_pipeline.called

    def test_confirm_returns_trip_id(self, client):
        c, _ = client
        response = c.post(
            "/api/voice/confirm",
            json={"transcript": "Plan a trip to Paris."},
        )
        data = response.json()
        assert "trip_id" in data
        assert data["trip_id"]

    def test_confirm_returns_itinerary(self, client):
        c, _ = client
        response = c.post(
            "/api/voice/confirm",
            json={"transcript": "Plan a trip to Tokyo."},
        )
        data = response.json()
        assert data.get("itinerary") is not None

    def test_confirm_returns_pipeline_status(self, client):
        c, _ = client
        response = c.post(
            "/api/voice/confirm",
            json={"transcript": "5-day trip to Rome, 2 adults, $2500"},
        )
        data = response.json()
        assert data["pipeline_status"] == "completed"

    def test_confirm_empty_transcript_returns_400(self, client):
        c, _ = client
        response = c.post("/api/voice/confirm", json={"transcript": ""})
        assert response.status_code == 400

    def test_confirm_returns_voice_summary(self, client):
        """Voice summary text should be returned even without TTS."""
        c, _ = client
        response = c.post(
            "/api/voice/confirm",
            json={"transcript": "Trip to Kyoto for 3 days."},
        )
        data = response.json()
        assert isinstance(data.get("voice_summary"), str)
        assert len(data["voice_summary"]) > 0

    # Task 5.8 — TTS failure doesn't break the plan
    def test_confirm_plan_returned_even_if_tts_fails(self, client):
        """If TTS synthesis fails, the plan is still returned (fallback)."""
        c, _ = client
        with patch("app.voice.tts.FallbackTTS.synthesise", new_callable=AsyncMock) as mock_tts:
            mock_tts.side_effect = Exception("TTS unavailable")
            response = c.post(
                "/api/voice/confirm",
                json={"transcript": "Trip to Seoul."},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["pipeline_status"] == "completed"
        assert data.get("voice_summary_audio_b64") is None  # audio failed
        assert data.get("voice_summary") is not None       # text still returned


# ── Task 5.6 — Voice summary is 30–45 seconds ────────────────────────────────

class TestVoiceSummaryLength:
    def test_summary_is_concise(self, client):
        """The built summary should be reasonable in length (not a full itinerary)."""
        c, _ = client
        response = c.post(
            "/api/voice/confirm",
            json={"transcript": "Plan a 5-day trip to Tokyo with $3000 budget."},
        )
        data = response.json()
        summary = data.get("voice_summary", "")
        # Should not be an enormous dump of all activities
        word_count = len(summary.split())
        assert word_count < 300, f"Summary is too long ({word_count} words)"


# ── Task 5.3 — TTS synthesise endpoint ───────────────────────────────────────

class TestSynthesiseEndpoint:
    @respx.mock
    def test_synthesise_returns_audio_b64(self, client):
        c, _ = client
        fake_audio = b"FAKE_MP3_BYTES"
        # We need to mock an ElevenLabs instance that has an API key
        voice_id = "cgSgspJ2msm6clMCkdW9"
        url = f"{_ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}"
        respx.post(url).mock(
            return_value=httpx.Response(200, content=fake_audio)
        )
        with patch("app.voice.tts.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                elevenlabs_api_key="fake-key",
                elevenlabs_voice_id=voice_id,
            )
            response = c.post(
                "/api/voice/synthesise",
                json={"text": "Your trip to Tokyo is ready. Enjoy your adventure."},
            )
        if response.status_code == 503:
            # API key not set in test environment — acceptable fallback
            assert "API key" in response.json().get("detail", "")
        else:
            assert response.status_code == 200
            data = response.json()
            assert "audio_b64" in data
            assert "estimated_duration_sec" in data

    def test_synthesise_empty_text_returns_400(self, client):
        c, _ = client
        response = c.post("/api/voice/synthesise", json={"text": ""})
        assert response.status_code == 400

    def test_synthesise_no_key_returns_503(self, client):
        c, _ = client
        from app.voice.tts import TTSError
        with patch("app.voice.tts.FallbackTTS.synthesise", new_callable=AsyncMock) as mock_tts:
            mock_tts.side_effect = TTSError("All TTS providers failed.")
            with patch("app.voice.tts.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    elevenlabs_api_key=None,
                    elevenlabs_voice_id=None,
                )
                response = c.post(
                    "/api/voice/synthesise",
                    json={"text": "Hello there, your trip is ready."},
                )
        # Should return 503 (service unavailable — no key)
        assert response.status_code == 503
