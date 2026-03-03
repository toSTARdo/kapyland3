import asyncio
import json
import random

from aiogram import Router, types, html, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ARTIFACTS, RARITY_META, DISPLAY_NAMES
from handlers.harbor.village.forge import UPGRADE_CONFIG
from config import load_game_data
from utils.helpers import calculate_lvl_data, ensure_dict

GACHA_ITEMS = ARTIFACTS
RECIPES = load_game_data("data/potion_craft.json")

router = Router()

async def render_inventory_page(message, user_id, db_pool, page="food", current_page=0, is_callback=False):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT inventory, equipment FROM capybaras WHERE owner_id = $1", 
            user_id
        )

    if not row:
        return await message.answer("❌ Профіль не знайдено.")

    inv = ensure_dict(row['inventory'])
    curr_equip = ensure_dict(row['equipment'])
    
    inv = inv or {}
    curr_equip = curr_equip or {}
    
    builder = InlineKeyboardBuilder()
    
    ITEMS_PER_PAGE = 5
    TYPE_ICONS = {"weapon": "🗡️", "armor": "🔰", "artifact": "🧿"}
    title = ""
    content = ""

    if page == "food":
        title = "🍎 <b>Провізія</b>"
        food = inv.get("food", {})
        food_names = {"tangerines": "🍊", "melon": "🍈", "watermelon_slices": "🍉", "mango": "🥭", "kiwi": "🥝"}
        active_food = {k: v for k, v in food.items() if v > 0}
        
        if not active_food:
            content = "<i>Твій кошик порожній...</i>"
        else:
            content = "<i>Обери їжу:</i>"
            for k, v in active_food.items():
                icon = food_names.get(k, "🍱")
                builder.button(text=f"{icon} ({v})", callback_data=f"food_choice:{k}")
        builder.adjust(2)

    elif page == "potions":
        title = "🧪 <b>Зілля</b>"
        potions = inv.get("potions", {})
        active_potions = {k: v for k, v in potions.items() if v > 0}
        
        if not active_potions:
            content = "<i>У тебе немає готових зілль.</i>"
        else:
            content = "<i>Твої магічні шмурдяки:</i>"
            for p_id, count in active_potions.items():
                recipe_info = RECIPES.get(p_id, {})
                p_name = recipe_info.get("name", p_id)
                p_emoji = recipe_info.get("emoji", "🧪")
                builder.row(
                    types.InlineKeyboardButton(
                        text=f"{p_emoji} {p_name} ({count})", 
                        callback_data=f"use_potion:{p_id}"
                    )
                )

    elif page.startswith("items"):
        title = "⚔️ <b>Амуніція</b>"
        parts = page.split(":")
        selected_key = parts[1] if len(parts) > 1 else None
        
        all_items = inv.get("equipment", [])
        
        if not all_items:
            content = "<i>Твій трюм порожній...</i>"
        else:
            unique_list = []
            seen = {}
            for item in all_items:
                if isinstance(item, str): 
                    item = {"name": item, "lvl": 0, "type": "artifact", "rarity": "Common"}
                n = item.get('name', '???')
                l = item.get('lvl', 0)
                k = f"{n}_{l}"
                
                if k not in seen:
                    seen[k] = len(unique_list)
                    unique_list.append({"data": item, "count": 1, "key": k})
                else:
                    unique_list[seen[k]]["count"] += 1
            
            max_p = (len(unique_list) - 1) // ITEMS_PER_PAGE
            items_slice = unique_list[current_page * ITEMS_PER_PAGE : (current_page + 1) * ITEMS_PER_PAGE]
            SELL_PRICES = {"Common": 1, "Rare": 2, "Epic": 3, "Legendary": 5, "Mythic": 10}
            
            content = f"<b>Стор. {current_page + 1}</b>\nОбери предмет для огляду:"

            for info in items_slice:
                item = info["data"]
                count = info["count"]
                k = info["key"]
                
                raw_name = item.get('name', '???')
                clean_name = raw_name
                
                for prefix in UPGRADE_CONFIG["prefixes"].values():
                    if raw_name.startswith(prefix):
                        clean_name = raw_name.replace(prefix, "").strip()
                        break

                rarity = item.get('rarity', 'Common')
                lvl = item.get('lvl', 0)
                stars = "⭐" * lvl if lvl > 0 else "" 
                i_type = item.get('type', 'artifact')
                
                t_icon = TYPE_ICONS.get(i_type, "🧿")
                r_icon = RARITY_META.get(rarity, {}).get('emoji', '⚪')
                                
                is_eq = any(
                    isinstance(v, dict) and v.get("name") == raw_name and v.get("lvl") == lvl 
                    for v in curr_equip.values()
                )
                
                status = " ✅" if is_eq else ""
                
                builder.row(
                    types.InlineKeyboardButton(
                        text=f"{r_icon}{t_icon} {clean_name} x{count}{status}", 
                        callback_data=f"inv_page:items:{current_page}:{k}"
                    )
                )

                if selected_key == k:
                    price = SELL_PRICES.get(rarity, 1) + lvl
                    item_desc = item.get("desc", "Опис відсутній.")
                    content = (
                        f"{r_icon} <b>{raw_name} {stars}</b>\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"<i>{item_desc}</i>\n\n"
                        f"💰 Ціна: <b>{price} 🍉</b>"
                    )
                    
                    builder.row(
                        types.InlineKeyboardButton(text="⚔️ Одягнути", callback_data=f"equip:{i_type}:{raw_name}:{lvl}"),
                        types.InlineKeyboardButton(text=f"🔥 Продати за {price} 🍉", callback_data=f"sell_item:{rarity}:{raw_name}:{lvl}"),
                        types.InlineKeyboardButton(text="✖️", callback_data=f"inv_page:items:{current_page}")
                    )

            if len(unique_list) > ITEMS_PER_PAGE:
                nav = []
                if current_page > 0: 
                    nav.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"inv_page:items:{current_page-1}"))
                nav.append(types.InlineKeyboardButton(text=f"{current_page+1}/{max_p+1}", callback_data="none"))
                if current_page < max_p: 
                    nav.append(types.InlineKeyboardButton(text="➡️", callback_data=f"inv_page:items:{current_page+1}"))
                builder.row(*nav)


    elif page == "loot":
        title = "🧳 <b>Скарби</b>"
        loot = inv.get("loot", {})
        loot_lines = [
            f"🎟️ Квитки: <b>{loot.get('lottery_ticket', 0)}</b>", 
            f"🗝️ Ключі: <b>{loot.get('key', 0)}</b>", 
            f"🪛 Відмички: <b>{loot.get('lockpicker', 0)}</b>",
            f"🗃 Скрині: <b>{loot.get('chest', 0)}</b>",
            f"🗿 Тотеми: <b>{loot.get('teleport_totem', 0)}</b>"
        ]
        valid_lines = [l for l in loot_lines if "<b>0</b>" not in l]
        content = "\n".join(valid_lines) if valid_lines else "<i>Твій сейф порожній...</i>"
        if loot.get("chest", 0) > 0:
            builder.button(text=f"🔑 Відкрити", callback_data="open_chest")
        if loot.get("lockpicker", 0) > 0:
            builder.button(text=f"🪛 Використати відмичку", callback_data="open_chest")
        builder.adjust(1)

    elif page == "maps":
        title = "🗺 <b>Твої Карти</b>"
        maps = inv.get("loot", {}).get("treasure_maps", [])
        if not maps:
            content = "<i>У тебе немає жодної карти.</i>"
        else:
            map_entries = []
            for m in maps:
                entry = f"📍 <b>Карта скарбів {m.get('id', '???')}</b>\n╰ Координати: <code>{m['pos']}</code>" if m.get("type") == "treasure" else f"💀 <b>Карта лігва Боса №{m.get('boss_num', '???')}</b>\n╰ Координати: <code>{m['pos']}</code>"
                map_entries.append(entry)
            content = "\n\n".join(map_entries)

    elif page == "materials":
        title = "📦 <b>Ресурси</b>"
        mats = inv.get("materials", {})
        mat_lines = [f"{DISPLAY_NAMES.get(k, k.capitalize())}: <b>{v}</b>" for k, v in mats.items() if v > 0]
        content = "Твої запаси:\n\n" + "\n".join(mat_lines) if mat_lines else "<i>Твій трюм порожній...</i>"

    if not page.startswith("items"):
        pages_meta = {
            "food": "🍎 Їжа", 
            "potions": "🧪 Зілля", 
            "maps": "🗺 Карти", 
            "loot": "🧳 Лут", 
            "items": "⚔️ Речі", 
            "materials": "🌱 Матеріали"
        }
        
        nav_builder = InlineKeyboardBuilder()
        
        for p_key, p_text in pages_meta.items():
            display_text = f"· {p_text} ·" if page == p_key else p_text
            
            nav_builder.button(
                text=display_text, 
                callback_data=f"inv_page:{p_key}:0"
            )
        
        nav_builder.adjust(2)
        builder.attach(nav_builder)

    builder.row(types.InlineKeyboardButton(text="⬅️ Назад до Трюму", callback_data="open_inventory_main"))
    
    text = f"{title}\n━━━━━━━━━━━━━━━\n{content}"
    
    if is_callback:
        try: await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except: pass
    else: 
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("inv_page:"))
async def handle_inventory_pagination(callback: types.CallbackQuery, db_pool):
    data = callback.data.split(":")
    page_type, p_idx = data[1], int(data[2])
    selected_item = data[3] if len(data) > 3 else None
    
    target_page = f"{page_type}:{selected_item}" if selected_item else page_type
    await render_inventory_page(callback.message, callback.from_user.id, db_pool, page=target_page, current_page=p_idx, is_callback=True)
    await callback.answer()

