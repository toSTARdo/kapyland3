import json
import random
import re
import logging
from utils.helpers import calculate_reincarnation_benefit, int_to_roman
from database.crud_capybaras import get_full_profile 

logger = logging.getLogger(__name__)

def clamp(n, min_n=0, max_n=149):
    return max(min_n, min(n, max_n))

async def handle_death(user_id: int, db_pool, death_reason: str = "Невідома причина"):
    data = await get_full_profile(db_pool, user_id)
    
    if not data:
        logger.error(f"Спроба обробити смерть для неіснуючого юзера: {user_id}")
        return None

    benefit = calculate_reincarnation_benefit(data)
    new_multiplier = benefit['new_mult']
    new_reinc_count = (data.get('reincarnation_count', 0) or 0) + 1
    
    base_name = re.sub(r'\s+[IVXLCDM]+\s*$', '', data['name'])
    new_fullname = f"{base_name}{int_to_roman(new_reinc_count)}"

    nav = data.get('navigation', {})
    if isinstance(nav, str): nav = json.loads(nav)
    
    real_x = nav.get('x', 77)
    real_y = nav.get('y', 144)
    
    approx_x = clamp(real_x + random.randint(-10, 10))
    approx_y = clamp(real_y + random.randint(-10, 10))
    
    final_stats = {
        "atk": data['atk'], "def": data['def'], 
        "agi": data['agi'], "luck": data['luck'],
        "lvl": data['lvl']
    }

    starting_inventory = {
        "food": {}, "materials": {},
        "loot": {
            "lottery_ticket": 5,
            "chest": 1,
            "key": 1,
            "treasure_maps": [{
                "id": new_reinc_count,
                "owner_id": user_id,
                "pos": f"{approx_x},{approx_y}",
                "type": "tomb",
                "description": f"Місце спочинку {data['name']}. Кажуть, там бачили привидів...",
                "is_beaten": False
            }]
        },
        "potions": {}, "maps": {}
    }

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO graveyard (
                        owner_id, name, final_lvl, final_stats, 
                        death_reason, ghost_inventory, born_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, 
                user_id, data['name'], data['lvl'], json.dumps(final_stats),
                death_reason, json.dumps(data['inventory']), data.get('last_feed'))

                await conn.execute("""
                    UPDATE users 
                    SET reincarnation_multiplier = $1,
                        reincarnation_count = $2
                    WHERE tg_id = $3
                """, new_multiplier, new_reinc_count, user_id)

                await conn.execute("""
                    UPDATE capybaras SET
                        name = $2,
                        exp = 0, lvl = 1, hp = 3, atk = 1, def = 0, agi = 1, luck = 0,
                        stamina = 100, hunger = 3, weight = 20.0, cleanness = 3,
                        wins = 0, losses = 0, total_fights = 0, zen = 0,
                        navigation = '{"x": 77, "y": 144, "discovered": [], "trees": {}, "flowers": {}}'::jsonb,
                        inventory = $3,
                        equipment = '{"weapon": {"name": "Лапки", "lvl": 0}, "armor": "Хутро", "artifact": null}'::jsonb,
                        state = '{"status": "active", "mode": "capy", "mood": "Chill", "location": "home"}'::jsonb,
                        last_feed = CURRENT_TIMESTAMP,
                        last_wash = CURRENT_TIMESTAMP
                    WHERE owner_id = $1
                """, user_id, new_fullname, json.dumps(starting_inventory, ensure_ascii=False))

        logger.info(f"💀 Реінкарнація успішна для {user_id}: {data['name']} -> {new_fullname}")
        
        benefit['new_name'] = new_fullname
        benefit['approx_pos'] = (approx_x, approx_y)
        return benefit

    except Exception as e:
        logger.error(f"❌ Помилка в handle_death: {e}")
        return None