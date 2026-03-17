import json
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.crud_capybaras import get_full_profile
from config import STAT_WEIGHTS, BASE_HIT_CHANCE, BASE_BLOCK_CHANCE

router = Router()

def get_fight_stats_text(data):
    total = data.get('total_fights') or 0
    wins = data.get('wins') or 0
    win_rate = (wins / total * 100) if total > 0 else 0
    
    equip = data.get('equipment')
    if isinstance(equip, str):
        try: equip = json.loads(equip)
        except: equip = {}
    elif equip is None:
        equip = {}

    weapon_data = equip.get('weapon', {"name": "Лапки"})
    weapon_name = weapon_data.get('name', "Лапки") if isinstance(weapon_data, dict) else "Лапки"

    armor_data = equip.get('armor', "Хутро")
    if isinstance(armor_data, dict):
        armor_name = armor_data.get('name', "Хутро")
    else:
        armor_name = str(armor_data)
    
    state = data.get('state')
    if isinstance(state, str):
        try: state = json.loads(state)
        except: state = {}
    elif state is None:
        state = {}
    
    blessings = data.get('blessings', [])
    curses = data.get('curses', [])

    blessing_text = " ✨ " + ", ".join(blessings) if blessings else "<i>(відсутні)</i>"
    curse_text = " 💀 " + ", ".join(curses) if curses else "<i>(відсутні)</i>"

    hit_chance = round(100 * (BASE_HIT_CHANCE + STAT_WEIGHTS['atk_to_hit'] * data['atk']), 0)
    block_chance = round(100 * (BASE_BLOCK_CHANCE + STAT_WEIGHTS['def_to_block'] * data['def']), 0)
    dodge_chance = round(100 * (STAT_WEIGHTS['agi_to_dodge'] * data['agi']), 0)
    crit_bonus = round(100 * (STAT_WEIGHTS['luck_to_crit'] * data['luck']), 0)
    inv = data.get("inventory")
    if isinstance(inv, str):
        try: inv = json.loads(inv)
        except: inv = {}
    elif inv is None:
        inv = {}

    eq_dict = inv.get("equipment", {})
    if isinstance(eq_dict, str):
        try: eq_dict = json.loads(eq_dict)
        except: eq_dict = {}

    # 3. Перевірка на "Котяче життя"
    has_cat_life = any(item.get("name") == "Котяче життя" for item in eq_dict.values() if isinstance(item, dict))
    additional_hp = 1 if has_cat_life else 0
    
    return (
        f"<b>⚔️ БОЙОВІ ХАРАКТЕРИСТИКИ</b>\n"
        f"<b>{data['name']}</b>\n"
        f"________________________________\n\n"
        f"🏆 Перемог: <b>{win_rate:.1f}%</b> ({data['wins']}/{total})\n"
        f"⚔️ Зброя: <b>{weapon_name}</b>\n"
        f"🔰 Броня: <b>{armor_name}</b>\n\n"
        f"✨ Благословення: {blessing_text}\n"
        f"💀 Прокляття: {curse_text}\n"
        f"________________________________\n\n"
        f"<b>Показники:</b>\n"
        f"🔥 ATK: <b>{hit_chance}%</b>  |  "
        f"🛡️ DEF: <b>{block_chance}%</b>\n"
        f"💨 AGI: <b>{dodge_chance}%</b>  |  "
        f"🍀 LCK: <b>+{crit_bonus}%</b>\n"
        f"♥️ HP: <b>{(data['max_hp'] + additional_hp) * 2}</b>"
    )

@router.callback_query(F.data == "show_fight_stats")
async def show_fight_stats(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    data = await get_full_profile(db_pool, uid)
    
    if not data:
        return await callback.answer("❌ Капібару не знайдено", show_alert=True)

    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="open_profile_main")
    
    await callback.message.edit_caption(
        caption=get_fight_stats_text(data),
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()