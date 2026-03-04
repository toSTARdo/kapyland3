from utils.helpers import calculate_reincarnation_benefit
from database.crud_capybaras import get_full_profile

async def handle_death(user_id: int, db_pool, death_reason: str = "Невідома причина"):
    data = await get_full_profile(db_pool, user_id)
    if not data:
        return

    benefit = calculate_reincarnation_benefit(data)
    
    final_stats = {
        "atk": data['atk'], 
        "def": data['def'], 
        "agi": data['agi'], 
        "luck": data['luck'],
        "mult": data['reincarnation_multiplier']
    }

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                INSERT INTO graveyard (
                    owner_id, name, final_lvl, final_stats, 
                    death_reason, ghost_inventory, born_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, 
            user_id, data['name'], data['lvl'], json.dumps(final_stats),
            death_reason, data['inventory'], data.get('last_feed') 
            )

            await conn.execute("""
                UPDATE users 
                SET reincarnation_multiplier = $1,
                    reincarnation_count = reincarnation_count + 1
                WHERE tg_id = $2
            """, benefit['new_mult'], user_id)

            await conn.execute("""
                UPDATE capybaras SET
                    exp = 0, lvl = 1, hp = 3, atk = 1, def = 0, agi = 1, luck = 0,
                    stamina = 100, hunger = 3, weight = 20.0, cleanness = 3,
                    wins = 0, losses = 0, total_fights = 0, zen = 0,
                    navigation = '{"x": 77, "y": 144, "discovered": [], "trees": {}, "flowers": {}}'::jsonb,
                    inventory = '{"food": {}, "materials": {}, "loot": {}, "potions": {}, "maps": {}}'::jsonb,
                    equipment = '{"weapon": {"name": "Лапки", "lvl": 0}, "armor": "Хутро", "artifact": null}'::jsonb,
                    state = '{"status": "active", "mode": "capy", "mood": "Chill", "location": "home"}'::jsonb
                WHERE owner_id = $1
            """, user_id)

    return benefit