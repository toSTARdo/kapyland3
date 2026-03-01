import asyncio
import logging
import uvicorn
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher


import config
from database.postgres_db import create_pool, init_pg
from handlers import get_handlers_router
from jobs.send_goodnight import send_goodnight
from jobs.give_everyday_gift import give_everyday_gift
from middlewares.capy_guard import CapyGuardMiddleware

app = FastAPI()

@app.get("/")
async def health_check():
    return {"status": "OK", "version": config.VERSION}

async def main():
    logging.basicConfig(level=logging.INFO)
    
    db_pool = await create_pool()
    await init_pg(db_pool)
    
    bot = Bot(token=config.TOKEN)
    dp = Dispatcher()
    dp.update.middleware(CapyGuardMiddleware())

    dp["db_pool"] = db_pool

    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    scheduler.add_job(give_everyday_gift, 'cron', hour=8, minute=0, args=[bot, db_pool])
    scheduler.add_job(send_goodnight, 'cron', hour=20, minute=0, args=[bot, db_pool])
    scheduler.start()

    dp.include_router(get_handlers_router())

    config_uvicorn = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="error")
    server = uvicorn.Server(config_uvicorn)

    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())