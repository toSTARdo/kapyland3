import json
import random
import datetime
import asyncio

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BASE_HIT_CHANCE, BASE_BLOCK_CHANCE, STAT_WEIGHTS
from core.combat.battles import run_battle_logic
from utils.helpers import check_daily_limit

router = Router()

ITEM_DISPLAY_NAMES = {
    "watermelon_slices": "🍉 Скибочка кавуна",
    "tangerines": "🍊 Мандарин",
    "melon": "🍈 Диня",
    "kiwi": "🥝 Ківі",
    "mango": "🥭 Манго"
}

@router.callback_query(F.data.startswith("steal_from:"))
async def execute_steal_logic(callback: types.CallbackQuery, db_pool):
    target_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        actor_row = await conn.fetchrow("SELECT meta, name FROM capybaras WHERE owner_id = $1", uid)
        target_row = await conn.fetchrow("SELECT meta, name FROM capybaras WHERE owner_id = $1", target_id)
        
        if not actor_row or not target_row: return
        
        a_meta = json.loads(actor_row['meta']) if isinstance(actor_row['meta'], str) else actor_row['meta']
        t_meta = json.loads(target_row['meta']) if isinstance(target_row['meta'], str) else target_row['meta']
        
        can_steal, _ = check_daily_limit(a_meta, "steal")
        if not can_steal:
            return await callback.answer("🥷 Ти вже сьогодні виходив на полювання. Спробуй завтра!", show_alert=True)

        base_success_chance = 0.05
        base_catch_chance = 0.10

        luck_stat = a_meta.get("stats", {}).get("luck", 1)
        luck_bonus = luck_stat * 0.01
        
        sleep_bonus = 0.10 if t_meta.get("status") == "sleep" else 0.0
        
        equipped_items = a_meta.get("equipment", [])
        has_steal_item = any("steal" in str(item).lower() for item in equipped_items)

        if has_steal_item:
            final_success_chance = 0.75
            final_catch_chance = 0.85
        else:
            final_success_chance = base_success_chance + luck_bonus + sleep_bonus
            final_catch_chance = final_success_chance + base_catch_chance

        roll = random.random()

        if roll < final_success_chance:
            t_items = t_meta.get("inventory", {}).get("equipment", [])
            
            if t_items:
                stolen_item = random.choice(t_items)
                t_meta["inventory"]["equipment"] = [i for i in t_items if i != stolen_item]
                a_meta.setdefault("inventory", {}).setdefault("equipment", []).append(stolen_item)

                await conn.execute("UPDATE capybaras SET meta = $1 WHERE owner_id = $2", json.dumps(t_meta, ensure_ascii=False), target_id)
                await conn.execute("UPDATE capybaras SET meta = $1 WHERE owner_id = $2", json.dumps(a_meta, ensure_ascii=False), uid)
                
                await callback.message.edit_caption(
                    f"🥷 <b>НАЙШВИДШІ ЛАПКИ!</b>\n"
                    f"Ви непомітно витягли <b>{stolen_item['name']}</b> у {target_row['name']}!\n"
                    f"🍀 Твій успіх: {int(final_success_chance*100)}%",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_caption(f"🧤 Ти обшукав {target_row['name']}, але в кишенях порожньо...")

        elif roll < final_catch_chance:
            if t_meta.get("status") == "sleep":
                start_time_str = t_meta.get("sleep_start")
                gained_stamina = 0
                
                if start_time_str:
                    start_time = datetime.datetime.fromisoformat(start_time_str)
                    now = datetime.datetime.now()
                    duration_mins = (now - start_time).total_seconds() / 60
                    gained_stamina = int(duration_mins * (100 / 120))
                    
                t_meta["status"] = "active"
                t_meta["stamina"] = min(100, t_meta.get("stamina", 0) + gained_stamina)
                t_meta.pop("wake_up", None)
                t_meta.pop("sleep_start", None)
                
                await conn.execute(
                    "UPDATE capybaras SET meta = $1 WHERE owner_id = $2", 
                    json.dumps(t_meta, ensure_ascii=False), target_id
                )
                
                wake_msg = f"\n🔔 Ціль миттєво прокинулась! (+{gained_stamina}⚡)"
            else:
                wake_msg = ""

            await callback.message.edit_caption(
                f"😱 <b>ЧОРТ! ВАС ПІЙМАЛИ!</b>{wake_msg}\n"
                f"Починається бій за життя!", parse_mode="HTML"
            )
            asyncio.create_task(run_battle_logic(callback, opponent_id=target_id, db_pool=db_pool))

        else:
            await callback.answer("💨 Ти злякався шурхоту і втік ні з чим. Буває...", show_alert=True)


@router.callback_query(F.data.startswith("ram:"))
async def execute_ram_logic(callback: types.CallbackQuery, db_pool):
    target_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT meta FROM capybaras WHERE owner_id = $1", uid)
        meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
        
        can_ram, _ = check_daily_limit(meta, "ram")
        if not can_ram:
            return await callback.answer("💥 Твій корабель ще лагодять після минулого тарану. Спробуй завтра!", show_alert=True)

        inv_items = [i['name'].lower() for i in meta.get("inventory", {}).get("equipment", [])]
        has_ram = any("таран" in item or "бур лаганна" in item for item in inv_items)
        
        if not has_ram:
            return await callback.answer("❌ Тобі потрібен 'Таран' або 'Бур Лаганна' в інвентарі!", show_alert=True)

        await conn.execute("UPDATE capybaras SET meta = $1 WHERE owner_id = $2", json.dumps(meta), uid)

    await callback.message.edit_caption("💥 <b>БА-БАХ!</b>\nТи влетів у суперника на повному ходу! Бій починається негайно!", parse_mode="HTML")
    
    asyncio.create_task(run_battle_logic(callback, opponent_id=target_id, db_pool=db_pool))

@router.callback_query(F.data.startswith("inspect:"))
async def handle_inspect_player(callback: types.CallbackQuery, db_pool):
    target_id = int(callback.data.split(":")[1])
    
    async with db_pool.acquire() as conn:
        target = await conn.fetchrow("""
            SELECT u.username, c.name as capy_name, c.lvl, c.karma, c.zen, c.meta, s.name as ship_name
            FROM users u 
            JOIN capybaras c ON u.tg_id = c.owner_id 
            LEFT JOIN ships s ON c.ship_id = s.id
            WHERE u.tg_id = $1
        """, target_id)
        
    if not target:
        return await callback.answer("Капібара зникла у тумані...")

    meta = json.loads(target['meta']) if isinstance(target['meta'], str) else target['meta']
    
    weight = meta.get("weight", 0.0)
    status = meta.get("status", "active")
    mood = meta.get("mood", "чілово")
    equip = meta.get("equipment", {})
    stats = meta.get("stats", {})
    
    status_text = "💤 Спить" if status == "sleep" else "🐾 Гуляє архіпелагом"
    karma_title = "😇 Свята булочка" if target['karma'] > 50 else "😈 Мародерна капі" if target['karma'] < -50 else "😐 Нейтральна капі"
    
    text = (
        f"📜 <b>Детальне досьє: {target['capy_name']}</b>\n"
        f"👤 Власник: {target['username']}\n"
        f"🚢 Човен: <b>{target['ship_name'] or 'Самотній плавець'}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔹 <b>Статус:</b> {status_text}\n"
        f"🔹 <b>Карма:</b> {karma_title} ({target['karma']})\n"
        f"🔹 <b>Настрій:</b> {mood}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎖 <b>Рівень:</b> {target['lvl']}\n"
        f"⚖️ <b>Вага:</b> {weight} кг\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚔️ <b>Арсенал:</b>\n"
        f"└ Снаряда: <b>{equip.get('weapon', 'Лапки')['name'] if isinstance(equip.get('weapon', 'Лапки'), dict) else equip.get('weapon', 'Лапки')}</b>\n"
        f"└ Захист: <b>{equip.get('armor', 'Хутро')}</b>\n"
        f"└ Реліквія: <b>{equip.get('artifact') or 'Порожньо'}</b>\n\n"
        f"<b>Показники:</b>\n"
        f"🔥 ATK: <b>{round(100*(BASE_HIT_CHANCE + STAT_WEIGHTS['atk_to_hit'] * stats.get('attack', 1)), 0)}%</b>  |  "
        f"🛡️ DEF: <b>{round(100*(BASE_BLOCK_CHANCE + STAT_WEIGHTS['def_to_block'] * stats.get('defense', 1)), 0)}%</b>\n"
        f"💨 AGI: <b>{round(100*(STAT_WEIGHTS['agi_to_dodge'] * stats.get('agility', 1)), 0)}%</b>  |  "
        f"🍀 LCK: <b>+{round(100*(STAT_WEIGHTS['luck_to_crit'] * stats.get('luck', 1)), 0)}%</b>\n"
        f"<i>Капібара виглядає {mood.lower()}, здається, вона готова до пригод.</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="⚔️ Виклик", callback_data=f"challenge_{target_id}")
    builder.button(text="🎁 Подарунок", callback_data=f"gift_to:{target_id}")
    builder.button(text="🔙 Назад", callback_data="social")
    builder.adjust(2, 1)

    await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("gift_to:"))
async def gift_category_select(callback: types.CallbackQuery, db_pool):
    target_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT meta FROM capybaras WHERE owner_id = $1", uid)
        meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
        
        await conn.execute("UPDATE capybaras SET meta = $1 WHERE owner_id = $2", json.dumps(meta), uid)
        
    builder = InlineKeyboardBuilder()
    builder.button(text="🍎 Їжа", callback_data=f"send_cat:food:{target_id}")
    builder.button(text="💎 Ресурси", callback_data=f"send_cat:materials:{target_id}")
    builder.button(text="⚔️ Спорядження", callback_data=f"send_cat:equipment:{target_id}")
    builder.button(text="🔙 Назад", callback_data=f"social")
    builder.adjust(2, 1, 1)

    await callback.message.edit_caption(
        caption="🎁 <b>Меню подарунків</b>\nОберіть категорію предметів для передачі:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("send_cat:"))
async def gift_item_select(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split(":")
    category = parts[1]
    target_id = int(parts[2])
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT meta FROM capybaras WHERE owner_id = $1", uid)
        meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
        
        can_gift, _ = check_daily_limit(meta, "gift")
        if not can_gift:
            return await callback.answer("🎁 Ти вже сьогодні надсилав подарунок. Спробуй завтра!", show_alert=True)

        builder = InlineKeyboardBuilder()
        has_items = False
        
        if category == "equipment":
            equipment_list = meta.get("inventory", {}).get("equipment", [])
            current_equip = meta.get("equipment", {}).values()
            
            for idx, item in enumerate(equipment_list):
                rarity = item.get("rarity", "Common").capitalize()
                
                if rarity in ["Common", "Rare"] and item['name'] not in current_equip:
                    builder.button(
                        text=f"🎁 {item['name']}", 
                        callback_data=f"gift_exec:equip:{idx}:{target_id}"
                    )
                    has_items = True
        else:
            items = meta.get("inventory", {}).get(category, {})
            for item_key, count in items.items():
                if count > 0:
                    builder.button(
                        text=f"{item_key} ({count})", 
                        callback_data=f"gift_exec:stack:{category}:{item_key}:{target_id}"
                    )
                    has_items = True
        
        if not has_items:
            return await callback.answer("У вас немає доступних предметів у цій категорії", show_alert=True)
            
        builder.button(text="🔙 Назад", callback_data=f"gift_to:{target_id}")
        builder.adjust(1)

        await callback.message.edit_caption(
            caption=f"🎁 <b>Ваш інвентар ({category}):</b>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("gift_exec:"))
async def execute_gift_transfer(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split(":")
    gift_type = parts[1]
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        if gift_type == "equip":
            item_idx = int(parts[2])
            target_id = int(parts[3])
            
            a_data = await conn.fetchrow("SELECT meta FROM capybaras WHERE owner_id = $1", uid)
            t_data = await conn.fetchrow("SELECT meta FROM capybaras WHERE owner_id = $1", target_id)
            
            a_meta = json.loads(a_data['meta']) if isinstance(a_data['meta'], str) else a_data['meta']
            t_meta = json.loads(t_data['meta']) if isinstance(t_data['meta'], str) else t_data['meta']
            
            inv = a_meta.get("inventory", {}).get("equipment", [])
            if item_idx >= len(inv): return await callback.answer("Помилка індексу")
            
            gift_item = inv.pop(item_idx)
            t_meta.setdefault("inventory", {}).setdefault("equipment", []).append(gift_item)
            
            await conn.execute("UPDATE capybaras SET meta = $1, karma = karma + 5 WHERE owner_id = $2", json.dumps(a_meta), uid)
            await conn.execute("UPDATE capybaras SET meta = $1 WHERE owner_id = $2", json.dumps(t_meta), target_id)
            item_name = gift_item['name']

        else:
            category = parts[2]
            item_key = parts[3]
            target_id = int(parts[4])
            
            res = await conn.execute(f"""
                UPDATE capybaras SET meta = jsonb_set(meta, '{{inventory, {category}, {item_key}}}', 
                (GREATEST((meta->'inventory'->'{category}'->>'{item_key}')::int - 1, 0))::text::jsonb)
                WHERE owner_id = $1 AND (meta->'inventory'->'{category}'->>'{item_key}')::int > 0
            """, uid)

            if res == "UPDATE 0": return await callback.answer("Предмет закінчився")

            await conn.execute(f"""
                UPDATE capybaras SET meta = jsonb_set(meta, '{{inventory, {category}, {item_key}}}', 
                (COALESCE(meta->'inventory'->'{category}'->>'{item_key}', '0')::int + 1)::text::jsonb)
                WHERE owner_id = $1
            """, target_id)
            
            await conn.execute("UPDATE capybaras SET karma = karma + 1 WHERE owner_id = $1", uid)
            item_name = item_key

    await callback.message.edit_caption(caption=f"✨ Успіх!\nВи подарували {ITEM_DISPLAY_NAMES.get(item_name, item_name)} та покращили свою карму.", parse_mode="HTML")
    
    try:
        await callback.bot.send_message(target_id, f"🎁 Гей! Тобі прийшов подарунок: {ITEM_DISPLAY_NAMES.get(item_name, item_name)}!")
    except: pass


@router.callback_query(F.data.startswith("leaderboard"))
async def show_leaderboard(callback: types.CallbackQuery, db_pool):
    parts = callback.data.split(":")
    criteria = parts[1] if len(parts) > 1 else "mass"
    page = int(parts[2]) if len(parts) > 2 else 0
    offset = page * 5

    configs = {
        "mass": ("⚖️ Топ Найважчих", "кг", "SELECT u.username, (c.meta->>'weight')::float as val FROM users u JOIN capybaras c ON u.tg_id = c.owner_id ORDER BY val DESC LIMIT 5 OFFSET $1"),
        "lvl": ("🎖 Топ Наймудріших", " Lvl", "SELECT u.username, c.lvl as val FROM users u JOIN capybaras c ON u.tg_id = c.owner_id ORDER BY val DESC LIMIT 5 OFFSET $1"),
        "winrate": ("⚔️ Топ Найсильніших", "%", "SELECT u.username, ROUND((c.wins::float / GREATEST(c.total_fights, 1)) * 100) as val FROM users u JOIN capybaras c ON u.tg_id = c.owner_id WHERE c.total_fights > 0 ORDER BY val DESC, c.wins DESC LIMIT 5 OFFSET $1"),
        
        "fishing": ("🎣 Майстри Риболовлі", "кг", """
            SELECT u.username, 
            (c.meta->'fishing_stats'->>'total_weight')::float as val,
            (c.meta->'fishing_stats'->>'max_weight')::float as secondary_val
            FROM users u JOIN capybaras c ON u.tg_id = c.owner_id 
            WHERE c.meta->'fishing_stats' IS NOT NULL
            ORDER BY val DESC LIMIT 5 OFFSET $1
        """)
    }

    title, label, query = configs.get(criteria, configs["mass"])
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, offset)
        
    text = f"<b>{title}</b>\n━━━━━━━━━━━━━━━\n"
    for i, row in enumerate(rows):
        pos = i + offset + 1
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, "🐾")
        
        if criteria == "fishing":
            text += (f"{medal} {pos}. <b>{row['username']}</b>\n"
                     f"   └ Улов: <code>{row['val']:.2f}</code> кг | Рекорд: <code>{row['secondary_val']:.2f}</code> {label}\n")
        else:
            text += f"{medal} {pos}. <b>{row['username']}</b> — {row['val']}{label}\n"

    if not rows: text += "<i>На цій сторінці порожньо...</i>"

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="⚖️ Вага", callback_data="leaderboard:mass:0"),
        types.InlineKeyboardButton(text="🎖 Рівень", callback_data="leaderboard:lvl:0"),
        types.InlineKeyboardButton(text="⚔️ Бій", callback_data="leaderboard:winrate:0"),
        types.InlineKeyboardButton(text="🎣 Риба", callback_data="leaderboard:fishing:0")
    )
    
    nav_btns = []
    if page > 0:
        nav_btns.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"leaderboard:{criteria}:{page-1}"))
    nav_btns.append(types.InlineKeyboardButton(text="➡️", callback_data=f"leaderboard:{criteria}:{page+1}"))
    builder.row(*nav_btns)
    
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="social"))
    builder.adjust(4, len(nav_btns), 1)

    await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")

        
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