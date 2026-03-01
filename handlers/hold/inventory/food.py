import asyncio
import json
import random
from aiogram import Router, types, html, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.helpers import grant_exp_and_lvl
from handlers.inventory.navigator import render_inventory_page

router = Router()

@router.callback_query(F.data.startswith("food_choice:"))
async def handle_food_choice(callback: types.CallbackQuery, db_pool):
    food_type = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        inv_json = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
    
    if inv_json is None:
        return await callback.answer("❌ Профіль не знайдено.")

    inv = json.loads(inv_json) if isinstance(inv_json, str) else inv_json
    count = inv.get("food", {}).get(food_type, 0)
    
    if count <= 0:
        return await callback.answer("Нічого немає! Кошик порожній... 🧺", show_alert=True)

    food_names = {"tangerines": "🍊", "melon": "🍈", "watermelon_slices": "🍉", "mango": "🥭", "kiwi": "🥝"}
    icon = food_names.get(food_type, "🍱")

    builder = InlineKeyboardBuilder()
    builder.button(text=f"🍴 З'їсти 1", callback_data=f"eat:one:{food_type}")
    
    if count > 1:
        builder.button(text=f"🍴 З'їсти все ({count})", callback_data=f"eat:all:{food_type}")
    
    builder.button(text="🔙 Назад", callback_data="inv_page:food:0")
    builder.adjust(1)

    await callback.message.edit_text(
        f"🍎 <b>Твій вибір: {icon}</b>\n<i>Смачного, маленька капібаро!</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("eat:"))
async def handle_eat(callback: types.CallbackQuery, db_pool):
    _, amount_type, food_type = callback.data.split(":")
    user_id = callback.from_user.id
    
    WEIGHT_TABLE = {
        "tangerines": 0.5,
        "watermelon_slices": 1.0,
        "melon": 5.0,
        "mango": 0.5,
        "kiwi": 0.5
    }
    
    async with db_pool.acquire() as conn:
        inv_json = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        if inv_json is None: return

        inv = json.loads(inv_json) if isinstance(inv_json, str) else inv_json
        current_count = inv.get("food", {}).get(food_type, 0)
        
        if current_count <= 0:
            await callback.answer("❌ Вже все з'їли!")
            return await render_inventory_page(callback.message, user_id, db_pool, page="food", is_callback=True)

        to_eat = 1 if amount_type == "one" else current_count
        unit_weight = WEIGHT_TABLE.get(food_type, 0.5)
        total_bonus = to_eat * unit_weight
        
        exp_gain = int(total_bonus)
        if total_bonus < 1 and random.random() < total_bonus:
            exp_gain = 1

        inv["food"][food_type] -= to_eat
        
        await conn.execute(
            "UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", 
            json.dumps(inv, ensure_ascii=False), user_id
        )

    res = await grant_exp_and_lvl(user_id, exp_gain=exp_gain, weight_gain=total_bonus, bot=callback.bot)

    if not res:
        return await callback.answer("🤔 Щось пішло не так з травленням...")
    
    await callback.answer(
        f"😋 Капі-ням!\n"
        f"⚖️ Вага: +{total_bonus} кг\n"
        f"✨ Досвід: +{exp_gain} EXP",
        show_alert=False
    )
    
    await render_inventory_page(callback.message, user_id, db_pool, page="food", is_callback=True)