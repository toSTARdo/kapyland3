from aiogram import Router, types, F
from aiogram.filters import Command, or_f
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import IMAGES_URLS

router = Router()

@router.callback_query(F.data == "open_village")
@router.message(F.text.lower().contains("містечко"))
async def open_village(event: types.Message | types.CallbackQuery):
    is_callback = isinstance(event, types.CallbackQuery)
    message = event.message if is_callback else event
    
    village_text = (
        "🛖 <b>Містечко Пух-Пух</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🏠 Тут пахне свіжою деревиною та апельсиновим соком. Життя вирує!\n\n"
        "⚗️ <b>Лавка Омо</b> — магічні зілля та еліксири\n"
        "🔨 <b>Кузня Ківі</b> — сталь, молот та крафт\n"
        "🎪 <b>Базар</b> — обмін скарбами"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⚗️ Лавка Омо", callback_data="open_alchemy"))
    builder.row(types.InlineKeyboardButton(text="🔨 Кузня Ківі", callback_data="open_forge"))
    builder.row(types.InlineKeyboardButton(text="🎪 Базар", callback_data="open_bazaar"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад до Порту", callback_data="open_port"))

    if is_callback:
        try:
            await message.edit_caption(
                caption=village_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception:
            await message.delete()
            await message.answer_photo(
                photo=IMAGES_URLS["village_main"],
                caption=village_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        await event.answer()
    else:
        await message.answer_photo(
            photo=IMAGES_URLS["village_main"],
            caption=village_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )