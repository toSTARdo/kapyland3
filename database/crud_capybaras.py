import logging

logger = logging.getLogger(__name__)

GET_FULL_PROFILE_SQL = """
SELECT 
    u.tg_id, u.username, u.reincarnation_multiplier,
    c.name, c.lvl, c.exp, c.hp, c.atk, c.def, c.agi, c.luck, 
    c.stamina, c.hunger, c.weight, c.cleanness, c.state, c.equipment,
    c.wins, c.losses, c.total_fights,
    s.name as ship_name, s.lvl as ship_lvl, s.gold
FROM users u
JOIN capybaras c ON u.tg_id = c.owner_id
LEFT JOIN ships s ON u.tg_id = s.captain_id
WHERE u.tg_id = $1;
"""

async def get_full_profile(db_pool, user_id: int):
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(GET_FULL_PROFILE_SQL, user_id)
            return row
    except Exception as e:
        logger.error(f"❌ Database error in get_full_profile for {user_id}: {e}")
        return None

async def update_capy_stats(db_pool, user_id: int, updates: dict):
    if not updates:
        return
        
    cols = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(updates.keys())])
    values = list(updates.values())
    
    sql = f"UPDATE capybaras SET {cols} WHERE owner_id = $1"
    
    async with db_pool.acquire() as conn:
        await conn.execute(sql, user_id, *values)