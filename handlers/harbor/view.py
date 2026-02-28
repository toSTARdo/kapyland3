from aiogram import Router, types, F
from aiogram.filters import Command, or_f
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

@router.message(or_f(F.text.contains("⚓ Порт"), Command("harbor")))
@router.callback_query(F.data == "open_port_main")
async def cmd_port(event: types.Message | types.CallbackQuery):
    is_callback = isinstance(event, types.CallbackQuery)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🍻 Таверна", callback_data="social"),
        types.InlineKeyboardButton(text="⛵ Мій Корабель", callback_data="ship_main")
    )
    builder.row(
        types.InlineKeyboardButton(text="🛖 Містечко", callback_data="open_village"),
        types.InlineKeyboardButton(text="⚙️ Налаштування", callback_data="open_settings")
    )

    text = "⚓ <b>Порт Ліворн-Бей</b>\n\n<i>Життя тут вирує. Відвідай таверну та хутчіш на борт корабля!</i>"

    if is_callback:
        try:
            await event.message.edit_caption(
                caption=text, 
                reply_markup=builder.as_markup(), 
                parse_mode="HTML"
            )
        except Exception:
            await event.message.delete()
            await event.message.answer_photo(
                photo=IMAGES_URLS["village_main"],
                caption=text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        await event.answer()
    else:
        await event.answer_photo(
            photo=IMAGES_URLS["village_main"],
            caption=text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
