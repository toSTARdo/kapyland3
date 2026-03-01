import asyncio
import json
import random
from aiogram import Router, types, html, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.harbor.settings.emotes import send_victory_celebration
from core.combat.combat_system import Fighter, CombatEngine
from utils.helpers import grant_exp_and_lvl
from config import BASE_HITPOINTS, WEAPON, ARMOR

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

    await callback.message.edit_text("🚀 Бій прийнято! Капібари виходять на дуель... (-5 ⚡)")
    
    asyncio.create_task(run_battle_logic(callback, db_pool, opponent_id=challenger_id))
    await callback.answer()

@router.callback_query(F.data == "fight_bot")
async def handle_fight_bot(callback: types.CallbackQuery, db_pool):
    await callback.message.answer("🤖 Папуга Павло гострить дзьоб...")
    asyncio.create_task(run_battle_logic(callback, db_pool, bot_type="parrotbot"))
    await callback.answer()


async def run_battle_logic(callback: types.CallbackQuery, db_pool, opponent_id: int = None, bot_type: str = None):
    bot = callback.bot
    uid = callback.from_user.id

    async with db_pool.acquire() as conn:
        stamina = await conn.fetchval("SELECT stamina FROM capybaras WHERE owner_id = $1", uid)
        if stamina is None or stamina < 5:
            return await callback.answer("🪫 Твоя капібара надто стомлена для бою! (Треба мінімум 5⚡)", show_alert=True)
    
    battle_config = {"WEAPONS": WEAPON, "ARMOR": ARMOR}

    async def get_full_capy_data(target_id: int, b_type: str = None):
        NPC_REGISTRY = {
            "parrotbot": {
                "kapy_name": "Папуга Павло", "color": "🦜",
                "stats": {"attack": 1, "defense": 1, "agility": 3, "luck": 1},
                "equipped_weapon": "Весло", "hp_bonus": 0
            },
            "mimic": {
                "kapy_name": "Мімік", "color": "🗃",
                "stats": {"attack": 4, "defense": 2, "agility": 5, "luck": 2},
                "equipped_weapon": "Зуби акули", "hp_bonus": 4
            },
            "boss_pelican": {
                "kapy_name": "Пелікан Петро", "color": "🦢",
                "stats": {"attack": 15, "defense": 8, "agility": 5, "luck": 5},
                "equipped_weapon": "Дзьоб", "hp_bonus": 7, "is_boss": True
            }
        }

        if b_type in NPC_REGISTRY:
            return NPC_REGISTRY[b_type]

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT name, weight, inventory, atk, def, agi, luck 
                FROM capybaras 
                WHERE owner_id = $1
            """, target_id)
            
            if not row: return None
            
            inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else (row['inventory'] or {})
            raw_equip = inv.get("equipment", [])
            
            eq_weapon_name = "Лапки"
            eq_armor_name = "Хутро"

            if isinstance(raw_equip, list):
                for item in raw_equip:
                    if not isinstance(item, dict): continue
                    if item.get("type") == "weapon" and eq_weapon_name == "Лапки":
                        eq_weapon_name = item.get("name", "Лапки")
                    elif item.get("type") == "armor" and eq_armor_name == "Хутро":
                        eq_armor_name = item.get("name", "Хутро")
            
            stats = {
                "attack": row['atk'] if row['atk'] is not None else 1,
                "defense": row['def'] if row['def'] is not None else 0,
                "agility": row['agi'] if row['agi'] is not None else 1,
                "luck": row['luck'] if row['luck'] is not None else 0
            }
            
            return {
                "kapy_name": row['name'],
                "weight": row['weight'],
                "stats": stats,
                "equipped_weapon": eq_weapon_name,
                "equipped_armor": eq_armor_name,
                "inventory": inv,
                "color": "🔴"
            }

    p1_data = await get_full_capy_data(uid)
    p2_data = await get_full_capy_data(opponent_id, b_type=bot_type)

    if not p1_data or not p2_data:
        return await callback.message.answer("❌ Помилка: Дані капібари не знайдено.")

    p1 = Fighter(p1_data, battle_config, color="🟢")
    p2 = Fighter(p2_data, battle_config, color=p2_data.get("color", "🔴"))

    if p2_data.get("hp_bonus"):
        p2.max_hp += p2_data["hp_bonus"]
        p2.hp = p2.max_hp

    start_info = f"🏟 <b>БІЙ: {p1.name} VS {p2.name}</b>"
    msg1 = await callback.message.answer(start_info, parse_mode="HTML")
    msg2 = None
    if opponent_id and not bot_type:
        try: msg2 = await bot.send_message(opponent_id, start_info, parse_mode="HTML")
        except: pass

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

    await msg1.answer(init_msg, parse_mode="HTML")
    if msg2:
        try: await msg2.answer(init_msg, parse_mode="HTML")
        except: pass

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
            await msg1.edit_text(full_report, parse_mode="HTML")
            if msg2: await msg2.edit_text(full_report, parse_mode="HTML")
        except: pass
            
        attacker, defender = defender, attacker
        await asyncio.sleep(2.3)
        round_num += 1

    winner_id, loser_id = None, None
    if p1.hp > 0 and p2.hp <= 0:
        winner, loser = p1, p2
        winner_id, loser_id = uid, opponent_id
        res = f"🏆 <b>ПЕРЕМОГА {p1.color}!</b>\n{html.bold(p1.name)} розгромив суперника {html.bold(p2.name)}!"
    elif p2.hp > 0 and p1.hp <= 0:
        winner, loser = p2, p1
        winner_id, loser_id = opponent_id, uid
        res = f"👑 <b>ПЕРЕМОГА {p2.color}!</b>\n{html.bold(p2.name)} виявився сильнішим за {html.bold(p1.name)}!"
    else: 
        res = "🤝 <b>НІЧИЯ! Капі обезсилені впали на травичку...</b>"

    await msg1.answer(res, parse_mode="HTML")
    if msg2:
        try: await msg2.answer(res, parse_mode="HTML")
        except: pass

    if winner and loser:
        is_parrot_fight = (bot_type == "parrotbot")
        
        async with db_pool.acquire() as conn:
            if isinstance(winner_id, int) and not is_parrot_fight: 
                await grant_exp_and_lvl(winner_id, exp_gain=3, weight_gain=3.0, bot=bot)
                
                await conn.execute("""
                    UPDATE capybaras 
                    SET wins = wins + 1, 
                        total_fights = total_fights + 1, 
                        stamina = GREATEST(stamina - 5, 0)
                    WHERE owner_id = $1
                """, winner_id)

            if isinstance(loser_id, int):
                weight_loss = -3.0 if not is_parrot_fight else 0.0
                await grant_exp_and_lvl(loser_id, exp_gain=0, weight_gain=weight_loss, bot=bot)
                
                await conn.execute("""
                    UPDATE capybaras 
                    SET total_fights = total_fights + 1, 
                        stamina = GREATEST(stamina - 5, 0)
                    WHERE owner_id = $1
                """, loser_id)
            
        if is_parrot_fight:
            reward_msg = "<b>Тренувальний бій завершено!</b>\n<i>«Гарна розминка, але досвіду за це не дають!»</i>\n"
        else:
            reward_msg = (
                f"📈 <b>Підсумки бою:</b>\n"
                f"🥇 {winner.name}: {'+3 кг, +3 EXP' if isinstance(winner_id, int) else 'Природжена сила'}\n"
                f"🥈 {loser.name}: {'-3 кг' if isinstance(loser_id, int) else 'Просто зник у кущах'}"
            )
        
        await msg1.answer(reward_msg, parse_mode="HTML")
        if msg2:
            try: await msg2.answer(reward_msg, parse_mode="HTML")
            except: pass

        if winner_id and not is_parrot_fight:
            await send_victory_celebration(msg1, winner_id)

@router.callback_query(F.data == "fight_bot")
async def handle_fight_bot(callback: types.CallbackQuery):
    await callback.message.answer("🤖 Папуга Павло гострить дзьоб...")
    asyncio.create_task(run_battle_logic(callback, bot_type="parrotbot"))
    await callback.answer()