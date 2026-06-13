"""Trip-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TripStatus(str, Enum):
    """Trip status enumeration."""

    PLANNING = "planning"
    COMPLETED = "completed"
    FAILED = "failed"


class TripPreferences(BaseModel):
    """User preferences for trip planning."""

    accommodation_type: Optional[str] = None  # hotel, hostel, apartment, etc.
    food_preferences: Optional[list[str]] = None  # vegetarian, vegan, etc.
    crowd_tolerance: Optional[str] = None  # low, medium, high
    activity_level: Optional[str] = None  # relaxed, moderate, active
    transport_preference: Optional[str] = None  # public, rental, walking
    budget_priority: Optional[str] = None  # economy, balanced, luxury


class TripConstraints(BaseModel):
    """Trip constraints extracted from user request."""

    destinations: list[str] = Field(default_factory=list)
    start_date: Optional[str] = None  # ISO format date string
    end_date: Optional[str] = None  # ISO format date string
    budget: Optional[float] = None
    budget_currency: Optional[str] = "USD"
    travelers: Optional[int] = Field(default=1, ge=1, le=20)
    preferences: Optional[TripPreferences] = None


class Trip(BaseModel):
    """Trip model."""

    id: UUID
    user_id: UUID
    title: str
    raw_request: Optional[str] = None
    constraints: Optional[TripConstraints] = None
    status: TripStatus = TripStatus.PLANNING
    created_at: datetime
    updated_at: datetime


class TripCreate(BaseModel):
    """Request model for creating a trip."""

    title: str = Field(..., min_length=1, max_length=200)
    raw_request: Optional[str] = None
    constraints: Optional[TripConstraints] = None


class TripUpdate(BaseModel):
    """Request model for updating a trip."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    raw_request: Optional[str] = None
    constraints: Optional[TripConstraints] = None
    status: Optional[TripStatus] = None
