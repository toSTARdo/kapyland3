from aiogram import Router
from .onboarding import router as onboarding_router

def get_handlers_router() -> Router:
    router = Router()
    router.include_router(onboarding_router)
    return router