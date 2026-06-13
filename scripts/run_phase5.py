#!/usr/bin/env python3
"""Verify Phase 5 — Voice pipeline (STT, TTS, VAD)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _phase_common import env_keys_documented, run_phase

REQUIRED = [
    "backend/app/voice/__init__.py",
    "backend/app/voice/stt.py",
    "backend/app/voice/tts.py",
    "backend/app/voice/vad.py",
    "backend/app/routers/voice.py",
    "backend/tests/unit/test_stt.py",
    "backend/tests/unit/test_tts.py",
    "backend/tests/unit/test_vad.py",
    "backend/tests/integration/test_voice_pipeline.py",
]

_PHASE5_ENV_KEYS = [
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "GROQ_WHISPER_MODEL",
    "VAD_AGGRESSIVENESS",
    "VAD_SAMPLE_RATE",
]


def _check_env_keys():
    missing = env_keys_documented(_PHASE5_ENV_KEYS)
    if missing:
        return False, f"Phase 5 env keys not documented in .env.example: {missing}"
    return True, "All Phase 5 env keys documented in .env.example"


if __name__ == "__main__":
    sys.exit(
        run_phase(
            5,
            "Voice Pipeline (STT + TTS)",
            REQUIRED,
            pytest_paths=[
                "backend/tests/unit/test_stt.py",
                "backend/tests/unit/test_tts.py",
                "backend/tests/unit/test_vad.py",
                "backend/tests/integration/test_voice_pipeline.py",
            ],
            extra_checks=[_check_env_keys],
        )
    )

