from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram import Router, types, F
from aiogram.filters import Command

def get_main_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    
    builder.row(
        KeyboardButton(text="🐾 Персонаж"),
        KeyboardButton(text="🚪 Трюм")
    )
    builder.row(
        KeyboardButton(text="🧭 Пригоди"),
        KeyboardButton(text="⚓ Порт")
    )
    
    return builder.as_markup(resize_keyboard=True)

router = Router()

@router.message(Command("load_menu"))
async def load_menu_keyboard(message: types.Message):
    user_id = message.from_user.id
    main_kb = get_main_kb()
    
    # 1. Відправляємо "невидиме" повідомлення з новою клавіатурою
    temp_msg = await message.answer(
        "⚙️ Оновлення...", 
        reply_markup=main_kb
    )
    
    # 2. Видаляємо команду користувача та наше сервісне повідомлення
    try:
        await message.delete()      # видаляємо /load_menu
    except Exception:
        pass