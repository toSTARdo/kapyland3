from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import IMAGES_URLS, DEV_ID

router = Router()

class SettingsStates(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_bug_report = State()

def get_settings_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(text="📝 Змінити ім'я", callback_data="change_name_start"))
    builder.row(InlineKeyboardButton(text="🎬 Переможна реакція (GIF)", callback_data="setup_victory_gif"))
    builder.row(InlineKeyboardButton(text="👾 Повідомити про баг", callback_data="report_bug_start"))
    
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
    await state.set_state(SettingsStates.waiting_for_new_name)
    await callback.message.answer("📝 Введи нове ім'я для своєї капібари (до 30 символів):")
    await callback.answer()

@router.message(SettingsStates.waiting_for_new_name)
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

@router.callback_query(F.data == "report_bug_start")
async def report_bug_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_bug_report)
    await callback.message.answer(
        "🐜 <b>Опиши проблему</b>\n\nБудь ласка, напиши максимально детально, що пішло не так. Якщо є можливість — додай скріншот помилки.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_bug_report)
async def report_bug_finish(message: types.Message, state: FSMContext, bot):
    bug_text = message.text or "[Повідомлення без тексту, можливо фото]"
    user_info = f"Від: {message.from_user.full_name} (@{message.from_user.username}, ID: {message.from_user.id})"
    
    report_msg = f"🆘 <b>НОВИЙ БАГ-РЕПОРТ!</b>\n━━━━━━━━━━━━━━━\n{user_info}\n\n<b>Текст:</b>\n{bug_text}\n\n#bug"
    
    try:
        await bot.send_message(chat_id=DEV_ID, text=report_msg, parse_mode="HTML")
        if message.photo:
            await bot.send_photo(chat_id=DEV_ID, photo=message.photo[-1].file_id, caption="Фото до баг-репорту")
            
        await message.answer("✅ Дякуємо! Твій звіт надіслано розробникам. Ми скоро все полагодимо!", reply_markup=get_settings_kb())
    except Exception as e:
        await message.answer(f"❌ Помилка при надсиланні репорту: {e}")
    
    await state.clear()