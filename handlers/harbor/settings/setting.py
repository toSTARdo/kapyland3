from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import IMAGES_URLS

router = Router()

class RenameStates(StatesGroup):
    waiting_for_new_name = State()

def get_settings_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(text="📝 Змінити ім'я", callback_data="change_name_start"))
    builder.row(InlineKeyboardButton(text="🎬 Переможна реакція (GIF)", callback_data="setup_victory_gif"))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад до Порту", callback_data="open_port_main"))
    
    return builder.as_markup()

@router.message(F.text.startswith("⚙️"))
@router.callback_query(F.data == "open_settings")
async def show_settings(event: types.Message | types.CallbackQuery):
    is_callback = isinstance(event, types.CallbackQuery)
    message = event.message if is_callback else event
    
    text = "⚙️ <b>Налаштування капібари</b>\n\nТут ти можеш змінити ім'я свого улюбленця або налаштувати візуальні ефекти для перемог."
    
    if is_callback:
        await message.edit_caption(caption=text, reply_markup=get_settings_kb(), parse_mode="HTML")
    else:
        await message.answer_photo(
            photo=IMAGES_URLS["village_main"],
            caption=text,
            reply_markup=get_settings_kb(),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "change_name_start")
async def rename_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(RenameStates.waiting_for_new_name)
    await callback.message.answer("📝 Введи нове ім'я для своєї капібари (до 30 символів):")
    await callback.answer()

@router.message(RenameStates.waiting_for_new_name)
async def rename_finish(message: types.Message, state: FSMContext, db_pool):
    new_name = message.text.strip()
    
    if len(new_name) > 30:
        return await message.answer("❌ Надто довге ім'я! Максимум — 30 символів.")

    uid = message.from_user.id
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE capybaras SET name = $1 WHERE owner_id = $2", 
            new_name, uid
        )

    await state.clear()
    await message.answer(
        f"✅ Готово! Тепер твою капібару звати <b>{new_name}</b>", 
        reply_markup=get_settings_kb(), 
        parse_mode="HTML"
    )