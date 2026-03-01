from aiogram import Router
from .onboarding import router as onboarding_router
from .profile.view import router as profile_router
from .hold.view import router as hold_router
from .harbor.view import router as harbor_router
from .adventures.view import router as adventures_router
from .profile.feed import router as feed_router
from .profile.wash import router as wash_router
from .profile.fight_stats import router as fight_stats_router
from .profile.meditation import router as meditation_router
from .hold.lottery import router as lottery_router
from .hold.inventory.navigator import router as inventory_router
from .adventures.map.map import router as map_router
from .adventures.fishing import router as fishing_router
from .adventures.quests.quests import router as quests_router
from .harbor.tavern.view import router as tavern_router
from .harbor.village.view import router as village_router
from .harbor.ship.view import router as ship_router
from .harbor.settings.setting import router as settings_router
from .harbor.ship.callbacks import router as ship_callbacks_router
from .harbor.tavern.callbacks import router as tavern_callbacks_router
from .harbor.settings.emotes import router as emotes_router
from .harbor.village.alchemy import router as alchemy_router
from .harbor.village.bazaar import router as bazaar_router
from .harbor.village.forge import router as forge_router
from core.combat.battles import router as battles_router 

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
    router.include_router(meditation_router)
    router.include_router(lottery_router)
    router.include_router(inventory_router)
    router.include_router(map_router)
    router.include_router(fishing_router)
    router.include_router(quests_router)
    router.include_router(tavern_router)
    router.include_router(village_router)
    router.include_router(ship_router)
    router.include_router(settings_router)
    router.include_router(ship_callbacks_router)
    router.include_router(tavern_callbacks_router)
    router.include_router(emotes_router)
    router.include_router(alchemy_router)
    router.include_router(bazaar_router)
    router.include_router(forge_router)
    router.include_router(battles_router)
    return router