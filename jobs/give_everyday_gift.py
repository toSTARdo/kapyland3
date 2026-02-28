def give_everyday_gift(bot, db_pool):

    async def _give_gift():
        async with db_pool.acquire() as conn:
            rows = await conn.fetch('SELECT tg_id FROM users')
            user_ids = [row['tg_id'] for row in rows]

            for tg_id in user_ids:
                try:
                    await bot.send_message(tg_id, "🎁 Your daily gift is here! Enjoy your day! 🎉")
                except Exception as e:
                    logger.error(f"Failed to send daily gift to {tg_id}: {e}")

    asyncio.create_task(_give_gift())