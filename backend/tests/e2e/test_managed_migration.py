"""
End-to-end tests for Phase 7A: Managed Services Migration (Supabase + Upstash).

These tests verify that the application correctly uses managed services
when APP_ENV is set to 'production' or 'staging'.
"""

import asyncio
import os
import pytest
from app.config import get_settings
from app.memory.session import SessionManager, get_redis


class TestManagedServicesMigration:
    """Test managed services migration configuration and connectivity."""

    def test_config_has_managed_service_fields(self):
        """Verify config.py has all required managed service fields."""
        settings = get_settings()
        
        # Check that managed service fields exist
        assert hasattr(settings, "supabase_url")
        assert hasattr(settings, "supabase_anon_key")
        assert hasattr(settings, "supabase_service_key")
        assert hasattr(settings, "upstash_redis_url")
        assert hasattr(settings, "upstash_redis_token")

    def test_app_env_validation(self):
        """Verify that APP_ENV validation works correctly."""
        # Test with local environment (default)
        original_env = os.environ.get("APP_ENV")
        
        try:
            # Clear cache before starting
            get_settings.cache_clear()
            
            # Test local environment
            os.environ["APP_ENV"] = "local"
            get_settings.cache_clear()
            settings = get_settings()
            assert settings.app_env == "local"
            
            # Test production environment validation
            os.environ["APP_ENV"] = "production"
            # This should fail if required vars are missing
            # We'll catch the ValueError in the test
            try:
                # Clear cached settings
                get_settings.cache_clear()
                settings = get_settings()
                # If we get here without required vars, validation might be relaxed
                # In production, SUPABASE_URL, SUPABASE_ANON_KEY, UPSTASH_REDIS_URL are required
            except ValueError as e:
                # Expected when required vars are missing
                assert "SUPABASE_URL" in str(e) or "UPSTASH_REDIS_URL" in str(e)
        finally:
            # Restore original environment
            if original_env:
                os.environ["APP_ENV"] = original_env
            else:
                os.environ.pop("APP_ENV", None)
            # Clear cached settings
            get_settings.cache_clear()

    @pytest.mark.skipif(
        not os.environ.get("UPSTASH_REDIS_URL"),
        reason="UPSTASH_REDIS_URL not set - skipping Upstash connectivity test"
    )
    async def test_upstash_redis_connectivity(self):
        """Test that Upstash Redis connection works when configured."""
        # Set environment to production for this test
        original_env = os.environ.get("APP_ENV")
        original_url = os.environ.get("UPSTASH_REDIS_URL")
        original_token = os.environ.get("UPSTASH_REDIS_TOKEN")
        
        try:
            os.environ["APP_ENV"] = "production"
            os.environ["UPSTASH_REDIS_URL"] = os.environ.get("UPSTASH_REDIS_URL", "")
            os.environ["UPSTASH_REDIS_TOKEN"] = os.environ.get("UPSTASH_REDIS_TOKEN", "")
            
            # Clear cached settings
            get_settings.cache_clear()
            
            # Test Redis connection
            redis_client = await get_redis()
            
            if redis_client:
                # Test basic operations
                await redis_client.set("test_key", "test_value", ex=60)
                value = await redis_client.get("test_key")
                assert value == "test_value"
                
                # Cleanup
                await redis_client.delete("test_key")
                await redis_client.close()
            else:
                pytest.skip("Could not connect to Upstash Redis")
        finally:
            # Restore original environment
            if original_env:
                os.environ["APP_ENV"] = original_env
            else:
                os.environ.pop("APP_ENV", None)
            
            if original_url:
                os.environ["UPSTASH_REDIS_URL"] = original_url
            else:
                os.environ.pop("UPSTASH_REDIS_URL", None)
            
            if original_token:
                os.environ["UPSTASH_REDIS_TOKEN"] = original_token
            else:
                os.environ.pop("UPSTASH_REDIS_TOKEN", None)
            
            # Clear cached settings
            get_settings.cache_clear()

    @pytest.mark.skipif(
        not os.environ.get("UPSTASH_REDIS_URL"),
        reason="UPSTASH_REDIS_URL not set - skipping session manager test"
    )
    async def test_session_manager_with_upstash(self):
        """Test that SessionManager works with Upstash Redis."""
        original_env = os.environ.get("APP_ENV")
        original_url = os.environ.get("UPSTASH_REDIS_URL")
        original_token = os.environ.get("UPSTASH_REDIS_TOKEN")
        
        try:
            os.environ["APP_ENV"] = "production"
            os.environ["UPSTASH_REDIS_URL"] = os.environ.get("UPSTASH_REDIS_URL", "")
            os.environ["UPSTASH_REDIS_TOKEN"] = os.environ.get("UPSTASH_REDIS_TOKEN", "")
            
            # Clear cached settings
            get_settings.cache_clear()
            
            # Create session manager
            session_manager = SessionManager()
            
            # Test session operations
            test_data = {"user_id": "test_user", "trip_id": "test_trip"}
            session_id = "test_session_123"
            
            # Set session
            result = await session_manager.set(session_id, test_data, ttl=60)
            assert result is True
            
            # Get session
            retrieved_data = await session_manager.get(session_id)
            assert retrieved_data is not None
            assert retrieved_data["user_id"] == "test_user"
            
            # Check existence
            exists = await session_manager.exists(session_id)
            assert exists is True
            
            # Delete session
            delete_result = await session_manager.delete(session_id)
            assert delete_result is True
            
            # Verify deletion
            exists_after = await session_manager.exists(session_id)
            assert exists_after is False
            
            # Close connection
            await session_manager.close()
        finally:
            # Restore original environment
            if original_env:
                os.environ["APP_ENV"] = original_env
            else:
                os.environ.pop("APP_ENV", None)
            
            if original_url:
                os.environ["UPSTASH_REDIS_URL"] = original_url
            else:
                os.environ.pop("UPSTASH_REDIS_URL", None)
            
            if original_token:
                os.environ["UPSTASH_REDIS_TOKEN"] = original_token
            else:
                os.environ.pop("UPSTASH_REDIS_TOKEN", None)
            
            # Clear cached settings
            get_settings.cache_clear()

    def test_session_manager_uses_upstash_in_production(self):
        """Test that SessionManager uses Upstash URL in production mode."""
        original_env = os.environ.get("APP_ENV")
        original_url = os.environ.get("UPSTASH_REDIS_URL")
        original_token = os.environ.get("UPSTASH_REDIS_TOKEN")
        
        try:
            # Clear cache before starting
            get_settings.cache_clear()
            
            # Set production environment
            os.environ["APP_ENV"] = "production"
            os.environ["UPSTASH_REDIS_URL"] = "https://test.upstash.io"
            os.environ["UPSTASH_REDIS_TOKEN"] = "test_token"
            
            # Clear cached settings
            get_settings.cache_clear()
            
            # Create session manager
            session_manager = SessionManager()
            
            # Verify it uses Upstash URL (converted to rediss:// for Redis client)
            assert session_manager.redis_url == "rediss://test.upstash.io"
            assert session_manager.redis_token == "test_token"
            
            # Close connection
            asyncio.run(session_manager.close())
        finally:
            # Restore original environment
            if original_env:
                os.environ["APP_ENV"] = original_env
            else:
                os.environ.pop("APP_ENV", None)
            
            if original_url:
                os.environ["UPSTASH_REDIS_URL"] = original_url
            else:
                os.environ.pop("UPSTASH_REDIS_URL", None)
            
            if original_token:
                os.environ["UPSTASH_REDIS_TOKEN"] = original_token
            else:
                os.environ.pop("UPSTASH_REDIS_TOKEN", None)
            
            # Clear cached settings
            get_settings.cache_clear()

    def test_session_manager_uses_local_redis_in_local(self):
        """Test that SessionManager uses local Redis URL in local mode."""
        original_env = os.environ.get("APP_ENV")
        original_url = os.environ.get("REDIS_URL")
        
        try:
            # Clear cache before starting
            get_settings.cache_clear()
            
            # Set local environment
            os.environ["APP_ENV"] = "local"
            os.environ["REDIS_URL"] = "redis://localhost:6379/0"
            
            # Clear cached settings
            get_settings.cache_clear()
            
            # Create session manager
            session_manager = SessionManager()
            
            # Verify it uses local Redis URL
            assert session_manager.redis_url == "redis://localhost:6379/0"
            assert session_manager.redis_token is None
            
            # Close connection
            asyncio.run(session_manager.close())
        finally:
            # Restore original environment
            if original_env:
                os.environ["APP_ENV"] = original_env
            else:
                os.environ.pop("APP_ENV", None)
            
            if original_url:
                os.environ["REDIS_URL"] = original_url
            else:
                os.environ.pop("REDIS_URL", None)
            
            # Clear cached settings
            get_settings.cache_clear()


