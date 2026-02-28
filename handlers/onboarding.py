import json
import logging
from aiogram import Router, F, types, html
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart
from keyboards.user_kb import get_main_kb

router = Router()

def load_story():
    try:
        with open('data/prolog_narrative_tree.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            nodes = {str(node['id']): node for node in data['nodes']}
            logging.info(f"✅ Story Engine: Завантажено {len(nodes)} вузлів сюжету.")
            return nodes
    except Exception as e:
        logging.error(f"❌ Story Engine Error: Не вдалося завантажити JSON: {e}")
        return {}

STORY_NODES = load_story()

async def render_story_node(message: types.Message, node_id: str):
    node = STORY_NODES.get(str(node_id))
    if not node: return

    builder = InlineKeyboardBuilder()
    display_text = node["text"]
    
    if node.get("status") in ["dead", "win"]:
        title = node.get("title", "Невідома доля")
        display_text += f"\n\n🏆 Отримано нову зав'язку: <b>{title}</b>"
        display_text += (
            f"\n\n✨ {html.bold('Богиня Капібар зʼявляється перед тобою і промовляє через свої розкішні локони:')}\n"
            f"«Твоє життя у цьому світі завершене, але на планеті Мофу ти можеш стати ким завгодно. "
            f"Який дар ти візьмеш із собою?»"
        )
        
        builder.button(text="⚔️ Сила", callback_data="godgift_atk")
        builder.button(text="💨 Спритність", callback_data="godgift_agi")
        builder.button(text="🛡 Захист", callback_data="godgift_def")
        builder.button(text="🍀 Удача", callback_data="godgift_luck")
    
    elif "options" in node:
        for opt in node["options"]:
            builder.button(text=opt["text"], callback_data=f"story_{opt['next_id']}")

    builder.adjust(1 if "options" in node else 2)
    
    try:
        await message.edit_text(display_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        await message.answer(display_text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("godgift_"))
async def handle_goddess_gift(callback: types.CallbackQuery, db_pool):
    stat_map = {
        "godgift_atk": "atk",
        "godgift_agi": "agi",
        "godgift_def": "def",
        "godgift_luck": "luck"
    }
    chosen_col = stat_map.get(callback.data)
    if not chosen_col: return
    
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO capybaras (owner_id, name) VALUES ($1, 'Безіменна булочка')
            ON CONFLICT (owner_id) DO NOTHING
        """, uid)
        
        await conn.execute(f"UPDATE capybaras SET {chosen_col} = {chosen_col} + 1 WHERE owner_id = $1", uid)

    gift_names = {"atk": "Силу", "agi": "Спритність", "def": "Захист", "luck": "Удачу"}
    new_text = (
        f"✨ Богиня посміхнулася: «Ти обрав {html.bold(gift_names[chosen_col])}. "
        f"Тепер я назад спати в хмарках...»"
    )
    
    confirm_kb = InlineKeyboardBuilder()
    confirm_kb.button(text="✨ Переродитися на землях Мофу", callback_data="finish_prologue")
    
    await callback.message.edit_text(new_text, reply_markup=confirm_kb.as_markup(), parse_mode="HTML")
    await callback.answer(f"Ви отримали +1 до {chosen_col}!")

@router.callback_query(F.data == "finish_prologue")
async def process_finish_prologue(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET has_finished_prologue = TRUE WHERE tg_id = $1", uid)
    
    await callback.message.edit_text("💫 В очах темніє і остання думка це 🍊...")
    
    await callback.message.answer(
        "⚓️ <b>Ласкаво просимо до Архіпелагу!</b>\n\nТвоя подорож починається прямо зараз.",
        reply_markup=get_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith('story_'))
async def process_story_step(callback: types.CallbackQuery):
    next_node_id = callback.data.replace("story_", "")
    await render_story_node(callback.message, next_node_id)
    await callback.answer()

@router.message(CommandStart())
async def cmd_start(message: types.Message, db_pool):
    user_id = message.from_user.id
    username = message.from_user.full_name or "Капібара"

    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("""
            INSERT INTO users (tg_id, username) 
            VALUES ($1, $2)
            ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username
            RETURNING has_finished_prologue
        """, user_id, username)

        if not user['has_finished_prologue']:
            await render_story_node(message, "1")
            return

        capy = await conn.fetchrow("SELECT name FROM capybaras WHERE owner_id = $1", user_id)
        
        if not capy:
            await conn.execute(
                "INSERT INTO capybaras (owner_id, name) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                user_id, "Безіменна булочка"
            )
            welcome_text = f"✨ <b>Вітаємо на планеті Мофу, {username}!</b>"
        else:
            welcome_text = f"⚓️ <b>З поверненням до Архіпелагу, {username}!</b>"

    await message.answer(
        f"{welcome_text}\n\n"
        f"Твоя пригода продовжується. Що будемо робити сьогодні?",
        reply_markup=get_main_kb(),
        parse_mode="HTML"
    )