import json
import random
from datetime import datetime, timedelta, timezone
from aiogram import types, F, Router
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ARTIFACTS, DISPLAY_NAMES, IMAGES_URLS
from utils.helpers import get_main_menu_chunk
from handlers.harbor.village.forge import apply_pagination

router = Router()

CURRENCY_VALUE = {"watermelon_slices": 1, "tangerines": 5, "mango": 15, "kiwi": 50}
FOOD_ICONS = {"watermelon_slices": "🍉", "tangerines": "🍊", "mango": "🥭", "kiwi": "🥝"}

RESOURCES_POOL = [
    "mint", "thyme", "rosemary", "chamomile", "lavender", "tulip", "lotus",
    "fly_agaric", "mushroom", "wood",
    "carp", "perch", "pufferfish", "octopus", "crab", "jellyfish", "swordfish", "shark"
]

SELL_PRICES = {
    "mushroom": 2, "wood": 3, "chamomile": 4, "mint": 5, "thyme": 5,
    "rosemary": 7, "lavender": 10, "fly_agaric": 12, "tulip": 15, "lotus": 25,
    
    "jellyfish": 6, "carp": 8, "perch": 10, "crab": 12, 
    "pufferfish": 15, "octopus": 20, "swordfish": 25, "shark": 30
}

def get_item_name(item_key):
    if item_key in DISPLAY_NAMES: return DISPLAY_NAMES[item_key]
    for rarity in ARTIFACTS:
        for item in ARTIFACTS[rarity]:
            if item["name"] == item_key: return item["name"]
    return item_key

@router.callback_query(F.data.startswith("open_bazaar"))
async def open_bazaar(callback: types.CallbackQuery, db_pool):
    # 1. Витягуємо сторінку (дефолт 0)
    menu_page = 0
    if ":p" in callback.data:
        menu_page = int(callback.data.split(":p")[1])

    # 2. Отримуємо налаштування одним запитом
    async with db_pool.acquire() as conn:
        row_val = await conn.fetchval("SELECT quicklinks FROM users WHERE tg_id = $1", callback.from_user.id)
    
    quicklinks_enabled = row_val if row_val is not None else True

    # 3. Будуємо інтерфейс
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🍱 Купити", callback_data="bazaar_shop"),
        types.InlineKeyboardButton(text="💰 Продати", callback_data="bazaar_sell_list")
    )
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_village"))
    
    if quicklinks_enabled:
        get_main_menu_chunk(builder, page=menu_page, callback_prefix="open_bazaar")
    
    # 4. Оновлюємо медіа або тільки кнопки
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=IMAGES_URLS["bazaar"], 
                caption="🏺 <b>Базар Пух-пух</b>\n━━━━━━━━━━━━━━━━━━━━\nОбмінюй фрукти на артефакти або здавай свій вилов за соковиті кавуни!", 
                parse_mode="HTML"
            ),
            reply_markup=builder.as_markup()
        )
    except Exception:
        # Виконується, якщо фото те саме (наприклад, при гортанні чанка)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    
    await callback.answer()

@router.callback_query(F.data == "bazaar_shop")
async def bazaar_shop(callback: types.CallbackQuery, db_pool):
    state = await get_weekly_bazaar_stock(db_pool)
    stock = state["items"]
    next_up = datetime.fromisoformat(state["next_update"])
    
    builder = InlineKeyboardBuilder()
    text = f"🍱 <b>Асортимент</b> (до {next_up.strftime('%d.%m %H:%M')})\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for k, v in stock.items():
        name = get_item_name(k)
        icon = FOOD_ICONS[v['currency']]
        left = v.get('left', 0)
        status = f"{left} шт." if left > 0 else "❌ НЕМАЄ"
        text += f"<b>{name}</b>\n└ {icon} {v['cost']} | Залишилось: <b>{status}</b>\n\n"
        if left > 0:
            builder.button(text=f"Купити {name}", callback_data=f"b_pay:{v['currency']}:{v['cost']}:{k}")
    
    builder.button(text="⬅️ Назад", callback_data="open_bazaar")
    builder.adjust(1)
    await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
