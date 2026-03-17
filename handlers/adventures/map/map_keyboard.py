import math
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_map_keyboard(px: int, py: int, mode: str, trees_at_pos: bool, inventory: dict, navigation: dict):
    builder = InlineKeyboardBuilder()

    loot = inventory.get("loot", {})
    # 1. Логіка скарбів: Закопати або Викопати
    my_treasure_maps = loot.get("treasure_maps", [])
    
    # Шукаємо саме той об'єкт, де збігаються координати ТА тип "my_treasure"
    is_my_treasure_here = any(
        t.get("pos") == f"{px},{py}" and t.get("type") == "my_treasure" 
        for t in my_treasure_maps
    )

    if is_my_treasure_here:
        # Якщо в цій точці є ВЛАСНИЙ закопаний скарб
        builder.row(types.InlineKeyboardButton(
            text="⛏ Викопати скарб з схованки", 
            callback_data=f"dig_treasure:{px}:{py}")
        )
    else:
        # Показуємо кнопку закопування, тільки якщо тут немає власного скарбу
        # і у гравця є порожня мапа в інвентарі
        if loot.get("handmade_map", 0) > 0:
            builder.row(types.InlineKeyboardButton(
                text="🪏 Закопати скарб", 
                callback_data=f"bury_treasure:{px}:{py}")
            )
    
    totems_in_loot = inventory.get("loot", {}).get("teleport_totem", 0)
    placed_totems = navigation.get("totems", [])
    
    if trees_at_pos:
        builder.row(types.InlineKeyboardButton(
            text="🪓 Зрубати дерево (-5 ⚡)", 
            callback_data=f"chop:{px}:{py}")
        )

    standing_on_totem = next((t for t in placed_totems if t['x'] == px and t['y'] == py), None)
    
    if standing_on_totem:
        builder.row(types.InlineKeyboardButton(
            text="🎒 Забрати тотем", 
            callback_data=f"map_pickup_totem:{standing_on_totem['id']}")
        )

    if totems_in_loot > 0 and len(placed_totems) < 3:
        builder.row(types.InlineKeyboardButton(
            text="🗿 Поставити тотем", 
            callback_data="map_place_totem")
        )

    is_near_totem = any(
    math.sqrt((px - t['x'])**2 + (py - t['y'])**2) <= 5 
    for t in placed_totems
    )

    if is_near_totem and len(placed_totems) > 1:
        for t in placed_totems:
            if not (t['x'] == px and t['y'] == py):
                builder.row(types.InlineKeyboardButton(
                    text=f"🌀 До тотему {t['name']} ({t['x']}, {t['y']})", 
                    callback_data=f"tp_to:{t['id']}")
                )

    if loot.get("random_totem", 0) > 0:
        builder.row(types.InlineKeyboardButton(
            text="🎲 Рандомний телепорт", 
            callback_data="use_random_totem")
        )

    # Контрольний тотем: дозволяє обрати координати (відкриває меню вводу)
    if loot.get("control_totem", 0) > 0:
        builder.row(types.InlineKeyboardButton(
            text="🎯 Точний телепорт", 
            callback_data="use_control_totem")
        )

    builder.row(types.InlineKeyboardButton(text="⬆️", callback_data=f"mv:up:{px}:{py}:{mode}"))
    builder.row(
        types.InlineKeyboardButton(text="⬅️", callback_data=f"mv:left:{px}:{py}:{mode}"),
        types.InlineKeyboardButton(text="⬇️", callback_data=f"mv:down:{px}:{py}:{mode}"),
        types.InlineKeyboardButton(text="➡️", callback_data=f"mv:right:{px}:{py}:{mode}")
    )
    
    builder.row(types.InlineKeyboardButton(text="🔭 Огляд", callback_data=f"view:{px}:{py}"))
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="open_adventure_main"))
    
    return builder.as_markup()

def get_viewer_keyboard(vx: int, vy: int, w: int = 20):
    builder = InlineKeyboardBuilder()
    
    # Крок переміщення залежить від зуму (чим ближче, тим менший крок)
    step = max(2, w // 4) 
    
    # Навігація
    builder.row(types.InlineKeyboardButton(text="⏫", callback_data=f"view:{vx}:{vy-step}:{w}"))
    builder.row(
        types.InlineKeyboardButton(text="⏪", callback_data=f"view:{vx-step}:{vy}:{w}"),
        types.InlineKeyboardButton(text="🔄 Центр", callback_data="open_map"),
        types.InlineKeyboardButton(text="⏩", callback_data=f"view:{vx+step}:{vy}:{w}")
    )
    builder.row(types.InlineKeyboardButton(text="⏬", callback_data=f"view:{vx}:{vy+step}:{w}"))
    
    # Кнопки Зум + / -
    # Обмежуємо зум від 10 (максимум близько) до 40 (максимум далеко)
    zoom_in = max(10, w - 6)
    zoom_out = min(40, w + 6)
    
    builder.row(
        types.InlineKeyboardButton(text="🔍 Збільшити (+)", callback_data=f"view:{vx}:{vy}:{zoom_in}"),
        types.InlineKeyboardButton(text="🔎 Зменшити (-)", callback_data=f"view:{vx}:{vy}:{zoom_out}")
    )
    
    builder.row(types.InlineKeyboardButton(text="🔙 Закрити", callback_data="open_map"))
    
    return builder.as_markup()
    
def get_group_redirect_kb(bot_username: str):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🗺️ Відкрити в особистих", 
        url=f"https://t.me/{bot_username}?start=map")
    )
    builder.row(types.InlineKeyboardButton(text="⚓ Відкрити тут", callback_data="force_map_group"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_adventure_main"))
    
    return builder.as_markup()