#!/usr/bin/env python3
"""
Migration script: Local PostgreSQL → Supabase (Phase 7A)

This script exports data from local PostgreSQL and migrates it to Supabase.
It also verifies the migration by comparing row counts and enabling RLS.

Usage:
    python scripts/migrate_to_managed.py

Prerequisites:
    - Local PostgreSQL must be running (docker-compose up postgres)
    - Supabase project must be created with credentials in .env
    - APP_ENV must be set to 'production' or 'staging'
"""

import asyncio
import sys
from pathlib import Path

# Add backend directory to sys.path to allow importing from app.config
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

import psycopg
from app.config import get_settings

settings = get_settings()


def check_prerequisites():
    """Verify that required environment variables are set."""
    missing = []
    
    # For migration, we need both local DATABASE_URL and Supabase credentials
    if not settings.database_url:
        missing.append("DATABASE_URL (for local PostgreSQL export)")
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_service_key:
        missing.append("SUPABASE_SERVICE_KEY")
    if not settings.upstash_redis_url:
        missing.append("UPSTASH_REDIS_URL")
    
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("   Please set these in your .env file")
        print("   Note: For migration, you need both DATABASE_URL (local) and SUPABASE_* (target)")
        sys.exit(1)
    
    print("OK Prerequisites check passed")


def get_local_db_connection():
    """Get connection to local PostgreSQL."""
    if not settings.database_url:
        print("ERROR: DATABASE_URL not set for local database")
        sys.exit(1)
    
    return psycopg.connect(settings.database_url)


def get_supabase_connection():
    """Get connection to Supabase PostgreSQL."""
    # Supabase connection string format: postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
    # The service key is a JWT token, not a database password. We need the actual database password.
    # For now, we'll use a simpler approach: extract project ref and construct connection string
    
    # Extract project ref from SUPABASE_URL
    # Format: https://[project-ref].supabase.co
    project_ref = settings.supabase_url.replace("https://", "").replace(".supabase.co", "")
    
    # Construct connection string using pooler (recommended for migrations)
    # Format: postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
    # We need the database password, which is different from the service key
    
    # For migration, we should ask user to provide SUPABASE_DB_PASSWORD or use connection string directly
    if not hasattr(settings, 'supabase_db_password') or not settings.supabase_db_password:
        print("ERROR: SUPABASE_DB_PASSWORD not set")
        print("   Please add SUPABASE_DB_PASSWORD to your .env file")
        print("   Get it from: https://app.supabase.com/project/[your-project]/settings/database")
        sys.exit(1)
    
    # URL-encode the password to handle special characters
    from urllib.parse import quote
    password_encoded = quote(settings.supabase_db_password, safe='')
    
    # Try direct database connection (port 5432)
    # Format: postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
    supabase_db_url = f"postgresql://postgres:{password_encoded}@db.{project_ref}.supabase.co:5432/postgres"
    
    return psycopg.connect(supabase_db_url)


def export_table_data(conn, table_name):
    """Export all data from a table."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table_name}")
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        return columns, rows


def import_table_data(conn, table_name, columns, rows):
    """Import data into a table."""
    if not rows:
        print(f"     No data to import for {table_name}")
        return 0
    
    with conn.cursor() as cur:
        placeholders = ", ".join(["%s"] * len(columns))
        column_names = ", ".join(columns)
        query = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        
        cur.executemany(query, rows)
        conn.commit()
        return cur.rowcount


def get_row_count(conn, table_name):
    """Get row count for a table."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cur.fetchone()[0]


def enable_rls_policies(conn):
    """Enable Row Level Security on Supabase tables."""
    tables = [
        "users",
        "profiles",
        "trips",
        "itineraries",
        "episodic_memory",
        "chat_messages",
        "audit_log",
    ]
    
    print("\nEnabling Row Level Security (RLS)...")
    
    with conn.cursor() as cur:
        for table in tables:
            try:
                cur.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                print(f"   OK RLS enabled for {table}")
            except Exception as e:
                print(f"   WARNING Could not enable RLS for {table}: {e}")
        
        conn.commit()


