def send_goodnight(bot, db_pool):

    async def _send_goodnight():
        async with db_pool.acquire() as conn:
            rows = await conn.fetch('SELECT tg_id FROM users')
            user_ids = [row['tg_id'] for row in rows]

            for tg_id in user_ids:
                try:
                    await bot.send_message(tg_id, "🌙 Good night! Sleep well and have sweet dreams!")
                except Exception as e:
                    logger.error(f"Failed to send good night message to {tg_id}: {e}")

    asyncio.create_task(_send_goodnight())