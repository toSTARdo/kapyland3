from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

def get_main_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    
    builder.row(
        KeyboardButton(text="🐾 Капібара"),
        KeyboardButton(text="🎒 Трюм")
    )
    builder.row(
        KeyboardButton(text="🧭 Пригоди"),
        KeyboardButton(text="⚓ Порт")
    )
    
    return builder.as_markup(resize_keyboard=True)