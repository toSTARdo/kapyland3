import math
from datetime import datetime
import json
from typing import Optional

def calculate_lvl_data(current_exp, added_exp):
    new_exp = current_exp + added_exp
    new_lvl = max(1, int(math.sqrt(new_exp / 2)))
    return new_exp, new_lvl

def calculate_winrate(wins, total_fights):
    return round(wins/total_fights, 1) * 100

def format_time(seconds):
    if isinstance(seconds, (int, float)):
        total_sec = seconds
    else:
        total_sec = seconds.total_seconds()
        
    hours, remainder = divmod(total_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02} год {int(minutes):02} хв"

def check_daily_limit(meta, action_key):
    today = datetime.now().strftime("%Y-%m-%d")
    last_action_date = meta.get("cooldowns", {}).get(action_key)
    
    if last_action_date == today:
        return False, today
    
    if "cooldowns" not in meta:
        meta["cooldowns"] = {}
    meta["cooldowns"][action_key] = today
    return True, today

async def consume_stamina(conn, uid: int, activity: str) -> bool:
    from config import STAMINA_COSTS, STAT_WEIGHTS
    
    base_amount = STAMINA_COSTS.get(activity, 10)
    
    row = await conn.fetchrow("""
        SELECT meta FROM capybaras WHERE owner_id = $1
    """, uid)
    
    if not row: return False
    
    meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
    
    stats = meta.get("stats", {})
    endurance = stats.get("endurance", 1)

    end_bonus = endurance * STAT_WEIGHTS.get("end_to_energy", 0.05)
    multiplier = max(0.3, 1.0 - end_bonus)
        
    final_amount = max(1, int(base_amount * multiplier))

    sql = """
        UPDATE capybaras 
        SET meta = jsonb_set(
            meta, 
            '{stamina}', 
            (GREATEST((meta->>'stamina')::int - $2, 0))::text::jsonb
        )
        WHERE owner_id = $1 AND (meta->>'stamina')::int >= $2
        RETURNING (meta->>'stamina')::int;
    """
    
    result = await conn.fetchval(sql, uid, final_amount)
    return result is not None