

async def handle_death(user_id: int, db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute('SELECT reincarnation_count, reincarnation_multiplier FROM user WHERE tg_id = $1', user_id)
    async with db_pool.acquire() as conn:
        capy = await conn.fetchrow('UPDATE user SET reincarnation_count = reincarnation_count + 1, reincarnation_multiplier = reincarnation_multiplier + 0.1 WHERE tg_id = $1 RETURNING *', user_id)