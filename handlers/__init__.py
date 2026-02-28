from aiogram import Router
from .onboarding import router as onboarding_router
from .handlers.profile.view import router as profile_router

def get_handlers_router() -> Router:
    router = Router()
    router.include_router(onboarding_router)
    router.include_router(profile_router)
    return router