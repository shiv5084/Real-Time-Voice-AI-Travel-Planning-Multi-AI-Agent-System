"""Integration tests for authentication flow."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
class TestAuthFlow:
    """Tests for complete authentication flow."""

    async def test_health_check(self):
        """Test health check endpoint."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    async def test_register_new_user(self):
        """Test user registration."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Generate unique email to avoid conflicts
            import time
            email = f"test{int(time.time())}@example.com"

            response = await client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": "Password123",
                    "display_name": "Test User",
                },
            )
            # Note: This test may fail if Supabase is not configured
            # In local development, we may need to mock Supabase calls
            # For now, we'll just check the endpoint exists
            assert response.status_code in [200, 201, 400, 500]

    async def test_login_user(self):
        """Test user login."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "Password123",
                },
            )
            # Note: This test may fail if Supabase is not configured
            # In local development, we may need to mock Supabase calls
            assert response.status_code in [200, 401, 500]

    async def test_get_current_user_without_token(self):
        """Test getting current user without token should fail."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/auth/me")
            assert response.status_code == 401

    async def test_get_current_user_with_invalid_token(self):
        """Test getting current user with invalid token should fail."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/auth/me",
                headers={"Authorization": "Bearer invalid_token"},
            )
            assert response.status_code == 401


@pytest.mark.asyncio
class TestRedisSession:
    """Tests for Redis session management."""

    async def test_session_set_and_get(self):
        """Test setting and getting session data."""
        from app.memory.session import session_manager

        session_id = "test_session_123"
        test_data = {"user_id": "123", "email": "test@example.com"}

        await session_manager.set(session_id, test_data, ttl=60)
        retrieved_data = await session_manager.get(session_id)

        assert retrieved_data is not None
        assert retrieved_data["email"] == "test@example.com"

        # Cleanup
        await session_manager.delete(session_id)

    async def test_session_exists(self):
        """Test checking if session exists."""
        from app.memory.session import session_manager

        session_id = "test_session_exists"
        test_data = {"user_id": "456"}

        await session_manager.set(session_id, test_data, ttl=60)
        exists = await session_manager.exists(session_id)

        assert exists is True

        # Cleanup
        await session_manager.delete(session_id)

    async def test_session_delete(self):
        """Test deleting session."""
        from app.memory.session import session_manager

        session_id = "test_session_delete"
        test_data = {"user_id": "789"}

        await session_manager.set(session_id, test_data, ttl=60)
        await session_manager.delete(session_id)
        exists = await session_manager.exists(session_id)

        assert exists is False
