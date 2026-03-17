import random
from config import FULL_MAP

PLANTS_LOOT = {
    "herbs": [
        {"id": "mint", "name": "🌿 М'ята", "chance": 40},
        {"id": "thyme", "name": "🌱 Чебрець", "chance": 30},
        {"id": "rosemary", "name": "🌿 Розмарин", "chance": 10},
        {"id": "blueberry", "name": "🫐 Чорниця", "chance": 30},
    ],
    "flowers": [
        {"id": "chamomile", "name": "🌼 Ромашка", "chance": 35},
        {"id": "lavender", "name": "🪻 Лаванда", "chance": 25},
        {"id": "tulip", "name": "🌷 Тюльпан", "chance": 15},
        {"id": "lotus", "name": "🪷 Лотос", "chance": 5} 
    ]
}

MUSHROOMS_LOOT = [
    {"id": "fly_agaric", "name": "🍄 Мухомор", "chance": 9},
    {"id": "mushroom", "name": "🍄‍🟫 Гриб", "chance": 90},
    {"id": "truffel", "name": "🟤 Трюфель", "chance": 1}
]

COORD_QUESTS = {
    "15,129": "carpathian_pearl",
}

MIN_LVL_FOR_UROBOROSTREAM = 7
MIN_LVL_FOR_STARFJORDS = 20
MAP_HEIGHT = len(FULL_MAP)
MAP_WIDTH = len(FULL_MAP[0])
WATER_TILES = {"~", "༄", "꩜"}
WATER_TILES_DANGER = {"~":0.1, "༄":0.5, "꩜":1}
FOREST_TILES = {"𖠰", "𖣂"}
FOG_ICON = "░"

def get_random_plant():
    all_plants = PLANTS_LOOT["herbs"] + PLANTS_LOOT["flowers"]
    
    weights = [p['chance'] for p in all_plants]
    selected = random.choices(all_plants, weights=weights, k=1)[0]
    
    return selected

def get_random_mushroom():
    weights = [m['chance'] for m in MUSHROOMS_LOOT]
    return random.choices(MUSHROOMS_LOOT, weights=weights, k=1)[0]

def get_biome_name(py, map_height = MAP_HEIGHT):
    progress = py / map_height
    if progress < 0.35: return {"emoji": "❄️", "name": "Зорефьорди Ехвазу", "id": 3}
    elif 0.35 <= progress < 0.65: return {"emoji": "🌊", "name": "Уроборострім", "id": 2}
    else: return {"emoji": "🏝️", "name": "Архіпелаг Джуа", "id": 1} 
