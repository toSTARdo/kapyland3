from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import IMAGES_URLS, DEV_ID

router = Router()

class SettingsStates(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_bug_report = State()

def get_settings_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(text="📝 Змінити ім'я", callback_data="change_name_start"))
    builder.row(InlineKeyboardButton(text="🎖 Обрати Титул", callback_data="open_titles_list"))
    builder.row(InlineKeyboardButton(text="📖 Довідник", callback_data="open_manual_main"))
    builder.row(InlineKeyboardButton(text="🎬 Переможна реакція (GIF)", callback_data="setup_victory_gif"))
    builder.row(InlineKeyboardButton(text="👾 Повідомити про баг", callback_data="report_bug_start"))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад до Порту", callback_data="open_port_main"))
    
    return builder.as_markup()

@router.message(F.text.startswith("⚙️"))
@router.callback_query(F.data == "open_settings")
async def show_settings(event: types.Message | types.CallbackQuery):
    is_callback = isinstance(event, types.CallbackQuery)
    message = event.message if is_callback else event
    
    text = "⚙️ <b>Налаштування капібари</b>\n\nТут ти можеш змінити ім'я свого улюбленця або налаштувати візуальні ефекти для перемог."
    
    if is_callback:
        await message.edit_caption(caption=text, reply_markup=get_settings_kb(), parse_mode="HTML")
    else:
        await message.answer_photo(
            photo=IMAGES_URLS["village_main"],
            caption=text,
            reply_markup=get_settings_kb(),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "change_name_start")
async def rename_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_new_name)
    await callback.message.answer("📝 Введи нове ім'я для своєї капібари (до 30 символів):")
    await callback.answer()

@router.message(SettingsStates.waiting_for_new_name)
async def rename_finish(message: types.Message, state: FSMContext, db_pool):
    new_name = message.text.strip()
    
    if len(new_name) > 30:
        return await message.answer("❌ Надто довге ім'я! Максимум — 30 символів.")

    uid = message.from_user.id
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE capybaras SET name = $1 WHERE owner_id = $2", 
            new_name, uid
        )

    await state.clear()
    await message.answer(
        f"✅ Готово! Тепер твою капібару звати <b>{new_name}</b>", 
        reply_markup=get_settings_kb(), 
        parse_mode="HTML"
    ) 

@router.callback_query(F.data == "report_bug_start")
async def report_bug_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_bug_report)
    await callback.message.answer(
        "🐜 <b>Опиши проблему</b>\n\nБудь ласка, напиши максимально детально, що пішло не так. Якщо є можливість — додай скріншот помилки.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_bug_report)
async def report_bug_finish(message: types.Message, state: FSMContext, bot):
    bug_text = message.text or "[Повідомлення без тексту, можливо фото]"
    user_info = f"Від: {message.from_user.full_name} (@{message.from_user.username}, ID: {message.from_user.id})"
    
    report_msg = f"🆘 <b>НОВИЙ БАГ-РЕПОРТ!</b>\n━━━━━━━━━━━━━━━\n{user_info}\n\n<b>Текст:</b>\n{bug_text}\n\n#bug"
    
    try:
        await bot.send_message(chat_id=DEV_ID, text=report_msg, parse_mode="HTML")
        if message.photo:
            await bot.send_photo(chat_id=DEV_ID, photo=message.photo[-1].file_id, caption="Фото до баг-репорту")
            
        await message.answer("✅ Дякуємо! Твій звіт надіслано розробникам. Ми скоро все полагодимо!", reply_markup=get_settings_kb())
    except Exception as e:
        await message.answer(f"❌ Помилка при надсиланні репорту: {e}")
    
    await state.clear()

@router.callback_query(F.data == "open_titles_list")
async def show_titles(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT unlocked_titles, state FROM capybaras WHERE owner_id = $1", 
            uid
        )
    
    if not row or not row['unlocked_titles']:
        return await callback.answer("❌ У тебе ще немає розблокованих титулів!", show_alert=True)

    titles = row['unlocked_titles']
    current_state = row['state'] if isinstance(row['state'], dict) else json.loads(row['state'] or '{}')
    current_title = current_state.get('current_title', "Немає")

    builder = InlineKeyboardBuilder()
    text = f"🎖 <b>Твої титули</b>\nПоточний: <b>{current_title}</b>\n\nОбери титул, який бачитимуть інші:"

    for title in titles:
        prefix = "✅ " if title == current_title else ""
        builder.button(text=f"{prefix}{title}", callback_data=f"set_title:{title}")

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="open_settings"))
    
    await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("set_title:"))
async def process_set_title(callback: types.CallbackQuery, db_pool):
    new_title = callback.data.split(":")[1]
    uid = callback.from_user.id

    async with db_pool.acquire() as conn:
        state_raw = await conn.fetchval("SELECT state FROM capybaras WHERE owner_id = $1", uid)
        state = state_raw if isinstance(state_raw, dict) else json.loads(state_raw or '{}')
        
        state['current_title'] = new_title
        
        await conn.execute(
            "UPDATE capybaras SET state = $1 WHERE owner_id = $2", 
            json.dumps(state, ensure_ascii=False), uid
        )

    await callback.answer(f"🎖 Титул «{new_title}» встановлено!")
    await show_titles(callback, db_pool) 

#MANUAL

