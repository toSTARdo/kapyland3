import asyncpg
import logging
from config import DB_URL
logger = logging.getLogger(__name__)

async def create_pool():
    try:
        pool = await asyncpg.create_pool(
            dsn=DB_URL,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        logger.info("✅ Postgres Connection Pool established.")
        return pool
    except Exception as e:
        logger.error(f"❌ Failed to create Postgres pool: {e}")
        raise e

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                tg_id BIGINT PRIMARY KEY,
                username TEXT,
                has_finished_prologue BOOLEAN DEFAULT FALSE,
                kb_layout INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        logger.info("🛠️ Database tables verified/created.")