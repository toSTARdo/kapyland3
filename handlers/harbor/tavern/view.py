import logging
import json
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InputMediaPhoto
from config import IMAGES_URLS, SOCIAL_TUTS
from utils.helpers import ensure_dict, get_main_menu_chunk
from handlers.harbor.tavern.callbacks import *
from core.combat.battles import send_challenge

logger = logging.getLogger(__name__)

router = Router()

@router.message(F.text.startswith("🍻"))
@router.callback_query(F.data.startswith("social"))
async def cmd_arena_hub(event: types.Message | types.CallbackQuery, db_pool):
    is_callback = isinstance(event, types.CallbackQuery)
    uid = event.from_user.id
    message = event.message if is_callback else event

    # 1. Визначаємо сторінку чанка
    menu_page = 0
    if is_callback and ":p" in event.data:
        menu_page = int(event.data.split(":p")[1])

    async with db_pool.acquire() as conn:
        # Отримуємо топ гравців ТА налаштування швидкого меню (u.row)
        players = await conn.fetch("""
            SELECT u.tg_id, u.username, c.lvl, u.quicklinks
            FROM users u
            JOIN capybaras c ON u.tg_id = c.owner_id
            WHERE u.tg_id != $1 
            ORDER BY c.lvl DESC LIMIT 8
        """, uid)
        

        show_quicklinks = await conn.fetchval("SELECT quicklinks FROM users WHERE tg_id = $1", uid)
        if show_quicklinks is None: show_quicklinks = True

    builder = InlineKeyboardBuilder()

    # 2. Список гравців
    if players:
        for p in players:
            display_name = p['username'] or f"id:{p['tg_id']}"
            name = display_name[:12] + "..." if len(display_name) > 15 else display_name
            
            builder.row(types.InlineKeyboardButton(
                text=f"🐾 {name} (Lvl {p['lvl']})", 
                callback_data=f"user_menu:{p['tg_id']}")
            )
    
    # 3. Основні кнопки таверни
    builder.row(
        types.InlineKeyboardButton(text="🦜 Бій з Павликом", callback_data="fight_bot"),
        types.InlineKeyboardButton(text="🏆 Топ", callback_data="leaderboard")
    )
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад до Порту", callback_data="open_port_main"))

    # 4. Додаємо чанк навігації
    if show_quicklinks:
        get_main_menu_chunk(builder, page=menu_page, callback_prefix="social")

    text = (
        "⚔️ <b>Таверна «Гнилий Апельсин»</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "<i>Тут збираються найсильніші капібари-пірати, щоб помірятися хвостами та випити апельсинового елю.</i>"
    )

    # 5. Рендеринг
    if is_callback:
        new_media = InputMediaPhoto(
            media=IMAGES_URLS["tavern"],
            caption=text,
            parse_mode="HTML"
        )
        try:
            await event.message.edit_media(media=new_media, reply_markup=builder.as_markup())
        except Exception:
            await event.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await event.answer()
    else:
        await message.answer_photo(photo=IMAGES_URLS["tavern"], caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("user_menu:"))
async def user_menu_handler(callback: types.CallbackQuery, db_pool):
    target_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        players = await conn.fetch("""
            SELECT u.tg_id, u.username, c.lvl 
            FROM users u
            JOIN capybaras c ON u.tg_id = c.owner_id
            WHERE u.tg_id != $1 
            ORDER BY c.lvl DESC LIMIT 8
        """, uid)

    builder = InlineKeyboardBuilder()
    layout = []

    if not players:
        return await callback.answer("Гравців не знайдено 🕸", show_alert=True)

    for p in players:
        display_name = p['username'] or f"id:{p['tg_id']}"
        name = display_name[:12] + "..." if len(display_name) > 15 else display_name
        
        builder.row(types.InlineKeyboardButton(
            text=f"🐾 {name} (Lvl {p['lvl']})", 
            callback_data=f"user_menu:{p['tg_id']}")
        )
        layout.append(1)
        
        if p['tg_id'] == target_id:
            builder.row(
                types.InlineKeyboardButton(text="⚔️", callback_data=f"challenge_{target_id}"),
                types.InlineKeyboardButton(text="💞", callback_data=f"date_request:{target_id}"),
                types.InlineKeyboardButton(text="🎁", callback_data=f"gift_to:{target_id}"),
                types.InlineKeyboardButton(text="🧤", callback_data=f"steal_from:{target_id}"),
                types.InlineKeyboardButton(text="🪵", callback_data=f"ram:{target_id}"),
                types.InlineKeyboardButton(text="🔍", callback_data=f"inspect:{target_id}")
            )
            layout.append(6)

    builder.row(types.InlineKeyboardButton(text="🦜 Бій з Павликом", callback_data="fight_bot"))
    builder.row(types.InlineKeyboardButton(text="🏆 Топ", callback_data="leaderboard"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад до Порту", callback_data="open_port_main"))
    layout.extend([1, 1, 1])

    builder.adjust(*layout)

    try:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error updating user menu: {e}")
        
    await callback.answer()

@router.callback_query(F.data.regexp(r"^(challenge|date_request|gift_to|steal_from|ram|inspect):?"))
async def handle_social_actions_with_tut(callback: types.CallbackQuery, db_pool):
    # Витягуємо тип дії (наприклад, challenge)
    action = callback.data.split(":")[0].split("_")[0] 
    try:
        target_id = int(data_parts[1])
    except (IndexError, ValueError):
        return await callback.answer("Помилка: ID гравця не знайдено ❌")
    uid = callback.from_user.id

    async with db_pool.acquire() as conn:
        user_row = await conn.fetchrow("SELECT tutorial FROM users WHERE tg_id = $1", uid)
        tutorial = ensure_dict(user_row['tutorial']) if user_row else {}

    tut_key = f"soc_{action}"
    
    # Якщо є опис і юзер ще не бачив — показуємо алерт
    if action in SOCIAL_TUTS and not tutorial.get(tut_key):
        await callback.answer(SOCIAL_TUTS[action], show_alert=True)
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET tutorial = COALESCE(tutorial, '{}'::jsonb) || $1::jsonb WHERE tg_id = $2",
                json.dumps({tut_key: True}), uid
            )
    if action == "challenge":
        await send_challenge(callback, target_id, db_pool)
    elif action == "inspect":
        await show_user_profile_card(callback, target_id, db_pool)
    elif action == "gift_to":
        await gift_category_select(callback, target_id, db_pool)
    elif action == "steal_from":
        await execute_steal_logic(callback, target_id, db_pool)
    elif action == "date_request":
        await send_date_request(callback, target_id, db_pool)
    elif action == "ram":
        await execute_ram_logic(callback, target_id, db_pool)
    elif action == "inspect":
        await handle_inspect_player(callback, target_id, db_pool)
    else:
        await callback.answer(f"Дія {action} ще в розробці 🍊")