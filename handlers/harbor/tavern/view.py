import logging
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InputMediaPhoto
from config import IMAGES_URLS

logger = logging.getLogger(__name__)

router = Router()

@router.message(F.text.startswith("🍻"))
@router.callback_query(F.data == "social")
async def cmd_arena_hub(event: types.Message | types.CallbackQuery, db_pool):
    is_callback = isinstance(event, types.CallbackQuery)
    uid = event.from_user.id
    message = event.message if is_callback else event

    async with db_pool.acquire() as conn:
        players = await conn.fetch("""
            SELECT u.tg_id, u.username, c.lvl 
            FROM users u
            JOIN capybaras c ON u.tg_id = c.owner_id
            WHERE u.tg_id != $1 
            ORDER BY c.lvl DESC LIMIT 8
        """, uid)

    builder = InlineKeyboardBuilder()

    if players:
        for p in players:
            display_name = p['username'] or f"id:{p['tg_id']}"
            name = display_name[:12] + "..." if len(display_name) > 15 else display_name
            
            builder.row(types.InlineKeyboardButton(
                text=f"🐾 {name} (Lvl {p['lvl']})", 
                callback_data=f"user_menu:{p['tg_id']}")
            )
    
    builder.row(
        types.InlineKeyboardButton(text="🤖 Бій з ботом", callback_data="fight_bot"),
        types.InlineKeyboardButton(text="🏆 Топ", callback_data="leaderboard")
    )
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад до Порту", callback_data="open_port_main"))

    text = (
        "⚔️ <b>Таверна «Гнилий Апельсин»</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "<i>Тут збираються найсильніші капібари-пірати, щоб помірятися хвостами та випити апельсинового елю.</i>"
    )

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
                types.InlineKeyboardButton(text="⚔️", callback_data=f"challenge:{target_id}"),
                types.InlineKeyboardButton(text="💞", callback_data=f"date_request:{target_id}"),
                types.InlineKeyboardButton(text="🎁", callback_data=f"gift_to:{target_id}"),
                types.InlineKeyboardButton(text="🧤", callback_data=f"steal_from:{target_id}"),
                types.InlineKeyboardButton(text="🪵", callback_data=f"ram:{target_id}"),
                types.InlineKeyboardButton(text="🔍", callback_data=f"inspect:{target_id}")
            )
            layout.append(6)

    builder.row(types.InlineKeyboardButton(text="🤖 Бій з ботом", callback_data="fight_bot"))
    builder.row(types.InlineKeyboardButton(text="🏆 Топ", callback_data="leaderboard"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад до Порту", callback_data="open_port_main"))
    layout.extend([1, 1, 1])

    builder.adjust(*layout)

    try:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error updating user menu: {e}")
        
    await callback.answer()