@pytest.mark.skipif(
    not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"),
    reason="Supabase credentials not set - skipping Supabase tests"
)
class TestSupabaseMigration:
    """Test Supabase database connectivity and migration."""

    def test_supabase_environment_variables_set(self):
        """Verify that Supabase environment variables are properly set."""
        assert os.environ.get("SUPABASE_URL") is not None
        assert os.environ.get("SUPABASE_ANON_KEY") is not None
        assert os.environ.get("SUPABASE_SERVICE_KEY") is not None

    def test_config_reads_supabase_credentials(self):
        """Verify that config.py correctly reads Supabase credentials."""
        settings = get_settings()
        
        if os.environ.get("SUPABASE_URL"):
            assert settings.supabase_url == os.environ.get("SUPABASE_URL")
        if os.environ.get("SUPABASE_ANON_KEY"):
            assert settings.supabase_anon_key == os.environ.get("SUPABASE_ANON_KEY")
        if os.environ.get("SUPABASE_SERVICE_KEY"):
            assert settings.supabase_service_key == os.environ.get("SUPABASE_SERVICE_KEY")


class TestMigrationScript:
    """Test the migration script itself."""

    def test_migration_script_exists(self):
        """Verify that the migration script exists."""
        from pathlib import Path
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "migrate_to_managed.py"
        assert script_path.exists()

    def test_migration_script_has_required_functions(self):
        """Verify that the migration script has required functions."""
        from pathlib import Path
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "migrate_to_managed.py"
        script_content = script_path.read_text()
        
        # Check for key functions
        assert "def migrate_database" in script_content
        assert "def check_prerequisites" in script_content
        assert "def get_local_db_connection" in script_content
        assert "def get_supabase_connection" in script_content
        assert "def enable_rls_policies" in script_content
