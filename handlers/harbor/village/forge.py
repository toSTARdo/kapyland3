import json
import asyncio
from aiogram import types, F, Router
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import load_game_data, DISPLAY_NAMES, IMAGES_URLS
from utils.helpers import ensure_dict

router = Router()

FORGE_RECIPES = load_game_data("data/forge_craft.json")
TYPE_ICONS = {"weapon": "🗡️", "armor": "🔰", "artifact": "🧿"}
MYTHIC_ICONS = {"fenix": "🐦‍🔥", "unicorn": "🦄", "dragon": "🐉"}

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

@router.callback_query(F.data == "open_forge")
async def process_open_forge(callback: types.CallbackQuery, db_pool):
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT lvl, inventory FROM capybaras WHERE owner_id = $1", user_id)
        if not row: return

        if row['lvl'] < 10:
            return await callback.answer("🔒 Кузня доступна лише з 10 рівня!", show_alert=True)

        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        _, kiwi_count = find_item_in_inventory(inv, "kiwi")

        builder = InlineKeyboardBuilder()
        builder.button(text="⚙️ Звичайний крафт", callback_data="common_craft_list")
        builder.button(text="🔨 Покращити спорядження", callback_data="upgrade_menu")
        builder.button(text="⚜️ Міфічний коваль", callback_data="forge_craft_list")
        builder.button(text="⬅️ Назад", callback_data="open_village")
        builder.adjust(1)

        text = (
            "🐦 <b>Кузня ківі</b>\n"
            "━━━━━━━━━━━━━━━\n"
            "Тут пахне сталлю та тропічними фруктами.\n"
            "Твій запас ківі: <b>{kiwi_count} 🥝</b>\n\n"
            "<i>«Гей, пухнастий! Хочеш гостріший ніж чи міцніший панцир?\n Можливості залежать від кількості ківі в твоїх кишенях»</i>"
        ).format(kiwi_count=kiwi_count)

        await callback.message.edit_media(
            media=InputMediaPhoto(media=IMAGES_URLS["forge"], caption=text, parse_mode="HTML"),
            reply_markup=builder.as_markup()
        )

@router.callback_query(F.data == "upgrade_menu")
async def upgrade_list(callback: types.CallbackQuery, db_pool):
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
    lvl = await conn.fetchval("SELECT lvl FROM capybaras WHERE owner_id = $1", user_id)
    if lvl < 15:
        return await callback.answer("❌ Ще не доріс! Повертайся на 15 рівні.", show_alert=True)

    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        if not inv_raw: return
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        equip = inv.get("equipment", {})
        
        builder = InlineKeyboardBuilder()

        def get_btn_text(data):
            name = data if isinstance(data, str) else data.get("name")
            lvl = 0 if isinstance(data, str) else data.get("lvl", 0)
            i_type = data.get("type", "") if isinstance(data, dict) else ""
            icon = TYPE_ICONS.get(i_type, "💎")
            stars = "⭐" * lvl if lvl > 0 else ""
            return f"{icon} {name} {stars}"

        if isinstance(equip, dict):
            for slot, item_data in equip.items():
                name = item_data if isinstance(item_data, str) else item_data.get("name")
                if name and name not in ["Лапки", "Хутро", "Нічого"]:
                    builder.button(text=get_btn_text(item_data), callback_data=f"up_item:{slot}")
        elif isinstance(equip, list):
            for index, item_data in enumerate(equip):
                name = item_data if isinstance(item_data, str) else item_data.get("name")
                if name and name not in ["Лапки", "Хутро", "Нічого"]:
                    builder.button(text=get_btn_text(item_data), callback_data=f"up_item:{index}")

        builder.button(text="⬅️ Назад", callback_data="open_forge")
        builder.adjust(1)

        await callback.message.edit_caption(
            caption="🛠️ <b>Загартування спорядження</b>\n\nМаксимальний рівень: <b>5</b>\nВартість: <b>5 🥝</b>",
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
        
        cat, kiwi_count = find_item_in_inventory(inv, "kiwi")
        if kiwi_count < 5:
            return await callback.answer("❌ Бракує ківі! Потрібно 5 🥝", show_alert=True)

        if isinstance(equip, list):
            try:
                slot_key_idx = int(slot_key)
                item_data = equip[slot_key_idx]
            except (ValueError, IndexError):
                return await callback.answer("❌ Предмет не знайдено")
        else:
            item_data = equip.get(slot_key)

        if not item_data: return await callback.answer("❌ Предмет не знайдено")

        if isinstance(item_data, str):
            item_data = {"name": item_data, "lvl": 0}
        
        current_lvl = item_data.get("lvl", 0)
        if current_lvl >= UPGRADE_CONFIG["max_lvl"]:
            return await callback.answer("✨ Цей предмет досяг піку своєї могутності!", show_alert=True)

        new_lvl = current_lvl + 1
        prefix = UPGRADE_CONFIG["prefixes"].get(new_lvl, "Покращений")
        base_name = item_data.get("base_name", item_data["name"])
        
        item_data["lvl"] = new_lvl
        item_data["name"] = f"{prefix} {base_name}"
        item_data["base_name"] = base_name
        
        inv[cat]["kiwi"] -= 5
        if isinstance(equip, list):
            equip[int(slot_key)] = item_data
        else:
            equip[slot_key] = item_data

        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv, ensure_ascii=False), user_id)
        await callback.answer(f"🔥 Коваль попрацював на славу! Тепер це: {item_data['name']}")
        await upgrade_list(callback, db_pool)

