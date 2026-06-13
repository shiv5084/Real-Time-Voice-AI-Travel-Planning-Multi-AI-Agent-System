"""Itinerary API routes.

Endpoints
---------
GET  /api/itineraries/{itinerary_id}         — fetch itinerary details
GET  /api/itineraries/{itinerary_id}/pdf     — generate & stream PDF
POST /api/itineraries/{itinerary_id}/email   — send itinerary by email

All routes require JWT auth via get_current_user_required.
"""

from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr

from app.middleware.auth import get_current_user_required
from app.models.user import User
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/itineraries", tags=["itineraries"])


# ── Request / Response models ──────────────────────────────────────────────

class EmailRequest(BaseModel):
    to_email: EmailStr


class EmailResponse(BaseModel):
    success: bool
    message: str





async def _fetch_itinerary_or_404(itinerary_id: str) -> dict[str, Any]:
    """Look up the trip/itinerary by ID from the database; raise 404 if not found."""
    from app.services.database import get_trip as db_get_trip, get_itinerary as db_get_itinerary

    # Look up the trip by ID
    trip = await db_get_trip(itinerary_id)
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Itinerary '{itinerary_id}' not found",
        )

    # Get the itinerary content associated with the trip
    itinerary = await db_get_itinerary(itinerary_id)

    return {
        "itinerary": itinerary.get("content") if itinerary else None,
        "constraints": trip.get("constraints") or {},
        "pipeline_status": trip.get("status"),
        "budget_breakdown": itinerary.get("budget_breakdown") if itinerary else None,
        "created_at": trip.get("created_at"),
    }


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/{itinerary_id}", status_code=status.HTTP_200_OK)
async def get_itinerary(
    itinerary_id: str,
) -> dict[str, Any]:
    """Return the full itinerary data for a given trip ID."""
    logger.info(
        "Itinerary fetch",
        extra={"event": {"itinerary_id": itinerary_id}},
    )

    trip = await _fetch_itinerary_or_404(itinerary_id)

    # Let's map activities and days to match the frontend Itinerary interface
    itinerary_content = trip.get("itinerary") or {}
    days_data = itinerary_content.get("days") or itinerary_content.get("day_plans") or []
    
    category_map = {
        "flight": "transport",
        "transport": "transport",
        "hotel": "accommodation",
        "accommodation": "accommodation",
        "attraction": "attraction",
        "restaurant": "meal",
        "meal": "meal",
    }

    mapped_days = []
    for day in days_data:
        activities = []
        for act in day.get("activities", []):
            activities.append({
                "time": act.get("start_time") or act.get("time") or "",
                "title": act.get("name") or act.get("title") or "",
                "description": act.get("description"),
                "location": act.get("location"),
                "duration": act.get("duration") or (f"{act.get('duration_minutes')}m" if act.get("duration_minutes") else None),
                "cost": act.get("cost_usd") if act.get("cost_usd") is not None else act.get("cost"),
                "category": category_map.get(str(act.get("type")).lower(), "other") if act.get("type") else "other"
            })
        
        mapped_days.append({
            "day": day.get("day") or 1,
            "date": day.get("date"),
            "title": day.get("location") or day.get("title"),
            "activities": activities
        })

    budget_data = trip.get("budget_breakdown") or {}
    total_val = budget_data.get("total_estimated_cost") or budget_data.get("total_cost") or budget_data.get("total") or 0
    currency_val = budget_data.get("currency", "USD")
    
    breakdown_list = []
    for cat in budget_data.get("categories", []):
        breakdown_list.append({
            "name": cat.get("category") or cat.get("name") or "Other",
            "amount": cat.get("amount") or 0
        })

    # Normalise into a standard response shape matching the frontend Itinerary interface
    return {
        "id":               itinerary_id,
        "destination":      itinerary_content.get("destination")
                            or ", ".join((trip.get("constraints") or {}).get("destinations", []))
                            or "Unknown",
        "startDate":        (trip.get("constraints") or {}).get("start_date") or (trip.get("constraints") or {}).get("departure_date"),
        "endDate":          (trip.get("constraints") or {}).get("end_date") or (trip.get("constraints") or {}).get("return_date"),
        "status":           "completed" if trip.get("pipeline_status") == "completed" else "planned",
        "days":             mapped_days,
        "budget": {
            "total":            total_val,
            "currency":         currency_val,
            "breakdown":        breakdown_list,
            "limit":            budget_data.get("total_budget") or (trip.get("constraints") or {}).get("budget"),
            "compliance":       budget_data.get("compliance") or "within_budget",
            "recommendations":  budget_data.get("recommendations") or []
        },
        "warnings":         itinerary_content.get("warnings") or trip.get("warnings") or []
    }