def get_manual_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = [
        ("1. Тамагочі", "man_1"), ("2. Бойова система", "man_2"),
        ("3. Лотерея", "man_3"), ("4. Карта та Світ", "man_4"),
        ("5. Кузня (Крафт)", "man_5"), ("6. Алхімія", "man_6"),
        ("7. Базар", "man_7"), ("8. Міфічні предмети", "man_8"),
        ("9. Еволюція", "man_9")
    ]
    for text, callback in buttons:
        builder.add(InlineKeyboardButton(text=text, callback_data=callback))
    
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Назад до налаштувань", callback_data="open_settings"))
    return builder.as_markup()

@router.callback_query(F.data == "open_manual_main")
async def manual_main(callback: types.CallbackQuery):
    text = (
        "📖 <b>Бібліотека земель Мофу (v2.2.1)</b>\n\n"
        "Обери розділ, щоб зрозуміти математику та механіки гри. "
        "Всі розрахунки базуються на поточних константах сервера."
    )
    await callback.message.edit_caption(caption=text, reply_markup=get_manual_kb(), parse_mode="HTML")

@router.callback_query(F.data.startswith("man_"))
async def show_manual_detail(callback: types.CallbackQuery):
    page_id = callback.data.split("_")[-1]
    
    details = {
        "1": (
            "<b>1. Тамагочі</b>\n\n"
            "Життя капібари базується на витривалості:\n"
            "• Сон відновлює енергію - 100% за 2 години.\n"
            "• Їжа дає до 5 кг. Можна пастися раз на 8 годин\n"
            "• Також енергія відновлюється пасивно від 0 до 100% за 1 добу (~1⚡️/14хв).\n"
            "• Гігієна впливає на загальний стан. Не забувай купатись! Можна митися раз на 12 годин."
        ),
        "2": (
            "<b>2. Бойова система</b>\n\n"
            "Битви відбуваються автоматично (макс. 30 ходів). Якщо обидва бійці вижили — нічия.\n"
            "• <b>Базова атака:</b> 60% шансу влучити.\n"
            "• <b>Базовий захист:</b> 5% шанс заблокувати атаку.\n"
            "• <b>ATK (Атака):</b> Кожна одиниця додає +1% до шансу влучання (Макс: 90%).\n"
            "• <b>DEF (Захист):</b> Базовий блок 5%. Стати дають +0.5% за одиницю (Макс: 30%).\n"
            "• <b>AGI (Спритність):</b> +2% до шансу ухилення за одиницю (Макс: 40%).\n"
            "• <b>LCK (Удача):</b> +1% до шансу криту або спец. ефекту зброї (Макс.: 20%).\n"
            "• <b> Також кожна зброя має свою послідівність акивації ефектів, які можуть спрацьовувати при атаці." 
        ),
        "3": (
            "<b>3. Лотерея</b>\n\n"
            "Шанси на успіх:\n"
            "• ⚪️ Common: 67%\n"
            "• 🔵 Rare: 20%\n"
            "• 🟣 Epic: 10%\n"
            "• 💎 Legendary: 3%\n"
            "Твоя <b>Удача (LCK)</b> підвищує шанс знайти кращий лут на +1% за одиницю. [IN DEVELOPMENT]"
        ),
        "4": (
            "<b>4. Карта та Мандрівки</b>\n\n"
            "Світ має розмір 150x150.\n"
            "Витрати енергії:\n"
            "• Крок: 1⚡️ | Дуель: 5⚡️\n"
            "• Бійка (Brawl): 10⚡️ | Бос: 15⚡️\n"
            "• Крадіжка/Збір ресурсів: 5⚡️\n"
            "• На карті можна збирати ресурси, рубати дерева, знаходити скарби, лігва, та брати квести. \n"
            "• Також можна встановлювати тотеми для телепортації між ними. \n"
            "<b>AGI</b> допомагає уникати пасток (+3% за одиницю)."
        ),
        "5": (
            "<b>5. Кузня (Крафт)</b>\n\n"
            "Створення предметів із ресурсів. Використовуй 🪵 Деревину та інші матеріали. \n"
            "Кузня дозволяє покращувати предмети, максимум до 5 рівня."
        ),
        "6": (
            "<b>6. Алхімія</b>\n\n"
            "Змішуй трави, гриби та рибу щоб зварганити різноманітні зілля. \n"
            "Зілля дозволяють відновлювати енергію або мати інші перманентні ефекти."
        ),
        "7": (
            "<b>7. Базар</b>\n\n"
            "Торгівля ресурсами. Ціни та валюта на 🐟 рибу та 🥭 фрукти можуть змінюватися щотижня. "
        ),
        "8": (
            "<b>8. Реінкарнація</b>\n\n"
            "Коли фортуна обертається до тебе іншою стороною, ти можеш загинути і переродитися. Це очищує всі параметри, \n"
            "але дає постійні множники, роблячи кожне наступне життя сильнішим. [IN DEVELOPMENT]"
        ),
        "9": (
            "<b>9. Міфіки</b>\n\n"
            "Це предмети які можна крафтити у кузні з 20 рівня. Є три основні класи (🐦‍🔥 Фенікс, 🦄 Єдиноріг, 🐉 Дракон). \n"
            "Крафт потребує різні предмети з лотереї та виконання вимог."
        )
    }

    text = details.get(page_id, "Сторінка в розробці...")
    
    back_kb = InlineKeyboardBuilder()
    back_kb.row(InlineKeyboardButton(text="⬅️ До списку розділів", callback_data="open_manual_main"))
    
    await callback.message.edit_caption(caption=text, reply_markup=back_kb.as_markup(), parse_mode="HTML")
    await callback.answer()