"""Voice pipeline API routes.

Endpoints
---------
POST /api/voice/transcribe
    Accept a multipart audio file upload, run VAD + STT, and return an
    editable transcript the user can confirm or correct before planning.

POST /api/voice/confirm
    Submit a (possibly edited) transcript to the planning pipeline and
    return the trip plan along with a TTS audio summary.

POST /api/voice/synthesise
    Generate a TTS audio summary for a given itinerary text.

POST /api/voice/transcribe/stream
    SSE-streaming transcription endpoint for the landing page.

--- Voice Session endpoints (new — Phase 5 Enhancement) ---

POST /api/voice/session/start
    Create a new voice session and return a greeting message (+ audio for
    real-time mode).

POST /api/voice/session/reply
    Submit one user turn (transcript).  Returns either a follow-up question
    or {status: "ready"} when all info has been collected.

GET  /api/voice/session/{session_id}/plan
    SSE stream that runs the full LangGraph pipeline using the conversation
    accumulated in the session, emitting per-agent progress events plus a
    final voice summary event.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import AsyncGenerator, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.middleware.auth import get_current_user_optional
from app.models.user import User
from app.utils.logging import get_logger
from app.utils.tracing import generate_trace_id, get_trace_id, set_trace_id

logger = get_logger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

# ── Constants ──────────────────────────────────────────────────────────────

_GREETING_TEXT = (
    "Hi! I'm your AI travel Planner. "
    "Tell me about your dream trip — where would you like to go?"
)

# ── Request / Response models ──────────────────────────────────────────────


class TranscriptConfirmRequest(BaseModel):
    transcript: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    trip_id: Optional[str] = None


class TranscriptResponse(BaseModel):
    trace_id: str
    transcript: str
    language: str
    confidence: float
    editable: bool = True
    requires_confirmation: bool = True
    fallback_to_text: bool = False
    error: Optional[str] = None


class VoicePlanResponse(BaseModel):
    trip_id: str
    trace_id: str
    pipeline_status: str
    validation_status: Optional[str] = None
    itinerary: Optional[dict] = None
    budget_breakdown: Optional[dict] = None
    constraints: Optional[dict] = None
    follow_up_questions: list[str] = []
    errors: list[dict] = []
    total_latency_ms: Optional[int] = None
    voice_summary: Optional[str] = None
    voice_summary_audio_b64: Optional[str] = None
    voice_summary_audio_format: Optional[str] = None


class SynthesiseRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None


class SynthesiseResponse(BaseModel):
    trace_id: str
    audio_format: str
    estimated_duration_sec: float
    latency_ms: float
    audio_b64: str


# ── New session models ─────────────────────────────────────────────────────


class SessionStartRequest(BaseModel):
    """Request body for starting a new voice session."""
    mode: Literal["realtime", "transcription"] = "realtime"


class SessionStartResponse(BaseModel):
    """Response from session/start — includes optional TTS greeting audio."""
    session_id: str
    greeting_text: str
    greeting_audio_b64: Optional[str] = None  # TTS audio for the greeting (both modes)
    greeting_audio_format: Optional[str] = None  # MIME type for the audio (e.g., "audio/mpeg", "audio/L16;rate=24000")


class SessionReplyRequest(BaseModel):
    """One user turn in the voice conversation."""
    session_id: str
    transcript: str
    mode: Literal["realtime", "transcription"] = "realtime"


class SessionReplyResponse(BaseModel):
    """Response from session/reply."""
    status: Literal["follow_up", "ready"]
    question: Optional[str] = None           # set when status == "follow_up"
    question_audio_b64: Optional[str] = None  # TTS audio for the follow-up question (both modes)
    question_audio_format: Optional[str] = None  # MIME type for the audio
    session_id: str


# ── Helpers ────────────────────────────────────────────────────────────────


def _build_voice_summary(state: dict) -> str:
    """Build a concise 30–45 second spoken trip summary from the plan state."""
    itinerary = state.get("itinerary") or {}
    constraints = state.get("constraints") or {}
    budget = state.get("budget_breakdown") or {}

    days = itinerary.get("days") or []
    destinations = constraints.get("destinations") or []
    dest_str = " and ".join(destinations) if destinations else "your destination"

    num_days = len(days)
    total_cost = budget.get("total_estimated_cost")
    currency = budget.get("currency", "USD")
    budget_note = (
        f"Total estimated cost: {currency} {total_cost:.0f}."
        if total_cost
        else ""
    )

    highlights: list[str] = []
    if days:
        first_day = days[0]
        acts = first_day.get("activities") or []
        if acts:
            highlights.append(f"Day one starts with {acts[0].get('name', 'an activity')}.")

    # Personalize the trip descriptor based on raw_request keywords
    raw_req = state.get("raw_request") or ""
    raw_req_lower = raw_req.lower()
    
    trip_type = "trip"
    normalized_req = raw_req_lower.replace("gateway", "getaway")
    
    if "honeymoon" in normalized_req:
        trip_type = "honeymoon"
    elif "weekend getaway" in normalized_req:
        trip_type = "weekend getaway"
    elif "weekend trip" in normalized_req or "weekend in" in normalized_req:
        trip_type = "weekend trip"
    elif "backpacking" in normalized_req:
        trip_type = "backpacking trip"
    elif "family vacation" in normalized_req or "family trip" in normalized_req:
        trip_type = "family trip"
    elif "business trip" in normalized_req:
        trip_type = "business trip"
    elif "day trip" in normalized_req:
        trip_type = "day trip"
    elif "getaway" in normalized_req:
        trip_type = "getaway"
        
    is_luxury = (
        "luxury" in normalized_req 
        or "five star" in normalized_req 
        or "5 star" in normalized_req
        or "premium" in normalized_req
        or "high-end" in normalized_req
        or "highend" in normalized_req
    )
    
    is_budget = (
        "budget" in normalized_req 
        or "cheap" in normalized_req 
        or "low cost" in normalized_req 
        or "low-cost" in normalized_req 
        or "hostel" in normalized_req
        or "backpacking" in normalized_req
        or "backpacker" in normalized_req
    )
    
    if is_luxury:
        if trip_type == "trip":
            descriptor = "luxury trip"
        else:
            descriptor = f"luxury {trip_type}"
    elif is_budget:
        if trip_type == "trip":
            descriptor = "budget-friendly trip"
        else:
            descriptor = f"budget-friendly {trip_type}"
    else:
        descriptor = f"{num_days}-day {trip_type}"

    lines = [f"Your {descriptor} to {dest_str} is ready."]
    lines.extend(highlights)
    if budget_note:
        lines.append(budget_note)

    return " ".join(lines)


async def _maybe_synthesise(text: str, mode: str) -> tuple[Optional[str], Optional[str]]:
    """Return base64 TTS audio and format if a TTS provider is configured.

    Works for both realtime and transcription voice modes — the frontend
    VoiceTranscriptBox renders the audio player for assistant messages in
    both modes. Silently returns None on any TTS failure so the caller can
    degrade gracefully.
    
    Returns:
        tuple: (audio_b64, audio_format) or (None, None) on failure
    """
    # mode parameter kept for signature compatibility but no longer restricts
    import re
    text = re.sub(r"\be\.g\.(?!\w)|\be\.g\b", "for example", text, flags=re.IGNORECASE)
    try:
        from app.voice.tts import FallbackTTS
        from app.config import get_settings
        settings = get_settings()
        
        # FallbackTTS contains a keyless fallback engine (Google Translate),
        # so we run it even when no proprietary keys are configured.
            
        logger.info(
            "Primary TTS started",
            extra={"event": {"text_length": len(text), "mode": mode}},
        )
        
        tts = FallbackTTS()
        try:
            result = await asyncio.wait_for(tts.synthesise(text), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(
                "TTS synthesis timed out after 10.0 seconds",
                extra={"event": {"text_length": len(text), "mode": mode}},
            )
            return None, None
        
        logger.info(
            "TTS synthesis successful",
            extra={
                "event": {
                    "duration_sec": result.estimated_duration_sec,
                    "latency_ms": result.latency_ms,
                    "audio_format": result.audio_format,
                    "audio_bytes": len(result.audio_bytes),
                    "provider": result.voice_id,
                }
            },
        )
        
        # Map audio format to MIME type
        audio_format = result.audio_format
        mime_type = "audio/mpeg"  # Default to MP3
        
        if audio_format == "wav":
            mime_type = "audio/wav"
        elif audio_format == "pcm_24000":
            mime_type = "audio/L16;rate=24000"
        elif audio_format == "pcm_22050":
            mime_type = "audio/L16;rate=22050"
        elif audio_format == "pcm_16000":
            mime_type = "audio/L16;rate=16000"
        elif audio_format.startswith("mp3"):
            mime_type = "audio/mpeg"
        
        logger.info(
            "Audio MIME type determined",
            extra={"event": {"audio_format": audio_format, "mime_type": mime_type}},
        )
        
        return base64.b64encode(result.audio_bytes).decode(), mime_type
    except Exception as exc:
        logger.warning(
            "TTS synthesis skipped",
            extra={
                "event": {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "error_details": str(exc.__dict__) if hasattr(exc, '__dict__') else None,
                }
            },
            exc_info=True,
        )
        return None, None


# ── Existing endpoints (unchanged) ────────────────────────────────────────


@router.post(
    "/transcribe",
    response_model=TranscriptResponse,
    status_code=status.HTTP_200_OK,
)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Audio file (WAV, MP3, OGG, WebM)"),
    language: Optional[str] = Form(default="en"),
) -> TranscriptResponse:
    """Transcribe an uploaded audio file using Groq Whisper API + WebRTC VAD."""
    trace_id = get_trace_id() or generate_trace_id(prefix="stt")
    set_trace_id(trace_id)

    logger.info(
        "Voice transcription request received",
        extra={"event": {"trace_id": trace_id, "content_type": audio.content_type}},
    )

    try:
        from app.voice.stt import GroqSTT

        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty.",
            )

        stt = GroqSTT(language=language or "en")
        result = await stt.atranscribe(audio_bytes, filename=audio.filename)

        if result.is_empty:
            return TranscriptResponse(
                trace_id=trace_id,
                transcript="",
                language=result.language,
                confidence=result.confidence,
                fallback_to_text=True,
                error="No speech detected. Please type your request.",
            )

        return TranscriptResponse(
            trace_id=trace_id,
            transcript=result.text,
            language=result.language,
            confidence=result.confidence,
            editable=True,
            requires_confirmation=True,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "STT transcription failed",
            extra={"event": {"trace_id": trace_id, "error": str(exc)}},
            exc_info=True,
        )
        return TranscriptResponse(
            trace_id=trace_id,
            transcript="",
            language="en",
            confidence=0.0,
            fallback_to_text=True,
            error=f"Voice processing failed: {exc}. Please type your request.",
        )


@router.post(
    "/confirm",
    response_model=VoicePlanResponse,
    status_code=status.HTTP_200_OK,
)
async def confirm_transcript(
    request: TranscriptConfirmRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> VoicePlanResponse:
    """Run the planning pipeline from a confirmed (possibly edited) transcript."""
    from app.graph.workflow import run_pipeline

    trace_id = get_trace_id() or generate_trace_id(prefix="voice_plan")
    set_trace_id(trace_id)
    trip_id = request.trip_id or str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())
    
    if current_user is not None:
        user_id = str(current_user.id)
    else:
        try:
            user_id = str(uuid.UUID(request.user_id)) if request.user_id else str(uuid.uuid4())
        except (ValueError, AttributeError):
            user_id = str(uuid.uuid4())

    if not request.transcript or not request.transcript.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript cannot be empty.",
        )

    try:
        final_state = await run_pipeline(
            raw_request=request.transcript,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            trip_id=trip_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline execution failed: {exc}",
        )

    # Persist to database
    try:
        from app.services.database import insert_trip, insert_itinerary
        await insert_trip(
            trip_id=trip_id,
            user_id=user_id,
            title=request.transcript[:100],
            raw_request=request.transcript,
            constraints=final_state.get("constraints") or {},
            status=final_state.get("pipeline_status", "completed"),
        )
        if final_state.get("itinerary"):
            itinerary_id = str(uuid.uuid4())
            await insert_itinerary(
                itinerary_id=itinerary_id,
                trip_id=trip_id,
                content=final_state.get("itinerary"),
                budget_breakdown=final_state.get("budget_breakdown"),
                validation_status=final_state.get("validation_status"),
            )
    except Exception as db_exc:
        logger.error(
            "Failed to persist confirmed voice transcript plan to database",
            extra={"event": {"trip_id": trip_id, "error": str(db_exc)}},
            exc_info=True
        )

    voice_summary_text = _build_voice_summary(final_state)
    voice_summary_audio_b64: str | None = None
    voice_summary_audio_format: str | None = None
    try:
        from app.voice.tts import FallbackTTS
        tts = FallbackTTS()
        import re
        spoken_summary = re.sub(r"\be\.g\.(?!\w)|\be\.g\b", "for example", voice_summary_text, flags=re.IGNORECASE)
        tts_result = await tts.synthesise(spoken_summary)
        voice_summary_audio_b64 = base64.b64encode(tts_result.audio_bytes).decode()
        
        # Map audio format to MIME type
        audio_format = tts_result.audio_format
        if audio_format == "wav":
            voice_summary_audio_format = "audio/wav"
        elif audio_format == "pcm_24000":
            voice_summary_audio_format = "audio/L16;rate=24000"
        elif audio_format == "pcm_22050":
            voice_summary_audio_format = "audio/L16;rate=22050"
        elif audio_format == "pcm_16000":
            voice_summary_audio_format = "audio/L16;rate=16000"
        elif audio_format.startswith("mp3"):
            voice_summary_audio_format = "audio/mpeg"
        else:
            voice_summary_audio_format = "audio/mpeg"  # Default
            
        logger.info(
            "Voice summary TTS synthesis complete",
            extra={
                "event": {
                    "audio_format": audio_format,
                    "mime_type": voice_summary_audio_format,
                    "audio_bytes": len(tts_result.audio_bytes),
                }
            },
        )
    except Exception as exc:
        logger.warning(
            "TTS synthesis failed",
            extra={"event": {"error": str(exc), "error_type": type(exc).__name__}},
            exc_info=True,
        )

    return VoicePlanResponse(
        trip_id=trip_id,
        trace_id=trace_id,
        pipeline_status=final_state.get("pipeline_status", "completed"),
        validation_status=final_state.get("validation_status"),
        itinerary=final_state.get("itinerary"),
        budget_breakdown=final_state.get("budget_breakdown"),
        constraints=final_state.get("constraints"),
        follow_up_questions=final_state.get("follow_up_questions") or [],
        errors=final_state.get("errors") or [],
        total_latency_ms=final_state.get("total_latency_ms"),
        voice_summary=voice_summary_text,
        voice_summary_audio_b64=voice_summary_audio_b64,
        voice_summary_audio_format=voice_summary_audio_format,
    )


@router.post(
    "/synthesise",
    response_model=SynthesiseResponse,
    status_code=status.HTTP_200_OK,
)
async def synthesise_text(request: SynthesiseRequest) -> SynthesiseResponse:
    """Generate TTS audio for a given text string."""
    from app.voice.tts import FallbackTTS, TTSError, ElevenLabsTTS

    trace_id = get_trace_id() or generate_trace_id(prefix="tts")
    set_trace_id(trace_id)

    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text cannot be empty.",
        )

    trimmed = ElevenLabsTTS.trim_to_target_length(request.text)
    import re
    spoken_text = re.sub(r"\be\.g\.(?!\w)|\be\.g\b", "for example", trimmed, flags=re.IGNORECASE)

    try:
        tts = FallbackTTS()
        result = await tts.synthesise(spoken_text)
    except TTSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    return SynthesiseResponse(
        trace_id=trace_id,
        audio_format=result.audio_format,
        estimated_duration_sec=result.estimated_duration_sec,
        latency_ms=result.latency_ms,
        audio_b64=base64.b64encode(result.audio_bytes).decode(),
    )


@router.post(
    "/transcribe/stream",
    status_code=status.HTTP_200_OK,
)
async def transcribe_audio_stream(
    audio: UploadFile = File(..., description="Audio file (WAV, MP3, OGG, WebM)"),
    language: Optional[str] = Form(default="en"),
):
    """Transcribe audio with SSE streaming for real-time transcription updates."""
    from app.services.streaming import create_sse_response
    from app.voice.stt import GroqSTT

    trace_id = get_trace_id() or generate_trace_id(prefix="stt_stream")
    set_trace_id(trace_id)

    async def stream_transcription() -> AsyncGenerator[dict[str, str], None]:
        try:
            audio_bytes = await audio.read()
            if not audio_bytes:
                yield {"event": "error", "data": json.dumps({"error": "Empty audio file"})}
                return

            yield {"event": "transcription_started", "data": json.dumps({"trace_id": trace_id})}

            stt = GroqSTT(language=language or "en")
            result = await stt.atranscribe(audio_bytes, filename=audio.filename)

            if result.is_empty:
                yield {
                    "event": "transcription_complete",
                    "data": json.dumps({
                        "trace_id": trace_id,
                        "transcript": "",
                        "language": result.language,
                        "confidence": result.confidence,
                        "fallback_to_text": True,
                        "error": "No speech detected. Please type your request.",
                    }),
                }
            else:
                yield {
                    "event": "transcription_complete",
                    "data": json.dumps({
                        "trace_id": trace_id,
                        "transcript": result.text,
                        "language": result.language,
                        "confidence": result.confidence,
                        "editable": True,
                        "requires_confirmation": True,
                    }),
                }
        except Exception as exc:
            logger.error(
                "Streaming transcription failed",
                extra={"event": {"trace_id": trace_id, "error": str(exc)}},
                exc_info=True,
            )
            yield {
                "event": "error",
                "data": json.dumps({
                    "trace_id": trace_id,
                    "error": f"Transcription failed: {exc}",
                    "fallback_to_text": True,
                }),
            }

    return create_sse_response(stream_transcription())


# ── New: Voice Session endpoints ───────────────────────────────────────────


@router.post(
    "/session/start",
    response_model=SessionStartResponse,
    status_code=status.HTTP_200_OK,
)
async def session_start(request: SessionStartRequest) -> SessionStartResponse:
    """Create a new voice session and return a greeting.

    In realtime mode the greeting is also synthesised to TTS audio so the
    frontend can play it immediately.  In transcription mode only text is
    returned — no audio.
    """
    from app.voice.session import voice_session_manager

    trace_id = get_trace_id() or generate_trace_id(prefix="vsess")
    set_trace_id(trace_id)

    session = await voice_session_manager.create(mode=request.mode)
    session_id = session["session_id"]

    # Append the greeting as the first assistant message
    await voice_session_manager.append_message(
        session_id=session_id,
        role="assistant",
        content=_GREETING_TEXT,
    )

    greeting_audio_b64, greeting_audio_format = await _maybe_synthesise(_GREETING_TEXT, request.mode)

    logger.info(
        "Voice session started",
        extra={
            "event": {
                "session_id": session_id,
                "mode": request.mode,
                "has_audio": bool(greeting_audio_b64),
                "audio_format": greeting_audio_format,
            }
        },
    )

    return SessionStartResponse(
        session_id=session_id,
        greeting_text=_GREETING_TEXT,
        greeting_audio_b64=greeting_audio_b64,
        greeting_audio_format=greeting_audio_format,
    )


@router.post(
    "/session/reply",
    response_model=SessionReplyResponse,
    status_code=status.HTTP_200_OK,
)
async def session_reply(request: SessionReplyRequest) -> SessionReplyResponse:
    """Process one user turn in the voice conversation.

    The transcript is appended to the session, then the backend checks whether
    enough information has been collected to run the planning pipeline.

    * If more info is needed → returns ``{status: "follow_up", question: "..."}``
      In realtime mode the question is also synthesised to TTS audio.

    * If all info collected → returns ``{status: "ready"}`` which signals the
      frontend to redirect to the planner page.
    """
    from app.voice.session import voice_session_manager, next_follow_up_question

    trace_id = get_trace_id() or generate_trace_id(prefix="vreply")
    set_trace_id(trace_id)

    logger.info(
        "[VOICE] Transcript received",
        extra={"event": {"trace_id": trace_id, "transcript": request.transcript, "session_id": request.session_id, "mode": request.mode}},
    )

    if not request.transcript or not request.transcript.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript cannot be empty.",
        )

    session = await voice_session_manager.get(request.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voice session '{request.session_id}' not found or expired.",
        )

    # Append user turn
    session = await voice_session_manager.append_message(
        session_id=request.session_id,
        role="user",
        content=request.transcript.strip(),
    )

    # Check what info is still missing
    collected = session.get("collected_texts") or []
    logger.info(
        "[VOICE] Parsed request - checking collected info",
        extra={"event": {"collected_texts": collected, "count": len(collected)}},
    )
    
    next_q = next_follow_up_question(collected)

    if next_q is None:
        # All info collected — mark ready
        await voice_session_manager.mark_ready(request.session_id)
        logger.info(
            "[VOICE] All info collected - session marked ready",
            extra={"event": {"session_id": request.session_id, "collected_texts": collected}},
        )
        return SessionReplyResponse(
            status="ready",
            session_id=request.session_id,
        )

    # Need one more piece of info
    await voice_session_manager.append_message(
        session_id=request.session_id,
        role="assistant",
        content=next_q,
    )

    question_audio_b64, question_audio_format = await _maybe_synthesise(next_q, request.mode)

    logger.info(
        "Voice session follow-up",
        extra={
            "event": {
                "session_id": request.session_id,
                "question": next_q[:60],
                "mode": request.mode,
                "audio_format": question_audio_format,
            }
        },
    )

    return SessionReplyResponse(
        status="follow_up",
        question=next_q,
        question_audio_b64=question_audio_b64,
        question_audio_format=question_audio_format,
        session_id=request.session_id,
    )


@router.get(
    "/session/{session_id}/plan",
    status_code=status.HTTP_200_OK,
)
async def session_plan(
    session_id: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """SSE stream that runs the full planning pipeline for a voice session.

    Emits per-agent progress events followed by a ``plan_complete`` event
    containing the itinerary and budget, and finally a ``voice_summary``
    event with the TTS audio (base64 encoded).

    SSE event types emitted:
    - ``agent_start``     — an agent has begun processing
    - ``agent_done``      — an agent finished (with optional partial data)
    - ``plan_complete``   — full itinerary + budget ready
    - ``voice_summary``   — TTS voice summary text + audio_b64
    - ``error``           — pipeline error
    """
    from app.services.streaming import create_sse_response
    from app.voice.session import voice_session_manager

    trace_id = get_trace_id() or generate_trace_id(prefix="vplan")
    set_trace_id(trace_id)

    if current_user is not None:
        user_id = str(current_user.id)
    else:
        user_id = str(uuid.uuid4())

    logger.info(
        "[VOICE] Session plan SSE requested",
        extra={"event": {"session_id": session_id, "trace_id": trace_id, "user_id": user_id}},
    )

    session = await voice_session_manager.get(session_id)
    if session is None:
        logger.error(
            "[VOICE] Session not found",
            extra={"event": {"session_id": session_id}},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voice session '{session_id}' not found or expired.",
        )

    logger.info(
        "[VOICE] Session retrieved",
        extra={"event": {
            "session_id": session_id,
            "status": session.get("status"),
            "collected_texts_count": len(session.get("collected_texts", [])),
            "collected_texts": session.get("collected_texts", []),
        }},
    )

    # ── Race-condition fix: retry until 'ready' or we confirm data is present ──
    # The frontend may connect to SSE milliseconds after session_reply returns
    # {status: "ready"}, before Redis has fully persisted the mark_ready() write.
    # For remote Redis (Upstash) we retry up to 10 times (2 seconds total) to
    # account for the higher network latency vs. local Redis.
    MAX_RETRIES = 10
    RETRY_DELAY_S = 0.2
    for attempt in range(MAX_RETRIES):
        if session.get("status") == "ready":
            break  # Already ready — proceed
        collected_texts = session.get("collected_texts") or []
        if collected_texts:
            # Data is present but status hasn't been written yet — promote now
            logger.info(
                "[VOICE] Auto-promoting session to ready (race-condition fix)",
                extra={"event": {
                    "session_id": session_id,
                    "attempt": attempt + 1,
                    "current_status": session.get("status"),
                    "collected_texts_count": len(collected_texts),
                    "collected_texts": collected_texts,
                }},
            )
            await voice_session_manager.mark_ready(session_id)
            session = await voice_session_manager.get(session_id)
            break
        # No data yet — wait a moment and re-read from Redis
        logger.info(
            "[VOICE] Session not ready yet, retrying",
            extra={"event": {"session_id": session_id, "attempt": attempt + 1}},
        )
        await asyncio.sleep(RETRY_DELAY_S)
        session = await voice_session_manager.get(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Voice session '{session_id}' not found after retry.",
            )

    # Final guard: if still not ready after all retries, auto-promote if we have any data
    if session.get("status") != "ready":
        collected_texts = session.get("collected_texts") or []
        if collected_texts:
            # We have user data — force-promote and proceed anyway
            logger.warning(
                "[VOICE] Session not 'ready' after retries but has data — force-promoting",
                extra={"event": {
                    "session_id": session_id,
                    "status": session.get("status"),
                    "collected_texts_count": len(collected_texts),
                }},
            )
            await voice_session_manager.mark_ready(session_id)
            session = {**session, "status": "ready"}
        else:
            logger.error(
                "[VOICE] Session not ready after retries",
                extra={"event": {
                    "session_id": session_id,
                    "status": session.get("status"),
                    "collected_texts_count": len(collected_texts),
                }},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Voice session is not yet ready — conversation still in progress.",
            )

    # Build augmented request from all user turns
    augmented_request = voice_session_manager.build_augmented_request(session)
    if not augmented_request or not augmented_request.strip():
        # Fallback: try to get from session messages
        messages_list = session.get("messages") or []
        user_messages = [m["content"] for m in messages_list if m.get("role") == "user"]
        augmented_request = "\n\n".join(user_messages)

    if not augmented_request or not augmented_request.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No travel request found in voice session — please restart.",
        )

    trip_id = str(uuid.uuid4())

    logger.info(
        "[VOICE] Itinerary generation started",
        extra={"event": {"session_id": session_id, "trip_id": trip_id, "augmented_request": augmented_request}},
    )

    async def run_and_stream() -> AsyncGenerator[dict[str, str], None]:
        # Emit progress events for each agent step (simulated — real agents run below)
        agent_names = [
            ("planner",     "Analysing your travel request…"),
            ("flights",     "Searching for flights…"),
            ("hotels",      "Finding the best hotels…"),
            ("attractions", "Discovering local attractions…"),
            ("transport",   "Calculating routes…"),
            ("budget",      "Optimising your budget…"),
            ("composer",    "Composing your itinerary…"),
            ("validator",   "Validating your plan…"),
        ]

        # We emit agent_start events optimistically while the pipeline runs in parallel
        pipeline_task = asyncio.create_task(
            _run_pipeline_task(augmented_request, trip_id, trace_id, session_id, user_id)
        )

        for agent_id, agent_msg in agent_names:
            yield {
                "event": "agent_start",
                "data": json.dumps({"agent": agent_id, "message": agent_msg}),
            }
            # Small delay so the frontend can render the spinner updates
            await asyncio.sleep(0.8)
            yield {
                "event": "agent_done",
                "data": json.dumps({"agent": agent_id}),
            }

        # Await the actual pipeline result
        try:
            final_state = await pipeline_task
            logger.info(
                "[VOICE] Itinerary generation completed",
                extra={"event": {"session_id": session_id, "trip_id": trip_id, "pipeline_status": final_state.get("pipeline_status"), "has_itinerary": bool(final_state.get("itinerary"))}},
            )

            # Persist to database so the user can view the itinerary
            try:
                from app.services.database import insert_trip, insert_itinerary
                user_id_from_state = final_state.get("user_id")
                try:
                    uuid.UUID(str(user_id_from_state))
                    db_user_id = str(user_id_from_state)
                except (ValueError, TypeError):
                    db_user_id = user_id

                await insert_trip(
                    trip_id=trip_id,
                    user_id=db_user_id,
                    title=augmented_request[:100] if augmented_request else "Voice Trip",
                    raw_request=augmented_request or "Voice session request",
                    constraints=final_state.get("constraints") or {},
                    status=final_state.get("pipeline_status", "completed"),
                )
                if final_state.get("itinerary"):
                    itinerary_id = str(uuid.uuid4())
                    await insert_itinerary(
                        itinerary_id=itinerary_id,
                        trip_id=trip_id,
                        content=final_state.get("itinerary"),
                        budget_breakdown=final_state.get("budget_breakdown"),
                        validation_status=final_state.get("validation_status"),
                    )
                    logger.info(
                        "[VOICE] Trip and itinerary persisted to database",
                        extra={"event": {"trip_id": trip_id, "itinerary_id": itinerary_id, "user_id": user_id}}
                    )
            except Exception as db_exc:
                logger.error(
                    "[VOICE] Failed to persist trip/itinerary to database",
                    extra={"event": {"trip_id": trip_id, "error": str(db_exc)}},
                    exc_info=True
                )
        except Exception as exc:
            logger.error(
                "[VOICE] Itinerary generation failed",
                extra={"event": {"session_id": session_id, "error": str(exc), "error_type": type(exc).__name__}},
                exc_info=True,
            )
            yield {
                "event": "error",
                "data": json.dumps({"error": str(exc)}),
            }
            return

        yield {
            "event": "plan_complete",
            "data": json.dumps(
                {
                    "trip_id": trip_id,
                    "pipeline_status": final_state.get("pipeline_status", "completed"),
                    "validation_status": final_state.get("validation_status"),
                    "itinerary": final_state.get("itinerary"),
                    "budget_breakdown": final_state.get("budget_breakdown"),
                    "constraints": final_state.get("constraints"),
                    "follow_up_questions": final_state.get("follow_up_questions") or [],
                    "errors": final_state.get("errors") or [],
                    "total_latency_ms": final_state.get("total_latency_ms"),
                },
                default=str,
            ),
        }

        # Build and optionally synthesise the voice summary (task 5.6)
        logger.info(
            "[VOICE] Summary generation started",
            extra={"event": {"session_id": session_id, "trip_id": trip_id}},
        )
        summary_text = _build_voice_summary(final_state)
        logger.info(
            "[VOICE] Summary generation completed",
            extra={"event": {"session_id": session_id, "summary_text": summary_text, "summary_length": len(summary_text)}},
        )
        summary_audio_b64: str | None = None
        summary_audio_format: str | None = None
        try:
            logger.info(
                "[VOICE] TTS started",
                extra={"event": {"session_id": session_id, "summary_text_length": len(summary_text)}},
            )
            from app.voice.tts import FallbackTTS
            tts = FallbackTTS()
            import re
            spoken_summary = re.sub(r"\be\.g\.(?!\w)|\be\.g\b", "for example", summary_text, flags=re.IGNORECASE)
            tts_result = await tts.synthesise(spoken_summary)
            summary_audio_b64 = base64.b64encode(tts_result.audio_bytes).decode()

            # Map audio format to MIME type
            audio_format = tts_result.audio_format
            if audio_format == "wav":
                summary_audio_format = "audio/wav"
            elif audio_format == "pcm_24000":
                summary_audio_format = "audio/L16;rate=24000"
            elif audio_format == "pcm_22050":
                summary_audio_format = "audio/L16;rate=22050"
            elif audio_format == "pcm_16000":
                summary_audio_format = "audio/L16;rate=16000"
            elif audio_format.startswith("mp3"):
                summary_audio_format = "audio/mpeg"
            else:
                summary_audio_format = "audio/mpeg"  # Default

            logger.info(
                "[VOICE] TTS completed",
                extra={
                    "event": {
                        "session_id": session_id,
                        "audio_format": audio_format,
                        "mime_type": summary_audio_format,
                        "audio_bytes": len(tts_result.audio_bytes),
                    }
                },
            )
        except Exception as exc:
            logger.warning(
                "[VOICE] TTS failed",
                extra={"event": {"session_id": session_id, "error": str(exc), "error_type": type(exc).__name__}},
                exc_info=True,
            )

        yield {
            "event": "voice_summary",
            "data": json.dumps(
                {
                    "text": summary_text,
                    "audio_b64": summary_audio_b64,
                    "audio_format": summary_audio_format,
                },
                default=str,
            ),
        }

        logger.info(
            "[VOICE] Audio URL generated",
            extra={"event": {"session_id": session_id, "has_audio": bool(summary_audio_b64), "audio_format": summary_audio_format}},
        )

        logger.info(
            "[VOICE] Response sent to frontend",
            extra={"event": {"session_id": session_id, "trip_id": trip_id}},
        )

        # Clean up the session after a successful plan
        await voice_session_manager.delete(session_id)

    return create_sse_response(run_and_stream())


async def _run_pipeline_task(
    augmented_request: str,
    trip_id: str,
    trace_id: str,
    session_id: str = "",
    user_id: str = "",
) -> dict:
    """Run the LangGraph pipeline and return final_state."""
    from app.graph.workflow import run_pipeline

    logger.info(
        "[VOICE] Pipeline task started",
        extra={"event": {"trip_id": trip_id, "trace_id": trace_id, "session_id": session_id, "augmented_request": augmented_request}},
    )

    try:
        result = await run_pipeline(
            raw_request=augmented_request,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            trip_id=trip_id,
        )
        logger.info(
            "[VOICE] Pipeline task completed",
            extra={"event": {"trip_id": trip_id, "trace_id": trace_id, "has_itinerary": bool(result.get("itinerary"))}},
        )
        return result
    except Exception as exc:
        logger.error(
            "[VOICE] Pipeline task failed",
            extra={"event": {"trip_id": trip_id, "trace_id": trace_id, "error": str(exc), "error_type": type(exc).__name__}},
            exc_info=True,
        )
        raise

