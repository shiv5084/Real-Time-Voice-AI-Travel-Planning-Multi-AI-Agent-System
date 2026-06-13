"""Database seed script for local development.

This script seeds the local PostgreSQL database with test users and sample trips.
Run this after running the database schema migration.
"""

import asyncio
import psycopg
from datetime import datetime, timedelta
from psycopg.types.json import Jsonb
from uuid import uuid4  # kept for chat_messages inserts

from app.config import get_settings

settings = get_settings()


async def seed_database():
    """Seed the database with test data."""
    conn = await psycopg.AsyncConnection.connect(settings.database_url)

    try:
        # Insert test users — upsert and read back the actual persisted IDs
        print("Seeding users...")

        cur = await conn.execute(
            """
            INSERT INTO users (id, email, password_hash, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id
            """,
            (
                "test@example.com",
                "hashed_password_1",
                datetime.utcnow(),
            ),
        )
        row = await cur.fetchone()
        user1_id = row[0]

        cur = await conn.execute(
            """
            INSERT INTO users (id, email, password_hash, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id
            """,
            (
                "jane@example.com",
                "hashed_password_2",
                datetime.utcnow(),
            ),
        )
        row = await cur.fetchone()
        user2_id = row[0]

        # Insert test profiles — upsert and read back the actual persisted IDs
        print("Seeding profiles...")

        cur = await conn.execute(
            """
            INSERT INTO profiles (id, user_id, email, display_name, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING id
            """,
            (
                user1_id,
                "test@example.com",
                "Test User",
                datetime.utcnow(),
                datetime.utcnow(),
            ),
        )
        row = await cur.fetchone()
        profile1_id = row[0]

        cur = await conn.execute(
            """
            INSERT INTO profiles (id, user_id, email, display_name, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING id
            """,
            (
                user2_id,
                "jane@example.com",
                "Jane Doe",
                datetime.utcnow(),
                datetime.utcnow(),
            ),
        )
        row = await cur.fetchone()
        profile2_id = row[0]

        # Insert test trips
        print("Seeding trips...")
        trip1_id = uuid4()
        trip2_id = uuid4()

        await conn.execute(
            """
            INSERT INTO trips (id, user_id, title, raw_request, constraints, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                trip1_id,
                profile1_id,
                "Paris Weekend Trip",
                "I want to visit Paris for a weekend trip with my partner",
                Jsonb(
                    {
                        "destinations": ["Paris"],
                        "budget": 2000,
                        "budget_currency": "USD",
                        "travelers": 2,
                        "start_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),
                        "end_date": (datetime.utcnow() + timedelta(days=32)).isoformat(),
                    }
                ),
                "planning",
                datetime.utcnow(),
                datetime.utcnow(),
            ),
        )

        await conn.execute(
            """
            INSERT INTO trips (id, user_id, title, raw_request, constraints, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                trip2_id,
                profile2_id,
                "Tokyo Adventure",
                "Planning a 5-day trip to Tokyo, interested in food and culture",
                Jsonb(
                    {
                        "destinations": ["Tokyo"],
                        "budget": 3000,
                        "budget_currency": "USD",
                        "travelers": 1,
                        "start_date": (datetime.utcnow() + timedelta(days=60)).isoformat(),
                        "end_date": (datetime.utcnow() + timedelta(days=65)).isoformat(),
                    }
                ),
                "planning",
                datetime.utcnow(),
                datetime.utcnow(),
            ),
           
        )

        # Insert sample chat messages
        print("Seeding chat messages...")
        await conn.execute(
            """
            INSERT INTO chat_messages (id, trip_id, role, content, metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                trip1_id,
                "user",
                "I want to visit Paris for a weekend trip with my partner",
                None,
                datetime.utcnow(),
            ),
            
        )

        await conn.execute(
            """
            INSERT INTO chat_messages (id, trip_id, role, content, metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                trip1_id,
                "assistant",
                "Great choice! I'll help you plan your Paris weekend trip. What's your budget?",
                None,
                datetime.utcnow(),
            ),
           
        )

        print("Database seeded successfully!")
        print(f"Created 2 test users:")
        print(f"  - test@example.com (ID: {user1_id})")
        print(f"  - jane@example.com (ID: {user2_id})")
        print(f"Created 2 test profiles:")
        print(f"  - Test User (ID: {profile1_id})")
        print(f"  - Jane Doe (ID: {profile2_id})")
        print(f"Created 2 test trips:")
        print(f"  - Paris Weekend Trip (ID: {trip1_id})")
        print(f"  - Tokyo Adventure (ID: {trip2_id})")

        await conn.commit()

    except Exception as e:
        print(f"Error seeding database: {e}")
        await conn.rollback()
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed_database())
