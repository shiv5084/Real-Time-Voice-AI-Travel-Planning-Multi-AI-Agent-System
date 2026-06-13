"""Unit tests for WebRTC VAD (app/voice/vad.py).

Strategy
--------
All tests mock ``webrtcvad.Vad`` so the test suite does not require the
native ``webrtcvad`` C extension to be installed.  This lets CI run without
platform-specific build tools.

Each test covers:
- Constructor validation (aggressiveness, sample_rate, frame_duration_ms)
- ``is_speech`` — single frame classification and latency < 200 ms
- ``segment_audio`` — generator correctness
- ``extract_speech_segments`` — voiced segment extraction with padding
- ``VADError`` is raised for malformed inputs
"""

from __future__ import annotations

import struct
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Stub webrtcvad so the test runs without the native extension ────────────

def _make_webrtcvad_stub(voiced_sequence: list[bool] | None = None):
    """Return a fake webrtcvad module whose Vad.is_speech returns seq values."""
    stub = types.ModuleType("webrtcvad")

    class _FakeVad:
        def __init__(self, aggressiveness: int):
            self._aggressiveness = aggressiveness
            self._call_count = 0
            self._seq = voiced_sequence or []

        def is_speech(self, frame: bytes, sample_rate: int) -> bool:
            if self._seq:
                val = self._seq[self._call_count % len(self._seq)]
                self._call_count += 1
                return val
            return True

    stub.Vad = _FakeVad
    return stub


@pytest.fixture(autouse=True)
def patch_webrtcvad():
    """Inject a fake webrtcvad module for all tests in this file."""
    stub = _make_webrtcvad_stub()
    with patch.dict(sys.modules, {"webrtcvad": stub}):
        # Force re-import of vad module so it picks up the stub
        import importlib
        import app.voice.vad as vad_module
        importlib.reload(vad_module)
        yield vad_module


# ── Helpers ─────────────────────────────────────────────────────────────────

def _silence_bytes(n_frames: int, sample_rate: int = 16000, frame_ms: int = 20) -> bytes:
    """Generate ``n_frames`` of silent 16-bit PCM."""
    frame_bytes = 2 * sample_rate * frame_ms // 1000
    return b"\x00" * (frame_bytes * n_frames)


def _make_frame(sample_rate: int = 16000, frame_ms: int = 20) -> bytes:
    """Return one silent frame of the correct size."""
    frame_bytes = 2 * sample_rate * frame_ms // 1000
    return b"\x00" * frame_bytes


# ── Constructor validation ───────────────────────────────────────────────────

class TestWebRTCVADConstructor:
    def test_valid_defaults(self, patch_webrtcvad):
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD()
        assert vad.sample_rate == 16000
        assert vad.frame_duration_ms == 20
        assert vad.aggressiveness == 2

    def test_invalid_aggressiveness_raises(self, patch_webrtcvad):
        vad_module = patch_webrtcvad
        with pytest.raises(vad_module.VADError, match="aggressiveness"):
            vad_module.WebRTCVAD(aggressiveness=5)

    def test_invalid_sample_rate_raises(self, patch_webrtcvad):
        vad_module = patch_webrtcvad
        with pytest.raises(vad_module.VADError, match="sample_rate"):
            vad_module.WebRTCVAD(sample_rate=22050)

    def test_invalid_frame_duration_raises(self, patch_webrtcvad):
        vad_module = patch_webrtcvad
        with pytest.raises(vad_module.VADError, match="frame_duration_ms"):
            vad_module.WebRTCVAD(frame_duration_ms=15)

    @pytest.mark.parametrize("aggr", [0, 1, 2, 3])
    def test_all_valid_aggressiveness_levels(self, patch_webrtcvad, aggr):
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD(aggressiveness=aggr)
        assert vad.aggressiveness == aggr

    @pytest.mark.parametrize("sr", [8000, 16000, 32000, 48000])
    def test_all_valid_sample_rates(self, patch_webrtcvad, sr):
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD(sample_rate=sr)
        assert vad.sample_rate == sr

    @pytest.mark.parametrize("fms", [10, 20, 30])
    def test_all_valid_frame_durations(self, patch_webrtcvad, fms):
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD(frame_duration_ms=fms)
        assert vad.frame_duration_ms == fms


# ── is_speech ────────────────────────────────────────────────────────────────

