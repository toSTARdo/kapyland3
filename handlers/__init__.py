from aiogram import Router
from .onboarding import router as onboarding_router
from .profile.view import router as profile_router
from .hold.view import router as hold_router
from .harbor.view import router as harbor_router
from .adventures.view import router as adventures_router
from .profile.feed import router as feed_router
from .profile.wash import router as wash_router
from .profile.fight_stats import router as fight_stats_router

def get_handlers_router() -> Router:
    router = Router()
    router.include_router(onboarding_router)
    router.include_router(profile_router)
    router.include_router(hold_router)
    router.include_router(harbor_router)
    router.include_router(adventures_router)
    router.include_router(feed_router)
    router.include_router(wash_router)
    router.include_router(fight_stats_router)
    return router