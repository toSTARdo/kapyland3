import json
from aiogram import html

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.helpers import get_main_menu_chunk

from config import IMAGES_URLS, DEV_ID

router = Router()

class SettingsStates(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_bug_report = State()

def get_settings_kb(quicklinks_enabled: bool = True, menu_page: int = 0) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        
        builder.row(
            InlineKeyboardButton(text="📝 Ім'я", callback_data="change_name_start"),
            InlineKeyboardButton(text="🎖 Титул", callback_data="open_titles_list")
        )
        
        builder.row(InlineKeyboardButton(text="🎬 Переможна реакція (GIF)", callback_data="setup_victory_gif"))
        
        builder.row(
            InlineKeyboardButton(text="📖 Довідник", callback_data="open_manual_main"),
            InlineKeyboardButton(text="🛠️ Повідомити", callback_data="report_start")
        )

        ql_status = "✅" if quicklinks_enabled else "❌"
        builder.row(InlineKeyboardButton(
            text=f"🔗 Швидкі посилання: {ql_status}", 
            callback_data="toggle_quicklinks"
        ))
        
        builder.row(InlineKeyboardButton(text="⬅️ Назад до Порту", callback_data="open_port_main"))
        
        if quicklinks_enabled:
            get_main_menu_chunk(builder, page=menu_page, callback_prefix="open_settings")
        
        return builder.as_markup()

@router.message(F.text.startswith("⚙️"))
@router.callback_query(F.data.startswith("open_settings"))
async def show_settings(event: types.Message | types.CallbackQuery, db_pool):
    is_callback = isinstance(event, types.CallbackQuery)
    user_id = event.from_user.id
    
    menu_page = 0
    if is_callback and ":p" in event.data:
        menu_page = int(event.data.split(":p")[1])

    async with db_pool.acquire() as conn:
        row_val = await conn.fetchval("SELECT quicklinks FROM users WHERE tg_id = $1", user_id)
        quicklinks_enabled = row_val if row_val is not None else True

    text = "⚙️ <b>Налаштування капібари</b>\n\nТут ти можеш змінити ім'я свого улюбленця або налаштувати швидке меню."
    kb = get_settings_kb(quicklinks_enabled, menu_page)
    
    if is_callback:
        try:
            await event.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
        except:
            try:
                await event.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
            except:
                await event.message.edit_reply_markup(reply_markup=kb)
        await event.answer()
    else:
        await event.answer_photo(photo=IMAGES_URLS["village_main"], caption=text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "toggle_quicklinks")
async def toggle_quicklinks(callback: types.CallbackQuery, db_pool):
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        new_val = await conn.fetchval(
            "UPDATE users SET quicklinks = NOT COALESCE(quicklinks, TRUE) WHERE tg_id = $1 RETURNING quicklinks", 
            user_id
        )

    await callback.answer(f"Меню {'увімкнено' if new_val else 'вимкнено'}")
    await callback.message.edit_reply_markup(reply_markup=get_settings_kb(quicklinks_enabled=new_val))

@router.callback_query(F.data == "change_name_start")
async def rename_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_new_name)
    await callback.message.answer("📝 Введи нове ім'я для своєї капібари (до 30 символів):")
    await callback.answer()

@router.message(SettingsStates.waiting_for_new_name)
async def rename_finish(message: types.Message, state: FSMContext, db_pool):
    new_name = html.quote(message.text.strip())
    
    if len(new_name) > 30:
        return await message.answer("❌ Надто довге ім'я! Максимум — 30 символів.")

    uid = message.from_user.id
    
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE capybaras SET name = $1 WHERE owner_id = $2", new_name, uid)
        quicklinks_enabled = await conn.fetchval("SELECT quicklinks FROM users WHERE tg_id = $1", uid)
        quicklinks_enabled = quicklinks_enabled if quicklinks_enabled is not None else True

    await state.clear()
    await message.answer(
        f"✅ Готово! Тепер твою капібару звати <b>{new_name}</b>", 
        reply_markup=get_settings_kb(quicklinks_enabled=quicklinks_enabled), 
        parse_mode="HTML"
    ) 

