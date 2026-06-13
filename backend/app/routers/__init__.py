"""API router modules."""

from .auth import router as auth_router
from .health import router as health_router
from .itineraries import router as itineraries_router
from .profile import router as profile_router
from .trips import router as trips_router
from .voice import router as voice_router

__all__ = [
    "auth_router",
    "health_router",
    "itineraries_router",
    "profile_router",
    "trips_router",
    "voice_router",
]
