from aiogram import Router, types, F
from aiogram.filters import Command, or_f
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

@router.message(or_f(F.text.contains("🚪 Трюм"), Command("hold")))
@router.callback_query(F.data == "open_inventory_main")
async def show_inventory_start(event: types.Message | types.CallbackQuery):
    is_callback = isinstance(event, types.CallbackQuery)
    builder = InlineKeyboardBuilder()
    
    builder.row(types.InlineKeyboardButton(text="🧺 Відкрити інвентар", callback_data="inv_page:food:0"))
    builder.row(types.InlineKeyboardButton(text="🎟️ Відкрити Газино", callback_data="lottery_menu"))
    
    text = "<i>Тут всі твої предмети та можна відвідати казино</i>"
    
    if is_callback:
        if event.message.photo: 
            await event.message.delete()
            await event.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else: 
            await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await event.answer()
    else: 
        await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")