"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.middleware.auth import get_current_user_required
from app.models.user import (
    AuthResponse,
    GoogleOAuthRequest,
    LoginRequest,
    RegisterRequest,
    User,
)
from app.services.auth import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class CreateProfileRequest(BaseModel):
    """Lightweight payload for creating a profile row for an already-registered auth user."""
    email: EmailStr
    user_id: str
    display_name: Optional[str] = None

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """Register a new user with email/password."""
    try:
        return await auth_service.register(
            email=request.email,
            password=request.password,
            display_name=request.display_name,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}",
        )


@router.post("/create-profile", status_code=status.HTTP_201_CREATED)
async def create_profile(request: CreateProfileRequest):
    """Create a profile row for a user who registered directly via the Supabase client SDK.

    Called by the frontend immediately after ``supabase.auth.signUp()`` succeeds.
    Uses the service role key to bypass RLS so the profile can be created before
    the user's email is confirmed.
    """
    try:
        await auth_service._create_profile(
            user_id=request.user_id,
            email=request.email,
            display_name=request.display_name,
        )
        return {"message": "Profile created", "user_id": request.user_id}
    except Exception as e:
        # 409 / duplicate — profile already exists, that's fine
        detail = str(e)
        if "duplicate" in detail.lower() or "unique" in detail.lower() or "409" in detail:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Profile already exists",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Profile creation failed: {detail}",
        )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Login user with email/password."""
    try:
        return await auth_service.login(email=request.email, password=request.password)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Login failed: {str(e)}",
        )


@router.post("/google", response_model=AuthResponse)
async def google_oauth(request: GoogleOAuthRequest):
    """Authenticate user with Google OAuth."""
    try:
        return await auth_service.google_oauth(id_token=request.id_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google OAuth failed: {str(e)}",
        )


@router.get("/me", response_model=User)
async def get_current_user(user: User = Depends(get_current_user_required)):
    """Get current user from JWT token in Authorization header."""
    return user
