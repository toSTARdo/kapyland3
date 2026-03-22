import json
from aiogram import Router, types, F
from aiogram.filters import Command, or_f
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.helpers import format_weight, next_lvl_exp, get_circle_bar, get_main_menu_chunk
from config import PROFILE_IMGS, STEPS_DATA, MOOD_SETS
from domain.base import Animal

router = Router()

def create_scale(current, max_val, emoji, empty_emoji='▫️'):
    current = max(0, min(int(current or 0), max_val))
    return f"{emoji * current}{empty_emoji * (max_val - current)} ({current}/{max_val})"

def get_stamina_icons(stamina):
    stamina = stamina or 0
    if stamina > 66: return "⚡⚡⚡"
    if stamina > 33: return "⚡⚡ ●"
    return "⚡ ● ●" if stamina > 0 else "● ● ●"

def get_profile_text(animal: Animal):

    race_set = MOOD_SETS.get(animal.race, MOOD_SETS["capybara"])
    current_mood = race_set.get("chill")
    visual_bar = get_circle_bar(animal.exp, next_lvl_exp(animal.level))
    ship_info = f"𓊝 {animal.ship_name}" if animal.ship_id else "⊥ Мандрує на плоті"

    return (
        f"<b>{current_mood} {animal.name}</b>\n"
        f"{ship_info}\n"
        f"________________________________\n\n"
        f"🌟 Рівень: <b>{animal.level}\n {animal.exp}/{next_lvl_exp(animal.level)} EXP</b>\n {visual_bar}\n"
        f"⚖️ Вага: <b>{format_weight(animal.weight):.2f} кг</b>\n\n"
        f"ХП: {create_scale(animal.stats.hp, animal.stats.hp, '♥️', '🖤')}\n"
        f"Ситість: {create_scale(animal.hunger, 3, '🍏', '●')}\n"
        f"Гігієна: {create_scale(animal.cleanness, 3, '🧼', '🦠')}\n"
        f"Енергія: <b>{get_stamina_icons(animal.stats.stamina)} ({animal.stats.max_stamina}/100)</b>"
    )

def get_profile_kb(animal: Animal, page=0, show_quicklinks=False):
    is_sleeping = animal.state.get("status") == "sleep" if animal.state.get("status") else False
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

    # Only add the menu chunk if the user has enabled it
    if show_quicklinks:
        get_main_menu_chunk(builder, page=page, callback_prefix="open_profile_main")
        
    return builder.as_markup()

@router.message(or_f(F.text.contains("🐾 Персонаж"), Command("profile")))
async def show_profile(message: types.Message, db_pool):
    from repositories.animal_repo import AnimalRepository
    repo = AnimalRepository(db_pool)
    animal = await repo.get_by_id(message.from_user.id)
    
    if not animal: 
        return await message.answer("❌ Тваринку не знайдено.")

    async with db_pool.acquire() as conn:
        # Fetching 'row' (our quicklinks toggle) along with tutorial
        user_data = await conn.fetchrow(
            "SELECT tutorial, quicklinks FROM users WHERE tg_id = $1", 
            message.from_user.id
        )
        
    tutorial = user_data['tutorial'] if user_data and user_data.get('tutorial') else {}
    if isinstance(tutorial, str): tutorial = json.loads(tutorial)
    
    # Check if 'row' is True (default to True if not set)
    quicklinks = user_data['quicklinks'] if user_data and user_data['quicklinks'] is not None else True

    if not tutorial.get("profile"):
        # Tutorial flow
        builder = InlineKeyboardBuilder()
        builder.button(text="📖 Посібник (Крок 1/8)", callback_data="tut_step:1")
        await message.answer_photo(
            photo=PROFILE_IMGS[animal.race],
            caption=get_profile_text(animal),
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    else:
        # Pass the quicklinks setting here
        await message.answer_photo(
            photo=PROFILE_IMGS[animal.race],
            caption=get_profile_text(animal),
            reply_markup=get_profile_kb(animal, show_quicklinks=quicklinks), 
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("open_profile_main"))
async def cb_return_to_profile(callback: types.CallbackQuery, db_pool):
    from repositories.animal_repo import AnimalRepository
    
    # 1. Parse page
    page = int(callback.data.split(":p")[1]) if ":p" in callback.data else 0
    
    # 2. Get Data & Settings
    repo = AnimalRepository(db_pool)
    animal = await repo.get_by_id(callback.from_user.id)
    
    async with db_pool.acquire() as conn:
        row_data = await conn.fetchval("SELECT quicklinks FROM users WHERE tg_id = $1", callback.from_user.id)
    
    quicklinks = row_data if row_data is not None else True

    # 3. Update UI
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=PROFILE_IMGS[animal.race],
                caption=get_profile_text(animal),
                parse_mode="HTML"
            ),
            reply_markup=get_profile_kb(animal, page, show_quicklinks=quicklinks)
        )
    except Exception:
        await callback.message.edit_reply_markup(
            reply_markup=get_profile_kb(animal, page, show_quicklinks=quicklinks)
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("tut_step:"))
async def tutorial_cascade(callback: types.CallbackQuery, db_pool):
    step = int(callback.data.split(":")[1])
    

    text, next_step = STEPS_DATA.get(step)

    # 1. Показуємо поточний алерт
    await callback.answer(text, show_alert=True)

    # 2. Логіка кнопок
    builder = InlineKeyboardBuilder()
    if next_step != 0:
        builder.button(text=f"➡️ Читати далі ({next_step}/8)", callback_data=f"tut_step:{next_step}")
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    else:
        # Фінал навчання: оновлюємо таблицю users
        async with db_pool.acquire() as conn:
            # Використовуємо COALESCE, щоб уникнути помилок з NULL
            await conn.execute(
                """
                UPDATE users 
                SET tutorial = COALESCE(tutorial, '{}'::jsonb) || '{"profile": true}'::jsonb 
                WHERE tg_id = $1
                """,
                callback.from_user.id
            )
        
        # Отримуємо тваринку через репозиторій для актуальної клавіатури
        from repositories.animal_repo import AnimalRepository
        repo = AnimalRepository(db_pool)
        animal = await repo.get_by_id(callback.from_user.id)
        
        # Повертаємо ігрові кнопки та видаляємо кнопку туторіалу
        if animal:
            await callback.message.edit_reply_markup(reply_markup=get_profile_kb(animal))
            await callback.message.answer("✅ Навчання завершено! Тепер ти готовий до пригод.")