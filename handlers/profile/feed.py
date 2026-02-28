import random
from aiogram import Router, F, types
from aiogram.filters import Command
#from database.queries.capybaras import try_feed_capybara
from utils.helpers import format_time
from datetime import datetime, timedelta

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
async def cmd_feed(message: types.Message, db_pool):
    uid = message.from_user.id
    
    gain = round(random.uniform(0, 5), 2)
    
    result = await try_feed_capybara(db_pool, uid, gain)
    
    if not result:
        async with db_pool.acquire() as conn:
            last_feed = await conn.fetchval("SELECT last_feed FROM capybaras WHERE owner_id = $1", uid)
        
        if last_feed:
            next_feed = last_feed + timedelta(hours=8)
            remaining = next_feed - datetime.now(last_feed.tzinfo)
            time_str = format_time(remaining.total_seconds())
            return await message.answer(f"⏳ Капібара ще сита! Приходь через: <b>{time_str}</b>", parse_mode="HTML")
        
        return await message.answer("❌ Капібару не знайдено. Натисни /start")

    await message.answer(
        f"🍎 Смакота!\n"
        f"Набрала: +{gain} кг (✨ +{gain} EXP)\n"
        f"Вага: {result['weight']} кг\n"
        f"🍏 Ситість: 3/3",
        parse_mode="HTML"
    )