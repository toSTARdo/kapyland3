import json
import asyncio
from uuid import uuid4
from aiogram import types, F, Router
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import load_game_data, DISPLAY_NAMES, IMAGES_URLS, TYPE_ICONS, MYTHIC_ICONS
from utils.helpers import ensure_dict, get_main_menu_chunk

router = Router()

FORGE_RECIPES = load_game_data("data/forge_craft.json")
ITEMS_PER_PAGE = 5

UPGRADE_CONFIG = {
    "max_lvl": 5,
    "prefixes": {
        1: "Загартований",
        2: "Відшліфований",
        3: "Майстерний",
        4: "Шляхетний",
        5: "Вічний"
    }
}

def find_item_in_inventory(inv, item_key):
    for category in ["food", "materials", "plants", "loot"]:
        cat_dict = inv.get(category)
        if isinstance(cat_dict, dict):
            count = cat_dict.get(item_key)
            if count is not None:
                return category, count
    return None, 0

@router.callback_query(F.data.startswith("open_forge"))
async def process_open_forge(callback: types.CallbackQuery, db_pool):
    user_id = callback.from_user.id
    
    # 1. Визначаємо сторінку чанка (меню)
    menu_page = 0
    if ":p" in callback.data:
        menu_page = int(callback.data.split(":p")[1])

    async with db_pool.acquire() as conn:
        # Отримуємо дані капібари та налаштування користувача через JOIN
        res = await conn.fetchrow("""
            SELECT c.lvl, c.inventory, u.quicklinks 
            FROM capybaras c 
            JOIN users u ON c.owner_id = u.tg_id 
            WHERE c.owner_id = $1
        """, user_id)
        
        if not res: return

        # Перевірка рівня
        if res['lvl'] < 10:
            return await callback.answer("🔒 Кузня доступна лише з 10 рівня!", show_alert=True)

        inv = json.loads(res['inventory']) if isinstance(res['inventory'], str) else res['inventory']
        show_quicklinks = res['quicklinks'] if res['quicklinks'] is not None else True

    # 2. Логіка інвентарю
    _, kiwi_count = find_item_in_inventory(inv, "kiwi")

    # 3. Будуємо інтерфейс
    builder = InlineKeyboardBuilder()
    builder.button(text="⚙️ Звичайний крафт", callback_data="common_craft_list")
    builder.button(text="🔨 Покращити спорядження", callback_data="upgrade_menu")
    builder.button(text="⚜️ Міфічний коваль", callback_data="forge_craft_list")
    builder.button(text="⬅️ Назад", callback_data="open_village")
    builder.adjust(1)

    # Додаємо чанк, якщо увімкнено
    if show_quicklinks:
        get_main_menu_chunk(builder, page=menu_page, callback_prefix="open_forge")

    text = (
        "🐦 <b>Кузня ківі</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "Тут пахне сталлю та тропічними фруктами.\n"
        "Твій запас ківі: <b>{kiwi_count} 🥝</b>\n\n"
        "<i>«Гей, пухнастий! Хочеш гостріший ніж чи міцніший панцир?\n Можливості залежать від кількості ківі в твоїх кишенях»</i>"
    ).format(kiwi_count=kiwi_count)

    # 4. Оновлення з обробкою однакових медіа
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(media=IMAGES_URLS["forge"], caption=text, parse_mode="HTML"),
            reply_markup=builder.as_markup()
        )
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    
    await callback.answer()

def get_upgrade_cost(rarity: str, current_lvl: int) -> int:
    base_costs = {
        "common": 1,
        "rare": 2,
        "epic": 3,
        "legendary": 4,
        "mythic": 5
    }
    base = base_costs.get(rarity.lower(), 1)
    return base + current_lvl

