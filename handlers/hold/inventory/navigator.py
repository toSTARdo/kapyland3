import asyncio
import json
import random
import datetime
from aiogram import Router, types, html, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pydantic import BaseModel, Field

from config import ARTIFACTS, RARITY_META, DISPLAY_NAMES, WEAPON, ARMOR, TYPE_ICONS, LOTTERY_BANNERS, load_game_data, INVENTORY_TUTS
from handlers.harbor.village.forge import UPGRADE_CONFIG
from utils.helpers import calculate_lvl_data, ensure_dict, get_main_menu_chunk
from domain.base import Item

router = Router()
GACHA_ITEMS = ARTIFACTS
RECIPES = load_game_data("data/potion_craft.json")

def is_eligible_for_lega(last_lega_str: str) -> bool:
    if not last_lega_str: return True
    if isinstance(last_lega_str, str):
        try: last_lega_str = datetime.datetime.fromisoformat(last_lega_str)
        except: return True
    return datetime.datetime.now() >= last_lega_str + datetime.timedelta(days=7)

async def render_inventory_page(message, user_id, db_pool, page="food", current_page=0, is_callback=False, show_more=False, curr_p = 0):
    parts = page.split(":")
    base_page = parts[0]
    
    async with db_pool.acquire() as conn:
        # Додаємо отримання quicklinks (row)
        user_row = await conn.fetchrow("SELECT quicklinks FROM users WHERE tg_id = $1", user_id)
        row = await conn.fetchrow("SELECT inventory, equipment FROM capybaras WHERE owner_id = $1", user_id)
    
    if not row: return await message.answer("❌ Профіль не знайдено.")

    show_quicklinks = user_row['quicklinks'] if user_row and user_row['quicklinks'] is not None else True
    inv = ensure_dict(row['inventory'])
    curr_equip = ensure_dict(row['equipment'])
    builder = InlineKeyboardBuilder()
    ITEMS_PER_PAGE = 5
    title, content = "", ""

    loot = inv.get("loot", {})
    has_handmade_map = loot.get("handmade_map", 0) > 0

    if page == "food":
        title = "🍎 <b>Провізія</b>"
        food = inv.get("food", {})
        food_names = {"tangerines": "🍊", "melon": "🍈", "watermelon_slices": "🍉", "mango": "🥭", "kiwi": "🥝", "mushroom": "🍄‍🟫", "fly_agaric": "🍄"}
        active_food = {k: v for k, v in food.items() if v > 0}
        if not active_food: content = "<i>Твій кошик порожній...</i>"
        else:
            content = "<i>Обери їжу:</i>"
            for k, v in active_food.items():
                builder.button(text=f"{food_names.get(k, '🍱')} ({v})", callback_data=f"food_choice:{k}")
        builder.adjust(2)

    elif page == "potions":
        title = "🧪 <b>Зілля</b>"
        potions = inv.get("potions", {})
        active_potions = {k: v for k, v in potions.items() if v > 0}
        if not active_potions: content = "<i>У тебе немає готових зілль.</i>"
        else:
            content = "<i>Твої магічні шмурдяки:</i>"
            for p_id, count in active_potions.items():
                recipe = RECIPES.get(p_id, {})
                builder.row(
                    types.InlineKeyboardButton(text=f"{recipe.get('emoji', '🧪')} {recipe.get('name', p_id)} ({count})", callback_data=f"use_potion:{p_id}"),
                    types.InlineKeyboardButton(text=f"📥 Покласти в скриню (1)", callback_data=f"put_in_chest:potions:{p_id}")
                )

    elif page.startswith("items"):
        title = "⚔️ <b>Амуніція</b>"
        
        selected_key = parts[1] if len(parts) > 1 and parts[1] != "none" else None
        sort_mode = parts[2] if len(parts) > 2 else "default"
        
        eq_dict = inv.get("equipment", {})

        if not eq_dict:
            content = "<i>Твій трюм порожній...</i>"
        else:
            # --- НОВА ЛОГІКА ГРУПУВАННЯ ---
            grouped = {}
            for k, data in eq_dict.items():
                try:
                    name = data.get("name")
                    if name not in grouped:
                        grouped[name] = []
                    grouped[name].append({"obj": Item(**data), "key": k})
                except: continue

            unique_list = []
            for name, copies in grouped.items():
                copies.sort(key=lambda x: x["obj"].lvl, reverse=True)
                
                best_version = copies[0] 
                total_count = len(copies)
                
                best_version["obj"].count = total_count 
                unique_list.append(best_version)

            if sort_mode in RARITY_META:
                unique_list = [x for x in unique_list if x["obj"].rarity == sort_mode]
            elif sort_mode in ["weapon", "armor", "artifact"]:
                unique_list = [x for x in unique_list if x["obj"].type == sort_mode]
            
            if sort_mode == "lvl":
                unique_list.sort(key=lambda x: x["obj"].lvl, reverse=True)
            else:
                rarity_order = {"Common": 0, "Rare": 1, "Epic": 2, "Legendary": 3, "Mythic": 4}
                unique_list.sort(key=lambda x: rarity_order.get(x["obj"].rarity, 0), reverse=True)

            max_p = max(0, (len(unique_list) - 1) // ITEMS_PER_PAGE)
            curr_p = min(curr_p, max_p)
            
            items_slice = unique_list[curr_p * ITEMS_PER_PAGE : (curr_p + 1) * ITEMS_PER_PAGE]
            
            status_text = f"Фільтр: <b>{sort_mode}</b>" if sort_mode != "default" else "За рідкістю"
            content = f"<b>Стор. {curr_p + 1}</b> | {status_text}\nОбери предмет:"

            for info in items_slice:
                item, k = info["obj"], info["key"]
                is_eq = any(isinstance(v, dict) and v.get("name") == item.name and v.get("lvl") == item.lvl for v in curr_equip.values())
                
                rarity_emoji = RARITY_META.get(item.rarity, {}).get('emoji', '⚪')
                type_emoji = TYPE_ICONS.get(item.type, '🧿')

                builder.row(types.InlineKeyboardButton(
                    text=f"{rarity_emoji}{type_emoji} {item.name} x{item.count}{' ✅' if is_eq else ''}",
                    callback_data=f"inv_page:items:{curr_p}:{k}:{sort_mode}"
                ))

                if selected_key == k:
                    rarity_data = RARITY_META.get(item.rarity, {})
                    base_price = {"Common": 1, "Rare": 2, "Epic": 3, "Legendary": 5, "Mythic": 10}.get(item.rarity, 1)
                    price = (base_price + item.lvl) * item.count
                    
                    type_label = "Невідомо"
                    stats_block = ""
                    effects_list = ""

                    if item.type == "weapon":
                        type_label = "⚔️ Зброя"
                        dmg = item.bonus_atk+0.05*item.lvl if item.bonus_atk > 0 else ((WEAPON.get(item.name, {}).get("hit_bonus", 0)+0.05*item.lvl) * 100)
                        stats_block = f"<b>💥 Атака:</b> <code>+{dmg:.1f}%</code>\n"
                        w_data = WEAPON.get(item.name, {})
                        pattern_raw = w_data.get("pattern")
                        PATTERN_MAP = {"sequential": "Послідовний", "chaotic": "Хаотичний", "ultimate": "Ультимативний"}
                        if pattern_raw:
                            stats_block += f"<b>🎯 Паттерн:</b> <code>{PATTERN_MAP.get(pattern_raw, pattern_raw)}</code>\n"
                        specials = w_data.get("special_text", [])
                        if specials:
                            effects_list = "\n<b>✨ Спеціальні ефекти:</b>\n" + "\n".join([f" • <i>{e}</i>" for e in specials])

                    elif item.type == "armor":
                        type_label = "🛡 Обладунки"
                        def_val = item.bonus_def+0.05*item.lvl if item.bonus_def > 0 else ((ARMOR.get(item.name, {}).get("defense", 0)+0.05*item.lvl) * 100)
                        stats_block = f"<b>🛡 Захист:</b> <code>+{def_val:.1f}%</code>\n"
                        a_data = ARMOR.get(item.name, {})
                        if "reflect" in a_data:
                            stats_block += f"<b>🌀 Відбиття:</b> <code>{a_data['reflect']}%</code>\n"

                    elif item.type == "artifact":
                        type_label = "🧿 Артефакт"
                        stats_block = "<i>Магічний предмет з пасивним ефектом.</i>\n"

                    content = (
                        f"{rarity_data.get('emoji', '⚪')} <b>{item.name}</b> [{'⭐' * item.lvl if item.lvl > 0 else 'Lvl 0'}] | "
                        f"<i>{type_label}</i>\n━━━━━━━━━━━━\n"
                        f"<b>📜 Опис:</b>\n<i>{item.desc}</i>\n{effects_list}\n\n"
                        f"<b>📊 Характеристики:</b>\n{stats_block}"
                        f"<b>💰 Ціна продажу:</b> {price} 🍉\n━━━━━━━━━━━━"
                    )

                    equip_text = "⚔️" if not is_eq else "❌")
                    
                    main_btns = [
                        types.InlineKeyboardButton(text=equip_text, callback_data=f"equip:{item.type}:{item.name}:{item.lvl}")
                    ]

                    if item.count == 1:
                        sell_text = "💰"
                        main_btns.append(types.InlineKeyboardButton(text=sell_text, callback_data=f"sell_item:{k}:one"))
                    
                    main_btns.append(types.InlineKeyboardButton(text="✖️", callback_data=f"inv_page:items:{curr_p}:none:{sort_mode}"))

                    if has_handmade_map:
                        main_btns.append(types.InlineKeyboardButton(text="📥", callback_data=f"put_in_chest:equipment:{k}"))

                    builder.row(*main_btns)

                    if item.count > 1:
                        builder.row(
                            types.InlineKeyboardButton(text="💰 Продати 1", callback_data=f"sell_item:{k}:one"),
                            types.InlineKeyboardButton(text="♻️ Продати зайві", callback_data=f"sell_item:{k}:all_but_best")
                        )


            if len(unique_list) > ITEMS_PER_PAGE:
                nav = []
                if curr_p > 0: 
                    nav.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"inv_page:items:{curr_p-1}:none:{sort_mode}"))
                nav.append(types.InlineKeyboardButton(text=f"{curr_p+1}/{max_p+1}", callback_data="none"))
                if curr_p < max_p: 
                    nav.append(types.InlineKeyboardButton(text="➡️", callback_data=f"inv_page:items:{curr_p+1}:none:{sort_mode}"))
                builder.row(*nav)
            
            if not show_more:
                builder.row(types.InlineKeyboardButton(text="✚ Сортування та фільтри", callback_data=f"inv_more:items:{curr_p}:{sort_mode}"))
            else:
                builder.row(
                    types.InlineKeyboardButton(text="⚔️", callback_data="inv_page:items:0:none:weapon"),
                    types.InlineKeyboardButton(text="🛡", callback_data="inv_page:items:0:none:armor"),
                    types.InlineKeyboardButton(text="🧿", callback_data="inv_page:items:0:none:artifact")
                )
                builder.row(
                    types.InlineKeyboardButton(text="⚪️", callback_data="inv_page:items:0:none:Common"),
                    types.InlineKeyboardButton(text="🔵", callback_data="inv_page:items:0:none:Rare"),
                    types.InlineKeyboardButton(text="🟣", callback_data="inv_page:items:0:none:Epic")
                )
                builder.row(
                    types.InlineKeyboardButton(text="💎 Leg", callback_data="inv_page:items:0:none:Legendary"),
                    types.InlineKeyboardButton(text="🐉 Myth", callback_data="inv_page:items:0:none:Mythic"),
                    types.InlineKeyboardButton(text="⭐ Lvl", callback_data="inv_page:items:0:none:lvl")
                )
                builder.row(
                    types.InlineKeyboardButton(text="🔄 Скинути", callback_data="inv_page:items:0:none:default"),
                    types.InlineKeyboardButton(text="🔼 Сховати", callback_data=f"inv_page:items:{curr_p}:none:{sort_mode}")
                )

    elif page == "loot":
        title = "🧳 <b>Скарби</b>"
        loot = inv.get("loot", {})
        
        chests = loot.get('chest', 0)
        mega_chests = loot.get('mega_chest', 0)
        keys = loot.get('key', 0)
        lockpickers = loot.get('lockpicker', 0)
        lottery_tickets = loot.get('lottery_ticket', 0)
        handmade_maps = loot.get("handmade_map", 0)
        
        # Нові тотеми
        teleport_totems = loot.get('teleport_totem', 0)
        random_totem = loot.get('random_totem', 0)
        control_totem = loot.get('control_totem', 0)
        lacrima = loot.get("lacrima", 0)

        # Форматування статусу для постійних тотемів
        has_random = "Наявний" if random_totem > 0 else "Немає"
        has_control = "Наявний" if control_totem > 0 else "Немає"
        has_lacrima = "Наявний" if lacrima > 0 else "Немає"

        lines = [
            f"🎟️ Квитки: <b>{lottery_tickets}</b>",
            f"🗝️ Ключі: <b>{keys}</b> | 🪛 Відмички: <b>{lockpickers}</b>",
            f"🗃 Скрині: <b>{chests}</b> | 🕋 Мега-скрині: <b>{mega_chests}</b>",
            f"🗺 Саморобні мапи: <b>{handmade_maps}</b>",
            f"🗿 Тотеми: <b>{teleport_totems}</b>",
            f"🎲🗿 Тотем хаосу: <b>{has_random}</b>",
            f"🎯🗿 Тотем контролю: <b>{has_control}</b>",
            f"⚗️ Лакрима: <b>{has_lacrima}</b>"
        ]
        
        content = "\n".join([l for l in lines if "<b>0</b>" not in l]) or "<i>Порожньо...</i>"

        # --- ЛОГІКА КНОПОК ВІДКРИТТЯ ---
        if chests > 0 or mega_chests > 0:            
            # Рядок для звичайної скрині
            if chests > 0:
                chest_btns = []
                if keys > 0:
                    chest_btns.append(types.InlineKeyboardButton(text="🗃 ⬅ 🗝", callback_data="open_chest:chest:key"))
                if lockpickers > 0:
                    chest_btns.append(types.InlineKeyboardButton(text="🗃 ⬅ 🪛", callback_data="open_chest:chest:lockpicker"))
                if chest_btns:
                    builder.row(*chest_btns)

            # Рядок для мега-скрині
            if mega_chests > 0:
                mega_btns = []
                if keys > 0:
                    mega_btns.append(types.InlineKeyboardButton(text="🕋 ⬅ 🗝", callback_data="open_chest:mega_chest:key"))
                if lockpickers > 0:
                    mega_btns.append(types.InlineKeyboardButton(text="🕋 ⬅ 🪛", callback_data="open_chest:mega_chest:lockpicker"))
                if mega_btns:
                    builder.row(*mega_btns)
            
            builder.adjust(2) # Це зробить кнопки в ряду однаковими за розміром
        # --- НОВА ЛОГІКА: КНОПКИ ДЛЯ СКАРБНИЦІ ---
        if has_handmade_map:
            # Створюємо кнопки для речей, які реально є в наявності
            bury_options = []
            if keys > 0: bury_options.append(types.InlineKeyboardButton(text="📥 Ключ", callback_data="put_in_chest:loot:key"))
            if lockpickers > 0: bury_options.append(types.InlineKeyboardButton(text="📥 Відмичку", callback_data="put_in_chest:loot:lockpicker"))
            if chests > 0: bury_options.append(types.InlineKeyboardButton(text="📥 Скриню", callback_data="put_in_chest:loot:chest"))
            if teleport_totems > 0: bury_options.append(types.InlineKeyboardButton(text="📥 Тотем", callback_data="put_in_chest:loot:teleport_totems"))
            if random_totem > 0: bury_options.append(types.InlineKeyboardButton(text="📥 Х-Тотем", callback_data="put_in_chest:loot:random_totem"))
            if control_totem > 0: bury_options.append(types.InlineKeyboardButton(text="📥 К-Тотем", callback_data="put_in_chest:loot:control_totem"))
            
            # Додаємо їх окремим рядком (або декількома)
            if bury_options:
                builder.row(types.InlineKeyboardButton(text="─── ЗАКОПАТИ ───", callback_data="none"))
                builder.row(*bury_options)
                
    elif page == "maps":
            title = "🗺 <b>Твої Карти</b>"
            maps = inv.get("loot", {}).get("treasure_maps", [])
            
            if not maps:
                content = "<i>У тебе немає жодної карти.</i>"
            else:
                TEMPLATES = {
                    "tomb": "⚰️ <b>Карта до могили №{id}</b>\n╰ Координати: <code>{pos}</code>\n<i>   Тут спочиває твій предок...</i>",
                    "boss_den": "💀 <b>Карта лігва Боса №{boss_num}</b>\n╰ Координати: <code>{pos}</code>",
                    "treasure": "📍 <b>Карта скарбів {id}</b>\n╰ Координати: <code>{pos}</code>",
                    "player_buried": "🏴‍☠️ <b>Твоя схованка #{id}</b>\n╰ Координати: <code>{pos}</code>\n{items_desc}"
                }

                map_entries = []
                for m in maps:
                    # Визначаємо ключ шаблону: якщо це скарб гравця, використовуємо специфічний шаблон
                    m_type = m.get("type", "treasure")
                    if m.get("origin") == "player_buried":
                        m_type = "player_buried"
                    
                    tpl = TEMPLATES.get(m_type, TEMPLATES["treasure"])
                    
                    # Формуємо список предметів для схованок гравця
                    items_desc = ""
                    if m_type == "player_buried":
                        chest_items = m.get("content", [])
                        if chest_items:
                            # Беремо назви перших 3-х предметів для короткого опису
                            names = []
                            for it in chest_items[:3]:
                                item_data = it.get("item", {})
                                name = item_data.get("name") or item_data.get("id") or "Предмет"
                                names.append(f"• {name}")
                            
                            items_desc = "<i>Зміст:</i>\n" + "\n".join(names)
                            if len(chest_items) > 3:
                                items_desc += f"\n... та ще {len(chest_items)-3} інше"
                        else:
                            items_desc = "<i>(Скриня порожня)</i>"

                    entry = tpl.format(
                        id=m.get('id', '???'),
                        pos=m.get('pos', '?,?'),
                        boss_num=m.get('boss_num', m.get('id', '???')),
                        items_desc=items_desc
                    )
                    map_entries.append(entry)
                    
                content = "\n\n".join(map_entries)

    elif page == "materials":
        title = "🧩 <b>Ресурси</b>"
        mats = inv.get("materials", {})
        # Перевіряємо наявність карти для закопування
        has_handmade_map = inv.get("loot", {}).get("handmade_map", 0) > 0
        
        mat_lines = [f"{DISPLAY_NAMES.get(k, k.capitalize())}: <b>{v}</b>" for k, v in mats.items() if v > 0]
        content = "Твої запаси:\n\n" + "\n".join(mat_lines) if mat_lines else "<i>Твій трюм порожній...</i>"

        if has_handmade_map:
            # Створюємо список кнопок для закопування ресурсів, які є в наявності
            bury_mats = []
            for mat_id, count in mats.items():
                if count > 0:
                    name = DISPLAY_NAMES.get(mat_id, mat_id.capitalize())[0]
                    bury_mats.append(types.InlineKeyboardButton(
                        text=f"📥 {name}", 
                        callback_data=f"put_in_chest:materials:{mat_id}")
                    )
            
            # Якщо є що закопувати, додаємо заголовок та кнопки
            if bury_mats:
                # Розбиваємо кнопки ресурсів по 2 в ряд для охайності
                builder.row(*bury_mats)
                builder.adjust(4)

    if not page.startswith("items"):
        pages_meta = {
            "food": "🍎 Їжа", "potions": "🧪 Зілля", "items": "⚔️ Речі", 
            "loot": "🧳 Лут", "maps": "🗺 Карти", "materials": "🌱 Ресурси"
        }
        nav_builder = InlineKeyboardBuilder()
        for p_key, p_text in pages_meta.items():
            btn_text = f"· {p_text} ·" if page.split(":")[0] == p_key else p_text
            cb_val = "inv_page:items:0:none:default" if p_key == "items" else f"inv_page:{p_key}:0"
            nav_builder.button(text=btn_text, callback_data=cb_val)
        nav_builder.adjust(2)
        builder.attach(nav_builder)
    
    if show_quicklinks:
        # Використовуємо окремий префікс для інвентарю, щоб пагінація чанка не ламала пагінацію предметів
        get_main_menu_chunk(builder, page=current_page, callback_prefix=f"inv_chunk:{page}")

    final_text = f"{title}\n━━━━━━━━━━━━\n{content}"
    
    # Рендеринг (додано обробку фото, якщо інвентар викликається з місця з картинкою)
    if is_callback:
        try:
            await message.edit_text(final_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except:
            # Якщо edit_text не спрацював (наприклад, було фото), видаляємо і шлемо заново
            await message.delete()
            await message.answer(final_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message.answer(final_text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("inv_page:"))
async def handle_inventory_pagination(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split(":")
    # Формат для items: inv_page : items : curr_p : selected_key : sort_mode : pX
    # Формат для інших: inv_page : category : chunk_p
    
    base_page = parts[1]
    
    # 1. Визначаємо сторінку списку предметів (для розділу амуніції)
    items_page = 0
    if base_page == "items" and len(parts) > 2:
        if parts[2].isdigit():
            items_page = int(parts[2])

    # 2. Шукаємо сторінку нижнього чанка (pX)
    chunk_page = 0
    for p in parts:
        if isinstance(p, str) and p.startswith("p") and p[1:].isdigit():
            chunk_page = int(p[1:])
            break
            
    # 3. Формуємо "чистий" рядок сторінки для render_inventory_page
    if base_page == "items":
        # Зберігаємо вибраний ключ та режим сортування
        selected_key = parts[3] if len(parts) > 3 else "none"
        sort_mode = parts[4] if len(parts) > 4 else "default"
        page_str = f"items:{selected_key}:{sort_mode}"
    else:
        # Для їжі, зілль тощо
        page_str = base_page
        if not items_page and len(parts) > 2 and parts[2].isdigit():
            chunk_page = int(parts[2]) # Якщо це звичайна пагінація категорії

    await render_inventory_page(
        callback.message, 
        callback.from_user.id, 
        db_pool, 
        page=page_str, 
        current_page=chunk_page, # Це сторінка чанка
        curr_p=items_page,       # Передаємо окремо сторінку предметів
        is_callback=True
    )
    await callback.answer()

@router.callback_query(F.data.startswith("inv_chunk:"))
async def handle_inventory_chunk_pagination(callback: types.CallbackQuery, db_pool):
    # data format: inv_chunk:base_page:p_index
    parts = callback.data.split(":")
    base_page = parts[1]
    chunk_page = int(parts[2].replace("p", ""))
    
    # Викликаємо рендер, передаючи поточну категорію та нову сторінку чанка
    await render_inventory_page(
        callback.message, 
        callback.from_user.id, 
        db_pool, 
        page=base_page, 
        current_page=chunk_page, 
        is_callback=True
    )
    await callback.answer()

@router.callback_query(F.data.startswith("inv_more:"))
async def handle_more_menu(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split(":")
    
    base_page = parts[1]
    current_page = int(parts[2]) if parts[2].isdigit() else 0
    sort_mode = parts[3] if len(parts) > 3 else "default"
    
    page_str = f"{base_page}:none:{sort_mode}"
    
    await render_inventory_page(
        callback.message, 
        callback.from_user.id, 
        db_pool, 
        page=page_str, 
        current_page=current_page, 
        is_callback=True, 
        show_more=True
    )

@router.callback_query(F.data.startswith("bulk_sell:"))
async def handle_bulk_sell(callback: types.CallbackQuery, db_pool):
    target_rarity = callback.data.split(":")[1]
    uid = callback.from_user.id
    prices = {"Common": 1, "Rare": 2, "Epic": 3, "Legendary": 5}
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, equipment FROM capybaras WHERE owner_id = $1", uid)
        inv, curr_eq = ensure_dict(row['inventory']), ensure_dict(row['equipment'])
        eq_dict = inv.setdefault("equipment", {})
        
        equipped_keys = {f"{v['name']}_{v['lvl']}" for v in curr_eq.values() if isinstance(v, dict)}
        
        reward, total_items_sold = 0, 0
        keys_to_delete = []

        for key, item_data in eq_dict.items():
            item = Item(**item_data)
            
            if item.rarity == target_rarity and item.lvl == 0 and key not in equipped_keys:
                reward += item.count * prices.get(target_rarity, 1)
                total_items_sold += item.count
                keys_to_delete.append(key)

        if total_items_sold == 0:
            return await callback.answer(f"❌ Немає вільних {target_rarity} Lvl 0", show_alert=True)
        
        for key in keys_to_delete:
            del eq_dict[key]

        inv.setdefault("food", {})["watermelon_slices"] = inv["food"].get("watermelon_slices", 0) + reward
        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv, ensure_ascii=False), uid)

    await callback.answer(f"♻️ Продано: {total_items_sold} шт. Отримано: {reward} 🍉", show_alert=True)
    await render_inventory_page(callback.message, uid, db_pool, page="items", is_callback=True)

@router.callback_query(F.data.startswith("sell_item:"))
async def handle_sell_equipment(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split(":")
    item_key = parts[1]
    mode = parts[2] if len(parts) > 2 else "one"
    uid = callback.from_user.id
    
    prices = {"Common": 1, "Rare": 2, "Epic": 3, "Legendary": 5, "Mythic": 10}

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, equipment FROM capybaras WHERE owner_id = $1", uid)
        if not row: return
        
        inv = ensure_dict(row['inventory'])
        curr_eq = ensure_dict(row['equipment'])
        eq_dict = inv.get("equipment", {})

        if item_key not in eq_dict:
            return await callback.answer("❌ Предмет не знайдено.", show_alert=True)

        target_data = eq_dict[item_key]
        target_name = target_data.get("name")
        
        total_reward = 0
        msg = ""

        if mode == "all_but_best":
            all_copies = [(k, v) for k, v in eq_dict.items() if v.get("name") == target_name]
            all_copies.sort(key=lambda x: x[1].get("lvl", 0), reverse=True)
            
            best_k = all_copies[0][0]
            to_remove = []

            for k, data in all_copies:
                if k == best_k: continue
                
                is_equipped = any(isinstance(v, dict) and v.get("name") == data["name"] and v.get("lvl") == data["lvl"] for v in curr_eq.values())
                
                if not is_equipped:
                    r = prices.get(data.get("rarity", "Common"), 1) + (10 * data.get("lvl", 0))
                    total_reward += r
                    to_remove.append(k)

            if not to_remove:
                return await callback.answer("У тебе лише один такий предмет або всі інші вдягнуті!", show_alert=True)

            for k in to_remove: del eq_dict[k]
            msg = f"♻️ Очищено {len(to_remove)} шт. Отримано: {total_reward} 🍉"

        else:
            is_equipped = any(isinstance(v, dict) and v.get("name") == target_data["name"] and v.get("lvl") == target_data["lvl"] for v in curr_eq.values())
            if is_equipped:
                return await callback.answer("❌ Не можна продати те, що вдягнуто!", show_alert=True)

            total_reward = prices.get(target_data.get("rarity", "Common"), 1) + (10 * target_data.get("lvl", 0))
            del eq_dict[item_key]
            msg = f"💰 Продано: {target_name} за {total_reward} 🍉"

        inv.setdefault("food", {})["watermelon_slices"] = inv.get("food", {}).get("watermelon_slices", 0) + total_reward
        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv, ensure_ascii=False), uid)

    await callback.answer(msg, show_alert=True if mode == "all_but_best" else False)
    await render_inventory_page(callback.message, uid, db_pool, page="items", is_callback=True)

@router.callback_query(F.data.startswith("equip:"))
async def handle_equip_item(callback: types.CallbackQuery, db_pool):
    _, itype, iname, ilvl = callback.data.split(":")
    ilvl, uid = int(ilvl), callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT equipment FROM capybaras WHERE owner_id = $1", uid)
        curr = ensure_dict(row['equipment'])
        
        is_already_wearing = (
            isinstance(curr.get(itype), dict) and 
            curr[itype].get("name") == iname and 
            curr[itype].get("lvl") == ilvl
        )

        if is_already_wearing:
            curr[itype] = {"name": "Лапки", "lvl": 0} if itype == "weapon" else None
            msg = "❌ Знято"
        else:
            curr[itype] = {"name": iname, "lvl": ilvl}
            msg = "✅ Одягнено"
            
        await conn.execute("UPDATE capybaras SET equipment = $1 WHERE owner_id = $2", json.dumps(curr, ensure_ascii=False), uid)
        
    await callback.answer(msg)
    await render_inventory_page(callback.message, uid, db_pool, page="items", is_callback=True)

@router.callback_query(F.data.startswith("put_in_chest:"))
async def handle_put_in_chest(callback: types.CallbackQuery, db_pool):
    # Безпечне розпакування
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer("⚠️ Помилка даних", show_alert=True)
        
    _, category, item_id = parts[:3]
    uid = callback.from_user.id

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT inventory, stamina FROM capybaras WHERE owner_id = $1
        """, uid)
        
        if not row: return
        
        inv = ensure_dict(row['inventory'])
        loot = inv.get("loot", {})
        
        # 1. Валідація: Чи є мапа, щоб "спланувати" схованку?
        if loot.get("handmade_map", 0) <= 0:
            return await callback.answer("📜 Вам потрібна Саморобна мапа, щоб почати збирати схованку!", show_alert=True)

        # 2. Витягування предмета з інвентаря
        item_to_bury = None
        
        if category == "food":
            items = inv.get("food", {})
            if items.get(item_id, 0) > 0:
                items[item_id] -= 1
                item_to_bury = {"type": "food", "id": item_id}
                if items[item_id] <= 0: del items[item_id]
                
        elif category == "potions":
            items = inv.get("potions", {})
            if items.get(item_id, 0) > 0:
                items[item_id] -= 1
                item_to_bury = {"type": "potion", "id": item_id}
                if items[item_id] <= 0: del items[item_id]

        elif category == "equipment":
            items = inv.get("equipment", {})
            if item_id in items:
                item_to_bury = items.pop(item_id)
                item_to_bury["type"] = "equipment"

        elif category == "loot":
            items = inv.get("loot", {})
            if items.get(item_id, 0) > 0:
                items[item_id] -= 1
                item_to_bury = {"type": "loot", "id": item_id}
                if items[item_id] <= 0: del items[item_id]

        elif category == "materials":
            items = inv.get("materials", {})
            if items.get(item_id, 0) > 0:
                items[item_id] -= 1
                item_to_bury = {"type": "material", "id": item_id}
                if items[item_id] <= 0: del items[item_id]

        if not item_to_bury:
            return await callback.answer("❌ Предмет не знайдено!", show_alert=True)

        # 3. Додавання до ГЛОБАЛЬНОЇ тимчасової скрині
        if "temporary_chest" not in inv:
            inv["temporary_chest"] = []
            
        inv["temporary_chest"].append({
            "item": item_to_bury,
            "time": datetime.datetime.now().isoformat()
        })

        # 4. Збереження в БД
        await conn.execute("""
            UPDATE capybaras SET inventory = $1 WHERE owner_id = $2
        """, json.dumps(inv, ensure_ascii=False), uid)

        count = len(inv["temporary_chest"])
        await callback.answer(f"📥 Предмет додано! У скрині зараз: {count} шт.", show_alert=True)
        
        # Оновлення сторінки інвентаря
        await render_inventory_page(callback.message, uid, db_pool, page=category, is_callback=True)