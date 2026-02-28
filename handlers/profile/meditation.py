import json
from aiogram import Router, types, F
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import IMAGES_URLS

router = Router()

@router.callback_query(F.data == "zen_upgrade")
async def meditation_menu(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT zen, atk, def, agi, luck FROM capybaras WHERE owner_id = $1", 
            uid
        )
    
    if not row: 
        return await callback.answer("❌ Капібару не знайдено.")
    
    text = (
        f"<b>Медитація капібари</b>\n\n"
        f"Використай духовну енергію для самовдосконалення.\n\n"
        f"❇️ Капі-дзен очки: <b>{row['zen']}</b>\n\n"
        f"⚔️ Атака (ATK): <b>{row['atk']}</b>\n"
        f"🛡️ Захист (DEF): <b>{row['def']}</b>\n"
        f"💨 Спритність (AGI): <b>{row['agi']}</b>\n"
        f"🍀 Удача (LCK): <b>{row['luck']}</b>\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⚔️ +1 ATK", callback_data="upgrade_stat:atk")
    builder.button(text="🛡️ +1 DEF", callback_data="upgrade_stat:def")
    builder.button(text="💨 +1 AGI", callback_data="upgrade_stat:agi")
    builder.button(text="🍀 +1 LCK", callback_data="upgrade_stat:luck")
    builder.button(text="🔙 Назад", callback_data="open_profile_main") 
    builder.adjust(2, 2, 1, 1)

    await callback.message.edit_media(
        media=InputMediaPhoto(media=IMAGES_URLS["meditation"], caption=text, parse_mode="HTML"),
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("upgrade_stat:"))
async def process_stat_upgrade(callback: types.CallbackQuery, db_pool):
    stat_map = {
        "atk": "atk", "defense": "def", "agility": "agi", 
        "luck": "luck"
    }
    
    stat_key = callback.data.split(":")[1]
    column = stat_map.get(stat_key, stat_key)
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        zen_points = await conn.fetchval("SELECT zen FROM capybaras WHERE owner_id = $1", uid)
        
        if not zen_points or zen_points < 1:
            return await callback.answer("🕯 Твоя чакра порожня... Треба більше капі-дзену!", show_alert=True)

        await conn.execute(f"""
            UPDATE capybaras 
            SET zen = zen - 1, {column} = {column} + 1 
            WHERE owner_id = $1
        """, uid)
    
    await callback.answer(f"✨ Оммм... {column.upper()} покращено!")
    
    await meditation_menu(callback, db_pool)