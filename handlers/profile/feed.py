import random
from aiogram import Router, F, types
from aiogram.filters import Command
#from database.queries.capybaras import try_feed_capybara
from utils.helpers import format_time
from datetime import datetime, timedelta
from utils.helpers import grant_exp_and_lvl

router = Router()

UPDATE_FEED_SQL = """
UPDATE capybaras 
SET 
    weight = weight + $2,
    hunger = 3,
    exp = exp + $2,
    last_feed = NOW()
WHERE owner_id = $1 
  AND (last_feed IS NULL OR last_feed <= NOW() - INTERVAL '8 hours')
RETURNING weight, last_feed;
"""

async def try_feed_capybara(db_pool, user_id: int, weight_gain: float):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(UPDATE_FEED_SQL, user_id, weight_gain)

@router.message(Command("feed"))
@router.callback_query(F.data == "feed_capy")
async def cmd_feed(event: types.Message | types.CallbackQuery, db_pool):
    is_callback = isinstance(event, types.CallbackQuery)
    message = event.message if is_callback else event
    user = event.from_user
    uid = user.id

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT weight, lvl, last_feed, name 
            FROM capybaras WHERE owner_id = $1
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

        gain = round(random.uniform(1.5, 5.0), 2)
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
        
        await grant_exp_and_lvl(uid, exp_gain=int(gain), weight_gain=0, bot=event.bot, db_pool=db_pool)

    await message.answer(
        f"🍎 Смакота!\n"
        f"Набрала: +{gain} кг (✨ +{gain} EXP)\n"
        f"Вага: {result['weight']} кг\n"
        f"🍏 Ситість: 3/3",
        parse_mode="HTML"
    )