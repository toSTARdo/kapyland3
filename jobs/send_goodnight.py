import asyncio
import logging
import json
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramBadRequest

async def send_goodnight(bot: Bot, db_pool):
    logging.info("🌙 Запуск розсилки 'Капібарної ночі' по чатах...")
    
    async with db_pool.acquire() as conn:
        # 1. Отримуємо конфігурацію поста
        row = await conn.fetchrow("SELECT value FROM world_state WHERE key = 'goodnight_config'")
        current_id = 1126
        if row:
            config = json.loads(row['value'])
            current_id = config.get("last_post_id", 1126)
        else:
            await conn.execute(
                "INSERT INTO world_state (key, value) VALUES ($1, $2)",
                'goodnight_config', json.dumps({"last_post_id": current_id})
            )

        post_link = f"https://t.me/dobranich_kapy/{current_id}"
        message_text = (
            f"🌙 <b>Капібарної ночі всім чатерам!</b>\n\n"
            f"👉 <a href='{post_link}'>Подивитись на інші вечірні капібари</a>"
        )

        # 2. Беремо список чатів з нашої "динамічної" таблиці active_chats
        chat_rows = await conn.fetch("SELECT chat_id FROM active_chats")
        # Додаємо DEV_ID окремо, якщо його немає в списку чатів
        target_ids = {r['chat_id'] for r in chat_rows}
        from config import DEV_ID
        target_ids.add(DEV_ID)

        success = 0
        errors = 0
        removed_chats = 0

        # 3. Розсилка
        for cid in target_ids:
            try:
                await bot.send_message(
                    chat_id=cid,
                    text=message_text,
                    parse_mode="HTML",
                    disable_web_page_preview=False
                )
                success += 1
                await asyncio.sleep(0.05) # ~20 повідомлень на секунду
            
            except TelegramForbiddenError:
                # Бот заблокований або видалений — видаляємо з бази
                await conn.execute("DELETE FROM active_chats WHERE chat_id = $1", cid)
                removed_chats += 1
                logging.warning(f"🚫 Бот видалений з чату {cid}, видаляю з бази.")
            
            except TelegramBadRequest as e:
                if "chat not found" in str(e).lower():
                    await conn.execute("DELETE FROM active_chats WHERE chat_id = $1", cid)
                    removed_chats += 1
                errors += 1

            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                await bot.send_message(cid, message_text, parse_mode="HTML")
                success += 1
            
            except Exception as e:
                logging.error(f"Помилка в чаті {cid}: {e}")
                errors += 1

        # 4. Оновлюємо лічильник
        new_id = current_id + 1
        await conn.execute(
            "UPDATE world_state SET value = $1 WHERE key = 'goodnight_config'",
            json.dumps({"last_post_id": new_id})
        )

        # 5. Детальний звіт
        report = (
            f"📊 <b>Звіт розсилки:</b>\n"
            f"✅ Успішно: {success}\n"
            f"❌ Помилок: {errors}\n"
            f"🧹 Видалено мертвих чатів: {removed_chats}\n"
            f"🆔 Наступний ID: {new_id}"
        )
        await bot.send_message(chat_id=DEV_ID, text=report, parse_mode="HTML")