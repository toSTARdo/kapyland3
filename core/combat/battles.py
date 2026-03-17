import asyncio
import json
import random
import logging
from aiogram import Router, types, html, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.harbor.settings.emotes import send_victory_celebration
from core.combat.combat_system import Fighter, CombatEngine
from utils.helpers import grant_exp_and_lvl, ensure_dict
from config import BASE_HITPOINTS, WEAPON, ARMOR, NPC_REGISTRY, BOSS_ID_MAP, BOSS_REWARDS

router = Router()

@router.callback_query(F.data.startswith("challenge_"))
async def send_challenge(callback: types.CallbackQuery):
    data = callback.data.split("_")
    opponent_id = int(data[1])
    challenger_id = callback.from_user.id
    challenger_name = callback.from_user.first_name

    if opponent_id == challenger_id:
        return await callback.answer("❌ Ви не можете викликати самого себе!", show_alert=True)

    builder = InlineKeyboardBuilder()
    builder.button(text="🤝 ПРИЙНЯТИ", callback_data=f"accept_{challenger_id}_{opponent_id}")
    builder.button(text="🏳️ ВІДМОВИТИСЯ", callback_data=f"decline_{challenger_id}_{opponent_id}")
    builder.adjust(2)

    await callback.message.answer(
        f"⚔️ <b>ПУБЛІЧНИЙ ВИКЛИК!</b>\n"
        f"Пірабара {html.bold(challenger_name)} кидає рукавичку <a href='tg://user?id={opponent_id}'>опоненту</a>!\n\n"
        f"<i>Тільки викликаний гравець може прийняти бій.</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer("Виклик кинуто в чат!")

@router.callback_query(F.data.startswith("decline_"))
async def battle_declined(callback: types.CallbackQuery):
    data = callback.data.split("_")
    opponent_id = int(data[2])

    if callback.from_user.id != opponent_id:
        return await callback.answer("❌ Ти не можеш відмовитися за іншого!", show_alert=True)

    await callback.message.edit_text(f"🏳️ Опонент злякався і втік у кущі.", parse_mode="HTML")

@router.callback_query(F.data.startswith("accept_"))
async def handle_accept(callback: types.CallbackQuery, db_pool):
    data = callback.data.split("_")
    challenger_id = int(data[1])
    opponent_id = int(data[2])
    
    if callback.from_user.id != opponent_id:
        return await callback.answer("Це виклик не для тебе! ⛔", show_alert=True)

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT owner_id, stamina FROM capybaras WHERE owner_id IN ($1, $2)",
            challenger_id, opponent_id
        )
        
        stats = {row['owner_id']: row['stamina'] for row in rows}
        
        if stats.get(opponent_id, 0) < 5:
            return await callback.answer("У тебе недостатньо енергії (треба 5 ⚡)!", show_alert=True)
        if stats.get(challenger_id, 0) < 5:
            return await callback.answer("У суперника закінчилася енергія! Бій скасовано. ❌", show_alert=True)

    await callback.message.edit_text("🚀 Бій прийнято! Капібари виходять на дуель... (-5 ⚡)")
    asyncio.create_task(run_battle_logic(callback, db_pool, opponent_id=challenger_id))
    await callback.answer()