def migrate_database():
    """Main migration function."""
    print("Starting migration from local PostgreSQL to Supabase...")
    print(f"   Local DB: {settings.database_url}")
    print(f"   Supabase: {settings.supabase_url}")
    
    # Connect to both databases
    print("\nConnecting to databases...")
    try:
        local_conn = get_local_db_connection()
        print("   OK Connected to local PostgreSQL")
    except Exception as e:
        print(f"   ERROR Failed to connect to local PostgreSQL: {e}")
        sys.exit(1)
    
    try:
        supabase_conn = get_supabase_connection()
        print("   OK Connected to Supabase")
    except Exception as e:
        print(f"   ERROR Failed to connect to Supabase: {e}")
        print("   Note: Make sure your SUPABASE_URL and SUPABASE_SERVICE_KEY are correct")
        sys.exit(1)
    
    # Tables to migrate (matching 001_initial_schema.sql)
    tables = [
        "users",
        "profiles",
        "trips",
        "itineraries",
        "episodic_memory",
        "chat_messages",
        "audit_log",
    ]
    
    print("\nMigrating data...")
    migration_results = {}
    
    for table in tables:
        print(f"\n   Processing {table}...")
        
        # Export from local
        try:
            columns, rows = export_table_data(local_conn, table)
            local_count = len(rows)
            print(f"      Exported {local_count} rows from local")
        except Exception as e:
            print(f"      WARNING Could not export {table}: {e}")
            continue
        
        # Import to Supabase
        try:
            imported_count = import_table_data(supabase_conn, table, columns, rows)
            print(f"      Imported {imported_count} rows to Supabase")
            migration_results[table] = {"local": local_count, "imported": imported_count}
        except Exception as e:
            print(f"      ERROR Failed to import {table}: {e}")
            migration_results[table] = {"local": local_count, "imported": 0, "error": str(e)}
    
    # Verify migration
    print("\nVerifying migration...")
    all_verified = True

    for table, result in migration_results.items():
        if "error" in result:
            print(f"   ERROR {table}: Migration failed")
            all_verified = False
            continue

        try:
            supabase_count = get_row_count(supabase_conn, table)
            local_count = result["local"]

            if supabase_count >= local_count:
                print(f"   OK {table}: {local_count} -> {supabase_count} rows")
            else:
                print(f"   WARNING {table}: {local_count} -> {supabase_count} rows (mismatch)")
                all_verified = False
        except Exception as e:
            print(f"   WARNING {table}: Could not verify: {e}")
    
    # Enable RLS
    enable_rls_policies(supabase_conn)
    
    # Close connections
    local_conn.close()
    supabase_conn.close()
    
    print("\n" + "="*60)
    if all_verified:
        print("OK Migration completed successfully!")
        print("\nNext steps:")
        print("1. Set APP_ENV=production in your .env file")
        print("2. Restart your application")
        print("3. Run: python scripts/run_phase7A.py to verify the migration")
    else:
        print("WARNING Migration completed with some issues")
        print("   Please review the output above and fix any errors")
    
    print("="*60)


def test_upstash_connection():
    """Test connection to Upstash Redis."""
    print("\nTesting Upstash Redis connection...")

    # Fix Upstash URL format if needed
    redis_url = settings.upstash_redis_url
    if redis_url and not redis_url.startswith(("redis://", "rediss://")):
        # Auto-fix: Add rediss:// scheme if missing
        if redis_url.startswith("https://"):
            redis_url = redis_url.replace("https://", "rediss://")
        elif redis_url.startswith("http://"):
            redis_url = redis_url.replace("http://", "redis://")
        else:
            redis_url = f"rediss://{redis_url}"
        print(f"   INFO Auto-fixed Upstash URL format: {redis_url}")

    try:
        import redis.asyncio as aioredis

        async def test_redis():
            redis_kwargs = {
                "encoding": "utf-8",
                "decode_responses": True,
            }

            if settings.upstash_redis_token:
                redis_kwargs["password"] = settings.upstash_redis_token

            client = aioredis.from_url(redis_url, **redis_kwargs)
            await client.ping()
            await client.set("migration_test", "success", ex=60)
            value = await client.get("migration_test")
            await client.close()

            return value == "success"

        result = asyncio.run(test_redis())

        if result:
            print("   OK Upstash Redis connection successful")
            print("   OK Read/write test passed")
        else:
            print("   ERROR Upstash Redis read/write test failed")
            return False
    except Exception as e:
        print(f"   ERROR Upstash Redis connection failed: {e}")
        return False

    return True


def main():
    """Main entry point."""
    print("="*60)
    print("Phase 7A: Managed Services Migration")
    print("="*60)
    
    check_prerequisites()
    
    # Test Upstash connection first
    if not test_upstash_connection():
        print("\nWARNING Upstash Redis test failed, but continuing with database migration...")
    
    # Migrate database
    migrate_database()
    
    print("\nOK Migration script completed")


if __name__ == "__main__":
    main()
