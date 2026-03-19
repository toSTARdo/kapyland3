import random
import json
from aiogram import Router, F, types
from aiogram.filters import Command
from datetime import datetime, timedelta
from utils.helpers import format_time, grant_exp_and_lvl
from handlers.hold.inventory.navigator import render_inventory_page
from core.reincarnation.death import handle_death 

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
        await event.answer(success_text, parse_mode="HTML")
    else:
        await message.answer(success_text, parse_mode="HTML")