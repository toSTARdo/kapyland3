from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_map_keyboard(px: int, py: int, mode: str, trees_at_pos: bool = False):
    builder = InlineKeyboardBuilder()
    
    if trees_at_pos:
        builder.row(types.InlineKeyboardButton(
            text="🪓 Зрубати дерево (-5 ⚡)", 
            callback_data=f"chop:{px}:{py}")
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

def get_viewer_keyboard(vx: int, vy: int):
    builder = InlineKeyboardBuilder()
    
    builder.row(types.InlineKeyboardButton(text="⏫", callback_data=f"view:{vx}:{vy-10}"))
    builder.row(
        types.InlineKeyboardButton(text="⏪", callback_data=f"view:{vx-10}:{vy}"),
        types.InlineKeyboardButton(text="🔄 Центр", callback_data="open_map"), # Return to player
        types.InlineKeyboardButton(text="⏩", callback_data=f"view:{vx+10}:{vy}")
    )
    builder.row(types.InlineKeyboardButton(text="⏬", callback_data=f"view:{vx}:{vy+10}"))
    
    builder.row(types.InlineKeyboardButton(text="🔙 Закрити огляд", callback_data="open_map"))
    
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