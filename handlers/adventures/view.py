from aiogram import Router, types, F
from aiogram.filters import Command, or_f
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

@router.message(or_f(F.text.contains("🧭 Пригоди"), Command("adventure")))
@router.callback_query(F.data == "open_adventure_main")
async def cmd_adventure(event: types.Message | types.CallbackQuery):
    is_callback = isinstance(event, types.CallbackQuery)
    builder = InlineKeyboardBuilder()
    
    builder.row(types.InlineKeyboardButton(text="🗺️ Карта світу", callback_data="open_map"))
    builder.row(
        types.InlineKeyboardButton(text="📜 Квести", callback_data="open_quests"),
        types.InlineKeyboardButton(text="🎣 Риболовля", callback_data="fish")
    )

    text = "🧭 <b>Морські пригоди</b>\n\nКуди відправимо твою капібару сьогодні?"

    if is_callback:
        try:
            await event.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except:
            pass
        await event.answer()
    else:
        await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
