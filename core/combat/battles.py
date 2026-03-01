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

async def get_full_capy_data(target_id, db_pool, b_type=None):
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
        
        return {
            "kapy_name": row['name'],
            "weight": row['weight'],
            "stats": {
                "attack": row['atk'] or 1,
                "defense": row['def'] or 0,
                "agility": row['agi'] or 1,
                "luck": row['luck'] or 0
            },
            "equipped_weapon": eq_weapon_name,
            "equipped_armor": eq_armor_name,
            "inventory": inv,
            "color": "🔴"
        }

async def run_battle_logic(callback: types.CallbackQuery, db_pool, opponent_id: int = None, bot_type: str = None):
    bot = callback.bot
    uid = callback.from_user.id

    async with db_pool.acquire() as conn:
        stamina = await conn.fetchval("SELECT stamina FROM capybaras WHERE owner_id = $1", uid)
        if stamina is None or stamina < 5:
            return await callback.answer("🪫 Твоя капібара надто стомлена для бою! (Треба мінімум 5⚡)", show_alert=True)
    
    p1_data = await get_full_capy_data(uid, db_pool)
    p2_data = await get_full_capy_data(opponent_id, db_pool, b_type=bot_type)

    if not p1_data or not p2_data:
        return await callback.message.answer("❌ Помилка: Дані капібари не знайдено.")

    battle_config = {"WEAPONS": WEAPON, "ARMOR": ARMOR}
    p1 = Fighter(p1_data, battle_config, color="🟢")
    p2 = Fighter(p2_data, battle_config, color=p2_data.get("color", "🔴"))

    if p2_data.get("hp_bonus"):
        p2.max_hp += p2_data["hp_bonus"]
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
    winner_id = uid if winner == p1 else opponent_id if winner == p2 else None
    loser_id = opponent_id if winner == p1 else uid if winner == p2 else None

    if not winner:
        res = "🤝 <b>НІЧИЯ! Капі обезсилені впали на травичку...</b>"
    else:
        res = f"🏆 <b>ПЕРЕМОГА {winner.color}!</b>\n{html.bold(winner.name)} здобув звитягу над {html.bold(loser.name)}!"

    is_parrot = (bot_type == "parrotbot")
    reward_info = ""
    if winner:
        if is_parrot:
            reward_info = "\n\n<i>Це був тренувальний бій. Досвід не нараховано.</i>"
        else:
            reward_info = f"\n\n📈 <b>Нагорода:</b>\n🥇 {winner.name}: +3 кг, +3 EXP\n🥈 {loser.name}: -3 кг"

    await main_msg.edit_text(f"🏁 <b>БІЙ ЗАВЕРШЕНО</b>\n━━━━━━━━━━━━━━\n{res}{reward_info}", parse_mode="HTML")

    if winner and loser:
        async with db_pool.acquire() as conn:
            if winner_id and not is_parrot: 
                await grant_exp_and_lvl(winner_id, exp_gain=3, weight_gain=3.0, bot=bot, db_pool=db_pool)
                await conn.execute("UPDATE capybaras SET wins = wins + 1, total_fights = total_fights + 1, stamina = GREATEST(stamina - 5, 0) WHERE owner_id = $1", winner_id)

            if loser_id:
                w_loss = -3.0 if not is_parrot else 0.0
                await grant_exp_and_lvl(loser_id, exp_gain=0, weight_gain=w_loss, bot=bot, db_pool=db_pool)
                await conn.execute("UPDATE capybaras SET total_fights = total_fights + 1, stamina = GREATEST(stamina - 5, 0) WHERE owner_id = $1", loser_id)

        if winner_id == uid and not is_parrot:
            await send_victory_celebration(main_msg, uid)

@router.callback_query(F.data == "fight_bot")
async def handle_fight_bot(callback: types.CallbackQuery, db_pool):
    await callback.message.answer("🤖 Папуга Павло гострить дзьоб...")
    asyncio.create_task(run_battle_logic(callback, db_pool, bot_type="parrotbot"))
    await callback.answer()