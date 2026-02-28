from aiogram import Router
from .onboarding import router as onboarding_router
from .profile.view import router as profile_router
from .hold.view import router as hold_router
from .harbor.view import router as harbor_router
from .adventures.view import router as adventures_router

def get_handlers_router() -> Router:
    router = Router()
    router.include_router(onboarding_router)
    router.include_router(profile_router)
    router.include_router(hold_router)
    router.include_router(harbor_router)
    router.include_router(adventures_router)
    return router