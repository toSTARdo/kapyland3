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
from jobs.give_everyday_gift import send_daily_notification
from middlewares.capy_guard import CapyGuardMiddleware

# --- ІМПОРТИ НОВИХ ШАРІВ ---
from repositories.animal_repo import AnimalRepository
from repositories.quests_repo import QuestRepository
from services.quests_service import QuestService, OnboardingService

app = FastAPI()

@app.get("/")
async def health_check():
    return {"status": "OK", "version": config.VERSION}

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # 1. База даних
    db_pool = await create_pool()
    await init_pg(db_pool)
    
    # 2. Ініціалізація РЕПОЗИТОРІЇВ (Data Layer)
    # Вони знають тільки про базу даних
    animal_repo = AnimalRepository(db_pool)
    quest_repo = QuestRepository(db_pool)
    
    # 3. Ініціалізація СЕРВІСІВ (Logic Layer)
    # Вони знають про репозиторії та правила гри
    onboarding_service = OnboardingService(animal_repo)
    quest_service = QuestService(animal_repo, quest_repo)
    
    # 4. Бот та Диспетчер
    bot = Bot(token=config.TOKEN)
    dp = Dispatcher()
    
    # Передаємо об'єкти в контекст диспетчера (Dependency Injection)
    # Тепер у будь-якому хендлері можна написати: 
    # async def my_handler(..., onboarding_service: OnboardingService)
    dp["db_pool"] = db_pool
    dp["animal_repo"] = animal_repo
    dp["onboarding_service"] = onboarding_service
    dp["quest_service"] = quest_service

    # 5. Мідлварі
    dp.update.middleware(CapyGuardMiddleware())

    # 6. Планувальник завдань
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    scheduler.add_job(send_daily_notification, 'cron', hour=8, minute=0, args=[bot, db_pool])
    scheduler.add_job(send_goodnight, 'cron', hour=20, minute=00, args=[bot, db_pool])
    scheduler.start()

    # 7. Роутери
    dp.include_router(get_handlers_router())

    # 8. Запуск FastAPI та Бота паралельно
    config_uvicorn = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="error")
    server = uvicorn.Server(config_uvicorn)

    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