@router.callback_query(F.data.startswith("bazaar_sell_list"))
async def bazaar_sell_list(callback: types.CallbackQuery, db_pool):
    # Парсимо дані: bazaar_sell_list:{стор_товарів}:p{стор_чанка}
    parts = callback.data.split(":")
    
    # 1. Сторінка товарів базару (твоя функція)
    bazaar_page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    
    # 2. Сторінка швидких посилань
    chunk_page = 0
    for p in parts:
        if p.startswith("p") and p[1:].isdigit():
            chunk_page = int(p[1:])

    state = await get_weekly_bazaar_stock(db_pool)
    sell_prices = state.get("sell_prices", {})
    
    async with db_pool.acquire() as conn:
        data = await conn.fetchrow(
            "SELECT c.inventory, u.quicklinks FROM capybaras c "
            "JOIN users u ON c.owner_id = u.tg_id WHERE c.owner_id = $1", 
            callback.from_user.id
        )
        
    inv = data['inventory'] if isinstance(data['inventory'], dict) else json.loads(data['inventory'])
    show_quicklinks = data['quicklinks'] if data['quicklinks'] is not None else True

    builder = InlineKeyboardBuilder()
    
    # Формуємо список доступних для продажу предметів для твоєї функції
    sellable_items = []
    for cat in ["materials", "food"]:
        for item, count in inv.get(cat, {}).items():
            if item in sell_prices and count > 0:
                offer = sell_prices[item]
                name = get_item_name(item)
                price = f"{offer['val']}{FOOD_ICONS.get(offer['curr'], '🍉')}"
                # Формат: (callback_suffix, button_text)
                sellable_items.append((f"{item}:p{chunk_page}", f"📦 {name} ({count}) → {price}"))

    # ВИКОРИСТОВУЄМО ТВОЮ ФУНКЦІЮ
    # Вона додасть кнопки товарів та стрілки навігації (якщо треба)
    current_b_page = apply_pagination(
        builder=builder,
        all_items=sellable_items,
        page=bazaar_page,
        per_page=5,
        item_prefix="b_sell", # Для кнопок "Здати"
        nav_prefix=f"bazaar_sell_list" # Для стрілок вліво/вправо самого списку
    )

    # Додаємо параметри до кнопок навігації списку, щоб не губити p{chunk_page}
    # (Маленький фікс для кнопок, які згенерував apply_pagination)
    for row in builder.export():
        for btn in row:
            if btn.callback_data.startswith("bazaar_sell_list:") and ":p" not in btn.callback_data:
                btn.callback_data += f":p{chunk_page}"

    # Системні кнопки
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"open_bazaar:p{chunk_page}"))

    # ДОДАЄМО QUICKLINKS (Окремо від пагінації списку)
    if show_quicklinks:
        # Префікс для гортання кнопок знизу
        # Формат: bazaar_sell_list:{поточна_стор_базару}
        get_main_menu_chunk(builder, page=chunk_page, callback_prefix=f"bazaar_sell_list:{current_b_page}")

    text = "💰 <b>Скупка ресурсів</b>\n<i>Базар сьогодні купує:</i>\n\n"
    if not sellable_items:
        text += "<i>У тебе порожньо...</i>"

    await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

