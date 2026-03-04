import asyncio
import json
import random
from aiogram import Router, types, html, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.harbor.settings.emotes import send_victory_celebration
from core.combat.combat_system import Fighter, CombatEngine
from utils.helpers import grant_exp_and_lvl
from config import BASE_HITPOINTS, WEAPON, ARMOR, NPC_REGISTRY, BOSS_ID_MAP

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
            SELECT name, weight, inventory, atk, def, agi, luck , equipment
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

        weapon_obj = eq_data.get("weapon") or {"name": "Лапки", "lvl": 0}
        armor_obj = eq_data.get("armor") or {"name": "Хутро", "lvl": 0}

        return {
            "kapy_name": row['name'],
            "weight": row['weight'],
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

async def run_battle_logic(callback: types.CallbackQuery, db_pool, opponent_id: int = None, bot_type: str = None, is_boss: bool = False, is_ghost: bool = False, tomb_id: int = None):
    bot = callback.bot
    uid = callback.from_user.id

    async with db_pool.acquire() as conn:
        stamina = await conn.fetchval("SELECT stamina FROM capybaras WHERE owner_id = $1", uid)
        if stamina is None or stamina < 5:
            return await callback.answer("🪫 Твоя капібара надто стомлена для бою! (Треба мінімум 5⚡)", show_alert=True)
    
    p1_data = await get_full_capy_data(uid, db_pool)
    p2_data = None

    if is_ghost and tomb_id:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT name, final_lvl, final_stats, ghost_inventory FROM graveyard WHERE id = $1", tomb_id)
            if row:
                g_stats = json.loads(row['final_stats'])
                g_inv = json.loads(row['ghost_inventory'])
                
                g_eq = g_inv.get("equipment", [])
                g_weapons = [i for i in g_eq if isinstance(i, dict) and i.get("type") == "weapon"]
                g_armors = [i for i in g_eq if isinstance(i, dict) and i.get("type") == "armor"]
                
                p2_data = {
                    "kapy_name": f"👻 Привид {row['name']}",
                    "lvl": row['final_lvl'],
                    "hp_bonus": 0,
                    "stats": {
                        "attack": max(1, int(g_stats.get('atk', 1) * 0.6)),
                        "defense": int(g_stats.get('def', 0) * 0.6),
                        "agility": max(1, int(g_stats.get('agi', 1) * 0.6)),
                        "luck": int(g_stats.get('luck', 0) * 0.6)
                    },
                    "weapon_full": random.choice(g_weapons) if g_weapons else {"name": "Примарні лапки", "lvl": 1},
                    "armor_full": random.choice(g_armors) if g_armors else {"name": "Саван", "lvl": 1},
                    "color": "⚪️",
                    "is_ghost": True,
                    "raw_inv": g_inv
                }

    if not p2_data:
        p2_data = await get_full_capy_data(opponent_id, db_pool, b_type=bot_type)

    if not p1_data or not p2_data:
        return await callback.message.answer("❌ Помилка: Дані капібари не знайдено.")

    for data in [p1_data, p2_data]:
        for key in ["weapon_full", "armor_full"]:
            val = data.get(key)
            if isinstance(val, str):
                data[key] = {"name": val, "lvl": 0}
            elif not val:
                data[key] = {"name": "Нічого", "lvl": 0}

    battle_config = {"WEAPONS": WEAPON, "ARMOR": ARMOR}
    p1 = Fighter(p1_data, battle_config, color="🟢")
    p2 = Fighter(p2_data, battle_config, color=p2_data.get("color", "🔴"))

    if p2_data.get("hp_bonus"):
        p2.max_hp = int(p2.max_hp + p2_data["hp_bonus"])
        p2.hp = p2.max_hp

    main_msg = await callback.message.answer(f"🏟 <b>ПІДГОТОВКА ДО БОЮ...</b>\n\n{p1.name} VS {p2.name}", parse_mode="HTML")
    await asyncio.sleep(1.5)

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
        try:
            await main_msg.edit_text(full_report, parse_mode="HTML")
        except:
            pass
            
        attacker, defender = defender, attacker
        await asyncio.sleep(2.3)
        round_num += 1

    winner, loser = (p1, p2) if p1.hp > 0 else (p2, p1) if p2.hp > 0 else (None, None)
    winner_id = uid if winner == p1 else (opponent_id if winner == p2 else None)
    
    is_parrot = (bot_type == "parrotbot")
    res = "🤝 <b>НІЧИЯ!</b>"
    reward_info = ""

    boss_cfg = BOSS_REWARDS.get(bot_type) if is_boss else None

    if winner == p1:
        res = f"🏆 <b>ПЕРЕМОГА {p1.color}!</b>\n{html.bold(p1.name)} здобув звитягу!"
        if is_ghost:
            g_inv = p2_data["raw_inv"]
            recovered = []
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT c.inventory, u.reincarnation_count 
                    FROM capybaras c
                    JOIN users u ON c.owner_id = u.user_id
                    WHERE c.owner_id = $1
                """, uid)     
                curr_inv = json.loads(row['inventory'])
                reinc_count = row['reincarnation_count'] or 0
                spiritual_power = min(1.0, reinc_count * 0.1)
                
                for cat in ["food", "materials", "equipment"]:
                    if cat in g_inv and g_inv[cat]:
                        items = list(g_inv[cat]) if isinstance(g_inv[cat], (list, dict)) else []
                        if items:
                            loot_count = max(1, int(len(items) * spiritual_power))
                            selected_items = random.sample(items, k=loot_count)
                            for target in selected_items:
                                if cat == "equipment":
                                    curr_inv.setdefault(cat, []).append(target)
                                    recovered.append(f"✨ {target.get('name', 'Екіпіровка')}")
                                else:
                                    total_qty = g_inv[cat][target]
                                    recovered_qty = max(1, int(total_qty * random.uniform(0.5, 1.0)))
                                    curr_inv.setdefault(cat, {})[target] = curr_inv[cat].get(target, 0) + recovered_qty
                                    recovered.append(f"{target} x{recovered_qty}")
                
                await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(curr_inv), uid)
                await conn.execute("DELETE FROM graveyard WHERE id = $1", tomb_id)
                nav_raw = await conn.fetchval("SELECT navigation FROM capybaras WHERE owner_id = $1", uid)
                nav = json.loads(nav_raw)
                if "loot" in nav and "treasure_maps" in nav["loot"]:
                    nav["loot"]["treasure_maps"] = [m for m in nav["loot"]["treasure_maps"] if not (m.get("type") == "tomb" and m.get("id") == tomb_id)]
                await conn.execute("UPDATE capybaras SET navigation = $1 WHERE owner_id = $2", json.dumps(nav), uid)

            reinc_text = f"<i>(Духовна сила: {int(spiritual_power*100)}%)</i>"
            reward_info = f"\n\n👻 <b>СПАДЩИНА ПРЕДКА:</b> {reinc_text}\n{', '.join(recovered)}"
    
        elif is_boss and boss_cfg:
            reward_info = f"\n\n🏆 <b>БОС ПОДОЛАНИЙ!</b>\n📈 +{boss_cfg['weight']} кг, +{boss_cfg['exp']} EXP"
        elif not is_parrot:
            reward_info = f"\n\n📈 <b>Нагорода:</b>\n🥇 +3 кг, +3 EXP"

    elif winner == p2:
        res = f"💀 <b>ПОРАЗКА {p1.color}!</b>\n{html.bold(p2.name)} виявився сильнішим."
        if is_parrot:
            reward_info = "\n\n🦜 <i>Папуга Павло дає тобі пораду: «Більше тренуйся, сопляк!»</i>"
        else:
            reward_info = "\n\n📉 <b>Збитки:</b>\n🥈 -3 кг"

    await main_msg.edit_text(f"🏁 <b>БІЙ ЗАВЕРШЕНО</b>\n━━━━━━━━━━━━━━\n{res}{reward_info}", parse_mode="HTML")

    if winner and loser:
        async with db_pool.acquire() as conn:
            if winner == p1 and not is_parrot:
                if is_boss and boss_cfg:
                    exp_gain = boss_cfg['exp']
                    weight_gain = boss_cfg['weight']
                else:
                    exp_gain = winner.hp
                    weight_gain = winner.hp

                await grant_exp_and_lvl(uid, exp_gain=exp_gain, weight_gain=weight_gain, bot=bot, db_pool=db_pool)
                await conn.execute("UPDATE capybaras SET wins=wins+1, total_fights=total_fights+1, stamina=GREATEST(stamina-5, 0) WHERE owner_id=$1", uid)
                
                if is_boss:
                    curr_prog = await conn.fetchval("SELECT (stats_track->>'boss_defeated')::int FROM capybaras WHERE owner_id=$1", uid) or 0
                    curr_id = next((k for k, v in BOSS_ID_MAP.items() if v == bot_type), 0)
                    if curr_id == curr_prog + 1:
                        await conn.execute("UPDATE capybaras SET stats_track=stats_track || jsonb_build_object('boss_defeated', $2::int) WHERE owner_id=$1", uid, curr_prog+1)
            
            if loser == p1:
                await grant_exp_and_lvl(uid, exp_gain=0, weight_gain=-1*winner.hp, bot=bot, db_pool=db_pool)
                await conn.execute("UPDATE capybaras SET total_fights=total_fights+1, stamina=GREATEST(stamina-5, 0) WHERE owner_id=$1", uid)

            if opponent_id and opponent_id != uid and not is_ghost and not is_boss:
                if winner == p2:
                    await grant_exp_and_lvl(opponent_id, exp_gain=winner.hp, weight_gain=winner.hp, bot=bot, db_pool=db_pool)
                else:
                    await grant_exp_and_lvl(opponent_id, exp_gain=0, weight_gain=-1*winner.hp, bot=bot, db_pool=db_pool)
                await conn.execute("UPDATE capybaras SET total_fights=total_fights+1, stamina=GREATEST(stamina-5, 0) WHERE owner_id=$1", opponent_id)

        if winner == p1 and not is_parrot:
            await send_victory_celebration(bot=callback.bot, chat_id=callback.message.chat.id, user_id=uid, db_pool=db_pool)

@router.callback_query(F.data == "fight_bot")
async def handle_fight_bot(callback: types.CallbackQuery, db_pool):
    await callback.message.answer("🤖 Папуга Павло гострить дзьоб...")
    asyncio.create_task(run_battle_logic(callback, db_pool, bot_type="parrotbot"))
    await callback.answer()