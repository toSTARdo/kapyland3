import asyncio
import json
import logging
from config import IMAGES_URLS

logger = logging.getLogger(__name__)

async def give_everyday_gift(bot, db_pool):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch('SELECT owner_id, inventory FROM capybaras')
        
        for row in rows:
            uid = row['owner_id']
            inv_raw = row['inventory']
            
            try:
                inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
                
                if "loot" not in inv:
                    inv["loot"] = {}
                inv["loot"]["lottery_ticket"] = inv["loot"].get("lottery_ticket", 0) + 1
                
                await conn.execute(
                    "UPDATE capybaras SET inventory = $1 WHERE owner_id = $2",
                    json.dumps(inv, ensure_ascii=False), uid
                )

                caption = (
                    "🎁 <b>Ранкова пошта Архіпелагу!</b>\n\n"
                    "Поки ви спали, чайки-поштарі принесли вам 🎟 <b>Лотерейний квиток</b>.\n"
                    "Він уже чекає у вашому інвентарі. Гарного дня!"
                )
                
                await bot.send_photo(
                    chat_id=uid,
                    photo=IMAGES_URLS["delivery"],
                    caption=caption,
                    parse_mode="HTML"
                )
                
                await asyncio.sleep(0.05) 

            except Exception as e:
                logger.error(f"Не вдалося надіслати квиток користувачу {uid}: {e}")
