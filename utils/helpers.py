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

async def grant_exp_and_lvl(tg_id: int, exp_gain: int, weight_gain: float = 0, bot=None, db_pool=None):
    if not db_pool:
        return None

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('''
            SELECT exp, lvl, zen, weight, stamina, inventory 
            FROM capybaras 
            WHERE owner_id = $1
        ''', tg_id)
        
        if not row:
            return None

        old_lvl = row['lvl'] or 1
        current_exp = row['exp'] or 0
        current_zen = row['zen'] or 0
        current_weight = row['weight'] or 20.0
        current_stamina = row['stamina'] or 100
        
        inventory = row['inventory']
        if isinstance(inventory, str):
            inventory = json.loads(inventory)
        inventory = inventory or {}

        new_total_exp, new_lvl = calculate_lvl_data(current_exp, exp_gain)
        
        lvl_diff = new_lvl - old_lvl
        new_zen = current_zen + max(0, lvl_diff)
        new_stamina = current_stamina
        new_weight = round(max(1.0, current_weight + weight_gain), 1)

        if lvl_diff > 0:
            new_stamina = 100
            
            loot = inventory.setdefault("loot", {})
            loot["lottery_ticket"] = loot.get("lottery_ticket", 0) + lvl_diff

        await conn.execute('''
            UPDATE capybaras 
            SET exp = $1, 
                lvl = $2, 
                zen = $3, 
                weight = $4, 
                stamina = $5, 
                inventory = $6
            WHERE owner_id = $7
        ''', 
        new_total_exp, 
        new_lvl, 
        new_zen, 
        new_weight, 
        new_stamina, 
        json.dumps(inventory, ensure_ascii=False), 
        tg_id)

        if lvl_diff > 0 and bot:
            try:
                await bot.send_message(
                    tg_id, 
                    f"🎊 <b>LEVEL UP!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Твоя капібара досягла <b>{new_lvl} рівня</b>!\n\n"
                    f"🎁 <b>Нагороди:</b>\n"
                    f"❇️ Капі-дзен: <b>+{lvl_diff}</b>\n"
                    f"🎟 Квитки: <b>+{lvl_diff} шт.</b>\n"
                    f"⚡ Енергія відновлена до <b>100%</b>\n",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Level up notify error: {e}")

        return {
            "new_lvl": new_lvl,
            "lvl_up": lvl_diff > 0,
            "added_zen": lvl_diff,
            "total_zen": new_zen,
            "new_weight": new_weight
        }

def ensure_dict(data):
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except:
            return {}
    return {}
