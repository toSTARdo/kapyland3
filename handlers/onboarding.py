import json
import logging
import asyncio
from aiogram import Router, F, types, html
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart
from keyboards.user_kb import get_main_kb
from services.quests_service import OnboardingService
from core.combat.battles import run_battle_logic
from database.crud_capybaras import get_full_profile
from utils.helpers import get_main_menu_chunk
from config import RACES as RACE_INFO

router = Router()

def load_story_file(filename: str):
    try:
        with open(f'data/{filename}.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            nodes = {str(node['id']): node for node in data['nodes']}
            logging.info(f"✅ Story Engine: Завантажено {len(nodes)} вузлів з {filename}.")
            return nodes
    except Exception as e:
        logging.error(f"❌ Story Engine Error ({filename}): {e}")
        return {}

PROLOGUE_NODES = load_story_file('prolog_narrative_tree')
MAIN_NODES = load_story_file('main_plot_narrative')

async def save_progress(db_pool, user_id: int, quest_id: str, node_id: str, is_completed: bool = False):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO story_progress (user_id, quest_id, node_id, is_completed)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, quest_id) 
            DO UPDATE SET node_id = EXCLUDED.node_id, is_completed = EXCLUDED.is_completed
        """, user_id, quest_id, str(node_id), is_completed)

async def render_story_node(message: types.Message, node_id: str, story_type: str, db_pool, menu_page: int = 0, show_quicklinks: bool = False):
    if str(node_id).startswith("event_"):
        await handle_story_event(message, node_id, db_pool)
        return

    nodes_pool = PROLOGUE_NODES if story_type == "prologue" else MAIN_NODES
    node = nodes_pool.get(str(node_id))
    
    if not node:
        return

    user_id = message.chat.id
    
    async with db_pool.acquire() as conn:
        user_data = await conn.fetchrow("SELECT quicklinks FROM users WHERE tg_id = $1", user_id)
        show_quicklinks = user_data['quicklinks'] if user_data and user_data['quicklinks'] is not None else True

        if str(node_id) == "sail_away":
            await conn.execute("""
                INSERT INTO story_progress (user_id, quest_id, node_id, is_completed)
                VALUES ($1, 'ship_arc', $2, TRUE)
                ON CONFLICT (user_id, quest_id) 
                DO UPDATE SET node_id = EXCLUDED.node_id, is_completed = TRUE
            """, user_id, str(node_id))

    await save_progress(db_pool, user_id, story_type, node_id)

    builder = InlineKeyboardBuilder()
    display_text = node["text"]
    
    requirements_met = True
    req_warning = ""

    if "requirements" in node:
        reqs = node["requirements"]
        if "player_coords" in reqs:
            profile = await get_full_profile(db_pool, user_id)
            current_pos = f"{profile['navigation']['x']},{profile['navigation']['y']}"
            target_pos = reqs["player_coords"]
            
            if current_pos != target_pos:
                requirements_met = False
                req_warning = f"\n\n📍 {html.italic(f'Ця дія доступна лише на координатах {target_pos} (ви зараз на {current_pos})')}"

    if not requirements_met:
        display_text += req_warning

    if "title" in node:
            new_title = node["title"]
            await conn.execute("""
                UPDATE capybaras 
                SET unlocked_titles = array_append(unlocked_titles, $1)
                WHERE owner_id = $2 
                AND NOT ($1 = ANY(unlocked_titles))
            """, new_title, user_id)
            
            display_text += f"\n\n✨ <b>Ви отримали новий титул:</b> {new_title}!"

    if story_type == "prologue" and node.get("status") in ["dead", "win"]:
        title = node.get("title", "Невідома доля")
        display_text = (
            f"🏆 <b>КІНЕЦЬ ПРОЛОГУ: {title}</b>\n\n"
            f"{display_text}\n\n"
            f"✨ {html.bold('Богиня Капібар зʼявляється перед тобою:')}\n"
            f"«Твоє земне життя завершене... Яку подобу ти обереш собі?»"
        )
        if requirements_met:
            for race_id, info in RACE_INFO.items():
                builder.button(text=f"{info['emoji']} {info['name']}", callback_data=f"preview_race_{race_id}")
            builder.adjust(2)
    
    elif "options" in node:
        if requirements_met:
            prefix = "story_" if story_type == "prologue" else "main_"
            for opt in node["options"]:
                builder.button(text=opt["text"], callback_data=f"{prefix}{opt['next_id']}")
            builder.adjust(1)
        else:
            builder.button(text="🔙 Назад до штурвалу", callback_data="open_navigation")

    if show_quicklinks:
        cb_prefix = "start_story_main" if story_type == "main" else "start_story_prologue"
        get_main_menu_chunk(builder, page=menu_page, callback_prefix=cb_prefix)

    if message.photo or message.video:
        try:
            await message.delete()
        except:
            pass
        await message.answer(display_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        try:
            await message.edit_text(display_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            await message.edit_reply_markup(reply_markup=builder.as_markup())
    
@router.callback_query(F.data.startswith("preview_race_"))
async def handle_race_preview(callback: types.CallbackQuery):
    race_id = callback.data.replace("preview_race_", "")
    info = RACE_INFO.get(race_id)
    if not info: return

    text = (
        f"{info['emoji']} <b>{info['name']}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<i>{info['desc']}</i>\n\n"
        
        f"<b>✨ Унікальна здібність:</b>\n"
        f"└ <b>{info['ability_name']}</b>: <i>{info['ability_desc']}</i>\n\n"
        
        f"<b>Початкові характеристики:</b>\n"
        f"<code>{info['stats_text']}</code>\n\n"
        
        f"Ви впевнені, що хочете стати <b>{info['name']}</b>?"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ Так, я {info['name']}!", callback_data=f"create_animal_{race_id}")
    builder.button(text="⬅️ Назад до вибору", callback_data="story_back_to_choice")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "story_back_to_choice")
async def handle_back_to_choice(callback: types.CallbackQuery, db_pool):
    await render_story_node(callback.message, "flower_win", "prologue", db_pool)

@router.callback_query(F.data.startswith("create_animal_"))
async def handle_animal_selection(callback: types.CallbackQuery, onboarding_service: OnboardingService):
    race = callback.data.replace("create_animal_", "")
    await onboarding_service.register_animal(callback.from_user.id, race)
    
    confirm_kb = InlineKeyboardBuilder()
    confirm_kb.button(text="✨ Переродитися на землях Мофу", callback_data="finish_prologue")
    info = RACE_INFO.get(race, {"name": race, "emoji": "✨"})
    
    await callback.message.edit_text(
        f"✨ {info['emoji']} <b>ВИБІР ЗРОБЛЕНО!</b>\n\n"
        f"Твоя нова доля чекає на тебе в Архіпелазі Мофу...",
        reply_markup=confirm_kb.as_markup(), parse_mode="HTML"
    )

@router.callback_query(F.data == "finish_prologue")
async def process_finish_prologue(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET has_finished_prologue = TRUE WHERE tg_id = $1", uid)
        await conn.execute("UPDATE story_progress SET is_completed = TRUE WHERE user_id = $1 AND quest_id = 'prologue'", uid)
    
    await callback.message.edit_text("💫 В очах темніє і остання думка це 🍊...")
    await callback.message.answer(
        "⚓️ <b>Ти розплющуєш очі в порту Ліворн Бей...</b>\nПригода починається!",
        reply_markup=get_main_kb(),
        parse_mode="HTML"
    )
    await render_story_node(callback.message, "1", "main", db_pool)

@router.callback_query(F.data.startswith('story_'))
async def process_story_step(callback: types.CallbackQuery, db_pool):
    node_id = callback.data.replace("story_", "")
    await render_story_node(callback.message, node_id, "prologue", db_pool)
    await callback.answer()

@router.callback_query(F.data.startswith('main_'))
async def process_main_step(callback: types.CallbackQuery, db_pool):
    node_id = callback.data.replace("main_", "")
    await render_story_node(callback.message, node_id, "main", db_pool)
    await callback.answer()

@router.message(CommandStart())
async def cmd_start(message: types.Message, db_pool):
    uid = message.from_user.id
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("""
            INSERT INTO users (tg_id, username) VALUES ($1, $2)
            ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username
            RETURNING has_finished_prologue
        """, uid, message.from_user.full_name)

        progress = await conn.fetchrow("SELECT quest_id, node_id FROM story_progress WHERE user_id = $1 AND is_completed = FALSE", uid)
        
        if progress:
            await render_story_node(message, progress['node_id'], progress['quest_id'], db_pool)
            return

        if not user['has_finished_prologue']:
            await render_story_node(message, "1", "prologue", db_pool)
            return

    await message.answer(f"⚓️ Вітаємо, {message.from_user.first_name}!", reply_markup=get_main_kb(), parse_mode="HTML")

async def handle_story_event(message: types.Message, event_id: str, db_pool):
    uid = message.chat.id
    
    # --- ПОДІЯ: БІЙ З ПАПУГОЮ ПАВЛОМ ---
    if event_id == "event_parrot_fight":
        await message.answer("🦜 <b>Папуга Павло гострить дзьоб і готується до нападу!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_parrot",   # Вузол, де Павло стає дружнім
            "lose_node": "lose_parrot", # Вузол, де ти лежиш на пірсі
            "story_type": "main"
        }
        
        # Запускаємо бій і передаємо outcomes
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="parrotbot", 
            outcomes=outcomes
        ))

    # --- ПОДІЯ: БІЙ ЗІ СТІДОМ «КОВШЕМ» (ПЕРШИЙ БОС) ---
    elif event_id == "event_stede_fight":
        await message.answer("🦢 <b>Стід «Ківш» поправляє камзол і замахується веслом!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_1",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_1",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_pelican", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_windbreaker_fight":
        await message.answer("🐆 <b>Рись «Рвивітер» вламується на пліт!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_m1",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_m1",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_lynx", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_rat_king":
        await message.answer("🐀 <b>Щур Кололь «Чума» накидається на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_2",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_2",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_rat_king", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_ricky_boss_fight":
        await message.answer("🦝 <b>Єнот Ріккі «Сміттяр» накидається на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_3",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_3",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_raccoon_trash", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_monkey_king":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_5",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_5",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_monkey_king", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_8_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_8",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_8",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_snake_lee", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_9_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_9",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_9",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_otter_river", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_10_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_10",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_10",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_frog_shinobi", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_11_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_11",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_11",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_catfish_gun", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_13_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_13",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_13",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_fat_cat", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_14_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_14",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_14",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_turtle_ancient", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_16_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_16",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_16",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_husky_kuzan", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_alvida_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_17a",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_17a",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_alvida", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_17_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_17",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_1",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_bear_north", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_14_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_14",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_14",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_turtle_ancient", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_boss_14_fight":
        await message.answer("<b>Мер мавпа блискавично наскакує на вас!</b>", parse_mode="HTML")
        
        outcomes = {
            "win_node": "win_boss_14",    # Перемога: легенда про Ехваз
            "lose_node": "lose_boss_14",   # Поразка: ти на плоту пробуєш ще раз
            "story_type": "main"
        }
        
        # Передаємо is_boss=True для підвищених нагород
        asyncio.create_task(run_battle_logic(
            event=message, 
            db_pool=db_pool, 
            bot_type="boss_turtle_ancient", 
            is_boss=True, 
            outcomes=outcomes
        ))

    elif event_id == "event_fishing_for_map":
        builder = InlineKeyboardBuilder()
        builder.button(text="🎣 Закинути вудочку", callback_data="fish")
        
        await message.answer(
            "🌊 <b>Океан навколо виглядає спокійним...</b>\n\n"
            "Ти згадуєш, що старий папуга щось казав про мапу, яку він впустив у воду. "
            "Можливо, якщо трохи порибалити, ти зможеш її знайти?",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )

    # --- ПОДІЯ: ОТРИМАННЯ МАПИ ---
    elif event_id == "event_get_map":
        await message.answer("📜 <b>Ви отримали стару мапу Рифового Острова!</b>", parse_mode="HTML")
        # Тут просто рендеримо наступний вузол без бою
        from handlers.story_handler import render_story_node
        await render_story_node(message, "map_discovery", "main", db_pool)

    else:
        logging.warning(f"⚠️ Спрацював невідомий event_id: {event_id}")

@router.callback_query(F.data.startswith("start_story_main"))
async def start_main_story(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    # Визначаємо сторінку чанка
    menu_page = 0
    if ":p" in callback.data:
        try: menu_page = int(callback.data.split(":p")[1])
        except: menu_page = 0

    async with db_pool.acquire() as conn:
        node_id = await conn.fetchval(
            "SELECT node_id FROM story_progress WHERE user_id = $1 AND quest_id = 'main'", 
            uid
        ) or "1"
        
        # Отримуємо налаштування швидкого меню
        show_quicklinks = await conn.fetchval("SELECT quicklinks FROM users WHERE tg_id = $1", uid)
        if show_quicklinks is None: show_quicklinks = True

    # Викликаємо рендер, передаючи стан меню
    await render_story_node(callback.message, node_id, "main", db_pool, menu_page, show_quicklinks)
    await callback.answer()