def apply_pagination(builder, all_items, page, per_page, callback_prefix, nav_prefix=None):
    if nav_prefix is None:
        nav_prefix = callback_prefix
        
    total_pages = max(1, (len(all_items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    
    start = page * per_page
    end = start + per_page
    items_slice = all_items[start:end]

    for suffix, text in items_slice:
        builder.row(types.InlineKeyboardButton(text=text, callback_data=f"{callback_prefix}:{suffix}"))

    if total_pages > 1:
        nav = []
        # Left
        cb_l = f"{nav_prefix}:{page-1}" if page > 0 else "none"
        nav.append(types.InlineKeyboardButton(text="⬅️" if page > 0 else " ", callback_data=cb_l))
        # Mid
        nav.append(types.InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="none"))
        # Right
        cb_r = f"{nav_prefix}:{page+1}" if page < total_pages - 1 else "none"
        nav.append(types.InlineKeyboardButton(text="➡️" if page < total_pages - 1 else " ", callback_data=cb_r))
        builder.row(*nav)
    
    return page

@router.callback_query(F.data.startswith("upgrade_menu") | F.data.startswith("up_menu_pg:"))
async def upgrade_list(callback: types.CallbackQuery, db_pool):
    page = 0
    if callback.data.startswith("up_menu_pg:"):
        page = int(callback.data.split(":")[1])

    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT lvl, inventory FROM capybaras WHERE owner_id = $1", user_id)
        if not row: return
        
        if row['lvl'] < 15:
            return await callback.answer("❌ Ще не доріс! Повертайся на 15 рівні.", show_alert=True)

        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        equip = inv.get("equipment", {})
        builder = InlineKeyboardBuilder()

        def get_btn_text(item_data):
            if isinstance(item_data, str): return f"💎 {item_data}"
            name = item_data.get("name", "Предмет")
            lvl = item_data.get("lvl", 0)
            rarity = item_data.get("rarity", "common")
            cost = get_upgrade_cost(rarity, lvl)
            icon = TYPE_ICONS.get(item_data.get("type"), "💎")
            stars = "⭐" * lvl if lvl > 0 else ""
            return f"{icon} {name} {stars} (💰 {cost}🥝)"

        items_to_paginate = []
        excluded = ["Лапки", "Хутро", "Нічого"]

        if isinstance(equip, dict):
            for slot, item in equip.items():
                if item and (isinstance(item, str) or item.get("name") not in excluded):
                    items_to_paginate.append((slot, get_btn_text(item)))
        elif isinstance(equip, list):
            for idx, item in enumerate(equip):
                if item and (isinstance(item, str) or item.get("name") not in excluded):
                    items_to_paginate.append((idx, get_btn_text(item)))

        current_p = apply_pagination(
            builder=builder, 
            all_items=items_to_paginate, 
            page=page, 
            per_page=5, 
            callback_prefix="up_item",
            nav_prefix="upgrade_menu"

        )

        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_forge"))

        await callback.message.edit_caption(
            caption=f"🛠️ <b>Загартування спорядження</b>\n\n"
                    f"Сторінка: <b>{page + 1}</b>\n"
                    f"<i>Чим потужніша річ, тим більше 🥝 вона вимагає!</i>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("up_item:"))
async def confirm_upgrade(callback: types.CallbackQuery, db_pool):
    slot_key = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        if not inv_raw: return
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        equip = inv.get("equipment", {})
        
        if isinstance(equip, list):
            try:
                item_data = equip[int(slot_key)]
            except: return await callback.answer("❌ Предмет не знайдено")
        else:
            item_data = equip.get(slot_key)

        if not item_data or item_data in ["Лапки", "Хутро"]: 
            return await callback.answer("❌ Цей предмет неможливо загартувати")

        if isinstance(item_data, str):
            item_data = {"name": item_data, "lvl": 0, "rarity": "common"}

        current_lvl = item_data.get("lvl", 0)
        rarity = item_data.get("rarity", "common")
        
        if current_lvl >= 5:
            return await callback.answer("✨ Предмет досяг ліміту могутності!", show_alert=True)

        needed_kiwi = get_upgrade_cost(rarity, current_lvl)
        
        cat, kiwi_count = find_item_in_inventory(inv, "kiwi")
        if kiwi_count < needed_kiwi:
            return await callback.answer(f"❌ Бракує ківі! Потрібно {needed_kiwi} 🥝", show_alert=True)

        new_lvl = current_lvl + 1
        prefix = UPGRADE_CONFIG["prefixes"].get(new_lvl, "Покращений")
        base_name = item_data.get("base_name", item_data["name"])
        
        item_data.update({
            "lvl": new_lvl,
            "name": f"{base_name}",
            "base_name": base_name
        })
        
        inv[cat]["kiwi"] -= needed_kiwi
        if isinstance(equip, list):
            equip[int(slot_key)] = item_data
        else:
            equip[slot_key] = item_data

        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", 
                           json.dumps(inv, ensure_ascii=False), user_id)
        
        await callback.answer(f"🔥 Успіх! {item_data['name']} загартовано до {new_lvl}⭐")
        await upgrade_list(callback, db_pool)

@router.callback_query(F.data.startswith("common_craft_list"))
async def common_craft_list(callback: types.CallbackQuery, db_pool):
    # 1. Безпечне отримання сторінки
    page = 0
    data_parts = callback.data.split(":")
    
    # Перевіряємо, чи є другий елемент і чи він складається лише з цифр
    if len(data_parts) > 1 and data_parts[1].isdigit():
        page = int(data_parts[1])
    else:
        # Якщо там "handmade_map" або порожньо — залишаємо сторінку 0
        page = 0

    user_id = callback.from_user.id
    builder = InlineKeyboardBuilder()
    
    async with db_pool.acquire() as conn:
        lvl = await conn.fetchval("SELECT lvl FROM capybaras WHERE owner_id = $1", user_id)
        if lvl is not None and lvl < 10:
            return await callback.answer("❌ Навчися зброю тримати! Повертайся на 10 рівні.", show_alert=True)
            
    # 2. Підготовка списку рецептів
    recipes = FORGE_RECIPES.get("common_craft", {})
    items_to_paginate = [
        (r_id, f"{r_data.get('emoji', '📦')} {r_data.get('name')}") 
        for r_id, r_data in recipes.items()
    ]

    # 3. Пагінація
    # Тут важливо, щоб другий аргумент (page) завжди був int, що ми забезпечили вище
    current_p = apply_pagination(
        builder=builder, 
        all_items=items_to_paginate, 
        page=page, 
        per_page=5, 
        callback_prefix="common_info", 
        nav_prefix="common_craft_list"
    )

    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_forge"))

    try:
        await callback.message.edit_caption(
            caption=f"📦 <b>Майстерня:</b>\nТут можна створити корисні дрібниці.\n\nСторінка: <b>{current_p + 1}</b>", 
            reply_markup=builder.as_markup(), 
            parse_mode="HTML"
        )
    except Exception as e:
        # Якщо повідомлення не змінилося (наприклад, та ж сторінка), ігноруємо помилку
        await callback.answer()
        
@router.callback_query(F.data.startswith("common_info:"))
async def show_common_recipe(callback: types.CallbackQuery, db_pool):
    recipe_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        inv = ensure_dict(inv_raw)
        recipe = FORGE_RECIPES.get("common_craft", {}).get(recipe_id)
        
        if not recipe: return await callback.answer("❌ Рецепт не знайдено")

        text = f" {recipe.get('emoji', '📦')} <b>{recipe['name']}</b>\n{recipe['desc']}\n━━━━━━━━━━━━━━━\n\n<b>Необхідно:</b>\n"
        can_craft = True
        
        user_equip_list = inv.get("equipment", [])
        req_equip = recipe.get("ingredients", {}).get("equipment", [])
        
        for item_name in req_equip:
            found = any(item_name in (i.get("name", "") if isinstance(i, dict) else str(i)) for i in user_equip_list)
            status = "✅" if found else "❌"
            text += f"{status} {item_name}\n"
            if not found: can_craft = False

        for mat, count in recipe.get("ingredients", {}).get("materials", {}).items():
            current = inv.get("materials", {}).get(mat, 0)
            status = "✅" if current >= count else "❌"
            text += f"{status} {DISPLAY_NAMES.get(mat, mat)}: {current}/{count}\n"
            if current < count: can_craft = False

        builder = InlineKeyboardBuilder()

        if can_craft:
            builder.button(text="🔨 Скрафтити", callback_data=f"do_common_craft:{recipe_id}")
        builder.button(text="⬅️ Назад", callback_data="common_craft_list")
        builder.adjust(1)
        await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")

# The base "price" of each tier
TIER_PRICES = {
    "Катлас": 2,
    "Вудочка": 1,
    "Посилена вудочка": 3,
    "Металева вудочка": 5
}

@router.callback_query(F.data.startswith("do_common_craft:"))
async def process_common_craft(callback: types.CallbackQuery, db_pool):
    recipe_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        inv = ensure_dict(inv_raw)
        recipe = FORGE_RECIPES.get("common_craft", {}).get(recipe_id)
        if not recipe: return

        can_craft = True
        user_equip = inv.get("equipment", {}) 
        ingredients = recipe.get("ingredients", {})
        
        ids_to_consume = []
        total_kiwi_refund = 0
        temp_equip_pool = user_equip.copy()

        for mat, count in ingredients.get("materials", {}).items():
            if inv.get("materials", {}).get(mat, 0) < count:
                can_craft = False
                break
        
        if can_craft:
            for req_name in ingredients.get("equipment", []):
                found_id = None
                for item_id, item_data in temp_equip_pool.items():
                    if item_data.get("name") == req_name:
                        found_id = item_id
                        
                        item_lvl = item_data.get("lvl", 0)
                        base_name = item_data.get("name", "").lower()
                        base_price = next((p for k, p in TIER_PRICES.items() if k in base_name), 0)
                        total_kiwi_refund += (base_price + item_lvl)
                        break
                
                if found_id:
                    ids_to_consume.append(found_id)
                    del temp_equip_pool[found_id]
                else:
                    can_craft = False
                    break

        if not can_craft:
            return await callback.answer("❌ Недостатньо ресурсів або предметів!", show_alert=True)

        for uid in ids_to_consume:
            del user_equip[uid]

        for mat, count in ingredients.get("materials", {}).items():
            inv["materials"][mat] -= count

        if total_kiwi_refund > 0:
            food = inv.setdefault("food", {})
            food["kiwi"] = food.get("kiwi", 0) + total_kiwi_refund

        item_type = recipe.get("type", "loot") 
        if item_type in ["weapon", "armor", "artifact"]:
            new_uid = str(uuid4())[:8]
            user_equip[new_uid] = {
                "name": recipe["name"],
                "type": item_type,
                "desc": recipe.get("desc", ""),
                "rarity": recipe.get("rarity", "common"),
                "lvl": 0
            }
        else:
            loot = inv.setdefault("loot", {})
            loot[recipe_id] = loot.get(recipe_id, 0) + 1

        inv["equipment"] = user_equip
        
        await conn.execute(
            "UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", 
            json.dumps(inv, ensure_ascii=False), user_id
        )
        
        msg = f"✅ {recipe['name']} виготовлено!"
        if total_kiwi_refund > 0:
            msg += f"\n🥝 Повернено {total_kiwi_refund} ківі за покращення."
            
        await callback.answer(msg, show_alert=True)
        await common_craft_list(callback, db_pool)

@router.callback_query(F.data.startswith("forge_craft_list"))
async def forge_craft_list(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split(":")
    current_page = int(parts[1]) if len(parts) > 1 else 0
    
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        lvl = await conn.fetchval("SELECT lvl FROM capybaras WHERE owner_id = $1", user_id)
        if lvl < 20:
            return await callback.answer("❌ Складна робота! Повертайся на 20 рівні.", show_alert=True)

    # 1. Prepare items list for mythic artifacts
    all_recipes = FORGE_RECIPES.get("mythic_artifacts", {})
    items_to_paginate = []
    for r_id, r_data in all_recipes.items():
        icon = MYTHIC_ICONS.get(r_data.get("class", "✨"), "✨")
        items_to_paginate.append((r_id, f"{icon} {r_data.get('name')}"))

    builder = InlineKeyboardBuilder()

    # 2. Apply paginator
    # Note: I'm using "forge_craft_list" as the callback_prefix for nav buttons 
    # but "mythic_info" for the items themselves.
    total_pages = max(1, (len(items_to_paginate) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    current_page = max(0, min(current_page, total_pages - 1))
    
    apply_pagination(
        builder=builder, 
        all_items=items_to_paginate, 
        page=current_page, 
        per_page=ITEMS_PER_PAGE, 
        callback_prefix="mythic_info",
        nav_prefix="forge_craft_list"
    )

    # Override the default nav buttons generated by apply_pagination to use forge_craft_list prefix
    # Or simply update your apply_pagination to accept a nav_prefix. 
    # Given your current function, we manually fix the row below:
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="open_forge"))

    caption = f"⚒️ <b>Міфічні креслення</b>\nСторінка: <b>{current_page + 1}/{total_pages}</b>"
    
    await callback.message.edit_caption(caption=caption, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("mythic_info:"))
async def show_mythic_recipe(callback: types.CallbackQuery, db_pool):
    mythic_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT inventory, equipment, state, stats_track, karma,
                   lvl, atk, def, agi, luck, zen, stamina, hunger,
                   wins, total_fights
            FROM capybaras WHERE owner_id = $1
        """, user_id) 
        
        if not row: return await callback.answer("❌ Капібару не знайдено")

        def safe_json(data):
            if isinstance(data, str):
                import json
                return json.loads(data)
            return data or {}

        inv = safe_json(row['inventory'])
        equip_worn = safe_json(row['equipment'])
        
        items_in_bag = inv.get("equipment", [])
        
        recipe = FORGE_RECIPES.get("mythic_artifacts", {}).get(mythic_id)
        if not recipe: return await callback.answer("❌ Рецепт не знайдено")

        text = f"✨ <b>{recipe['name']}</b>\n<i>{recipe['desc']}</i>\n━━━━━━━━━━━━━━━\n\n<b>Необхідні артефакти:</b>\n"
        can_craft = True
        
        for ing_name in recipe["ingredients"]:
            in_res = inv.get("materials", {}).get(ing_name, 0) > 0 or inv.get("loot", {}).get(ing_name, 0) > 0
            
            in_bag = any(ing_name == (i.get("name") if isinstance(i, dict) else str(i)) for i in items_in_bag)
            
            in_worn = any(ing_name in str(v) for v in equip_worn.values() if v)
            
            is_present = in_res or in_bag or in_worn
            text += f"{'✅' if is_present else '❌'} {ing_name}\n"
            if not is_present: can_craft = False

        if "requirements" in recipe:
            text += "\n<b>📜 Особливі умови:</b>\n"
            
            sum_stats = (row['atk'] + row['def'] + row['agi'] + row['luck'])
            
            checks = {
                "wins": ("Перемоги", row['wins'], "⚔️"),
                "total_fights": ("Всього боїв", row['total_fights'], "👊"),
                #"clean_chat_days": ("Дні без муту", state.get("clean_days", 0), "😇"),
                "speed_stat": ("Швидкість", row['agi'], "👟"),
                "zen": ("Наявний Дзен", row['zen'], "❇️"),
                "stamina": ("Поточна стаміна", row['stamina'], "⚡️"),
                "hunger": ("Голод (макс)", row['hunger'], "🍏"),
                "level": ("Рівень", row['lvl'], "🆙"),
                "all_stats_sum": ("Здобутий Дзен", sum_stats, "📊"),
                "karma": ("Карма", row["karma"], "⚖️")
            }

            for key, req_val in recipe["requirements"].items():
                if key == "location":
                    curr_loc = state.get("location", "home")
                    text += f"{'✅' if curr_loc == req_val else '⏳'} Локація: {curr_loc}/{req_val}\n"
                    if curr_loc != req_val: can_craft = False
                elif key in checks:
                    label, curr_val, icon = checks[key]
                    pass_chk = curr_val <= req_val if key == "hunger" else curr_val >= req_val
                    text += f"{'✅' if pass_chk else '⏳'} {icon} {label}: {curr_val}/{req_val}\n"
                    if not pass_chk: can_craft = False

        builder = InlineKeyboardBuilder()
        if can_craft: 
            builder.button(text="🔥 КУВАТИ АРТЕФАКТ", callback_data=f"craft_mythic:{mythic_id}")
        builder.button(text="⬅️ Назад", callback_data="forge_craft_list")
        builder.adjust(1)
        
        await callback.message.edit_caption(
            caption=text, 
            reply_markup=builder.as_markup(), 
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("craft_mythic:"))
async def process_mythic_craft(callback: types.CallbackQuery, db_pool):
    mythic_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        recipe = FORGE_RECIPES.get("mythic_artifacts", {}).get(mythic_id)
        
        equip, loot = inv.get("equipment", []), inv.get("loot", {})
        to_rem_loot, to_rem_equip = [], []
        
        for ing_name in recipe["ingredients"]:
            found, target = False, ing_name.strip()
            if loot.get(target, 0) > 0:
                loot[target] -= 1
                if loot[target] <= 0: del loot[target]
                found = True
            if not found:
                for i, item in enumerate(equip):
                    if target in (item.get("name", "") if isinstance(item, dict) else str(item)):
                        to_rem_equip.append(i)
                        found = True
                        break
            if not found: return await callback.answer(f"❌ Не вистачає: {target}", show_alert=True)

        for idx in sorted(to_rem_equip, reverse=True): equip.pop(idx)
        
        mythic_item = {"name": recipe["name"], "type": recipe["type"], "rarity": "Mythic", "desc": recipe["desc"], "stats": recipe["stats"]}
        equip.append(mythic_item)

        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv, ensure_ascii=False), user_id)
        await callback.message.edit_caption(
            caption=f"✨ <b>РИТУАЛ ЗАВЕРШЕНО!</b>\n⚡️ <b>{mythic_item['name']}</b>",
            reply_markup=InlineKeyboardBuilder().button(text="🔥 ЛЕС ГОООУ",
             callback_data="open_forge").as_markup(), parse_mode="HTML")