async def get_weekly_bazaar_stock(db_pool):
    async with db_pool.acquire() as conn:
        now = datetime.now(timezone.utc)
        row = await conn.fetchrow("SELECT value FROM world_state WHERE key = 'bazaar_weekly'")
        
        state = row['value'] if row and row['value'] else {}
        if isinstance(state, str): state = json.loads(state)
        
        if not state.get("next_update") or now > datetime.fromisoformat(state["next_update"]):
            new_stock = {}
            sorted_cur = sorted(CURRENCY_VALUE.items(), key=lambda x: x[1], reverse=True)

            all_gacha = [i["name"] for r in ARTIFACTS.values() for i in r]
            g_key = random.choice(all_gacha)
            g_curr = random.choice(list(CURRENCY_VALUE.keys()))
            new_stock[g_key] = {
                "cost": max(1, random.randint(150, 300) // CURRENCY_VALUE[g_curr]),
                "currency": g_curr, "cat": "loot", "left": 1
            }
            
            for res in random.sample(RESOURCES_POOL, 5):
                base_p = SELL_PRICES.get(res, 10)
                markup_price = int(base_p * random.uniform(1.3, 1.8))
                
                final_curr, final_cost = "watermelon_slices", markup_price
                for c_name, c_nom in sorted_cur:
                    if markup_price >= c_nom:
                        final_curr, final_cost = c_name, markup_price // c_nom
                        break
                
                new_stock[res] = {
                    "cost": max(1, final_cost),
                    "currency": final_curr, "cat": "materials", "left": random.randint(5, 15)
                }

            weekly_sell = {}
            for res_key, base_price in SELL_PRICES.items():
                target_curr, target_val = "watermelon_slices", base_price
                
                for curr_name, curr_nominal in sorted_cur:
                    if base_price >= curr_nominal:
                        target_curr = curr_name
                        target_val = base_price // curr_nominal
                        break
                
                weekly_sell[res_key] = {"curr": target_curr, "val": target_val}

            next_monday = (now + timedelta(days=(3 - now.weekday()))).replace(hour=0, minute=0, second=0, microsecond=0)
            
            state = {
                "items": new_stock, 
                "sell_prices": weekly_sell, 
                "next_update": next_monday.isoformat()
            }
            
            await conn.execute(
                "INSERT INTO world_state (key, value) VALUES ('bazaar_weekly', $1) "
                "ON CONFLICT (key) DO UPDATE SET value = $1", json.dumps(state)
            )
        return state

@router.callback_query(F.data.startswith("b_sell:"))
async def bazaar_process_sell(callback: types.CallbackQuery, db_pool):
    item_key = callback.data.split(":")[1]
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM world_state WHERE key = 'bazaar_weekly'")
        weekly_sell = json.loads(row['value']).get("sell_prices", {})
        
        if item_key not in weekly_sell:
            return await callback.answer("❌ Базар це не купує!", show_alert=True)
            
        offer = weekly_sell[item_key]
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", callback.from_user.id)
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        
        cat = "materials"
        if inv.get(cat, {}).get(item_key, 0) <= 0:
            return await callback.answer("❌ Вже немає!", show_alert=True)
            
        inv[cat][item_key] -= 1
        food = inv.setdefault("food", {})
        food[offer['curr']] = food.get(offer['curr'], 0) + offer['val']
        
        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv, ensure_ascii=False), callback.from_user.id)
        await callback.answer(f"✅ Отримано {FOOD_ICONS[offer['curr']]}{offer['val']}!")
        await bazaar_sell_list(callback, db_pool)

@router.callback_query(F.data.startswith("b_pay:"))
async def bazaar_process_pay(callback: types.CallbackQuery, db_pool):
    _, food_id, amount, item_key = callback.data.split(":")
    amount, user_id = int(amount), callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row_world = await conn.fetchrow("SELECT value FROM world_state WHERE key = 'bazaar_weekly'")
        state = json.loads(row_world['value'])
        stock = state["items"]

        if item_key not in stock or stock[item_key].get("left", 0) <= 0:
            return await callback.answer("❌ Товар закінчився!", show_alert=True)

        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw

        if inv.get("food", {}).get(food_id, 0) < amount:
            return await callback.answer("❌ Бракує їжі!", show_alert=True)

        inv["food"][food_id] -= amount
        cat = stock[item_key].get("cat", "materials")
        inv.setdefault(cat, {})[item_key] = inv[cat].get(item_key, 0) + 1
        stock[item_key]["left"] -= 1
        
        await conn.execute("UPDATE world_state SET value = $1 WHERE key = 'bazaar_weekly'", json.dumps(state))
        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv, ensure_ascii=False), user_id)
        
        await callback.answer(f"✅ Придбано! Залишилось: {stock[item_key]['left']}")
        await bazaar_shop(callback, db_pool)