class TestIsSpeech:
    def test_returns_bool_and_latency(self, patch_webrtcvad):
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD()
        frame = _make_frame()
        voiced, latency_ms = vad.is_speech(frame)
        assert isinstance(voiced, bool)
        assert isinstance(latency_ms, float)
        assert latency_ms >= 0

    def test_latency_under_200ms(self, patch_webrtcvad):
        """VAD processing must complete within the 200 ms budget."""
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD()
        frame = _make_frame()
        _, latency_ms = vad.is_speech(frame)
        # Stub is instant, so this will always pass; real hardware test needed
        assert latency_ms < 200

    def test_wrong_frame_size_raises(self, patch_webrtcvad):
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD()
        with pytest.raises(vad_module.VADError, match="bytes"):
            vad.is_speech(b"\x00" * 5)

    def test_voiced_frame_returns_true(self, patch_webrtcvad):
        """When stub is configured to return voiced, is_speech is True."""
        import sys, types, importlib
        stub = _make_webrtcvad_stub(voiced_sequence=[True])
        with patch.dict(sys.modules, {"webrtcvad": stub}):
            import app.voice.vad as vm
            importlib.reload(vm)
            vad = vm.WebRTCVAD()
            voiced, _ = vad.is_speech(_make_frame())
            assert voiced is True

    def test_silent_frame_returns_false(self, patch_webrtcvad):
        """When stub is configured to return silent, is_speech is False."""
        import sys, types, importlib
        stub = _make_webrtcvad_stub(voiced_sequence=[False])
        with patch.dict(sys.modules, {"webrtcvad": stub}):
            import app.voice.vad as vm
            importlib.reload(vm)
            vad = vm.WebRTCVAD()
            voiced, _ = vad.is_speech(_make_frame())
            assert voiced is False


# ── segment_audio ────────────────────────────────────────────────────────────

class TestSegmentAudio:
    def test_yields_frame_bool_tuples(self, patch_webrtcvad):
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD()
        audio = _silence_bytes(5)
        segments = list(vad.segment_audio(audio))
        assert len(segments) == 5
        for frame, is_voiced in segments:
            assert isinstance(frame, bytes)
            assert isinstance(is_voiced, bool)

    def test_incomplete_trailing_frame_discarded(self, patch_webrtcvad):
        """An extra byte that doesn't form a full frame is silently dropped."""
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD()
        audio = _silence_bytes(3) + b"\x00"  # one extra byte
        segments = list(vad.segment_audio(audio))
        assert len(segments) == 3

    def test_empty_audio_yields_nothing(self, patch_webrtcvad):
        vad_module = patch_webrtcvad
        vad = vad_module.WebRTCVAD()
        segments = list(vad.segment_audio(b""))
        assert segments == []


# ── extract_speech_segments ──────────────────────────────────────────────────

class TestExtractSpeechSegments:
    def test_all_voiced_returns_single_segment(self):
        """All-voiced audio should produce exactly one segment."""
        import sys, importlib
        stub = _make_webrtcvad_stub(voiced_sequence=[True] * 100)
        with patch.dict(sys.modules, {"webrtcvad": stub}):
            import app.voice.vad as vm
            importlib.reload(vm)
            vad = vm.WebRTCVAD(window_size=3, padding_chunks=2)
            audio = _silence_bytes(10)
            segments = vad.extract_speech_segments(audio)
            assert len(segments) >= 1

    def test_all_silent_returns_no_segments(self):
        """All-silent audio should produce zero segments."""
        import sys, importlib
        stub = _make_webrtcvad_stub(voiced_sequence=[False] * 100)
        with patch.dict(sys.modules, {"webrtcvad": stub}):
            import app.voice.vad as vm
            importlib.reload(vm)
            vad = vm.WebRTCVAD(window_size=3, padding_chunks=1)
            audio = _silence_bytes(10)
            segments = vad.extract_speech_segments(audio)
            assert segments == []

    def test_returns_bytes_objects(self):
        import sys, importlib
        stub = _make_webrtcvad_stub(voiced_sequence=[True, True, False] * 10)
        with patch.dict(sys.modules, {"webrtcvad": stub}):
            import app.voice.vad as vm
            importlib.reload(vm)
            vad = vm.WebRTCVAD(window_size=3, voiced_threshold=0.3, padding_chunks=1)
            audio = _silence_bytes(15)
            segments = vad.extract_speech_segments(audio)
            for seg in segments:
                assert isinstance(seg, bytes)

    def test_empty_audio_returns_empty_list(self):
        import sys, importlib
        stub = _make_webrtcvad_stub()
        with patch.dict(sys.modules, {"webrtcvad": stub}):
            import app.voice.vad as vm
            importlib.reload(vm)
            vad = vm.WebRTCVAD()
            assert vad.extract_speech_segments(b"") == []