@router.callback_query(F.data == "report_start")
async def report_category_choice(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="👾 Баг", callback_data="report_type:bug")
    builder.button(text="💡 Пропозиції", callback_data="report_type:idea")
    builder.button(text="⚖️ Скарга/Баланс", callback_data="report_type:complaint")
    builder.button(text="❓ Інше", callback_data="report_type:other")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="open_settings"))

    await callback.message.answer(
        "📝 <b>Центр підтримки</b>\n\nОберіть тип вашого звернення:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("report_type:"))
async def report_bug_start(callback: types.CallbackQuery, state: FSMContext):
    report_type = callback.data.split(":")[1]
    await state.update_data(report_type=report_type)
    await state.set_state(SettingsStates.waiting_for_bug_report)
    
    prompts = {
        "bug": "Будь ласка, напиши максимально детально, що пішло не так. Якщо є можливість — додай скріншот помилки.",
        "idea": "Яку круту фічу ти хочеш бачити в Planet Mofu?",
        "complaint": "На що або на кого ти хочеш поскаржитися?",
        "other": "Напиши своє питання або пропозицію."
    }
    
    await callback.message.answer(
        f"✍️ <b>{prompts.get(report_type, 'Опишіть ваше звернення')}</b>\n\nМожна додати фото/скріншот.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(SettingsStates.waiting_for_bug_report)
async def report_finish(message: types.Message, state: FSMContext, bot, db_pool):
    data = await state.get_data()
    rep_type = data.get("report_type", "other")
    
    types_meta = {
        "bug": ("🐜 БАГ-РЕПОРТ", "#bug"),
        "idea": ("💡 НОВА ІДЕЯ", "#idea"),
        "complaint": ("⚖️ СКАРГА", "#complaint"),
        "other": ("❓ ЗВЕРНЕННЯ", "#other")
    }
    
    title, tag = types_meta.get(rep_type, ("❓ ЗВЕРНЕННЯ", "#other"))
    bug_text = message.text or message.caption or "[Текст відсутній]"
    user_info = (
        f"👤 <b>Від:</b> {html.quote(message.from_user.full_name)}\n"
        f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n"
        f"🔗 <b>Username:</b> @{message.from_user.username or 'немає'}"
    )
    
    report_msg = (
        f"🆘 <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{user_info}\n\n"
        f"📝 <b>Повідомлення:</b>\n{html.quote(bug_text)}\n\n"
        f"{tag}"
    )
    
    try:
        if message.photo:
            await bot.send_photo(chat_id=DEV_ID, photo=message.photo[-1].file_id, caption=report_msg, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=DEV_ID, text=report_msg, parse_mode="HTML")
            
        async with db_pool.acquire() as conn:
            ql = await conn.fetchval("SELECT quicklinks FROM users WHERE tg_id = $1", message.from_user.id)
            ql = ql if ql is not None else True

        await message.answer(
            "✅ <b>Надіслано!</b>\nДякуємо за допомогу у розвитку Planet Mofu.",
            parse_mode="HTML",
            reply_markup=get_settings_kb(quicklinks_enabled=ql)
        )
    except Exception as e:
        await message.answer(f"❌ Помилка при надсиланні: {e}")
    
    await state.clear()

@router.callback_query(F.data == "open_titles_list")
async def show_titles(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT unlocked_titles, state FROM capybaras WHERE owner_id = $1", uid)
    
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
        await conn.execute("UPDATE capybaras SET state = $1 WHERE owner_id = $2", json.dumps(state, ensure_ascii=False), uid)

    await callback.answer(f"🎖 Титул «{new_title}» встановлено!")
    await show_titles(callback, db_pool) 

def get_manual_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = [
        ("1. Тамагочі", "man_1"), ("2.1 Характеристики", "man_2_stats"),
        ("2.2 Логіка бою", "man_2_logic"), ("3. Лотерея", "man_3"), 
        ("4. Карта та Світ", "man_4"), ("5. Кузня (Крафт)", "man_5"), 
        ("6. Алхімія", "man_6"), ("7. Базар", "man_7"), 
        ("8. Реінкарнація", "man_8"), ("9. Міфіки", "man_9")
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
        "stats": (
            "<b>2.1 Характеристики (Stats)</b>\n\n"
            "Твої стати прямо впливають на ймовірності в бою:\n"
            "• <b>ATK (Атака):</b> Кожна одиниця додає +1% до шансу влучання (Макс: 90%). База — 60%.\n"
            "• <b>DEF (Захист):</b> Дає +0.5% до шансу блоку за одиницю (Макс: 30%). База — 5%.\n"
            "• <b>AGI (Спритність):</b> Дає +2% до шансу ухилення за одиницю (Макс: 40%).\n"
            "• <b>LCK (Удача):</b> +1% до шансу криту (Макс: 20%)."
        ),
        
        "logic": (
            "<b>2.2 Логіка та механіка бою</b>\n\n"
            "Битва — це покроковий процес (макс. 30 ходів):\n"
            "1. <b>Розрахунок ініціативи:</b> Хто б'є першим.\n"
            "2. <b>Перевірка влучання:</b> Шанс атакуючого мінус ухилення цілі.\n"
            "3. <b>Блок:</b> Якщо влучив, ціль може заблокувати частину шкоди.\n"
            "4. <b>Ефекти зброї:</b> Спрацьовують після успішного влучання згідно з пріоритетом.\n\n"
            "<i>Якщо за 30 ходів ніхто не впав — оголошується нічия.</i>"
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
