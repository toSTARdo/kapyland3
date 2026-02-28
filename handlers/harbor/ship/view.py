import json
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InputMediaPhoto

from config import IMAGES_URLS

router = Router()

@router.callback_query(F.data == "ship_main")
async def cmd_ship_menu(event: types.Message | types.CallbackQuery, state: FSMContext, db_pool):
    await state.clear()
    uid = event.from_user.id
    is_callback = isinstance(event, types.CallbackQuery)
    message = event.message if is_callback else event
    
    async with db_pool.acquire() as conn:
        ship = await conn.fetchrow("""
            SELECT s.*, c.name as capy_name 
            FROM capybaras c
            LEFT JOIN ships s ON c.ship_id = s.id
            WHERE c.owner_id = $1
        """, uid)

    builder = InlineKeyboardBuilder()

    if not ship or ship['id'] is None:
        text = (
            "🌊 <b>Ти — вільний плавець</b>\n\n"
            "У тебе поки немає власного судна. Ти можеш заснувати флот за <b>10 дерева</b> або приєднатися до існуючого екіпажу."
        )
        builder.row(types.InlineKeyboardButton(text="🔨 Збудувати корабель", callback_data="ship_create_init"))
        builder.row(types.InlineKeyboardButton(text="🔍 Пошук команди", callback_data="leaderboard:mass:0"))
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад в порт", callback_data="open_port"))
    else:
        def parse_json(data):
            if isinstance(data, dict): return data
            if isinstance(data, str): return json.loads(data)
            return {}

        engine_data = parse_json(ship['engine'])
        engine_name = engine_data.get('name', 'Відсутній')
        
        ship_meta = parse_json(ship['meta'])
        flag = ship_meta.get('flag', '🏴‍☠️')
        
        text = (
            f"🚢 <b>{flag} Корабель: «{ship['name']}»</b>\n"
            f"🎖 Рівень: {ship['lvl']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🍉 Скарбниця: <b>{ship['gold']} шт.</b>\n"
            f"⚙️ Двигун: <b>{engine_name}</b>\n"
            f"👤 Роль: {'👑 Капітан' if ship['captain_id'] == uid else '⚓ Матрос'}\n"
            f"━━━━━━━━━━━━━━━"
        )
        
        builder.row(
            types.InlineKeyboardButton(text="👥 Екіпаж", callback_data=f"ship_crew:{ship['id']}"),
            types.InlineKeyboardButton(text="🍉 Скарбниця", callback_data="ship_treasury")
        )
        builder.row(
            types.InlineKeyboardButton(text="⚙️ Машинне відділення", callback_data="ship_engine"),
            types.InlineKeyboardButton(text="🛠 Покращити", callback_data="ship_upgrade")
        )
        builder.row(types.InlineKeyboardButton(text="📢 Запросити на борт", callback_data="ship_search_players"))
        
        if ship['captain_id'] == uid:
            builder.row(types.InlineKeyboardButton(text="⚙️ Налаштування", callback_data="ship_settings"))
        else:
            builder.row(types.InlineKeyboardButton(text="🏃 Покинути борт", callback_data="ship_leave_confirm"))
            
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад в порт", callback_data="open_port"))

    if is_callback:
        try:
            await message.edit_media(
                media=InputMediaPhoto(
                    media=IMAGES_URLS["harbor"], 
                    caption=text,
                    parse_mode="HTML"
                ),
                reply_markup=builder.as_markup()
            )
        except Exception:
            await message.answer_photo(
                photo=IMAGES_URLS["harbor"],
                caption=text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        await event.answer()
    else:
        await message.answer_photo(
            photo=IMAGES_URLS["harbor"],
            caption=text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )