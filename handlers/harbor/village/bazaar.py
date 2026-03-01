import json
import random
from datetime import datetime, timedelta, timezone
from aiogram import types, F, Router
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ARTIFACTS, DISPLAY_NAMES, IMAGES_URLS

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

@router.callback_query(F.data == "open_bazaar")
async def open_bazaar(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🍱 Купити", callback_data="bazaar_shop"),
                types.InlineKeyboardButton(text="💰 Продати", callback_data="bazaar_sell_list"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_village"))
    
    await callback.message.edit_media(
        media=InputMediaPhoto(media=IMAGES_URLS["bazaar"], 
        caption="🏺 <b>Базар Пух-пух</b>\n━━━━━━━━━━━━━━━━━━━━\nОбмінюй фрукти на артефакти або здавай свій вилов за соковиті кавуни!", 
        parse_mode="HTML"),
        reply_markup=builder.as_markup()
    )

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
    
@router.callback_query(F.data == "bazaar_sell_list")
async def bazaar_sell_list(callback: types.CallbackQuery, db_pool):
    state = await get_weekly_bazaar_stock(db_pool)
    sell_prices = state.get("sell_prices", {})
    
    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", callback.from_user.id)
        inv = inv_raw if isinstance(inv_raw, dict) else json.loads(inv_raw)

    builder = InlineKeyboardBuilder()
    text = "💰 <b>Скупка ресурсів</b>\n<i>Базар сьогодні купує:</i>\n\n"
    
    found_any = False
    for cat in ["materials", "food"]:
        for item, count in inv.get(cat, {}).items():
            if item in sell_prices and count > 0:
                offer = sell_prices[item]
                price_text = f"{offer['val']} {FOOD_ICONS[offer['curr']]}"
                text += f"📦 {get_item_name(item)}: {count} шт. → <b>{price_text}</b>\n"
                builder.button(text=f"Здати {get_item_name(item)}", callback_data=f"b_sell:{item}")
                found_any = True

    if not found_any:
        text += "<i>У тебе немає нічого, що зацікавило б торгівців...</i>"
    
    builder.button(text="⬅️ Назад", callback_data="open_bazaar")
    builder.adjust(1)
    await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")

async def get_weekly_bazaar_stock(db_pool):
    async with db_pool.acquire() as conn:
        now = datetime.now(timezone.utc)
        row = await conn.fetchrow("SELECT value FROM world_state WHERE key = 'bazaar_weekly'")
        
        state = row['value'] if row and row['value'] else {}
        if isinstance(state, str): state = json.loads(state)
        
        if not state.get("next_update") or now > datetime.fromisoformat(state["next_update"]):
            new_stock = {}
            all_gacha = [i["name"] for r in ARTIFACTS.values() for i in r]
            g_key = random.choice(all_gacha)
            g_curr = random.choice(list(CURRENCY_VALUE.keys()))
            new_stock[g_key] = {
                "cost": max(1, random.randint(150, 300) // CURRENCY_VALUE[g_curr]),
                "currency": g_curr, "cat": "loot", "left": 1
            }
            
            # 2. Ресурси
            for res in random.sample(RESOURCES_POOL, 5):
                cat = "plants" if res in ["mint", "thyme", "rosemary", "chamomile", "lavender", "tulip", "lotus"] else "materials"
                
                r_curr = random.choice(list(CURRENCY_VALUE.keys()))
                base_price = SELL_PRICES.get(res, 10)
                new_stock[res] = {
                    "cost": max(1, int(base_price * random.uniform(1.3, 1.8)) // CURRENCY_VALUE[r_curr]),
                    "currency": r_curr, "cat": cat, "left": random.randint(5, 15)
                }

            weekly_sell = {}
            for res_key, base_price in SELL_PRICES.items():
                curr = random.choice(list(CURRENCY_VALUE.keys()))
                val = max(1, base_price // CURRENCY_VALUE[curr])
                weekly_sell[res_key] = {"curr": curr, "val": val}

            next_monday = (now + timedelta(days=(7 - now.weekday()))).replace(hour=0, minute=0, second=0, microsecond=0)
            
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
        
        cat = "plants" if item_key in ["mint", "thyme", "rosemary", "chamomile", "lavender", "tulip", "lotus"] else "materials"
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