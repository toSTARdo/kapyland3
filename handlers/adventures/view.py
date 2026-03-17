import json
from aiogram import Router, types, F
from aiogram.filters import Command, or_f
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.helpers import ensure_dict
from handlers.adventures.quests.quests import cmd_quests_board
from handlers.adventures.map.map import render_map
from handlers.adventures.fishing import handle_fishing

router = Router()

# Словник підказок у стилі профілю
ADVENTURE_TUTS = {
    "open_map": (
        "🗺️ КАРТА СВІТУ\n"
        "────────────────────\n"
        "Відкривай нові землі та шукай приховані локації.\n\n"
        "Кожен крок по карті коштує 1 ⚡️. Досліджуй туман, щоб знайти скарби!"
    ),
    "start_story_main": (
        "🏞️ МАНДРІВКА (СЮЖЕТ)\n"
        "────────────────────\n"
        "Це серце твоєї історії. Просувайся по сюжету, щоб відкривати нові глави життя своєї капібари.\n\n"
        "Тут на тебе чекають ключові битви та доленосні рішення."
    ),
    "open_quests": (
        "📜 КВЕСТИ ТА ПОДІЇ\n"
        "────────────────────\n"
        "Додаткові завдання та тимчасові івенти.\n\n"
        "Виконуй доручення місцевих, щоб отримати рідкісний лут, досвід та унікальні нагороди!"
    ),
    "fish": (
        "🎣 РИБОЛОВЛЯ\n"
        "────────────────────\n"
        "Час розслабитися... чи ні?\n\n"
        "Закидай вудку, щоб піймати рибу для їжі. Іноді замість карася можна витягнути щось дуже несподіване!"
    )
}

@router.callback_query(F.data.in_(ADVENTURE_TUTS.keys()))
async def handle_adventure_tutorials(callback: types.CallbackQuery, db_pool):
    action = callback.data
    uid = callback.from_user.id

    async with db_pool.acquire() as conn:
        user_row = await conn.fetchrow("SELECT tutorial FROM users WHERE tg_id = $1", uid)
        tutorial = ensure_dict(user_row['tutorial']) if user_row else {}

    tut_key = f"adv_{action}"
    
    # Показуємо алерт, якщо це перший раз
    if not tutorial.get(tut_key):
        await callback.answer(ADVENTURE_TUTS[action], show_alert=True)
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET tutorial = COALESCE(tutorial, '{}'::jsonb) || $1::jsonb WHERE tg_id = $2",
                json.dumps({tut_key: True}), uid
            )
    else:
        await callback.answer()
    
    if action == "open_map":
        await render_map(callback, db_pool)
    elif action == "open_quests":
        await cmd_quests_board(callback)
    elif action == "fish":
        await handle_fishing(callback, db_pool)

@router.message(or_f(F.text.contains("🧭 Пригоди"), Command("adventure")))
@router.callback_query(F.data == "open_adventure_main")
async def cmd_adventure(event: types.Message | types.CallbackQuery):
    is_callback = isinstance(event, types.CallbackQuery)
    builder = InlineKeyboardBuilder()
    
    builder.row(
        types.InlineKeyboardButton(text="🗺️ Карта світу", callback_data="open_map"),
        types.InlineKeyboardButton(text="🏞️ Мандрівкa", callback_data="start_story_main")
    )
    builder.row(
        types.InlineKeyboardButton(text="❓ Квести", callback_data="open_quests"),
        types.InlineKeyboardButton(text="🎣 Риболовля", callback_data="fish")
    )

    text = "🧭 <b>Морські пригоди</b>\n\nКуди відправимо твою капібару сьогодні?"

    if is_callback:
        msg = event.message
        if msg.photo or msg.video or msg.animation:
            try:
                await msg.delete()
                await event.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                print(f"Error handling media: {e}")
        else:
            try:
                await msg.edit_text(text=text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                print(f"Error editing: {e}")
        await event.answer()
    else:
        await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")