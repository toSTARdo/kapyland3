import asyncio
import json
import random
import datetime
from uuid import uuid4

from aiogram import Router, types, html, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import RARITY_META, ARTIFACTS, LOTTERY_BANNERS, load_game_data
from utils.helpers import ensure_dict, get_main_menu_chunk

GACHA_ITEMS = ARTIFACTS
router = Router()

def is_eligible_for_lega(last_lega_str: str) -> bool:
    if not last_lega_str:
        return True

    if isinstance(last_lega_str, str):
        try:
            last_lega_str = datetime.datetime.fromisoformat(last_lega_str)
        except:
            return True
            
    return datetime.datetime.now() >= last_lega_str + datetime.timedelta(days=7)

@router.message(F.text.startswith("🎟️"))
@router.callback_query(F.data.startswith("lottery_menu"))
async def cmd_lottery_start(event: types.Message | types.CallbackQuery, db_pool):
    uid = event.from_user.id
    is_callback = isinstance(event, types.CallbackQuery)
    
    # 1. Парсимо індекс банера та сторінку чанка
    banner_idx = 0
    menu_page = 0
    
    if is_callback:
        # Обробка банерів (через підкреслення: lottery_menu_1)
        if "_" in event.data:
            try: banner_idx = int(event.data.rsplit("_", 1)[-1])
            except: banner_idx = 0
        
        # Обробка чанка (через двокрапку: lottery_menu:p1)
        if ":p" in event.data:
            try: menu_page = int(event.data.split(":p")[1])
            except: menu_page = 0

    lottery_img = LOTTERY_BANNERS[banner_idx % len(LOTTERY_BANNERS)]
    
    # 2. Отримуємо дані одним запитом (Inventory + Settings)
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT c.inventory, c.last_weekly_lega, u.quicklinks 
            FROM capybaras c 
            JOIN users u ON c.owner_id = u.tg_id 
            WHERE c.owner_id = $1
        """, uid)
    
    if not row: return

    inventory = (json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']) or {}
    tickets = inventory.get("loot", {}).get("lottery_ticket", 0)
    can_get_lega = is_eligible_for_lega(row.get('last_weekly_lega'))
    show_quicklinks = row['quicklinks'] if row['quicklinks'] is not None else True

    builder = InlineKeyboardBuilder()
    
    # 3. Логіка контенту банера
    if banner_idx == 0:
        label = "LEGENDARY" if can_get_lega else "EPIC"
        text = (
            f"🎰 <b>ГАЗИНО «ФОРТУНА КАПІ»</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Твої квитки: <b>{tickets}</b> 🎟\n"
            f"<i>Гортай банери, щоб побачити акції!</i>"
        )
        builder.row(types.InlineKeyboardButton(text="🏴‍☠️ Крутити (1🎟 / 5кг)", callback_data="gacha_spin"))
        builder.row(types.InlineKeyboardButton(text=f"🔥 10+1 / 100% {label}", callback_data="gacha_guaranteed_10"))
    else:
        text = (
            f"🎰 <b>ГАЗИНО «ФОРТУНА КАПІ»</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🚧 <b>[COMING SOON]</b>\n"
            f"<i>Цей розіграш ще готується кухарями-капібарами.</i>"
        )
        builder.row(types.InlineKeyboardButton(text="⏳ В розробці...", callback_data="none"))

    # 4. Навігація банерів
    prev_idx = (banner_idx - 1) % len(LOTTERY_BANNERS)
    next_idx = (banner_idx + 1) % len(LOTTERY_BANNERS)
    
    builder.row(
        types.InlineKeyboardButton(text="◀️", callback_data=f"lottery_menu_{prev_idx}"),
        types.InlineKeyboardButton(text=f"{banner_idx + 1} / {len(LOTTERY_BANNERS)}", callback_data="none"),
        types.InlineKeyboardButton(text="▶️", callback_data=f"lottery_menu_{next_idx}")
    )
    
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_inventory_main"))

    # 5. Додаємо чанк (зберігаємо поточний банер у префіксі, щоб він не скидався)
    if show_quicklinks:
        # Додаємо поточний банер у префікс, щоб при гортанні чанка банер не перемикався на 0
        get_main_menu_chunk(builder, page=menu_page, callback_prefix=f"lottery_menu_{banner_idx}")

    # 6. Рендеринг
    if is_callback:
        input_media = types.InputMediaPhoto(media=lottery_img, caption=text, parse_mode="HTML")
        try:
            await event.message.edit_media(media=input_media, reply_markup=builder.as_markup())
        except Exception:
            # Якщо медіа не змінилося, оновлюємо тільки кнопки
            await event.message.edit_reply_markup(reply_markup=builder.as_markup())
        await event.answer()
    else:
        await event.answer_photo(photo=lottery_img, caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
        
@router.callback_query(F.data == "gacha_spin")
async def handle_gacha_spin(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, weight FROM capybaras WHERE owner_id = $1", uid)
        inv = ensure_dict(row['inventory'])
        weight = row['weight']
        
        loot = inv.setdefault("loot", {})
        tickets = loot.get("lottery_ticket", 0)
        
        if tickets > 0:
            loot["lottery_ticket"] -= 1
            pay_msg = "🎟 Використано квиток!"
        elif weight >= 5.1:
            weight -= 5.0
            pay_msg = "⚖️ Списано 5 кг ваги!"
        else:
            return await callback.answer("❌ Недостатньо ваги/квитків!", show_alert=True)

        # Roll Item
        rarity = random.choices(["Common", "Rare", "Epic", "Legendary"], weights=[60, 25, 12, 3], k=1)[0]
        item = random.choice(GACHA_ITEMS[rarity])
        safe_name = html.quote(item['name'])
        safe_desc = html.quote(item.get('desc', ''))
        prefix = RARITY_META[rarity]["emoji"]

        eq_dict = inv.setdefault("equipment", {})
        food = inv.setdefault("food", {})
        
        # BETTER ANTI-DUPE: Check if ANY level of this item exists in keys
        # Since keys are "Name_Lvl", we check if any key starts with "Name_"
        has_item = any(v.get('name') == item['name'] for v in eq_dict.values())
        
        reward_msg = ""
        if has_item:
            # Логіка компенсації (скибки кавуна)
            gain = {"Common": 1, "Rare": 2, "Epic": 3, "Legendary": 5}.get(rarity, 1)
            food["watermelon_slices"] = food.get("watermelon_slices", 0) + gain
            
            reward_msg = (
                f"🧩 <b>Повторка!</b>\n"
                f"Предмет <b>{safe_name}</b> вже є у твоєму рюкзаку.\n"
                f"Отримано компенсацію: {gain} 🍉\n\n"
                f"🎟️ Квитків: <b>{loot['lottery_ticket']}</b>"
            )
        else:
            # Створення нового унікального ID
            item_id = str(uuid4())[:8]
            eq_dict[item_id] = {
                "name": item["name"], 
                "type": item["type"], 
                "rarity": rarity, 
                "lvl": 0, 
                "count": 1,
                "desc": item.get("desc", "")
            }
            reward_msg = (
                f"✨ <b>НОВИЙ ПРЕДМЕТ!</b>\n\n"
                f"{prefix} <b>{safe_name}</b>\n\n"
                f"<i>{safe_desc}</i>\n\n"
                f"🎟️ Квитків: <b>{loot['lottery_ticket']}</b>"
            )
            
        await conn.execute(
            "UPDATE capybaras SET inventory = $1, weight = $2 WHERE owner_id = $3",
            json.dumps(inv, ensure_ascii=False), weight, uid
        )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 Ще раз", callback_data="gacha_spin"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="lottery_menu"))
    
    await callback.message.edit_caption(caption=reward_msg, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "gacha_guaranteed_10")
async def handle_bulk_spin(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    now = datetime.datetime.now()
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, last_weekly_lega FROM capybaras WHERE owner_id = $1", uid)
        inv = ensure_dict(row['inventory'])
        
        loot = inv.setdefault("loot", {})
        if loot.get("lottery_ticket", 0) < 10:
            return await callback.answer("❌ Треба 10 квитків!", show_alert=True)
        
        eq_dict = inv.setdefault("equipment", {})
        food = inv.setdefault("food", {})
        
        can_get_lega = is_eligible_for_lega(row.get('last_weekly_lega'))
        results_icons = []
        total_watermelon = 0
        used_weekly_bonus = False

        # Pre-calculate owned names for faster lookup
        owned_names = {v.get('name') for v in eq_dict.values()}

        for i in range(11):
            if i == 10:
                rarity = "Legendary" if can_get_lega else "Epic"
                if can_get_lega: used_weekly_bonus = True
            else:
                r = random.random()
                if r < 0.03: rarity = "Legendary"
                elif r < 0.15: rarity = "Epic"
                elif r < 0.40: rarity = "Rare"
                else: rarity = "Common"

            item = random.choice(GACHA_ITEMS[rarity])
            name = item['name']
            prefix = RARITY_META[rarity]["emoji"]

            if name in owned_names:
                # Компенсація
                gain = {"Common": 1, "Rare": 2, "Epic": 3, "Legendary": 5}.get(rarity, 1)
                total_watermelon += gain
                results_icons.append(f"{prefix} <s>{name}</s> 🍉+{gain}")
            else:
                # Додаємо новий предмет
                item_id = str(uuid4())[:8]
                eq_dict[item_id] = {
                    "name": name, "type": item["type"], 
                    "rarity": rarity, "lvl": 0, "count": 1,
                    "desc": item.get("desc", "")
                }
                owned_names.add(name) # Додаємо в список власності, щоб не вибити два однакових за один пак
                results_icons.append(f"{prefix} <b>{name}</b> ✨")

        food["watermelon_slices"] = food.get("watermelon_slices", 0) + total_watermelon
        loot["lottery_ticket"] -= 10
        
        # SQL Update... (same as before)
        sql = "UPDATE capybaras SET inventory = $1" + (", last_weekly_lega = $2" if used_weekly_bonus else "") + " WHERE owner_id = " + ("$3" if used_weekly_bonus else "$2")
        params = [json.dumps(inv, ensure_ascii=False)]
        if used_weekly_bonus: params.append(now); params.append(uid)
        else: params.append(uid)
        await conn.execute(sql, *params)
        
    text = f"🎰 <b>РЕЗУЛЬТАТИ 10+1</b>\n\n" + "\n".join(results_icons) + f"\n\n🍉 Всього компенсації: <b>{total_watermelon}</b>\n" + f"🎟️ Залишилось квитків: <b>{loot['lottery_ticket']}</b>"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎰 Знову (🎟️x10)", callback_data="gacha_guaranteed_10")
    builder.button(text="🔙 Назад", callback_data="lottery_menu")
    builder.adjust(1)
    await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")