@router.get("/{itinerary_id}/pdf", response_class=StreamingResponse)
async def download_itinerary_pdf(
    itinerary_id: str,
) -> StreamingResponse:
    """Generate and stream the itinerary as a PDF file."""
    from app.services.pdf import generate_itinerary_pdf

    logger.info(
        "PDF generation request",
        extra={"event": {"itinerary_id": itinerary_id}},
    )

    trip = await _fetch_itinerary_or_404(itinerary_id)

    # Build the data dict expected by the PDF generator
    raw_itinerary = trip.get("itinerary") or {}
    raw_days = raw_itinerary.get("days", [])
    raw_budget = trip.get("budget_breakdown") or {}

    # Map days to the format the PDF generator expects
    pdf_days = []
    for day in raw_days:
        pdf_activities = []
        for act in (day.get("activities") or []):
            pdf_activities.append({
                "time": act.get("start_time") or act.get("time") or "",
                "name": act.get("name") or act.get("title") or "",
                "location": act.get("location") or "",
                "duration_minutes": act.get("duration_minutes"),
                "cost": act.get("cost_usd") if act.get("cost_usd") is not None else act.get("cost"),
            })
        pdf_days.append({
            "day_number": day.get("day") or "?",
            "date": day.get("date") or "",
            "activities": pdf_activities,
        })

    # Map budget categories to flat keys the PDF generator expects
    pdf_budget: dict[str, Any] = {"currency": raw_budget.get("currency", "$")}
    for cat in (raw_budget.get("categories") or []):
        cat_name = (cat.get("category") or "").lower()
        amount = cat.get("amount") or 0
        if cat_name in ("flights", "flight"):
            pdf_budget["flights"] = amount
        elif cat_name in ("hotels", "hotel", "accommodation"):
            pdf_budget["hotels"] = amount
        elif cat_name in ("attractions", "activities", "activity"):
            pdf_budget["activities"] = amount
        elif cat_name in ("food", "meals", "restaurant"):
            pdf_budget["food"] = amount
        elif cat_name in ("transport", "local_transport", "local transport"):
            pdf_budget["transport"] = amount
    pdf_budget["total"] = raw_budget.get("total_estimated_cost") or raw_budget.get("total") or 0

    itinerary_data: dict[str, Any] = {
        "destination":      raw_itinerary.get("destination", "Trip"),
        "traveler_name":    "Traveller",
        "start_date":       (trip.get("constraints") or {}).get("start_date", ""),
        "end_date":         (trip.get("constraints") or {}).get("end_date", ""),
        "days":             pdf_days,
        "budget_breakdown": pdf_budget,
        "summary":          raw_itinerary.get("summary", ""),
    }

    try:
        pdf_bytes = generate_itinerary_pdf(itinerary_data)
    except Exception as exc:
        logger.error(
            "PDF generation failed",
            extra={"event": {"itinerary_id": itinerary_id, "error": str(exc)}},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {exc}",
        )

    filename = f"itinerary-{itinerary_id[:8]}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length":      str(len(pdf_bytes)),
        },
    )


@router.post(
    "/{itinerary_id}/email",
    response_model=EmailResponse,
    status_code=status.HTTP_200_OK,
)
async def email_itinerary(
    itinerary_id: str,
    body: EmailRequest,
    current_user: User = Depends(get_current_user_required),
) -> EmailResponse:
    """Send the itinerary to the specified email address."""
    from app.services.email import send_itinerary_email
    from app.services.pdf import generate_itinerary_pdf

    logger.info(
        "Email itinerary request",
        extra={
            "event": {
                "itinerary_id": itinerary_id,
                "to":           body.to_email,
                "user_id":      current_user.id,
            }
        },
    )

    trip = await _fetch_itinerary_or_404(itinerary_id)

    itinerary_dict: dict[str, Any] = {
        **(trip.get("itinerary") or {}),
        "traveler_name":    current_user.display_name or current_user.email or "Traveller",
        "budget_breakdown": trip.get("budget_breakdown") or {},
    }

    # Generate PDF to attach (best-effort — email still sends if PDF fails)
    pdf_bytes: bytes | None = None
    try:
        pdf_bytes = generate_itinerary_pdf({
            "destination":      itinerary_dict.get("destination", "Trip"),
            "traveler_name":    itinerary_dict.get("traveler_name", "Traveller"),
            "start_date":       (trip.get("constraints") or {}).get("start_date", ""),
            "end_date":         (trip.get("constraints") or {}).get("end_date", ""),
            "days":             itinerary_dict.get("days", []),
            "budget_breakdown": itinerary_dict.get("budget_breakdown", {}),
            "summary":          itinerary_dict.get("summary", ""),
        })
    except Exception as pdf_exc:
        logger.warning(
            "PDF generation skipped for email",
            extra={"event": {"error": str(pdf_exc)}},
        )

    success = await send_itinerary_email(
        to_email=body.to_email,
        itinerary=itinerary_dict,
        pdf_bytes=pdf_bytes,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send email. Please try again later.",
        )

    return EmailResponse(
        success=True,
        message=f"Itinerary sent to {body.to_email}",
    )
