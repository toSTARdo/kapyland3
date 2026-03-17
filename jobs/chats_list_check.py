from aiogram import types, F, Router
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, MEMBER, KICKED, LEFT
import logging

# 1. Створюємо окремий роутер для сервісних подій
service_router = Router()

@service_router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def bot_added_to_group(event: types.ChatMemberUpdated, db_pool):
    if event.chat.type in ["group", "supergroup"]:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO active_chats (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", 
                event.chat.id
            )
            logging.info(f"🆕 Нова локація знайдена: {event.chat.title}")

@service_router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED | LEFT))
async def bot_removed_from_group(event: types.ChatMemberUpdated, db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM active_chats WHERE chat_id = $1", event.chat.id)
        logging.info(f"🚫 Локація втрачена: {event.chat.id}")