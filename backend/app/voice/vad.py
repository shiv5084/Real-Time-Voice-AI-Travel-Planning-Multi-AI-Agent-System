"""WebRTC-based Voice Activity Detection (VAD).

Detects speech boundaries in a PCM audio byte stream.  The implementation
wraps the ``webrtcvad`` library (aggressiveness 1–3) and adds:

  - Configurable frame duration (10 / 20 / 30 ms).
  - Rolling window with majority-vote to smooth noisy decisions.
  - Latency tracking so tests can assert < 200 ms boundary detection.
  - Padding: extends voiced segments by N frames on both sides to avoid
    clipping the start/end of speech.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Generator

try:
    import webrtcvad  # type: ignore
    _WEBRTCVAD_AVAILABLE = True
except ImportError:  # pragma: no cover
    _WEBRTCVAD_AVAILABLE = False

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Supported sample rates for webrtcvad
_SUPPORTED_SAMPLE_RATES = {8000, 16000, 32000, 48000}
_SUPPORTED_FRAME_MS = {10, 20, 30}


class VADError(RuntimeError):
    """Raised when VAD configuration or audio format is invalid."""


class WebRTCVAD:
    """Wraps ``webrtcvad.Vad`` with frame-chunking and latency tracking.

    Parameters
    ----------
    aggressiveness:
        VAD filtering aggressiveness (0–3).  Higher values are more
        aggressive about filtering out non-speech.  Default is 2.
    sample_rate:
        Audio sample rate in Hz.  Must be one of {8000, 16000, 32000, 48000}.
    frame_duration_ms:
        Duration of each VAD frame in milliseconds.  Must be 10, 20, or 30.
    padding_chunks:
        Number of leading/trailing frames to include as padding around
        voiced segments.  Prevents hard clipping at speech boundaries.
    window_size:
        Rolling window size for majority-vote smoothing.
    voiced_threshold:
        Fraction of frames in the window that must be voiced to declare
        a voiced segment (default 0.6 → at least 60% voiced frames).
    """

    def __init__(
        self,
        *,
        aggressiveness: int = 2,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        padding_chunks: int = 5,
        window_size: int = 10,
        voiced_threshold: float = 0.6,
    ) -> None:
        if not _WEBRTCVAD_AVAILABLE:
            raise VADError(
                "webrtcvad is not installed. Add 'webrtcvad' to requirements.txt."
            )
        if aggressiveness not in range(4):
            raise VADError(f"aggressiveness must be 0–3, got {aggressiveness}")
        if sample_rate not in _SUPPORTED_SAMPLE_RATES:
            raise VADError(
                f"sample_rate must be one of {_SUPPORTED_SAMPLE_RATES}, got {sample_rate}"
            )
        if frame_duration_ms not in _SUPPORTED_FRAME_MS:
            raise VADError(
                f"frame_duration_ms must be one of {_SUPPORTED_FRAME_MS}, got {frame_duration_ms}"
            )

        self._vad = webrtcvad.Vad(aggressiveness)
        self.aggressiveness = aggressiveness
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.padding_chunks = padding_chunks
        self.window_size = window_size
        self.voiced_threshold = voiced_threshold

        # Bytes per frame: 2 bytes/sample (16-bit PCM) × samples per frame
        self.frame_bytes = 2 * sample_rate * frame_duration_ms // 1000

        logger.info(
            "VAD initialised",
            extra={
                "event": {
                    "aggressiveness": aggressiveness,
                    "sample_rate": sample_rate,
                    "frame_duration_ms": frame_duration_ms,
                    "frame_bytes": self.frame_bytes,
                }
            },
        )

    # ── Public API ──────────────────────────────────────────────────────────

    def is_speech(self, audio_frame: bytes) -> tuple[bool, float]:
        """Classify a single PCM frame as speech or non-speech.

        Parameters
        ----------
        audio_frame:
            Raw 16-bit little-endian PCM data.  Must be exactly
            ``self.frame_bytes`` bytes long.

        Returns
        -------
        (is_voiced, latency_ms)
            ``is_voiced`` — True if the frame contains speech.
            ``latency_ms`` — Processing time in milliseconds.

        Raises
        ------
        VADError
            If the frame length does not match the expected size.
        """
        if len(audio_frame) != self.frame_bytes:
            raise VADError(
                f"Frame must be {self.frame_bytes} bytes, got {len(audio_frame)}"
            )
        t0 = time.perf_counter()
        voiced = self._vad.is_speech(audio_frame, self.sample_rate)
        latency_ms = (time.perf_counter() - t0) * 1000
        return voiced, latency_ms

    def segment_audio(
        self, audio_bytes: bytes
    ) -> Generator[tuple[bytes, bool], None, None]:
        """Yield (frame_bytes, is_voiced) pairs with majority-vote smoothing.

        The generator frames the raw PCM stream, classifies each frame, and
        applies a rolling window majority vote to smooth transient noise.

        Incomplete trailing frames are silently discarded.
        """
        frames = self._frame_generator(audio_bytes)
        window: deque[bool] = deque(maxlen=self.window_size)

        for frame in frames:
            voiced, latency_ms = self.is_speech(frame)
            window.append(voiced)
            smoothed = (
                sum(window) / len(window) >= self.voiced_threshold
                if window
                else False
            )
            if latency_ms > 200:  # pragma: no cover
                logger.warning(
                    "VAD latency exceeded 200ms threshold",
                    extra={"event": {"latency_ms": round(latency_ms, 2)}},
                )
            yield frame, smoothed

    def extract_speech_segments(self, audio_bytes: bytes) -> list[bytes]:
        """Return a list of voiced PCM segments with padding applied.

        Each element is a contiguous byte string representing a single
        continuous voiced segment (with leading/trailing padding frames).
        """
        voiced_frames: list[bytes] = []
        all_frames = list(self._frame_generator(audio_bytes))
        classifications: list[bool] = []

        for frame in all_frames:
            voiced, _ = self.is_speech(frame)
            classifications.append(voiced)

        # Smooth with a rolling window + majority vote
        smoothed: list[bool] = []
        win: deque[bool] = deque(maxlen=self.window_size)
        for v in classifications:
            win.append(v)
            smoothed.append(sum(win) / len(win) >= self.voiced_threshold)

        # Collect voiced frames with padding
        segments: list[bytes] = []
        in_segment = False
        segment_frames: list[bytes] = []
        pad_counter = 0

        for i, (frame, is_voiced) in enumerate(zip(all_frames, smoothed)):
            if is_voiced:
                if not in_segment:
                    # Include padding frames before current
                    start = max(0, i - self.padding_chunks)
                    segment_frames = list(all_frames[start:i])
                    in_segment = True
                    pad_counter = 0
                segment_frames.append(frame)
            elif in_segment:
                segment_frames.append(frame)
                pad_counter += 1
                if pad_counter >= self.padding_chunks:
                    segments.append(b"".join(segment_frames))
                    segment_frames = []
                    in_segment = False
                    pad_counter = 0

        # Flush any remaining open segment
        if in_segment and segment_frames:
            segments.append(b"".join(segment_frames))

        return segments

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _frame_generator(self, audio_bytes: bytes) -> list[bytes]:
        """Split raw PCM bytes into fixed-size frames."""
        frames: list[bytes] = []
        offset = 0
        while offset + self.frame_bytes <= len(audio_bytes):
            frames.append(audio_bytes[offset : offset + self.frame_bytes])
            offset += self.frame_bytes
        return frames