@router.callback_query(F.data == "common_craft_list")
async def common_craft_list(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    async with db_pool.acquire() as conn:
        lvl = await conn.fetchval("SELECT lvl FROM capybaras WHERE owner_id = $1", user_id)
        if lvl < 10:
            return await callback.answer("❌ Навчися зброю тримати! Повертайся на 10 рівні.", show_alert=True)
    for r_id, r_data in FORGE_RECIPES.get("common_craft", {}).items():
        builder.button(text=f"{r_data.get('emoji', '📦')} {r_data.get('name')}", callback_data=f"common_info:{r_id}")
    builder.button(text="⬅️ Назад", callback_data="open_forge")
    builder.adjust(1)
    await callback.message.edit_caption(caption="📦 <b>Майстерня:</b>\nТут можна створити корисні дрібниці.", reply_markup=builder.as_markup(), parse_mode="HTML")

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

@router.callback_query(F.data.startswith("do_common_craft:"))
async def process_common_craft(callback: types.CallbackQuery, db_pool):
    recipe_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        inv = ensure_dict(inv_raw)
        recipe = FORGE_RECIPES.get("common_craft", {}).get(recipe_id)

        user_equip = inv.get("equipment", [])
        for req_item_name in recipe["ingredients"].get("equipment", []):
            for i, item in enumerate(user_equip):
                name_in_inv = item.get("name", "") if isinstance(item, dict) else str(item)
                if req_item_name in name_in_inv:
                    user_equip.pop(i)
                    break
        
        for mat, count in recipe["ingredients"].get("materials", {}).items():
            inv["materials"][mat] -= count

        loot = inv.setdefault("loot", {})
        loot[recipe_id] = loot.get(recipe_id, 0) + 1

        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv, ensure_ascii=False), user_id)
        
        await callback.answer(f"✅ {recipe['name']} готово!", show_alert=True)
        await common_craft_list(callback)

@router.callback_query(F.data == "forge_craft_list")
async def forge_craft_list(callback: types.CallbackQuery, db_pool):
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        lvl = await conn.fetchval("SELECT lvl FROM capybaras WHERE owner_id = $1", user_id)
        if lvl < 20:
            return await callback.answer("❌ Складна робота! Повертайся на 20 рівні.", show_alert=True)

        builder = InlineKeyboardBuilder()
        for r_id, r_data in FORGE_RECIPES.get("mythic_artifacts", {}).items():
            icon = MYTHIC_ICONS.get(r_data.get("class", "✨"), "✨")
            builder.button(text=f"{icon} {r_data.get('name')}", callback_data=f"mythic_info:{r_id}")
        
        builder.button(text="⬅️ Назад", callback_data="open_forge")
        builder.adjust(1)
        await callback.message.edit_caption(caption="⚒️ <b>Доступні креслення:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("mythic_info:"))
async def show_mythic_recipe(callback: types.CallbackQuery, db_pool):
    mythic_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT inventory, equipment, state, stats_track, 
                   lvl, atk, def, agi, luck, zen, stamina, hunger,
                   wins, total_fights
            FROM capybaras WHERE owner_id = $1
        """, user_id) 
        
        if not row: return await callback.answer("❌ Капібару не знайдено")

        inv = row['inventory'] or {}
        equip = row['equipment'] or {}
        state = row['state'] or {}
        track = row['stats_track'] or {}
        
        recipe = FORGE_RECIPES.get("mythic_artifacts", {}).get(mythic_id)
        if not recipe: return await callback.answer("❌ Рецепт не знайдено")

        text = f"✨ <b>{recipe['name']}</b>\n<i>{recipe['desc']}</i>\n━━━━━━━━━━━━━━━\n\n<b>Необхідні артефакти:</b>\n"
        can_craft = True
        
        for ing_name in recipe["ingredients"]:
            in_loot = inv.get("materials", {}).get(ing_name, 0) > 0 or inv.get("loot", {}).get(ing_name, 0) > 0
            in_equip = any(ing_name in str(v) for v in equip.values() if v)
            
            text += f"{'✅' if in_loot or in_equip else '❌'} {ing_name}\n"
            if not (in_loot or in_equip): can_craft = False

        if "requirements" in recipe:
            text += "\n<b>📜 Особливі умови:</b>\n"
            
            avg_stats = round((row['atk'] + row['def'] + row['agi'] + row['luck']) / 4, 2)
            
            checks = {
                "wins": ("Перемоги", row['wins'], "⚔️"),
                "total_fights": ("Всього боїв", row['total_fights'], "👊"),
                "clean_chat_days": ("Дні без муту", state.get("clean_days", 0), "😇"),
                "speed_stat": ("Швидкість", row['agi'], "👟"),
                "zen": ("Дзен", row['zen'], "❇️"),
                "stamina": ("Поточна стаміна", row['stamina'], "⚡️"),
                "hunger": ("Голод (макс)", row['hunger'], "🍏"),
                "level": ("Рівень", row['lvl'], "🆙"),
                "all_stats_average": ("Сер. стат", avg_stats, "📊"),
                "karma": ("Карма", track.get("karma", 0), "⚖️")
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
            reply_markup=InlineKeyboardBuilder().button(text="🔥 ГАРАЗД",
             callback_data="open_forge").as_markup(), parse_mode="HTML")