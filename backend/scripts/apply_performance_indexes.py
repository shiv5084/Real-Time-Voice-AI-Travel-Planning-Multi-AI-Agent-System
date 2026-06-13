"""Apply database performance indexes migration."""

import asyncio
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.database import get_pool, close_pool


async def apply_migration():
    """Apply the performance indexes migration."""
    print("Applying performance indexes migration...")
    
    try:
        pool = await get_pool()
        
        # Read migration SQL
        migration_path = Path(__file__).parent.parent / "migrations" / "add_performance_indexes.sql"
        with open(migration_path, "r") as f:
            migration_sql = f.read()
        
        # Execute migration
        async with pool.acquire() as conn:
            await conn.execute(migration_sql)
        
        print("Performance indexes created successfully")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        raise
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(apply_migration())
