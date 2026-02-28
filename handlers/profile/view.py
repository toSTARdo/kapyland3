import json
from aiogram import Router, types, F
from aiogram.filters import Command, or_f
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import IMAGES_URLS

router = Router()

def create_scale(current, max_val, emoji, empty_emoji='▫️'):
    current = max(0, min(int(current or 0), max_val))
    return f"{emoji * current}{empty_emoji * (max_val - current)} ({current}/{max_val})"

def get_stamina_icons(stamina):
    stamina = stamina or 0
    if stamina > 66: return "⚡⚡⚡"
    if stamina > 33: return "⚡⚡ ●"
    return "⚡ ● ●" if stamina > 0 else "● ● ●"

def get_profile_text(data):
    return (
        f"<b>ദ്ദി₍ᐢ•(ܫ)•ᐢ₎ {data['name']}</b>\n"
        f"________________________________\n\n"
        f"🌟 Рівень: <b>{data['lvl']}</b> ({data['exp']} XP)\n"
        f"⚖️ Вага: <b>{data['weight']:.2f} кг</b>\n\n"
        f"ХП: {create_scale(data['hp'], 3, '♥️', '🖤')}\n"
        f"Ситість: {create_scale(data['hunger'], 3, '🍏', '●')}\n"
        f"Гігієна: {create_scale(data['cleanness'], 3, '🧼', '🦠')}\n"
        f"Енергія: <b>{get_stamina_icons(data['stamina'])} ({data['stamina']}/100)</b>"
    )

def get_profile_kb(state):
    """Generates the main profile keyboard based on current state."""
    is_sleeping = state.get("status") == "sleep" if state else False
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🍎 Їсти", callback_data="feed_capy")
    builder.button(text="🧼 Мити", callback_data="wash_capy")
    
    if is_sleeping:
        builder.button(text="☀️ Прокинутися", callback_data="wakeup_now")
    else:
        builder.button(text="💤 Сон", callback_data="sleep_capy")
        
    builder.button(text="⚔️ Характеристики", callback_data="show_fight_stats")
    builder.button(text="🪷 Медитація", callback_data="zen_upgrade")
    builder.adjust(3, 1, 1)
    return builder.as_markup()

@router.message(or_f(F.text.contains("🐾 Капібара"), Command("profile")))
async def show_profile(message: types.Message, db_pool):
    uid = message.from_user.id
    
    async with db_pool.acquire() as conn:
        data = await conn.fetchrow("SELECT * FROM capybaras WHERE owner_id = $1", uid)
    
    if not data: 
        return await message.answer("❌ Капібару не знайдено. Почни з /start")

    state = data['state']
    state = json.loads(state) if isinstance(state, str) else (state or {})

    await message.answer_photo(
        photo=IMAGES_URLS["profile"],
        caption=get_profile_text(data),
        reply_markup=get_profile_kb(state), 
        parse_mode="HTML"
    )

@router.callback_query(F.data == "open_profile_main")
async def cb_return_to_profile(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        data = await conn.fetchrow("SELECT * FROM capybaras WHERE owner_id = $1", uid)
    
    state = data['state']
    state = json.loads(state) if isinstance(state, str) else (state or {})

    await callback.message.delete()
    
    await callback.message.answer_photo(
        photo=IMAGES_URLS["profile"],
        caption=get_profile_text(data),
        reply_markup=get_profile_kb(state),
        parse_mode="HTML"
    )
    await callback.answer()