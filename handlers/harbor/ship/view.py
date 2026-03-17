import json
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InputMediaPhoto
from utils.helpers import get_main_menu_chunk

from config import IMAGES_URLS

router = Router()

@router.callback_query(F.data.startswith("ship_main"))
async def cmd_ship_menu(callback: types.CallbackQuery, state: FSMContext, db_pool):
    await state.clear()
    uid = callback.from_user.id
    message = callback.message
    
    # 1. Визначаємо сторінку чанка
    menu_page = 0
    if ":p" in callback.data:
        menu_page = int(callback.data.split(":p")[1])
    
    async with db_pool.acquire() as conn:
        # Додаємо JOIN з users для отримання налаштувань row (quicklinks)
        ship = await conn.fetchrow("""
            SELECT 
                s.id as ship_id, s.name as ship_name, s.lvl as ship_lvl, 
                s.gold, s.engine, s.meta, s.stats, s.cargo,
                c.owner_id as capy_owner_id,
                u.quicklinks
            FROM capybaras c
            JOIN users u ON c.owner_id = u.tg_id
            LEFT JOIN ships s ON c.ship_id = s.id
            WHERE c.owner_id = $1
        """, uid)

    if not ship: return await callback.answer("❌ Дані не знайдено.")

    # Отримуємо стан швидких посилань
    show_quicklinks = ship['quicklinks'] if ship['quicklinks'] is not None else True
    builder = InlineKeyboardBuilder()

    # Логіка, якщо корабля немає
    if ship['ship_id'] is None:
        text = (
            "🌊 <b>Ти — вільний плавець</b>\n\n"
            "У тебе поки немає власного судна. Ти можеш заснувати флот за <b>10 дерева</b> або приєднатися до існуючого екіпажу."
        )
        builder.row(types.InlineKeyboardButton(text="🔨 Збудувати корабель", callback_data="ship_create_init"))
        builder.row(types.InlineKeyboardButton(text="🔍 Пошук команди", callback_data="social"))
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад в порт", callback_data="open_port_main"))
    else:
        # Парсинг JSON
        def parse_json(data):
            if not data: return {}
            if isinstance(data, dict): return data
            try: return json.loads(data)
            except: return {}

        engine_data = parse_json(ship['engine'])
        engine_name = engine_data.get('name', 'Відсутній')
        ship_meta = parse_json(ship['meta'])
        flag = ship_meta.get('flag', '🏴‍☠️')
        
        is_captain = True # Тут можна додати реальну перевірку на капітана

        text = (
            f"𓊝 <b>[{flag}] Корабель: «{ship['ship_name']}»</b>\n"
            f"🎖 Рівень: {ship['ship_lvl']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🍉 Скарбниця: <b>{ship['gold']} шт.</b>\n"
            f"⚙️ Двигун: <b>{engine_name}</b>\n"
            f"🐾 Роль: {'👑 Капітан' if is_captain else '⚓ Матрос'}\n"
            f"━━━━━━━━━━━━━━━"
        )
        
        builder.row(
            types.InlineKeyboardButton(text="🐾 Екіпаж", callback_data=f"ship_crew:{ship['ship_id']}"),
            types.InlineKeyboardButton(text="🍉 Скарбниця", callback_data="ship_treasury")
        )
        builder.row(
            types.InlineKeyboardButton(text="⚙️ Машинне відділення", callback_data="ship_engine"),
            types.InlineKeyboardButton(text="🛠 Покращити", callback_data="ship_upgrade")
        )
        builder.row(types.InlineKeyboardButton(text="📨 Запросити", callback_data="ship_search_players"))
        
        if is_captain:
            builder.row(types.InlineKeyboardButton(text="⚙️ Налаштування", callback_data="ship_settings"))
        else:
            builder.row(types.InlineKeyboardButton(text="➜] Покинути борт", callback_data="ship_leave_confirm"))
            
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад в порт", callback_data="open_port_main"))

    # 2. Додаємо чанк навігації (якщо увімкнено)
    if show_quicklinks:
        get_main_menu_chunk(builder, page=menu_page, callback_prefix="ship_main")

    photo = IMAGES_URLS["harbor"]

    # 3. Рендеринг
    try:
        await message.edit_media(
            media=InputMediaPhoto(media=photo, caption=text, parse_mode="HTML"),
            reply_markup=builder.as_markup()
        )
    except Exception:
        try:
            await message.edit_reply_markup(reply_markup=builder.as_markup())
        except:
            await message.delete()
            await message.answer_photo(photo=photo, caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    await callback.answer()