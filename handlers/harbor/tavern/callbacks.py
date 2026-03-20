import json
import random
import datetime
import asyncio

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BASE_HIT_CHANCE, BASE_BLOCK_CHANCE, STAT_WEIGHTS, DISPLAY_NAMES
from core.combat.battles import run_battle_logic
from utils.helpers import check_daily_limit, ensure_dict

router = Router()

ITEM_DISPLAY_NAMES = {
    "watermelon_slices": "🍉 Скибочка кавуна",
    "tangerines": "🍊 Мандарин",
    "melon": "🍈 Диня",
    "kiwi": "🥝 Ківі",
    "mango": "🥭 Манго"
}

async def execute_ram_logic(callback: types.CallbackQuery, target_id: int, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT equipment, inventory, state, stamina FROM capybaras WHERE owner_id = $1", uid)
        if not row: return
        
        if (row['stamina'] or 0) < 15:
            return await callback.answer("🪫 Бракує сил (треба 15⚡)", show_alert=True)

        state = ensure_dict(row['state'])
        last_ram_str = state.get("last_ram")
        if last_ram_str and (datetime.now() - datetime.fromisoformat(last_ram_str)).total_seconds() < 3600:
            return await callback.answer("🛠 Корабель ще лагодять!", show_alert=True)

        all_items = str(row['equipment']) + str(row['inventory'])
        if not any(x in all_items.lower() for x in ["таран", "бур"]):
            return await callback.answer("❌ Тобі потрібен 'Таран'!", show_alert=True)

        state["last_ram"] = datetime.now().isoformat()
        await conn.execute("UPDATE capybaras SET state = $1, stamina = stamina - 15 WHERE owner_id = $2", json.dumps(state), uid)

    await callback.message.edit_caption(caption="💥 <b>БА-БАХ!</b>\nТріски летять в усі боки! 🪵", parse_mode="HTML")
    asyncio.create_task(run_battle_logic(callback, opponent_id=target_id, db_pool=db_pool))

async def execute_steal_logic(callback: types.CallbackQuery, target_id: int, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        actor = await conn.fetchrow("""
            SELECT name, inventory, state, cooldowns, luck, equipment 
            FROM capybaras WHERE owner_id = $1
        """, uid)
        target = await conn.fetchrow("""
            SELECT name, inventory, state, luck 
            FROM capybaras WHERE owner_id = $1
        """, target_id)
        
        if not actor or not target: 
            return await callback.answer("Ціль зникла у тумані...")

        a_inv = ensure_dict(actor['inventory'])
        a_cool = ensure_dict(actor['cooldowns'])
        a_state = ensure_dict(actor['state'])
        a_eq = ensure_dict(actor['equipment'])
        
        t_inv = ensure_dict(target['inventory'])
        t_state = ensure_dict(target['state'])

        daily_steals = a_cool.get("daily_steals", 0)
        if daily_steals >= 3:
            return await callback.answer("🥷 Лапки втомилися красти! (Ліміт вичерпано)", show_alert=True)

        has_thief_gear = any("злодій" in str(v).lower() for v in a_eq.values())
        
        success_chance = 0.45 if has_thief_gear else (0.10 + actor['luck'] * 0.01)
        if t_state.get("status") == "sleep":
            success_chance += 0.20
            
        catch_chance = success_chance + 0.15
        roll = random.random()

        if roll < success_chance:
            steal_type = random.choice(["food", "equipment"])
            target_pool = t_inv.get(steal_type, {})
            
            available_items = [k for k, v in target_pool.items() if (v > 0 if steal_type == "food" else True)]

            if not available_items:
                steal_type = "equipment" if steal_type == "food" else "food"
                target_pool = t_inv.get(steal_type, {})
                available_items = [k for k, v in target_pool.items() if (v > 0 if steal_type == "food" else True)]

            if not available_items:
                return await callback.answer("🧤 У капібари зовсім порожні кишені...", show_alert=True)

            stolen_key = random.choice(available_items)
            
            if steal_type == "food":
                t_inv["food"][stolen_key] -= 1
                if t_inv["food"][stolen_key] <= 0: del t_inv["food"][stolen_key]
                a_inv.setdefault("food", {})[stolen_key] = a_inv.get("food", {}).get(stolen_key, 0) + 1
            else:
                item_data = t_inv["equipment"].pop(stolen_key)
                a_inv.setdefault("equipment", {})[stolen_key] = item_data

            a_cool["daily_steals"] = daily_steals + 1

            await conn.execute("""
                UPDATE capybaras SET inventory = $1, cooldowns = $2 WHERE owner_id = $3
            """, json.dumps(a_inv), json.dumps(a_cool), uid)
            await conn.execute("""
                UPDATE capybaras SET inventory = $1 WHERE owner_id = $2
            """, json.dumps(t_inv), target_id)

            item_display = DISPLAY_NAMES[stolen_key] if steal_type == "food" else stolen_key
            await callback.message.edit_caption(
                caption=f"🥷 <b>НАЙШВИДШІ ЛАПКИ!</b>\nПоцуплено ({steal_type}): <b>{item_display}</b>!"
            )

        elif roll < catch_chance:
            if t_state.get("status") == "sleep":
                t_state["status"] = "active"
                await conn.execute("UPDATE capybaras SET state = $1 WHERE owner_id = $2", json.dumps(t_state), target_id)
            
            await callback.message.edit_caption(caption="😱 <b>ВАС ПІЙМАЛИ!</b>\nГосподареві це не сподобалося!")
            asyncio.create_task(run_battle_logic(callback, db_pool=db_pool, opponent_id=target_id))
        else:
            await callback.answer("💨 Ви шмигнули в кущі, нічого не знайшовши.", show_alert=True)

async def handle_inspect_player(callback: types.CallbackQuery, target_id: int, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        target = await conn.fetchrow("""
            SELECT u.username, c.name, c.lvl, c.karma, c.atk, c.def, c.luck, c.agi, c.max_hp, c.weight, c.state, c.equipment, s.name as ship_name
            FROM users u JOIN capybaras c ON u.tg_id = c.owner_id LEFT JOIN ships s ON c.ship_id = s.id
            WHERE u.tg_id = $1
        """, target_id)
        
    if not target: return await callback.answer("❌ Капібара зникла...", show_alert=True)

    state, equip = parse_json(target['state']), parse_json(target['equipment'])
    atk, def_, agi, luck = target["atk"], target["def"], target["agi"], target["luck"]
    max_hp = target["max_hp"]    

    ship_info = f"𓊝 {target['ship_name']}" if {target['ship_name']} else "⊥ Мандрує на плоті"

    text = (f"📜 <b>Розшукується: {target['name']}</b>\n"
            f"👤 Власник: <code>{target['username']}</code>\n"
            f"{ship_info}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🔹 <b>Зараз:</b> {'💤 Спить' if state.get('status') == 'sleep' else '🐾 Гуляє'}\n"
            f"🎖 <b>Рівень:</b> {target['lvl']} | ⚖️ <b>Вага:</b> {target['weight']} кг\n"
            f"⚔️ <b>Арсенал:</b> {get_item_name(equip.get('weapon'), 'Лапки')}"
            f"ATK: {atk} | DEF: {def_} | AGI: {agi} | LUCK: {luck}"
            f"♥️: {max_hp}")

    builder = InlineKeyboardBuilder()
    builder.button(text="⚔️ Виклик", callback_data=f"challenge_{target_id}")
    builder.button(text="🎁 Подарунок", callback_data=f"gift_to:{target_id}")
    builder.button(text="🔙 Назад", callback_data="social")
    builder.adjust(2, 1)

    if callback.message.photo:
        await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await callback.message.edit_text(text=text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("gift_to:"))
async def gift_category_select(callback: types.CallbackQuery, db_pool):
    target_id = int(callback.data.split(":")[1])
    builder = InlineKeyboardBuilder()
    builder.button(text="🍎 Їжа", callback_data=f"send_cat:food:{target_id}")
    builder.button(text="💎 Ресурси", callback_data=f"send_cat:materials:{target_id}")
    builder.button(text="⚔️ Спорядження", callback_data=f"send_cat:loot:{target_id}")
    builder.button(text="🔙 Назад", callback_data=f"social")
    builder.adjust(2, 1, 1)
    await callback.message.edit_caption(
        caption="🎁 <b>Меню подарунків</b>\nОберіть, що саме хочете надіслати друзяці:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("send_cat:"))
async def gift_item_select(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split(":")
    category, target_id, uid = parts[1], int(parts[2]), callback.from_user.id
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, cooldowns FROM capybaras WHERE owner_id = $1", uid)
        inv = row['inventory'] if isinstance(row['inventory'], dict) else json.loads(row['inventory'])
        cools = row['cooldowns'] if isinstance(row['cooldowns'], dict) else json.loads(row['cooldowns'])
        can_gift, _ = check_daily_limit(cools, "gift")
        if not can_gift:
            return await callback.answer("🎁 Ти вже сьогодні дарував! Спробуй завтра.", show_alert=True)
        builder = InlineKeyboardBuilder()
        items = inv.get(category, {})
        valid_items = {k: v for k, v in items.items() if v > 0}
        if not valid_items:
            return await callback.answer("Тут порожньо... 🕸", show_alert=True)
        for item_key, count in valid_items.items():
            name = DISPLAY_NAMES.get(item_key, item_key)
            builder.button(
                text=f"{name} ({count})", 
                callback_data=f"gift_exec:{category}:{item_key}:{target_id}"
            )
        builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data=f"gift_to:{target_id}"))
        builder.adjust(1)
        await callback.message.edit_caption(
            caption=f"🎁 <b>Твій рюкзак ({category}):</b>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("gift_exec:"))
async def execute_gift_transfer(callback: types.CallbackQuery, db_pool):
    _, category, item_key, target_id = callback.data.split(":")
    uid, target_id = callback.from_user.id, int(target_id)
    async with db_pool.acquire() as conn:
        sender_data = await conn.fetchrow("SELECT username, cooldowns FROM users u JOIN capybaras c ON u.tg_id = c.owner_id WHERE u.tg_id = $1", uid)
        sender_name = sender_data['username'] if sender_data and sender_data['username'] else callback.from_user.first_name
        res = await conn.execute(f"""
            UPDATE capybaras 
            SET inventory = jsonb_set(inventory, '{{{category}, {item_key}}}', 
                ((inventory->'{category}'->>'{item_key}')::int - 1)::text::jsonb),
                karma = karma + 1
            WHERE owner_id = $1 AND (inventory->'{category}'->>'{item_key}')::int > 0
        """, uid)
        if res == "UPDATE 0": 
            return await callback.answer("Предмет раптово закінчився! 💨", show_alert=True)
        await conn.execute(f"""
            UPDATE capybaras 
            SET inventory = jsonb_set(
                inventory, 
                '{{{category}}}', 
                (COALESCE(inventory->'{category}', '{{}}')::jsonb || 
                 jsonb_build_object('{item_key}', (COALESCE(inventory->'{category}'->>'{item_key}', '0')::int + 1)))
            )
            WHERE owner_id = $1
        """, target_id)
        row_cool = await conn.fetchval("SELECT cooldowns FROM capybaras WHERE owner_id = $1", uid)
        cools = (json.loads(row_cool) if isinstance(row_cool, str) else row_cool) or {}
        _, updated_cools = check_daily_limit(cools, "gift")
        await conn.execute("UPDATE capybaras SET cooldowns = $1 WHERE owner_id = $2", json.dumps(updated_cools), uid)
    item_name = DISPLAY_NAMES.get(item_key, item_key)
    await callback.message.edit_caption(
        caption=f"✨ <b>Подарунок надіслано!</b>\nВи передали <b>{item_name}</b> гравцю <code>{target_id}</code>.\nВаша карма зросла на +1 ✨", 
        parse_mode="HTML"
    )
    try:
        await callback.bot.send_message(
            target_id, 
            f"🎁 Гей! Тобі прийшов подарунок від @{sender_name}: <b>{item_name}</b>!\n<i>Перевір свій інвентар.</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer("Подарунок доставлено! 🐾")
    
@router.callback_query(F.data.startswith("leaderboard"))
async def show_leaderboard(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split(":")
    criteria = parts[1] if len(parts) > 1 else "mass"
    page = int(parts[2]) if len(parts) > 2 else 0
    offset = page * 5

    configs = {
        "mass": (
            "⚖️ Топ Найважчих", " кг", 
            "SELECT u.username, c.weight as val FROM users u JOIN capybaras c ON u.tg_id = c.owner_id ORDER BY c.weight DESC LIMIT 5 OFFSET $1"
        ),
        "lvl": (
            "🎖 Топ Наймудріших", " Lvl", 
            "SELECT u.username, c.lvl as val FROM users u JOIN capybaras c ON u.tg_id = c.owner_id ORDER BY c.lvl DESC LIMIT 5 OFFSET $1"
        ),
        "winrate": (
            "⚔️ Топ Найсильніших", "%", 
            "SELECT u.username, ROUND((c.wins::float / GREATEST(c.total_fights, 1)) * 100) as val FROM users u JOIN capybaras c ON u.tg_id = c.owner_id WHERE c.total_fights > 0 ORDER BY val DESC, c.wins DESC LIMIT 5 OFFSET $1"
        ),
        "fishing": (
            "🎣 Майстри Риболовлі", " кг", 
            """SELECT u.username, 
               (c.fishing_stats->>'total_weight')::float as val,
               (c.fishing_stats->>'max_weight')::float as secondary_val
               FROM users u JOIN capybaras c ON u.tg_id = c.owner_id 
               ORDER BY val DESC LIMIT 5 OFFSET $1"""
        ),
        # --- UPDATED BURP TOP (JSONB EXTRACTION) ---
        "burp": (
            "🍺 Королі Відрижки", " dB",
            """SELECT u.username, 
               (COALESCE(c.stats_track->>'max_burp', '0'))::float as val 
               FROM users u 
               JOIN capybaras c ON u.tg_id = c.owner_id 
               ORDER BY val DESC LIMIT 5 OFFSET $1"""
        )
    }

    title, label, query = configs.get(criteria, configs["mass"])
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, offset)
        
    text = f"<b>{title}</b>\n━━━━━━━━━━━━━━━\n"
    for i, row in enumerate(rows):
        pos = i + offset + 1
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, "🐾")
        
        val = row['val'] if row['val'] is not None else 0
        
        if criteria == "fishing":
            s_val = row['secondary_val'] if row['secondary_val'] is not None else 0
            text += (f"{medal} {pos}. <b>{row['username']}</b>\n"
                     f"   └ Улов: <code>{val:.2f}</code> кг | Рекорд: <code>{s_val:.2f}</code> {label}\n")
        elif criteria == "burp":
            # Round decibels to 1 decimal place
            text += f"{medal} {pos}. <b>{row['username']}</b> — <code>{val:.1f}</code>{label}\n"
        else:
            text += f"{medal} {pos}. <b>{row['username']}</b> — {val}{label}\n"

    if not rows: text += "<i>На цій сторінці порожньо...</i>"

    builder = InlineKeyboardBuilder()
    # 3-button row
    builder.row(
        types.InlineKeyboardButton(text="⚖️ Вага", callback_data="leaderboard:mass:0"),
        types.InlineKeyboardButton(text="🎖 Рівень", callback_data="leaderboard:lvl:0"),
        types.InlineKeyboardButton(text="⚔️ Бій", callback_data="leaderboard:winrate:0")
    )
    # 2-button row
    builder.row(
        types.InlineKeyboardButton(text="🎣 Риба", callback_data="leaderboard:fishing:0"),
        types.InlineKeyboardButton(text="📢 Відрижка", callback_data="leaderboard:burp:0")
    )
    
    # Navigation and Back
    nav_btns = []
    if page > 0:
        nav_btns.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"leaderboard:{criteria}:{page-1}"))
    if len(rows) == 5:
        nav_btns.append(types.InlineKeyboardButton(text="➡️", callback_data=f"leaderboard:{criteria}:{page+1}"))
    
    if nav_btns:
        builder.row(*nav_btns)
    
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="social"))
    builder.adjust(3, 2, len(nav_btns) if nav_btns else 1, 1)

    try:
        await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except:
        await callback.message.edit_text(text=text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    await callback.answer()

@router.callback_query(F.data.startswith("date_request:"))
async def send_date_request(callback: types.CallbackQuery):
    target_id = int(callback.data.split(":")[1])
    sender_id = callback.from_user.id
    sender_name = callback.from_user.full_name

    if target_id == sender_id:
        return await callback.answer("Ти не можеш піти на побачення сам із собою (хоча це теж чіл).", show_alert=True)

    invite_kb = InlineKeyboardBuilder()
    invite_kb.button(text="🥂 Погодитись", callback_data=f"date_accept:{sender_id}")
    invite_kb.button(text="💔 Відхилити", callback_data=f"date_reject:{sender_id}")
    
    try:
        await callback.bot.send_message(
            target_id,
            f"💌 <b>Романтика!</b>\n\nКапібара <b>{sender_name}</b> запрошує тебе на романтичне побачення до озера!",
            reply_markup=invite_kb.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer("💌 Запит на побачення надіслано!", show_alert=True)
    except:
        await callback.answer("🚨 Не вдалося надіслати запит.", show_alert=True)

@router.callback_query(F.data.startswith("date_reject:"))
async def process_date_reject(callback: types.CallbackQuery):
    sender_id = int(callback.data.split(":")[1])
    target_name = callback.from_user.full_name

    await callback.answer("💔 Ти відхилив(ла) запит на побачення.")
    
    try:
        await callback.bot.send_message(
            sender_id,
            f"💔 На жаль, капібара <b>{target_name}</b> відшила тебе...",
            parse_mode="HTML"
        )
    except:
        pass

@router.callback_query(F.data.startswith("date_accept:"))
async def accept_date(callback: types.CallbackQuery, db_pool):
    partner_id = int(callback.data.split(":")[1])
    my_id = callback.from_user.id
    
    date_plots = [
        "🏴‍☠️ Ви пробралися на ворожий фрегат і вкрали бочку кавунового рому!",
        "🏜️ Ви знайшли захований на березі скарб, але там були лише стиглі манго. Ви з'їли їх разом.",
        "🌊 Ви влаштували перегони на дельфінах вздовж узбережжя Ліворн-Бей!",
        "🃏 Ви обіграли старого пірата в карти в таверні, але вигране спустили в газино.",
        "🔥 Ви розпалили величезне багаття на скелях, щоб заманити та розграбувати торгові судна, і просто чілили разом.",
        "🍻 Ви випили стільки елю в таверні, що почали бачити морських зміїв.",
        "⚓ Ви разом начищали якір корабля до блиску, поки не почали бачити в ньому своє відображення."
    ]
    current_plot = random.choice(date_plots)

    async with db_pool.acquire() as conn:
        users_data = await conn.fetch("SELECT owner_id, meta FROM capybaras WHERE owner_id IN ($1, $2)", my_id, partner_id)
        if len(users_data) < 2: return await callback.answer("Партнер десь зник...")

        metas = {u['owner_id']: (json.loads(u['meta']) if isinstance(u['meta'], str) else u['meta']) for u in users_data}

        for uid, p_id in [(my_id, partner_id), (partner_id, my_id)]:
            rel = metas[uid].get("relationships", {})
            p_stats = rel.get(str(p_id), {"dates": 0, "status": "знайомі"})
            
            p_stats["dates"] += 1
            
            if p_stats["dates"] >= 50:
                p_stats["status"] = "💍 у шлюбі"
            elif p_stats["dates"] >= 10:
                p_stats["status"] = "❤️ пара"
            
            rel[str(p_id)] = p_stats
            metas[uid]["relationships"] = rel
            
            metas[uid]["stamina"] = min(100, metas[uid].get("stamina", 0) + 15)

            await conn.execute("UPDATE capybaras SET meta = $1 WHERE owner_id = $2", 
                               json.dumps(metas[uid], ensure_ascii=False), uid)

    current_status = metas[my_id]["relationships"][str(partner_id)]["status"]
    date_count = metas[my_id]["relationships"][str(partner_id)]["dates"]

    res_text = (
        f"💖 <b>Романтичне побачення!</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<i>{current_plot}</i>\n\n"
        f"📊 Результат:\n"
        f"• Побачення №<b>{date_count}</b>\n"
        f"• Ваш статус: <b>{current_status}</b>\n"
        f"• Енергія: <b>+15%</b> ✨"
    )

    if date_count == 10:
        res_text += "\n\n🎉 <b>ОГО! Тепер ви офіційно ПАРА!</b> ❤️"
    elif date_count == 50:
        res_text += "\n\n🎊 <b>НЕЙМОВІРНО! Ви ПОВІНЧАЛИСЯ!</b> 💍🔔"

    await callback.message.edit_text(res_text, parse_mode="HTML")
    
    try:
        await callback.bot.send_message(partner_id, res_text, parse_mode="HTML")
    except:
        pass