async def get_full_capy_data(target_id, db_pool, b_type=None):
    if b_type in NPC_REGISTRY:
        return NPC_REGISTRY[b_type]

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT name, weight, inventory, state, lvl, atk, def, agi, luck , equipment, stamina, max_hp, race
            FROM capybaras 
            WHERE owner_id = $1
        """, target_id)
        
        if not row: return None
        
        eq_data = row['equipment']
        if isinstance(eq_data, str):
            eq_data = json.loads(eq_data)
        eq_data = eq_data or {}

        inv = row['inventory']
        if isinstance(inv, str):
            inv = json.loads(inv)
        inv = inv or {}

        state = row['state']
        print(type(state))
        if isinstance(state, str):
            state = json.loads(state)
        state = state or {}

        weapon_obj = eq_data.get("weapon") or {"name": "Лапки", "lvl": 0}
        armor_obj = eq_data.get("armor") or {"name": "Хутро", "lvl": 0}

        return {
            "kapy_name": row['name'],
            "max_hp": row["max_hp"],
            "race": row["race"],
            "lvl": row["lvl"],
            "weight": row['weight'],
            "stamina": row['stamina'] or 0,
            "state": state,
            "stats": {
                "attack": row['atk'] or 1,
                "defense": row['def'] or 0,
                "agility": row['agi'] or 1,
                "luck": row['luck'] or 0
            },
            "weapon_full": weapon_obj,
            "armor_full": armor_obj,
            "inventory": inv,
            "color": "🔴"
        }

async def run_battle_logic(
    event: Union[types.Message, types.CallbackQuery], 
    db_pool, 
    opponent_id: int = None, 
    bot_type: str = None, 
    is_boss: bool = False, 
    is_ghost: bool = False, 
    tomb_id: int = None,
    outcomes: dict = None
):
    uid, msg_interface = (event.from_user.id, event.message) if isinstance(event, types.CallbackQuery) else (event.chat.id, event)
    
    # 1. Завантаження даних
    p1_data, p2_data = await _fetch_battle_data(uid, opponent_id, bot_type, is_ghost, tomb_id, db_pool, event)
    if not p1_data or not p2_data: return

    print(f"DEBUG: p1_stamina = {p1_data.get('stamina')}, type = {type(p1_data.get('stamina'))}")
    # Перевірка стаміни
    if bot_type != "parrotbot" and (p1_data.get('stamina', 0) < 5):
        msg = "🪫 Твоя капібара надто стомлена! (Треба 5⚡)"
        return await event.answer(msg, show_alert=True) if isinstance(event, types.CallbackQuery) else await msg_interface.answer(msg)

    # 2. Створення об'єктів бійців
    p1, p2 = _initialize_fighters(p1_data, p2_data)

    # 3. Симуляція бою (включаючи ініціативу та повідомлення про спритність)
    winner, loser = await _execute_battle_simulation(msg_interface, p1, p2)

    # 4. Обробка результатів та генерація reward_info
    res_text, reward_info = await _apply_battle_results(
        uid, opponent_id, winner, loser, p1, p2, p2_data, 
        is_boss, is_ghost, bot_type, tomb_id, db_pool, event.bot
    )

    # 5. Фінальний звіт
    await msg_interface.answer(f"🏁 <b>БІЙ ЗАВЕРШЕНО</b>\n━━━━━━━━━━━━━━\n{res_text}{reward_info}", parse_mode="HTML")

    # 6. Сюжетний перехід
    if outcomes:
        await _handle_story_outcomes(msg_interface, winner, p1, outcomes, db_pool)

def _initialize_fighters(p1_data: dict, p2_data: dict):
    """
    Ініціалізує бійців. p2_data вже містить дані з NPC_REGISTRY, 
    якщо це бот, або дані з БД, якщо це гравець/привид.
    """
    battle_config = {"WEAPONS": WEAPON, "ARMOR": ARMOR}

    # Ініціалізація гравця
    p1 = Fighter(p1_data, battle_config, color="🟢")

    # Ініціалізація противника
    # Використовуємо колір з реєстру або дефолтний червоний
    enemy_color = p2_data.get("color", "🔴")
    p2 = Fighter(p2_data, battle_config, color=enemy_color)

    # Якщо в реєстрі прописаний hp_bonus, додаємо його
    if p2_data.get("hp_bonus"):
        p2.max_hp += int(p2_data["hp_bonus"])
        p2.hp = p2.max_hp

    # Встановлюємо ім'я з реєстру (якщо воно там є як kapy_name)
    if p2_data.get("kapy_name"):
        p2.name = p2_data["kapy_name"]

    return p1, p2

async def _fetch_battle_data(uid, opp_id, bot_type, is_ghost, tomb_id, db_pool, event):
    p1_data = await get_full_capy_data(uid, db_pool)
    p2_data = None

    if is_ghost and tomb_id:
        p2_data = await _get_ghost_data(tomb_id, db_pool)
    else:
        p2_data = await get_full_capy_data(opp_id, db_pool, b_type=bot_type)

    if not p1_data or not p2_data:
        msg = "❌ Помилка: Дані капібари не знайдено."
        if isinstance(event, types.CallbackQuery): await event.answer(msg)
        else: await event.answer(msg)
        return None, None
    
    return p1_data, p2_data

async def _execute_battle_simulation(msg_interface, p1, p2):
    main_msg = await msg_interface.answer(f"🏟 <b>ПІДГОТОВКА ДО БОЮ...</b>\n\n{p1.name} VS {p2.name}", parse_mode="HTML")
    await asyncio.sleep(1.5)

    # Логіка першого удару
    if p1.agi > p2.agi:
        attacker, defender = p1, p2
        init_msg = f"⚡ {html.bold(p1.name)} виявився спритнішим і атакує першим!"
    elif p2.agi > p1.agi:
        attacker, defender = p2, p1
        init_msg = f"⚡ {html.bold(p2.name)} швидше зорієнтувався і вистрибує вперед!"
    else:
        attacker, defender = random.sample([p1, p2], 2)
        init_msg = f"⚡ Спритність рівна! Але першим вдається ударити {html.bold(attacker.name)}."

    await main_msg.edit_text(f"🏟 <b>БІЙ: {p1.name} VS {p2.name}</b>\n\n{init_msg}", parse_mode="HTML")
    await asyncio.sleep(1.5)

    round_num = 1
    while p1.hp > 0 and p2.hp > 0 and round_num <= 30:
        report = CombatEngine.resolve_turn(attacker, defender, round_num)
        full_report = (
            f"🏟 <b>Раунд {round_num}</b>\n"
            f"{p1.color} {p1.name}: {p1.get_hp_display()}\n"
            f"{p2.color} {p2.name}: {p2.get_hp_display()}\n"
            f"━━━━━━━━━━━━━━\n\n{report}"
        )
        try: await main_msg.edit_text(full_report, parse_mode="HTML")
        except: pass
        
        attacker, defender = defender, attacker
        await asyncio.sleep(2.3)
        round_num += 1

    return (p1, p2) if p1.hp > 0 else (p2, p1) if p2.hp > 0 else (None, None)

async def _apply_battle_results(uid, opp_id, winner, loser, p1, p2, p2_data, is_boss, is_ghost, bot_type, tomb_id, db_pool, bot):
    reward_info = ""
    res = "🤝 <b>НІЧИЯ!</b>"
    is_parrot = (bot_type == "parrotbot")
    boss_cfg = BOSS_REWARDS.get(bot_type) if is_boss else None

async def _apply_battle_results(uid, opp_id, winner, loser, p1, p2, p2_data, is_boss, is_ghost, bot_type, tomb_id, db_pool, bot):
    reward_info = ""
    res = "🤝 <b>НІЧИЯ!</b>"
    is_parrot = (bot_type == "parrotbot")
    boss_cfg = BOSS_REWARDS.get(bot_type) if is_boss else None

    async with db_pool.acquire() as conn:
        # Знімаємо стаміну та рахуємо бої для реальних гравців
        if not is_parrot:
            await conn.execute("""
                UPDATE capybaras 
                SET stamina = GREATEST(stamina - 5, 0), 
                    total_fights = total_fights + 1 
                WHERE owner_id = $1
            """, uid)

        # ЛОГІКА ПЕРЕМОГИ (p1)
        if winner == p1:
            res = f"🏆 <b>ПЕРЕМОГА {p1.color}!</b>\n{html.bold(p1.name)} здобув звитягу!"
            
            if is_ghost:
                reward_info = await _process_ghost_loot(uid, p2_data, tomb_id, conn)
                
            elif is_boss and boss_cfg:
                # Оновлюємо прогрес босів та отримуємо їх кількість
                bosses_count = await _update_boss_progress(uid, conn)
                
                reward_info = f"\n\n🏆 <b>БОС ПОДОЛАНИЙ!</b>\n📈 +{boss_cfg['weight']} кг, +{boss_cfg['exp']} EXP"
                
                if bosses_count == 1:
                    # ПЕРША ПЕРЕМОГА: Видаємо Мега-скриню
                    await conn.execute("""
                        UPDATE capybaras 
                        SET inventory = jsonb_set(
                            inventory, '{loot,mega_chest}', 
                            (COALESCE((inventory->'loot'->>'mega_chest')::int, 0) + 1)::text::jsonb
                        ) 
                        WHERE owner_id = $1
                    """, uid)
                    reward_info += "\n🎁 <b>ПЕРША ПЕРЕМОГА:</b> Отримано 1 мега-скриню!"
                else:
                    # ПОВТОРНА ПЕРЕМОГА: Видаємо звичайну скриню
                    await conn.execute("""
                        UPDATE capybaras 
                        SET inventory = jsonb_set(
                            inventory, '{loot,chest}', 
                            (COALESCE((inventory->'loot'->>'chest')::int, 0) + 1)::text::jsonb
                        ) 
                        WHERE owner_id = $1
                    """, uid)
                    reward_info += "\n🎁 <b>ПЕРЕМОГА:</b> Отримано 1 скриню!"

                # Нараховуємо досвід за боса
                await grant_exp_and_lvl(uid, exp_gain=boss_cfg['exp'], weight_gain=boss_cfg['weight'], bot=bot, db_pool=db_pool)

            elif not is_parrot:
                # Звичайна перемога (не папуга, не бос, не привид)
                reward_info = f"\n\n📈 <b>Нагорода:</b>\n🥇 +{winner.hp} кг, +{winner.hp} EXP"
                await grant_exp_and_lvl(uid, exp_gain=winner.hp, weight_gain=winner.hp, bot=bot, db_pool=db_pool)

        # ЛОГІКА ПОРАЗКИ (p1 програв)
        elif winner == p2:
            res = f"💀 <b>ПОРАЗКА {p1.color}!</b>\n{html.bold(p2.name)} виявився сильнішим."
            
            if is_parrot:
                reward_info = "\n\nParrot 🦜 <i>Папуга Павло дає тобі пораду: «Більше тренуйся, сопляк!»</i>"
            else:
                reward_info = f"\n\n📉 <b>Збитки:</b>\n🥈 -{p2.hp} кг"
                # Використовуємо p2.hp (переможця), щоб вирахувати втрату ваги
                await grant_exp_and_lvl(uid, exp_gain=0, weight_gain=-1 * p2.hp, bot=bot, db_pool=db_pool)

    return res, reward_info

async def _update_boss_progress(uid: int, conn) -> int:
    query = """
        UPDATE capybaras 
        SET stats_track = COALESCE(stats_track, '{}'::jsonb) || 
                          jsonb_build_object(
                              'bosses_defeated', 
                              COALESCE((stats_track->>'bosses_defeated')::int, 0) + 1
                          )
        WHERE owner_id = $1
        RETURNING (stats_track->>'bosses_defeated')::int;
    """
    try:
        new_count = await conn.fetchval(query, uid)
        if new_count is not None:
            return int(new_count)
        return 0
    except Exception as e:
        logging.error(f"Error updating bosses_defeated for {uid}: {e}")
        return 0

async def _process_ghost_loot(uid, p2_data, tomb_id, conn):
    # Отримуємо дані реінкарнації
    row = await conn.fetchrow("""
        SELECT c.inventory, u.reincarnation_count FROM capybaras c
        JOIN users u ON c.owner_id = u.tg_id WHERE c.owner_id = $1
    """, uid)
    
    reinc_count = row['reincarnation_count'] or 0
    spiritual_power = min(1.0, reinc_count * 0.1)
    
    # ... логіка вибору предметів (як у тебе в коді) ...
    recovered = ["✨ Предмет 1", "Яблуко x5"] # Сюди заповнюємо результат циклу
    
    reinc_text = f"<i>(Духовна сила: {int(spiritual_power*100)}%)</i>"
    return f"\n\n👻 <b>СПАДЩИНА ПРЕДКА:</b> {reinc_text}\n{', '.join(recovered)}"

async def _handle_story_outcomes(msg_interface, winner, p1, outcomes, db_pool):
    """
    Вирішує, куди направити гравця після бою в сюжетному режимі.
    """
    await asyncio.sleep(3)
    from handlers.onboarding import render_story_node
    
    # Визначаємо ID наступного вузла на основі результату бою
    target_node = outcomes.get("win_node") if winner == p1 else outcomes.get("lose_node")
    
    if target_node:
        await render_story_node(msg_interface, target_node, outcomes.get("story_type", "main"), db_pool)

@router.callback_query(F.data == "fight_bot")
async def handle_fight_bot(callback: types.CallbackQuery, db_pool):
    await callback.message.answer("🦜 Папуга Павло гострить дзьоб...")
    asyncio.create_task(run_battle_logic(callback, db_pool, bot_type="parrotbot"))
    await callback.answer()