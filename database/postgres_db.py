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

async def init_pg(pool):
    async with pool.acquire() as conn:
        logger.info("🛠️ Starting database schema initialization...")

        # USERS TABLE
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                tg_id BIGINT PRIMARY KEY,
                username TEXT,
                lang TEXT DEFAULT 'ua',
                has_finished_prologue BOOLEAN DEFAULT FALSE,
                reincarnation_count INTEGER DEFAULT 0,
                reincarnation_multiplier FLOAT DEFAULT 1.0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                kb_layout INTEGER DEFAULT 0
            )
        ''')

        # SHIPS TABLE
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS ships (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                captain_id BIGINT REFERENCES users(tg_id),
                lvl INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                gold BIGINT DEFAULT 0,
                engine JSONB DEFAULT NULL,
                meta JSONB DEFAULT '{"flag": "🏴‍☠️"}'::jsonb,
                stats JSONB DEFAULT '{"hull": 100, "cannons": 2, "speed": 10}'::jsonb,
                cargo JSONB DEFAULT '{"wood": 0, "iron": 0, "watermelons": 0}'::jsonb,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # CAPYBARAS TABLE
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS capybaras (
                id SERIAL PRIMARY KEY,
                owner_id BIGINT UNIQUE REFERENCES users(tg_id) ON DELETE CASCADE,
                name TEXT NOT NULL DEFAULT 'Безіменна булочка',
                lvl INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                hp INTEGER DEFAULT 3,
                atk INTEGER DEFAULT 1,
                def INTEGER DEFAULT 0,
                agi INTEGER DEFAULT 1,
                luck INTEGER DEFAULT 0,
                stamina INTEGER DEFAULT 100,
                hunger INTEGER DEFAULT 3,
                weight FLOAT DEFAULT 20.0,
                cleanness INTEGER DEFAULT 3,
                navigation JSONB DEFAULT '{"x": 2, "y": 1, "discovered": [], "trees": {}, "flowers": {}}'::jsonb,
                inventory JSONB DEFAULT '{"food": {}, "materials": {}, "loot": {}, "potions": {}, "maps": {}}'::jsonb,
                equipment JSONB DEFAULT '{"weapon": {"name": "Лапки", "lvl": 0}, "armor": "Хутро", "artifact": null}'::jsonb,
                achievements TEXT[] DEFAULT '{}',
                unlocked_titles TEXT[] DEFAULT '{ "Новачок" }',
                stats_track JSONB DEFAULT '{}'::jsonb,
                fishing_stats JSONB DEFAULT '{"max_weight": 0, "total_weight": 0}'::jsonb,
                state JSONB DEFAULT '{"status": "active", "mode": "capy", "mood": "Normal"}'::jsonb,
                cooldowns JSONB DEFAULT '{}'::jsonb,
                last_feed TIMESTAMP,
                last_wash TIMESTAMP
            )
        ''')

        # WORLD STATE
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS world_state (
                key TEXT PRIMARY KEY,
                value JSONB DEFAULT '{}'::jsonb,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await conn.execute('''
            INSERT INTO world_state (key, value) 
            VALUES ('environment', '{"weather": "clear", "time_of_day": "zenith", "cycle_count": 1, "is_eclipse": false}')
            ON CONFLICT (key) DO NOTHING
        ''')

        # GRAVEYARD
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS graveyard (
                id SERIAL PRIMARY KEY,
                owner_id BIGINT REFERENCES users(tg_id) ON DELETE CASCADE,
                name TEXT,
                final_lvl INTEGER,
                final_stats JSONB,
                death_reason TEXT,
                born_at TIMESTAMP,
                died_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        logger.info("✅ Database schema is ready. Capybaras can now spawn.")