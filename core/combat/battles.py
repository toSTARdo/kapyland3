import asyncio
import json
import random
import logging
from uuid import uuid4
from typing import Any, List, Union
from aiogram import Router, types, html, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.harbor.settings.emotes import send_victory_celebration
from core.combat.combat_system import Fighter, CombatEngine
from utils.helpers import grant_exp_and_lvl, ensure_dict
from config import BASE_HITPOINTS, WEAPON, ARMOR, NPC_REGISTRY, BOSS_ID_MAP, BOSS_REWARDS, ARTIFACTS

router = Router()

# Updated signature to accept 3 arguments
@router.callback_query(F.data.startswith("challenge_"))
async def send_challenge(callback: types.CallbackQuery, target_id: int = None, db_pool = None):
    # If target_id wasn't passed by the router (e.g. direct button click), 
    # we extract it from callback.data as a fallback
    if target_id is None:
        data = callback.data.split("_")
        target_id = int(data[1])
        
    challenger_id = callback.from_user.id
    challenger_name = callback.from_user.first_name

    if target_id == challenger_id:
        return await callback.answer("❌ Ви не можете викликати самого себе!", show_alert=True)

    # Check stamina (since you have db_pool now)
    if db_pool:
        async with db_pool.acquire() as conn:
            stamina = await conn.fetchval("SELECT stamina FROM capybaras WHERE owner_id = $1", challenger_id)
            if stamina and stamina < 15:
                return await callback.answer("🪫 Ви занадто втомилися (треба 15⚡️)", show_alert=True)

    builder = InlineKeyboardBuilder()
    # Note: Using target_id here instead of opponent_id to keep variable names consistent
    builder.button(text="🤝 ПРИЙНЯТИ", callback_data=f"accept_{challenger_id}_{target_id}")
    builder.button(text="🏳️ ВІДМОВИТИСЯ", callback_data=f"decline_{challenger_id}_{target_id}")
    builder.adjust(2)

    await callback.message.answer(
        f"⚔️ <b>ПУБЛІЧНИЙ ВИКЛИК!</b>\n"
        f"Пірабара <b>{challenger_name}</b> кидає рукавичку <a href='tg://user?id={target_id}'>опоненту</a>!\n\n"
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
    is_training = bot_type in ["parrotbot", "testbot"]
    stamina_cost = 15 if is_boss else 5

    if not is_training:
        p1_stamina = p1_data.get('stamina', 0)
        
        if p1_stamina < stamina_cost:
            msg = f"🪫 Надто мало енергії для такого бою! (Треба {stamina_cost}⚡️)"
            if isinstance(event, types.CallbackQuery):
                return await event.answer(msg, show_alert=True)
            return await msg_interface.answer(msg)
    # 2. Створення об'єктів бійців
    p1, p2 = _initialize_fighters(p1_data, p2_data)

    # 3. Симуляція бою (включаючи ініціативу та повідомлення про спритність)
    winner, loser = await _execute_battle_simulation(msg_interface, p1, p2, is_boss)

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

async def _execute_battle_simulation(msg_interface, p1, p2, is_boss):
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
    while p1.hp > 0 and p2.hp > 0 and round_num <= (30 if (not is_boss) else 50):
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

    async with db_pool.acquire() as conn:
        if not is_parrot:
            await conn.execute("""
                UPDATE capybaras 
                SET stamina = GREATEST(stamina - 5, 0), 
                    total_fights = total_fights + 1 
                WHERE owner_id = $1
            """, uid)

        if winner == p1:
            res = f"🏆 <b>ПЕРЕМОГА {p1.color}!</b>\n{html.bold(p1.name)} здобув звитягу!"
            
            if is_ghost:
                reward_info = await _process_ghost_loot(uid, p2_data, tomb_id, conn)
                
            elif is_boss and boss_cfg:
                boss_id = str(boss_cfg.get('id'))
                was_defeated = await conn.fetchval("""
                    SELECT (stats_track->'bosses_defeated') ? $2 
                    FROM capybaras WHERE owner_id = $1
                """, uid, boss_id)

                multiplier = 0.25 if was_defeated else 1.0
                reward_info = f"\n\n<b>{'ПОВТОРНА ПЕРЕМОГА' if was_defeated else '🏆 БОС ПОДОЛАНИЙ ВПЕРШЕ!'}</b>"

                final_weight = round(boss_cfg['weight'] * multiplier, 2)
                final_exp = int(boss_cfg['exp'] * multiplier)
                reward_info += f"\n📈 +{final_weight} кг, +{final_exp} EXP"

                update_query = """
                    UPDATE capybaras 
                    SET inventory = jsonb_set(inventory, '{loot,chest}', 
                        (COALESCE((inventory->'loot'->>'chest')::int, 0) + 1)::text::jsonb)
                    WHERE owner_id = $1
                """
                if not was_defeated:
                    update_query = """
                        UPDATE capybaras 
                        SET inventory = jsonb_set(inventory, '{loot,mega_chest}', 
                            (COALESCE((inventory->'loot'->>'mega_chest')::int, 0) + 1)::text::jsonb),
                            stats_track = jsonb_set(stats_track, '{bosses_defeated}', 
                            COALESCE(stats_track->'bosses_defeated', '[]'::jsonb) || jsonb_build_array($2::text))
                        WHERE owner_id = $1
                    """
                    reward_info += "\n🎁 Отримано 1 мега-скриню!"
                
                await conn.execute(update_query, uid, boss_id)

                if random.random() < (1.0 if not was_defeated else 0.25):
                    await conn.execute("""
                        UPDATE capybaras 
                        SET inventory = jsonb_set(inventory, '{loot,lottery_ticket}', 
                            (COALESCE((inventory->'loot'->>'lottery_ticket')::int, 0) + 1)::text::jsonb) 
                        WHERE owner_id = $1
                    """, uid)
                    reward_info += "\n🎟 <b>Бонус:</b> Знайдено лотерейний квиток!"

                await grant_exp_and_lvl(uid, exp_gain=final_exp, weight_gain=final_weight, bot=bot, db_pool=db_pool)

            elif not is_parrot:
                gain = int(abs(p1.hp - p2.hp) * 0.5) 
                reward_info = f"\n\n📈 <b>Нагорода:</b>\n🥇 +{gain} кг, +{gain} EXP"
                
                if bot_type is not None and random.random() < 0.25:
                    rarity = random.choices(["Common", "Rare"], weights=[80, 20])[0]
                    pool = ARTIFACTS.get(rarity, [{"name": "Іржавий ніж", "type": "weapon"}])
                    item = random.choice(pool)
                    item_id = str(uuid4())[:8]
                    
                    inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", uid)
                    inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
                    inv.setdefault("equipment", {})[item_id] = {
                        "name": item["name"], "rarity": rarity, "type": item["type"],
                        "lvl": 0, "desc": f"Трофей після бою з {p2.name}."
                    }
                    await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv), uid)
                    reward_info += f"\n\n✨ <b>Артефакт:</b> {item['name']} ({rarity})!"

                await grant_exp_and_lvl(uid, exp_gain=gain, weight_gain=gain, bot=bot, db_pool=db_pool)

            bonus_chance = 0.3 + (p1.luck * 0.02)
            if random.random() < bonus_chance:
                food_pool = ["tangerines", "watermelon_slices", "melon", "mango", "kiwi"]
                
                food_weights = [50, 25, 15, 8, 2] 
                
                dropped_food = random.choices(food_pool, weights=food_weights, k=1)[0]
                
                await conn.execute(f"""
                    UPDATE capybaras 
                    SET inventory = jsonb_set(inventory, '{{food, {dropped_food}}}', 
                    (COALESCE((inventory->'food'->>'{dropped_food}')::int, 0) + 1)::text::jsonb)
                    WHERE owner_id = $1
                """, uid)
                
                emoji_map = {
                    "tangerines": "🍊", 
                    "watermelon_slices": "🍉", 
                    "melon": "🍈", 
                    "mango": "🥭", 
                    "kiwi": "🥝"
                }
                
                food_icon = emoji_map.get(dropped_food, "🍽")
                reward_info += f"\n🎁 <b>Знайдено:</b> 1x {food_icon}!"

            if hasattr(p1, 'stolen_items') and p1.stolen_items and opp_id and not (is_boss or bot_type or is_ghost):
                summary = []
                for item in p1.stolen_items:
                    await conn.execute(f"""
                        UPDATE capybaras 
                        SET inventory = jsonb_set(inventory, '{{food, {item}}}', 
                        (COALESCE((inventory->'food'->>'{item}')::int, 0) + 1)::text::jsonb)
                        WHERE owner_id = $1
                    """, uid)
                    summary.append(item)
                
                await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", 
                                json.dumps(p2.inv), opp_id)

                if summary:
                    reward_info += f"\n🏴‍☠️ <b>Вибито в бою:</b> " + ", ".join([f"<code>{i}</code>" for i in summary])

        elif winner == p2:
            res = f"💀 <b>ПОРАЗКА {p1.color}!</b>\n{html.bold(p2.name)} зніс кабіну."
            if is_parrot:
                reward_info = "\n\n🦜 <i>Павло: «Більше тренуйся, сопляк!»</i>"
            else:
                loss_weight = -1 * int(p2.hp * 0.2)
                reward_info = f"\n\n📉 <b>Збитки:</b>\n🥈 {loss_weight} кг"
                await grant_exp_and_lvl(uid, exp_gain=0, weight_gain=loss_weight, bot=bot, db_pool=db_pool)

        else:
            res = "🤝 <b>НІЧИЯ!</b>\nСили виявилися рівними, бійці впали на травичку."
            if not is_parrot:
                draw_exp = 1
                reward_info = f"\n\n📈 <b>Результат:</b>\n⚪️ +0 кг, +{draw_exp} EXP"
                await grant_exp_and_lvl(uid, exp_gain=draw_exp, weight_gain=0, bot=bot, db_pool=db_pool)

    return res, reward_info

async def _execute_actual_steal(winner_id: int, loser_id: int, stolen_list: list, conn) -> str:
    if not stolen_list: return ""
    
    to_steal = stolen_list[:2]
    
    row = await conn.fetchrow("SELECT inventory FROM capybaras WHERE owner_id = $1", loser_id)
    inv_loser = json.loads(row['inventory']) if isinstance(row['inventory'], str) else (row['inventory'] or {})
    
    summary = []
    for item in to_steal:
        if inv_loser.get("food", {}).get(item, 0) > 0:
            inv_loser["food"][item] -= 1
            if inv_loser["food"][item] <= 0: del inv_loser["food"][item]
            
            await conn.execute(f"""
                UPDATE capybaras 
                SET inventory = jsonb_set(inventory, '{{food, {item}}}', 
                (COALESCE((inventory->'food'->>'{item}')::int, 0) + 1)::text::jsonb)
                WHERE owner_id = $1
            """, winner_id)
            summary.append(item)

    await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv_loser), loser_id)
    
    if summary:
        items_str = ", ".join([f"<code>{i}</code>" for i in summary])
        return f"\n🏴‍☠️ <b>Здобич з бою:</b> {items_str}"
    return ""

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
