import random
from aiogram import Router, F, types
from aiogram.filters import Command
from utils.helpers import format_time
from datetime import datetime, timedelta

router = Router()

UPDATE_WASH_SQL = """
UPDATE capybaras 
SET 
    cleanness = 3,
    exp = exp + 1,
    last_wash = NOW()
WHERE owner_id = $1 
  AND (last_wash IS NULL OR last_wash <= NOW() - INTERVAL '8 hours')
RETURNING cleanness, last_wash, exp;
"""

async def try_wash_capybara(db_pool, user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(UPDATE_WASH_SQL, user_id)

@router.message(Command("wash"))
@router.callback_query(F.data == "wash_capy")
async def cmd_wash(message: types.Message, db_pool):
    uid = message.from_user.id
    
    result = await try_wash_capybara(db_pool, uid)
    
    if not result:
        async with db_pool.acquire() as conn:
            last_wash = await conn.fetchval("SELECT last_wash FROM capybaras WHERE owner_id = $1", uid)
        
        if last_wash:
            next_wash = last_wash + timedelta(hours=8)
            remaining = next_wash - datetime.now(last_wash.tzinfo)
            time_str = format_time(remaining.total_seconds())
            return await message.answer(
                f"🧼 Капібара ще сяє!\n"
                f"Наступне купання через: {time_str}", 
                parse_mode="HTML"
            )
        
        return await message.answer("❌ Капібару не знайдено. Натисни /start")

    await message.answer(
        f"🧼 Буль-буль!\n\n"
        f"Ви ретельно помили капібару. Тепер вона пахне морським бризом!\n"
        f"✨ Отримано: +1 EXP\n"
        f"🫧 Гігієна: 3/3",
        parse_mode="HTML"
    )