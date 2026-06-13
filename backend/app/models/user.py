"""User and authentication-related Pydantic models."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class Profile(BaseModel):
    """User profile model."""

    id: UUID
    display_name: Optional[str] = None
    email: EmailStr
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class User(BaseModel):
    """User model combining profile with auth info."""

    id: UUID
    email: EmailStr
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class RegisterRequest(BaseModel):
    """Request model for user registration."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    """Request model for user login."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class AuthResponse(BaseModel):
    """Response model for authentication operations."""

    access_token: str
    token_type: str = "bearer"
    user: User


class GoogleOAuthRequest(BaseModel):
    """Request model for Google OAuth."""

    id_token: str = Field(..., min_length=1)
