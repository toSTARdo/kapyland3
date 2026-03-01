import json
import asyncio
from aiogram import types, F, Router
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import load_game_data, DISPLAY_NAMES, IMAGES_URLS

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
        builder.button(text="🔨 Покращити спорядження (5 🥝)", callback_data="upgrade_menu")
        builder.button(text="📦 Звичайний крафт", callback_data="common_craft_list")
        builder.button(text="⚒️ Крафт нових речей (Lvl 30)", callback_data="forge_craft_list")
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
    for r_id, r_data in FORGE_RECIPES.get("common_craft", {}).items():
        builder.button(text=f"📦 {r_data.get('name')}", callback_data=f"common_info:{r_id}")
    builder.button(text="⬅️ Назад", callback_data="open_forge")
    builder.adjust(1)
    await callback.message.edit_caption(caption="📦 <b>Майстерня:</b>\nТут можна створити корисні дрібниці.", reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("common_info:"))
async def show_common_recipe(callback: types.CallbackQuery, db_pool):
    recipe_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        recipe = FORGE_RECIPES.get("common_craft", {}).get(recipe_id)
        
        if not recipe: return await callback.answer("❌ Рецепт не знайдено")

        text = f"📦 <b>{recipe['name']}</b>\n{recipe['desc']}\n━━━━━━━━━━━━━━━\n\n<b>Необхідно:</b>\n"
        can_craft = True
        equip = inv.get("equipment", [])
        has_hook = any("Гак" in (i.get("name", "") if isinstance(i, dict) else str(i)) for i in equip)
        
        text += f"{'✅' if has_hook else '❌'} Гак (в руках)\n"
        if not has_hook: can_craft = False

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
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        recipe = FORGE_RECIPES.get("common_craft", {}).get(recipe_id)

        equip = inv.get("equipment", [])
        for i, item in enumerate(equip):
            if "Гак" in (item.get("name", "") if isinstance(item, dict) else str(item)):
                equip.pop(i)
                break
        
        for mat, count in recipe["ingredients"]["materials"].items():
            inv["materials"][mat] -= count

        inv.setdefault("loot", {})["lockpicker"] = inv.get("loot", {}).get("lockpicker", 0) + 1

        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv, ensure_ascii=False), user_id)
        await callback.answer("✅ Відмичка готова!", show_alert=True)
        await common_craft_list(callback)

@router.callback_query(F.data == "forge_craft_list")
async def forge_craft_list(callback: types.CallbackQuery, db_pool):
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        lvl = await conn.fetchval("SELECT lvl FROM capybaras WHERE owner_id = $1", user_id)
        if lvl < 30:
            return await callback.answer("❌ Складна робота! Повертайся на 30 рівні.", show_alert=True)

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
        row = await conn.fetchrow("SELECT inventory, hp, atk, def, state, stats_track, lvl FROM capybaras WHERE owner_id = $1", user_id)        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        stats = json.loads(row['stats']) if isinstance(row['stats'], str) else row['stats']
        track = json.loads(row['stats_track']) if isinstance(row['stats_track'], str) else row['stats_track']
        
        recipe = FORGE_RECIPES.get("mythic_artifacts", {}).get(mythic_id)
        if not recipe: return await callback.answer("❌ Рецепт не знайдено")

        text = f"✨ <b>{recipe['name']}</b>\n<i>{recipe['desc']}</i>\n━━━━━━━━━━━━━━━\n\n<b>Необхідні артефакти:</b>\n"
        can_craft, equip = True, inv.get("equipment", {})
        
        for ing_name in recipe["ingredients"]:
            in_loot = inv.get("loot", {}).get(ing_name, 0) > 0
            in_equip = False
            items = equip.values() if isinstance(equip, dict) else equip
            for item in items:
                if ing_name in (item if isinstance(item, str) else item.get("name", "")):
                    in_equip = True
                    break
            
            text += f"{'✅' if in_loot or in_equip else '❌'} {ing_name}\n"
            if not (in_loot or in_equip): can_craft = False

        if "requirements" in recipe:
            text += "\n<b>📜 Особливі умови:</b>\n"
            checks = {
                "wins": ("Перемоги", "wins", "⚔️"), "total_fights": ("Всього боїв", "total_fights", "👊"),
                "stamina_regen_total": ("Реген стаміни", "stamina_regen", "🔋"), "clean_chat_days": ("Дні без муту", "clean_days", "😇"),
                "lifesteal_total": ("Всього вампіризму", "lifesteal_done", "🩸"), "speed_stat": ("Швидкість", "speed", "👟"),
                "zen": ("Дзен", "zen", "❇️"), "stamina": ("Поточна стаміна", "stamina", "⚡️"),
                "hunger": ("Голод (макс)", "hunger", "🍏"), "level": ("Рівень", "level", "🆙"), "all_stats_average": ("Сер. стат", "avg_stats", "📊")
            }
            for key, val in recipe["requirements"].items():
                if key == "location":
                    text += f"{'✅' if row['state'].get('location') == val else '⏳'} Локація: {row['state'].get('location')}/{val}\n"
                    if row['state'].get('location') != val: can_craft = False
                elif key == "karma":
                    curr = track.get("karma", 0)
                    text += f"{'✅' if curr <= val else '⏳'} Карма: {curr}/{val}\n"
                    if curr > val: can_craft = False
                elif key in checks:
                    label, m_key, icon = checks[key]
                    curr = track.get(m_key, stats.get(m_key, row.get(m_key, 0)))
                    pass_chk = curr <= val if key == "hunger" else curr >= val
                    text += f"{'✅' if pass_chk else '⏳'} {icon} {label}: {curr}/{val}\n"
                    if not pass_chk: can_craft = False

        builder = InlineKeyboardBuilder()
        if can_craft: builder.button(text="🔥 КУВАТИ АРТЕФАКТ", callback_data=f"craft_mythic:{mythic_id}")
        builder.button(text="⬅️ Назад", callback_data="forge_craft_list")
        builder.adjust(1)
        await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")

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