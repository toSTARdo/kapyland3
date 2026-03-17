import math
from datetime import datetime
import json
from typing import Optional

def calculate_lvl_data(current_exp, added_exp):
    new_exp = current_exp + added_exp
    new_lvl = max(1, int(math.sqrt(new_exp / 2)))
    return new_exp, new_lvl

def next_lvl_exp(current_lvl):
    return 2*((current_lvl+1)**2)

def get_circle_bar(current, total, length=10):
    if total <= 0: return "<code>○○○○○○○○○○</code>"
        
    filled = int(length * current / total)
    filled = max(0, min(length, filled)) # Захист від помилок
        
    # Використовуємо ● для заповненого і ○ для порожнього
    bar = "●" * filled + "○" * (length - filled)
    return f"<code>{bar}</code>"

def calculate_winrate(wins, total_fights):
    return round(wins/total_fights, 1) * 100

def format_weight(weight: float) -> float:
    return round(weight * 2) / 2

def format_time(seconds):
    if isinstance(seconds, (int, float)):
        total_sec = seconds
    else:
        total_sec = seconds.total_seconds()
        
    hours, remainder = divmod(total_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02} год {int(minutes):02} хв"

def check_daily_limit(cools_dict, action_key):
    if not isinstance(cools_dict, dict):
        cools_dict = {}
        
    today = datetime.now().strftime("%Y-%m-%d")
    
    if cools_dict.get(action_key) == today:
        return False, cools_dict
    
    cools_dict[action_key] = today
    return True, cools_dict

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
            SELECT exp, lvl, zen, weight, stamina, max_stamina,inventory 
            FROM capybaras 
            WHERE owner_id = $1
        ''', tg_id)
        
        if not row:
            return None

        old_lvl = row['lvl'] or 1
        current_exp = row['exp'] or 0
        current_zen = row['zen'] or 0
        current_weight = row['weight'] or 20.0
        current_stamina = row['stamina'] if row['stamina'] is not None else 100
        MAX_STAMINA = row["max_stamina"]

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
            new_stamina = MAX_STAMINA
            
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

class Paginator:
    def __init__(self, items, page=0, per_page=5, callback_base="page"):
        self.items = items if isinstance(items, list) else list(items.items())
        self.page = page
        self.per_page = per_page
        self.callback_base = callback_base
        self.total_pages = (len(self.items) - 1) // per_page + 1

    def get_page_items(self):
        start = self.page * self.per_page
        return self.items[start : start + self.per_page]

    def add_navigation(self, builder):
        if self.total_pages <= 1:
            return
        
        nav_row = []
        if self.page > 0:
            nav_row.append(types.InlineKeyboardButton(
                text="⬅️", callback_data=f"{self.callback_base}:{self.page - 1}"))
        else:
            nav_row.append(types.InlineKeyboardButton(text=" ", callback_data="none"))

        nav_row.append(types.InlineKeyboardButton(
            text=f"{self.page + 1}/{self.total_pages}", callback_data="none"))

        if self.page < self.total_pages - 1:
            nav_row.append(types.InlineKeyboardButton(
                text="➡️", callback_data=f"{self.callback_base}:{self.page + 1}"))
        else:
            nav_row.append(types.InlineKeyboardButton(text=" ", callback_data="none"))

        builder.row(*nav_row)

def calculate_reincarnation_benefit(profile: dict):
    current_lvl = profile.get('lvl', 1)
    current_mult = profile.get('reincarnation_multiplier', 1.0)
    
    if current_lvl < 10:
        bonus = 0.0
        can_reincarnate = False
    else:
        bonus = round(current_lvl / 100, 2)
        can_reincarnate = True
    
    new_mult = round(current_mult + bonus, 2)
    
    return {
        "can_reincarnate": can_reincarnate,
        "bonus": bonus,
        "new_mult": new_mult,
        "required_lvl": 10
    }

def int_to_roman(n: int) -> str:
    if n <= 1: return ""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syb = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    roman_num = ""
    i = 0
    while n > 0:
        for _ in range(n // val[i]):
            roman_num += syb[i]
            n -= val[i]
        i += 1
    return f" {roman_num}"

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu_chunk(builder: InlineKeyboardBuilder, page: int = 0, callback_prefix: str = "open_main_menu"):
    all_btns = [
        ("🐾", "open_profile_main"), ("🎒", "inv_page:food:0"), ("🎟️", "lottery_menu"),
        ("🗺️", "open_map"), ("🎣", "fish"), ("📜", "start_story_main"),
        ("🍻", "social"), ("⛵", "ship_main"), ("🎪", "open_bazaar"),
        ("🔨", "open_forge"), ("⚗️", "open_alchemy"), ("⚙️", "open_settings")
    ]
    
    per_chunk = 6
    chunks = [all_btns[i:i + per_chunk] for i in range(0, len(all_btns), per_chunk)]
    page = page % len(chunks)
    
    nav_row = []
    # Стрілка вліво
    nav_row.append(types.InlineKeyboardButton(text="❮", callback_data=f"{callback_prefix}:p{(page-1)%len(chunks)}"))
    
    for icon, cb in chunks[page]:
        # ВАЖЛИВО: Додаємо стан сторінки до кожного колбеку
        # Якщо в кнопці вже є ':', додаємо через ':', якщо ні — створюємо структуру
        state_cb = f"{cb}:p{page}" if ":" in cb else f"{cb}:p{page}"
        
        # Спеціальна обробка для складних інвентарних посилань (якщо треба)
        if "inv_page" in cb:
            # Наприклад: inv_page:food:0 перетвориться на inv_page:food:0:p1
            state_cb = f"{cb}:p{page}"

        nav_row.append(types.InlineKeyboardButton(text=icon, callback_data=state_cb))
    
    # Стрілка вправо
    nav_row.append(types.InlineKeyboardButton(text="❯", callback_data=f"{callback_prefix}:p{(page+1)%len(chunks)}"))
    
    builder.row(*nav_row)