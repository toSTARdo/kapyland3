import asyncpg
import logging
import ssl
from config import POSTGRE_URL

POSTGRE_URL = "postgresql://neondb_owner:npg_3GWqKQ0JhFRY@ep-solitary-butterfly-agjuh9dk-pooler.c-2.eu-central-1.aws.neon.tech/neondb"

logger = logging.getLogger(__name__)

async def create_pool():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        pool = await asyncpg.create_pool(
            dsn=POSTGRE_URL,
            ssl=ctx, 
            min_size=1,
            max_size=10,
            command_timeout=60,
            # --- ДОДАЙ ЦІ ДВА РЯДКИ ---
            statement_cache_size=0,         # Вимикає кешування на рівні пулу
            max_cached_statement_lifetime=0 # Забороняє зберігати плани запитів
            # --------------------------
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
                ship_id INTEGER REFERENCES ships(id) ON DELETE SET NULL,
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
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_fights INTEGER DEFAULT 0,
                zen INTEGER DEFAULT 0,
                navigation JSONB DEFAULT '{"x": 77, "y": 144, "discovered": [], "trees": {}, "flowers": {}}'::jsonb,
                inventory JSONB DEFAULT '{"food": {}, "materials": {}, "loot": {}, "potions": {}, "maps": {}}'::jsonb,
                equipment JSONB DEFAULT '{"weapon": {"name": "Лапки", "lvl": 0}, "armor": {"name": "Хутро", "lvl": 0}, "artifact": null}'::jsonb,
                achievements TEXT[] DEFAULT '{}',
                victory_media JSONB DEFAULT '[]'::jsonb,
                unlocked_titles TEXT[] DEFAULT '{ "Новачок" }',
                stats_track JSONB DEFAULT '{}'::jsonb,
                fishing_stats JSONB DEFAULT '{"max_weight": 0, "total_weight": 0}'::jsonb,
                state JSONB DEFAULT '{"status": "active", "mode": "capy", "mood": "Chill", "location": "home", "blessings": [], "curses": []}'::jsonb,
                cooldowns JSONB DEFAULT '{}'::jsonb,
                last_feed TIMESTAMP,
                last_wash TIMESTAMP,
                last_weekly_lega TIMESTAMP
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
                ghost_inventory JSONB,
                death_reason TEXT,
                born_at TIMESTAMP,
                died_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        #ACTIVE CHATS
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS active_chats (
            chat_id BIGINT PRIMARY KEY,
            last_seen TIMESTAMP DEFAULT NOW()
        );
        ''')
        
        logger.info("✅ Database schema is ready. Capybaras can now spawn.")
