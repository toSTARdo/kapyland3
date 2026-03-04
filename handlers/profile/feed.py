import random
import json
from aiogram import Router, F, types
from aiogram.filters import Command
from datetime import datetime, timedelta
from utils.helpers import format_time, grant_exp_and_lvl

router = Router()

UPDATE_FEED_SQL = """
UPDATE capybaras 
SET 
    weight = weight + $2,
    exp = exp + $2,
    hunger = 3,
    last_feed = NOW()
WHERE owner_id = $1;
"""

@router.message(Command("feed"))
@router.callback_query(F.data == "feed_capy")
async def cmd_feed(event: types.Message | types.CallbackQuery, db_pool):
    is_callback = isinstance(event, types.CallbackQuery)
    message = event.message if is_callback else event
    uid = event.from_user.id

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT c.weight, c.lvl, c.last_feed, c.name, u.reincarnation_multiplier 
            FROM capybaras c
            JOIN users u ON c.owner_id = u.tg_id
            WHERE c.owner_id = $1
        """, uid)
        
        if not row:
            return await message.answer("❌ Капібару не знайдено. Натисни /start")

        last_feed = row['last_feed']
        if last_feed:
            next_feed = last_feed + timedelta(hours=8)
            now = datetime.now(last_feed.tzinfo)
            if now < next_feed:
                remaining = next_feed - now
                time_str = format_time(remaining.total_seconds())
                msg = f"⏳ Капібара ще сита! Приходь через: {time_str}"
                if is_callback:
                    return await event.answer(msg, show_alert=True)
                return await message.answer(msg)

        reinc_mult = row['reincarnation_multiplier'] or 1.0
        base_gain = random.uniform(1.5, 5.0)
        gain = round(base_gain * reinc_mult, 2)
        
        current_weight = row['weight']
        current_lvl = row['lvl']
        
        max_safe_weight = 50 + (current_lvl * 10)
        new_weight = current_weight + gain
        
        pop_chance = 0
        if new_weight > max_safe_weight:
            pop_chance = (new_weight - max_safe_weight) * 0.1
            
        if random.random() < pop_chance:
            benefit = await handle_death(uid, db_pool, death_reason="Луснула від переїдання 🍉")
            
            death_text = (
                f"💥 <b>БА-БАХ!</b>\n\n"
                f"Шлунок {row['name']} не витримав такої кількості їжі і вибухнув!\n"
                f"✨ Але дух капібари переродився! Новий множник: <b>x{benefit.get('new_mult', 1.0)}</b>"
            )
            
            if is_callback:
                await event.answer("💥 БА-БАХ!", show_alert=True)
            return await message.answer(death_text, parse_mode="HTML")

        await conn.execute(UPDATE_FEED_SQL, uid, gain)
        await grant_exp_and_lvl(uid, exp_gain=0, weight_gain=0, bot=event.bot, db_pool=db_pool)

    mult_info = f" (x{reinc_mult} 💫)" if reinc_mult > 1 else ""
    success_text = (
        f"🍎 <b>Смакота!</b>\n"
        f"Набрала: +{gain} кг{mult_info} (✨ +{gain} EXP)\n"
        f"Поточна вага: <b>{round(new_weight, 2)} кг</b>\n"
        f"🍏 Ситість: 3/3"
    )

    if is_callback:
        await event.answer("🍎 Ням-ням!")
        await message.edit_text(success_text, parse_mode="HTML")
    else:
        await message.answer(success_text, parse_mode="HTML")

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
            JOIN users u ON c.owner_id = u.user_id
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
        
        max_safe_weight = 50 + (current_lvl * 10)
        new_weight = current_weight + total_bonus
        
        pop_chance = 0
        if new_weight > max_safe_weight:
            pop_chance = (new_weight - max_safe_weight) * 0.1
            
        if random.random() < pop_chance:
            await callback.answer("💥 БА-БАХ!", show_alert=True)
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
            "UPDATE capybaras SET inventory = $1, weight = weight + $3, exp = exp + $3 WHERE owner_id = $2", 
            json.dumps(inv, ensure_ascii=False), user_id, total_bonus
        )

    await grant_exp_and_lvl(user_id, exp_gain=0, weight_gain=0, bot=callback.bot, db_pool=db_pool)
    
    mult_text = f" (x{reinc_mult} 🔮)" if reinc_mult > 1 else ""
    await callback.answer(
        f"😋 Капі-ням!{mult_text}\n⚖️ +{total_bonus} кг\n✨ +{exp_gain} EXP"
    )
    
    await render_inventory_page(callback.message, user_id, db_pool, page="food", is_callback=True)