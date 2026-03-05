import asyncio
import json
import random
from aiogram import Router, types, html, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.helpers import grant_exp_and_lvl
from handlers.hold.inventory.navigator import render_inventory_page
from core.reincarnation.death import handle_death

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
        "tangerines": 0.1,
        "watermelon_slices": 0.5,
        "melon": 5.0,
        "mango": 0.5,
        "kiwi": 0.1
    }
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT c.inventory, c.lvl, c.weight, u.reincarnation_multiplier 
            FROM capybaras c
            JOIN users u ON c.owner_id = u.tg_id
            WHERE c.owner_id = $1
        """, user_id)
        
        if not row: return

        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        current_lvl = row['lvl']
        current_weight = row['weight']
        reinc_mult = row['reincarnation_multiplier'] or 1.0
        
        current_count = inv.get("food", {}).get(food_type, 0)
        
        if current_count <= 0:
            await callback.answer("❌ Вже все з'їли!")
            return await render_inventory_page(callback.message, user_id, db_pool, page="food", is_callback=True)

        to_eat = 1 if amount_type == "one" else current_count
        unit_weight = WEIGHT_TABLE.get(food_type, 0.5)
        
        total_bonus = round(to_eat * unit_weight * reinc_mult, 2)
        
        safe_one_time_limit = 5.0 + (current_lvl * 0.5) 

        pop_chance = 0
        if total_bonus > safe_one_time_limit:
            excess = total_bonus - safe_one_time_limit
            pop_chance = min(0.95, excess * 0.01)

        if random.random() < pop_chance:
            await callback.answer("💥 БА-БАХ! Капібара луснула від жадібності!", show_alert=True)
            benefit = await handle_death(user_id, db_pool, death_reason="Луснула від переїдання 🍉")
            
            await callback.message.answer(
                f"💀 Твоя капібара не змогла вмістити стільки їжі і вибухнула!\n"
                f"✨ Але її дух сильніший за шлунок! Новий множник: x{benefit.get('new_mult', 1.0)}"
            )
            return

        exp_gain = int(total_bonus)
        if total_bonus < 1 and random.random() < total_bonus:
            exp_gain = 1

        inv["food"][food_type] -= to_eat
        await conn.execute(
            "UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", 
            json.dumps(inv, ensure_ascii=False), user_id
        )

    res = await grant_exp_and_lvl(user_id, exp_gain=exp_gain, weight_gain=total_bonus, bot=callback.bot, db_pool=db_pool)

    if not res:
        return await callback.answer("🤔 Щось пішло не так...")
    
    mult_text = f" (x{reinc_mult}) 💫" if reinc_mult > 1 else ""
    await callback.answer(
        f"😋 Капі-ням!{mult_text}\n"
        f"⚖️ Вага: +{total_bonus} кг\n"
        f"✨ Досвід: +{exp_gain} EXP",
        show_alert=False
    )
    
    await render_inventory_page(callback.message, user_id, db_pool, page="food", is_callback=True)