import logging
import json

logger = logging.getLogger(__name__)

GET_FULL_PROFILE_SQL = """
SELECT 
    u.tg_id, u.username, u.reincarnation_multiplier,
    c.name, c.lvl, c.exp, c.hp, c.atk, c.def, c.agi, c.luck, 
    c.stamina, c.hunger, c.weight, c.cleanness, c.state, c.equipment,
    c.inventory, c.location, c.zen,
    c.wins, c.losses, c.total_fights,
    s.id as ship_id, s.name as ship_name, s.lvl as ship_lvl, s.gold as ship_gold,
    s.stats as ship_stats, s.meta as ship_meta
FROM users u
JOIN capybaras c ON u.tg_id = c.owner_id
LEFT JOIN ships s ON c.ship_id = s.id
WHERE u.tg_id = $1;
"""

async def get_full_profile(db_pool, user_id: int):
    if not db_pool:
        return None
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(GET_FULL_PROFILE_SQL, user_id)
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"❌ Database error in get_full_profile for {user_id}: {e}")
        return None

async def update_capy_stats(db_pool, user_id: int, updates: dict):
    if not updates or not db_pool:
        return
        
    cols = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(updates.keys())])
    values = list(updates.values())
    
    sql = f"UPDATE capybaras SET {cols} WHERE owner_id = $1"
    
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(sql, user_id, *values)
    except Exception as e:
        logger.error(f"❌ Database error in update_capy_stats for {user_id}: {e}")