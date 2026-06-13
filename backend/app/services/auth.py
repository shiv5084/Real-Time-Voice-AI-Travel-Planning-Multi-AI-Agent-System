"""Supabase Auth wrapper for JWT verification and OAuth."""

from typing import Optional

import httpx
from app.config import get_settings
from app.models.user import AuthResponse, User

settings = get_settings()


class AuthService:
    """Wrapper for Supabase authentication operations."""

    def __init__(self):
        """Initialize Supabase client settings."""
        self.supabase_url = settings.supabase_url
        self.supabase_anon_key = settings.supabase_anon_key
        self.supabase_service_key = settings.supabase_service_key

    async def register(
        self,
        email: str,
        password: str,
        display_name: Optional[str] = None,
    ) -> AuthResponse:
        """Register a new user with email/password."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.supabase_url}/auth/v1/signup",
                json={
                    "email": email,
                    "password": password,
                    "data": {"display_name": display_name} if display_name else {},
                },
                headers={
                    "apikey": self.supabase_anon_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            # Create user profile in profiles table
            await self._create_profile(data["user"]["id"], email, display_name)

            return AuthResponse(
                access_token=data["access_token"],
                token_type="bearer",
                user=User(
                    id=data["user"]["id"],
                    email=data["user"]["email"],
                    display_name=display_name,
                ),
            )

    async def login(self, email: str, password: str) -> AuthResponse:
        """Login user with email/password."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.supabase_url}/auth/v1/token?grant_type=password",
                json={
                    "email": email,
                    "password": password,
                },
                headers={
                    "apikey": self.supabase_anon_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            # Get user profile
            profile = await self._get_profile(data["user"]["id"])

            return AuthResponse(
                access_token=data["access_token"],
                token_type="bearer",
                user=User(
                    id=data["user"]["id"],
                    email=data["user"]["email"],
                    display_name=profile.get("display_name") if profile else None,
                    avatar_url=profile.get("avatar_url") if profile else None,
                ),
            )

    async def google_oauth(self, id_token: str) -> AuthResponse:
        """Authenticate user with Google OAuth."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.supabase_url}/auth/v1/token?grant_type=id_token",
                json={
                    "id_token": id_token,
                    "provider": "google",
                },
                headers={
                    "apikey": self.supabase_anon_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            # Get or create user profile
            profile = await self._get_profile(data["user"]["id"])
            if not profile:
                await self._create_profile(
                    data["user"]["id"],
                    data["user"]["email"],
                    data["user"].get("user_metadata", {}).get("display_name"),
                )
                profile = await self._get_profile(data["user"]["id"])

            return AuthResponse(
                access_token=data["access_token"],
                token_type="bearer",
                user=User(
                    id=data["user"]["id"],
                    email=data["user"]["email"],
                    display_name=profile.get("display_name") if profile else None,
                    avatar_url=profile.get("avatar_url") if profile else None,
                ),
            )

    async def verify_jwt(self, token: str) -> Optional[dict]:
        """Verify JWT token and return user info."""
        if not self.supabase_url or not self.supabase_anon_key:
            # Supabase not configured (local dev without Supabase) — treat as invalid
            return None
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": self.supabase_anon_key,
                },
            )
            if response.status_code == 200:
                return response.json()
            return None

    async def get_user(self, token: str) -> Optional[User]:
        """Get user info from JWT token."""
        user_data = await self.verify_jwt(token)
        if not user_data:
            return None

        profile = await self._get_profile(user_data["id"])

        return User(
            id=user_data["id"],
            email=user_data["email"],
            display_name=profile.get("display_name") if profile else None,
            avatar_url=profile.get("avatar_url") if profile else None,
        )

    async def _create_profile(
        self,
        user_id: str,
        email: str,
        display_name: Optional[str] = None,
    ) -> dict:
        """Create user profile in profiles table using service role."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.supabase_url}/rest/v1/profiles",
                json={
                    "id": user_id,
                    "email": email,
                    "display_name": display_name,
                },
                headers={
                    "apikey": self.supabase_service_key,
                    "Authorization": f"Bearer {self.supabase_service_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
            )
            response.raise_for_status()
            return response.json()

    async def _get_profile(self, user_id: str) -> Optional[dict]:
        """Get user profile from profiles table."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.supabase_url}/rest/v1/profiles?id=eq.{user_id}",
                headers={
                    "apikey": self.supabase_anon_key,
                    "Authorization": f"Bearer {self.supabase_anon_key}",
                },
            )
            if response.status_code == 200:
                data = response.json()
                return data[0] if data else None
            return None


# Global auth service instance
auth_service = AuthService()
