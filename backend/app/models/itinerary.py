"""Itinerary-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    """Itinerary validation status."""

    APPROVED = "approved"
    WARNINGS = "warnings"
    REJECTED = "rejected"


class Activity(BaseModel):
    """Single activity in a day plan."""

    id: Optional[str] = None
    name: str
    type: str  # flight, hotel, attraction, restaurant, transport, etc.
    location: Optional[str] = None
    start_time: Optional[str] = None  # HH:MM format
    end_time: Optional[str] = None  # HH:MM format
    duration_minutes: Optional[int] = None
    cost: Optional[float] = None
    currency: Optional[str] = "USD"
    description: Optional[str] = None
    booking_url: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class DayPlan(BaseModel):
    """Single day itinerary plan."""

    day: int = Field(..., ge=1)
    date: Optional[str] = None  # ISO format date string
    location: Optional[str] = None
    activities: list[Activity] = Field(default_factory=list)
    total_cost: Optional[float] = None
    notes: Optional[str] = None


class Itinerary(BaseModel):
    """Complete itinerary model."""

    id: UUID
    trip_id: UUID
    content: dict[str, Any]  # Structured day-by-day itinerary
    budget_breakdown: Optional[dict[str, Any]] = None
    validation_status: ValidationStatus = ValidationStatus.APPROVED
    version: int = 1
    created_at: datetime


class ItineraryCreate(BaseModel):
    """Request model for creating an itinerary."""

    trip_id: UUID
    content: dict[str, Any]
    budget_breakdown: Optional[dict[str, Any]] = None
    validation_status: ValidationStatus = ValidationStatus.APPROVED
