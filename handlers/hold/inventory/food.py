import asyncio
import json
import random
from aiogram import Router, types, html, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.helpers import grant_exp_and_lvl
from handlers.hold.inventory.navigator import render_inventory_page
from core.reincarnation.death import handle_death

router = Router()

@router.callback_query(F.data.startswith("food_choice:"))
async def handle_food_choice(callback: types.CallbackQuery, db_pool):
    food_type = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        inv_json = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
    
    if inv_json is None:
        return await callback.answer("❌ Профіль не знайдено.")

    inv = json.loads(inv_json) if isinstance(inv_json, str) else inv_json
    count = inv.get("food", {}).get(food_type, 0)
    
    if count <= 0:
        return await callback.answer("Нічого немає! Кошик порожній... 🧺", show_alert=True)

    food_names = {"tangerines": "🍊", "melon": "🍈", "watermelon_slices": "🍉", "mango": "🥭", "kiwi": "🥝"}
    icon = food_names.get(food_type, "🍱")

    builder = InlineKeyboardBuilder()
    builder.button(text=f"🍴 З'їсти 1", callback_data=f"eat:one:{food_type}")
    
    if count >= 10:
        builder.button(text=f"🍴 З'їсти 10", callback_data=f"eat:10:{food_type}")

    if count > 1:
        builder.button(text=f"🍴 З'їсти все ({count})", callback_data=f"eat:all:{food_type}")
    
    loot = inv.get("loot", {})
    has_handmade_map = loot.get("handmade_map", 0) > 0
    if has_handmade_map:
        builder.button(text=f"📥 Покласти в скриню (1)", callback_data=f"put_in_chest:food:{food_type}")

    builder.button(text="🔙 Назад", callback_data="inv_page:food:0")
    builder.adjust(1)

    await callback.message.edit_text(
        f"🍎 <b>Твій вибір: {icon}</b>\n<i>Смачного, маленька капібаро!</i>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("eat:"))
async def handle_eat(callback: types.CallbackQuery, db_pool):
    _, amount_type, food_type = callback.data.split(":")
    user_id = callback.from_user.id
    
    # Константи
    WEIGHT_TABLE = {
        "kiwi": 0.2,
        "fly_agaric": 0.3,
        "mushroom": 0.5,
        "tangerines": 1.2,
        "mango": 2.5,
        "watermelon_slices": 1.0,
        "melon": 10.0
    }
    TOXIC_CHANCE = {"mushroom": 0.001, "fly_agaric": 0.05}
    C_PHRASES = [
        "😋 Капі-ням!", "😋 Агресивне чавкання...", "😋 Ом-ном-ном!", 
        "🌪️ Всмоктала як пилосос!", "😋 Справжній гурман"
    ]

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT c.inventory, c.lvl, u.reincarnation_multiplier, c.stats_track 
            FROM capybaras c
            JOIN users u ON c.owner_id = u.tg_id
            WHERE c.owner_id = $1
        """, user_id)
        
        if not row: return

        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        stats_track = json.loads(row['stats_track']) if isinstance(row['stats_track'], str) else (row['stats_track'] or {})
        current_lvl = row['lvl']
        reinc_mult = row['reincarnation_multiplier'] or 1.0
        
        current_count = inv.get("food", {}).get(food_type, 0)
        if current_count <= 0:
            await callback.answer("❌ Вже все з'їли!")
            return await render_inventory_page(callback.message, user_id, db_pool, page="food", is_callback=True)

        # Розрахунок порції
        if amount_type not in ["one, all"]:
            to_eat = int(amount_type)
        else
            to_eat = 1 if amount_type == "one" else current_count
        unit_weight = WEIGHT_TABLE.get(food_type, 0.5)
        total_bonus = round(to_eat * unit_weight * reinc_mult, 2)
        
        # --- ЛОГІКА ВИБУХУ (OVERFEEDING) ---
        safe_limit = 10.0 + (current_lvl * 30) 
        if total_bonus > safe_limit:
            if random.random() < min(0.95, (total_bonus - safe_limit) * 0.01):
                await callback.answer("💥 БА-БАХ! Капібара луснула!", show_alert=True)
                benefit = await handle_death(user_id, db_pool, death_reason="Луснула від переїдання 🍉")
                await callback.message.answer(f"💀 Тварина вибухнула! Новий множник: x{benefit.get('new_mult', 1.0)}")
                return

        # --- ЛОГІКА ОТРУЄННЯ ---
        toxic_risk = TOXIC_CHANCE.get(food_type, 0)
        if toxic_risk > 0 and random.random() < (1 - (1 - toxic_risk) ** to_eat):
            await callback.answer("🍄 Світ став надто яскравим...", show_alert=True)
            benefit = await handle_death(user_id, db_pool, death_reason=f"Отруївся грибом ({food_type})")
            await callback.message.answer(f"💀 Тварина отруїлася! Новий множник: x{benefit.get('new_mult', 1.0)}")
            return

        # --- ZEN & BURP ---
        zen_gain = sum(1 for _ in range(to_eat) if random.random() < 0.20) if food_type == "fly_agaric" else 0
        
        burp_loudness = 0
        burp_display = "\n💨 (тихенько відригнула)"
        if total_bonus >= 2.0:
            burp_loudness = min(190, (40 + random.randint(1, 20) + int(total_bonus * 2)))
            if burp_loudness > 120: burp_display = f"\n🔊 ВІДРИЖКА: {burp_loudness} дБ (Апко... пока...лікоп... Кінець світу короче! 💥)"
            elif burp_loudness > 80: burp_display = f"\n🔊 ВІДРИЖКА: {burp_loudness} дБ (ПОТУЖНО І НЕЗЛАМНО 💨)"
            else: burp_display = f"\n🔊 Відрижка: {burp_loudness} дБ (Ганьба)"

        # --- ОНОВЛЕННЯ ІНВЕНТАРЯ ТА СТАТИСТИКИ ---
        inv["food"][food_type] -= to_eat
        if inv["food"][food_type] <= 0: del inv["food"][food_type]

        await conn.execute("""
            UPDATE capybaras 
            SET inventory = $1, 
                zen = zen + $2,
                stats_track = stats_track || jsonb_build_object('max_burp', GREATEST(COALESCE((stats_track->>'max_burp')::int, 0), $3))
            WHERE owner_id = $4
        """, json.dumps(inv), zen_gain, burp_loudness, user_id)

    # Нарахування досвіду
    exp_gain = max(1, int(total_bonus)) if total_bonus >= 1 or random.random() < total_bonus else 0
    await grant_exp_and_lvl(user_id, exp_gain=exp_gain, weight_gain=total_bonus, bot=callback.bot, db_pool=db_pool)

    # Фінальна відповідь
    phrase = "МАСОНАБІРНИЙ ОБІД!" if total_bonus > 50 else random.choice(C_PHRASES)
    zen_text = f"\n🪷 Дзен: +{zen_gain}" if zen_gain > 0 else ""
    mult_text = f" (x{reinc_mult}) 💫" if reinc_mult > 1 else ""
    
    await callback.answer(
        f"{phrase}{mult_text}\n"
        f"⚖️ Вага: +{total_bonus} кг\n"
        f"✨ EXP: +{exp_gain}{zen_text}{burp_display}",
        show_alert=False
    )
    
    await render_inventory_page(callback.message, user_id, db_pool, page="food", is_callback=True)