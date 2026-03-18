import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import IMAGES_URLS

logger = logging.getLogger(__name__)

async def send_daily_notification(bot: Bot, db_pool):
    """Функція для розсилки повідомлень про нагороду"""
    async with db_pool.acquire() as conn:
        # Беремо тих, хто заходив останні 3 дні, щоб не спамити мертвим аккаунтам
        active_threshold = int(datetime.now().timestamp()) - 259200
        rows = await conn.fetch(
            "SELECT owner_id FROM capybaras WHERE last_seen > $1", 
            active_threshold
        )
        
        count = 0
        for row in rows:
            uid = row['owner_id']
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎁 Забрати подарунок", callback_data="claim_daily")]
                ])
                
                await bot.send_photo(
                    chat_id=uid,
                    photo=IMAGES_URLS["delivery"],
                    caption=(
                        "🎁 <b>Ранкова пошта Архіпелагу!</b>\n\n"
                        "Чайки-поштарі щось принесли. Швидше перевір, що там у пакунку!"
                    ),
                    reply_markup=kb,
                    parse_mode="HTML"
                )
                count += 1
                await asyncio.sleep(0.05) # Захист від Flood Limit
            except Exception as e:
                logger.error(f"Помилка розсилки для {uid}: {e}")
        
        logger.info(f"Розсилка завершена. Надіслано {count} повідомлень.")