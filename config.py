import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DEV_ID = os.getenv("DEV_ID")
MONGO_URL = os.getenv("MONGO_URL")
POSTGRE_URL = os.getenv("POSTGRE_URL")

VERSION = "2.2.0"


IMAGES_URLS = {
    "profile": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_profile.jpg",
    "village_main": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_village1.png",
    "delivery": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_delivery.png",
    "forge": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_forge.jpg",
    "alchemy": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_alchemy.jpg",
    "harbor": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_harbor.jpg",
    "bazaar": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_bazaar.jpg",
    "meditation": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_meditation.jpg",
    "tavern": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_tavern.jpg",
    "fishing": "https://raw.githubusercontent.com/toSTARdo/kapyland3/main/assets/capyimg_fishing.jpg"
}

    #STAMINA_CONST:
STAMINA_COSTS = {
    "move": 1,
    "fight_1v1": 5,
    "brawl": 10,
    "boss": 15,
    "guild_boss": 5,
    "ram": 15,
    "steal": 5,
    "chop": 5
}

    #FIGHT_CONSTS:
BASE_HIT_CHANCE = 0.60
BASE_HEARTS = 3
UNITS_PER_HEART = 2
BASE_HITPOINTS = BASE_HEARTS * UNITS_PER_HEART
BASE_BLOCK_CHANCE = 0.05
STAT_WEIGHTS = {
    # FIGHT
    "atk_to_hit": 0.04,
    "def_to_block": 0.05,
    "agi_to_dodge": 0.03,
    "luck_to_crit": 0.02,
    
    # NON-FIGHT
    "agi_to_trap": 0.03,
    "def_to_anti_steal": 0.05,
    "luck_to_drop": 0.01,
    "luck_to_steal": 0.01,
    "end_to_energy": 0.05
}

    #ECONOMY_СONSTS:
DROP_RATES = {
    "common": 0.67,
    "rare": 0.20,
    "epic": 0.10,
    "legendary": 0.03
}

RARITY_META = {
    "Common": {"emoji": "⚪️", "label": "Звичайний", "color": 0x808080},
    "Rare": {"emoji": "🔵", "label": "Рідкісний", "color": 0x0000FF},
    "Epic": {"emoji": "🟣", "label": "Епічний", "color": 0xA020F0},
    "Legendary": {"emoji": "💎", "label": "Легендарний", "color": 0xFFD700}
}