@router.callback_query(F.data.startswith("sell_item:"))
async def handle_sell_equipment(callback: types.CallbackQuery, db_pool):
    _, rarity, item_name, lvl = callback.data.split(":")
    lvl, uid = int(lvl), callback.from_user.id
    prices = {"Common": 1, "Rare": 2, "Epic": 3, "Legendary": 5, "Mythic": 10}
    reward = prices.get(rarity, 1) + lvl
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, equipment FROM capybaras WHERE owner_id = $1", uid)
        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        curr_eq = json.loads(row['equipment']) if isinstance(row['equipment'], str) else row['equipment']
        
        if any(isinstance(v, dict) and v.get("name") == item_name and v.get("lvl") == lvl for v in curr_eq.values()):
            return await callback.answer("❌ Спочатку зніми цей предмет!", show_alert=True)

        inv_eq = inv.get("equipment", [])
        found = False
        for i, it in enumerate(inv_eq):
            if it.get("name") == item_name and it.get("lvl") == lvl:
                inv_eq.pop(i)
                found = True
                break
        
        if not found: return await callback.answer("❌ Предмет не знайдено.")
        
        food = inv.setdefault("food", {})
        food["watermelon_slices"] = food.get("watermelon_slices", 0) + reward
        
        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv), uid)
    
    await callback.answer(f"🍉 +{reward} за {item_name}")
    await render_inventory_page(callback.message, uid, db_pool, page="items", is_callback=True)

@router.callback_query(F.data.startswith("equip:"))
async def handle_equip_item(callback: types.CallbackQuery, db_pool):
    _, itype, iname, ilvl = callback.data.split(":")
    ilvl, uid = int(ilvl), callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT equipment FROM capybaras WHERE owner_id = $1", uid)
        curr_equip = json.loads(row['equipment']) if isinstance(row['equipment'], str) else row['equipment']
        curr_equip = curr_equip or {}
        
        current = curr_equip.get(itype)
        if isinstance(current, dict) and current.get("name") == iname and current.get("lvl") == ilvl:
            curr_equip[itype] = {"name": "Лапки", "lvl": 0} if itype == "weapon" else None
            msg = f"❌ Знято: {iname}"
        else:
            curr_equip[itype] = {"name": iname, "lvl": ilvl}
            msg = f"✅ Одягнено: {iname} ⭐{ilvl}"
            
        await conn.execute("UPDATE capybaras SET equipment = $1 WHERE owner_id = $2", json.dumps(curr_equip, ensure_ascii=False), uid)
        
    await callback.answer(msg)
    await render_inventory_page(callback.message, uid, db_pool, page="items", is_callback=True)
