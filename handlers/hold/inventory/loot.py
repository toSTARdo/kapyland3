import asyncio
import json
import random
import datetime
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from uuid import uuid4

from core.combat.battles import run_battle_logic
from config import ARTIFACTS, BOSSES_COORDS

router = Router()

materials_names = {
    "mint": "🌿 М'ята",
    "thyme": "🌱 Чебрець",
    "rosemary": "🌿 Розмарин",
    "chamomile": "🌼 Ромашка",
    "lavender": "🪻 Лаванда",
    "tulip": "🌷 Тюльпан",
    "lotus": "🪷 Лотос",
    "blueberry": "🫐 Чорниця"
}

@router.callback_query(F.data.startswith("open_chest:"))
async def handle_open_chest(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    try:
        _, chest_type, method = callback.data.split(":")
    except ValueError:
        return await callback.answer("❌ Помилка читання замка!", show_alert=True)
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT inventory, state, stats_track 
            FROM capybaras WHERE owner_id = $1
        """, uid)
        
        if not row:
            return await callback.answer("❌ Капібару не знайдено!")

        inv = row['inventory'] if isinstance(row['inventory'], dict) else json.loads(row['inventory'] or '{}')
        state = row['state'] if isinstance(row['state'], dict) else json.loads(row['state'] or '{}')
        stats = row['stats_track'] if isinstance(row['stats_track'], dict) else json.loads(row['stats_track'] or '{}')

        loot = inv.get("loot", {})
        food = inv.get("food", {})
        display = inv.setdefault("display", {})
        materials = inv.setdefault("materials", {})
        
        target_chest_key = "chest" if chest_type == "chest" else "mega_chest"
        chests_owned = loot.get(target_chest_key, 0)
        keys = loot.get("key", 0)
        lockpickers = loot.get("lockpicker", 0)

        if chests_owned < 1:
            chest_name = "Скрині" if chest_type == "normal" else "Мега-скрині"
            return await callback.answer(f"❌ У тебе немає {chest_name}!", show_alert=True)
        
        if method == "key" and keys < 1:
            return await callback.answer("❌ У тебе немає ключа!", show_alert=True)
        if method == "lockpicker" and lockpickers < 1:
            return await callback.answer("❌ У тебе немає відмички!", show_alert=True)

        if method == "lockpicker":
            dice = random.random()
            fail_chance = 0.8 if chest_type == "normal" else 0.88
            jam_chance = 0.55 if chest_type == "normal" else 0.65
            
            if dice > fail_chance:
                loot["lockpicker"] -= 1
                await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv), uid)
                builder = InlineKeyboardBuilder()
                if chests_owned > 0 and (keys > 0 or loot["lockpicker"] > 0):
                    builder.button(text="🔄 Спробувати ще раз", callback_data=f"open_chest:{chest_type}:lockpicker")
                    if keys > 0:
                        builder.button(text="🔑 Відкрити ключем", callback_data=f"open_chest:{chest_type}:key")
                builder.button(text="🔙 Назад", callback_data="inv_page:loot:0")
                builder.adjust(1)
                return await callback.message.edit_text(
                    "🔧 <b>ХРУСЬ!</b>\n━━━━━━━━━━━━━━━\nВідмичка зламалася.",
                    reply_markup=builder.as_markup(), parse_mode="HTML"
                )
            elif dice > jam_chance:
                return await callback.answer("⚠️ Замок заклинило!", show_alert=True)

        loot[target_chest_key] -= 1
        if method == "key":
            loot["key"] -= 1

        mimic_chance = 0.02 if chest_type == "chest" else 0.05
        if random.random() < mimic_chance:
            await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv), uid)
            await callback.message.edit_text("💥 ОТ БЛЯХА!\n━━━━━━━━━━━━━━━\nЦе був Мімік!")
            bot_type = "mimic" if chest_type == "normal" else "mega_mimic" 
            return asyncio.create_task(run_battle_logic(callback, db_pool, bot_type=bot_type))

        rewards = []
        
        if chest_type == "chest":
            food_pool = [
                {"key": "tangerines", "name": "🍊 Мандарин", "chance": 50, "amt": (3, 7)},
                {"key": "watermelon_slices", "name": "🍉 Скибочка кавуна", "chance": 30, "amt": (2, 4)},
                {"key": "melon", "name": "🍈 Диня", "chance": 5, "amt": (1, 2)},
                {"key": "mango", "name": "🥭 Манго", "chance": 15, "amt": (1, 2)},
                {"key": "kiwi", "name": "🥝 Ківі", "chance": 4, "amt": (1, 2)},
                # Added the missing mushrooms to the pool:
                {"key": "fly_agaric", "name": "🍄 Мухомор", "chance": 5, "amt": (1, 3)},
                {"key": "mushroom", "name": "🍄‍🟫 Гриб", "chance": 20, "amt": (2, 5)},
                {"key": "truffel", "name": "🟤 Трюфель", "chance": 1, "amt": (1, 1)}
            ]

            f = random.choices(food_pool, weights=[i['chance'] for i in food_pool])[0]
            count = random.randint(*f['amt'])
            food[f['key']] = food.get(f['key'], 0) + count
            rewards.append(f"{f['name']} x{count}")

            if random.random() < 0.3:
                m_key = random.choice(list(materials_names.keys()))
                m_amt = random.randint(1, 3)
                materials[m_key] = materials.get(m_key, 0) + m_amt
                rewards.append(f"{materials_names[m_key]} x{m_amt}")

            if random.random() < 0.4:
                t_count = random.randint(1, 3)
                loot["lottery_ticket"] = loot.get("lottery_ticket", 0) + t_count
                rewards.append(f"🎟️ Квиток x{t_count}")

            if random.random() < 0.15:
                rarity = random.choices(["Epic", "Legendary"], weights=[1, 1])[0]
                pool = ARTIFACTS.get(rarity, [{"name": "Іржавий ніж", "type": "weapon"}])
                item = random.choice(pool)
                item_id = str(uuid4())[:8]
                eq_dict = inv.setdefault("equipment", {})
                eq_dict[item_id] = {
                    "name": item["name"], "rarity": rarity, "type": item["type"],
                    "lvl": 0, "count": 1, "desc": "Знайдено у скрині."
                }
                rewards.append(f"✨ {item['name']} ({rarity})")

        elif chest_type == "mega_chest":
            rewards.append("🌟 <b>МЕГА-ДРОП:</b>")

            food_pool = [
                {"key": "tangerines", "name": "🍊 Мандарин", "chance": 50, "amt": (9, 21)},
                {"key": "watermelon_slices", "name": "🍉 Скибочка кавуна", "chance": 30, "amt": (6, 20)},
                {"key": "melon", "name": "🍈 Диня", "chance": 15, "amt": (3, 6)},
                {"key": "mango", "name": "🥭 Манго", "chance": 20, "amt": (3, 6)},
                {"key": "kiwi", "name": "🥝 Ківі", "chance": 8, "amt": (1, 4)},
                {"key": "fly_agaric", "name": "🍄 Мухомор", "chance": 15, "amt": (1, 3)},
                {"key": "mushroom", "name": "🍄‍🟫 Гриб", "chance": 20, "amt": (2, 5)},
                {"key": "truffel", "name": "🟤 Трюфель", "chance": 3, "amt": (1, 1)}
            ]
            f = random.choices(food_pool, weights=[i['chance'] for i in food_pool])[0]
            count = random.randint(*f['amt'])
            food[f['key']] = food.get(f['key'], 0) + count
            rewards.append(f"{f['name']} x{count}")

            t_count = random.randint(10, 25)
            loot["lottery_ticket"] = loot.get("lottery_ticket", 0) + t_count
            rewards.append(f"🎟️ Золоті квитки x{t_count}")

            m_kinds = random.randint(2, 4)
            selected_mats = random.sample(list(materials_names.keys()), m_kinds)
            for m_key in selected_mats:
                m_amt = random.randint(2, 6)
                materials[m_key] = materials.get(m_key, 0) + m_amt
                rewards.append(f"{materials_names[m_key]} x{m_amt}")

            for _ in range(random.randint(1, 3)):
                rarity = random.choices(["Legendary", "Mythic"], weights=[999, 1])[0]
                pool = ARTIFACTS.get(rarity, [{"name": "Сяючий камінь", "type": "gem"}])
                item = random.choice(pool)
                item_id = str(uuid4())[:8]
                eq_dict = inv.setdefault("equipment", {})
                eq_dict[item_id] = {
                    "name": item["name"], "rarity": rarity, "type": item["type"],
                    "lvl": 1, "count": 1, "desc": "Мега-Скриня!"
                }
                rewards.append(f"🔥 {item['name']} ({rarity})")

            treasure_maps = loot.setdefault("treasure_maps", [])
            defeated = stats.get("bosses_defeated", 0)
            next_boss = defeated + 1
            if next_boss <= 20 and not any(m.get("boss_num") == next_boss for m in treasure_maps):
                coords = BOSSES_COORDS.get(next_boss)
                if coords:
                    treasure_maps.append({
                        "type": "boss_den", "boss_num": next_boss, 
                        "pos": f"{coords['x']},{coords['y']}",
                        "discovered": datetime.datetime.now().isoformat()
                    })
                    rewards.append(f"💀 Карта лігва №{next_boss}")

        await conn.execute("""
            UPDATE capybaras SET inventory = $1, state = $2, stats_track = $3 WHERE owner_id = $4
        """, json.dumps(inv), json.dumps(state), json.dumps(stats), uid)

        builder = InlineKeyboardBuilder()
        if loot.get(target_chest_key, 0) > 0:
            if loot.get("key", 0) > 0:
                builder.button(text=f"🔑 Ще одну ({loot['key']})", callback_data=f"open_chest:{chest_type}:key")
            if loot.get("lockpicker", 0) > 0:
                builder.button(text=f"🪛 Відмичкою ({loot['lockpicker']})", callback_data=f"open_chest:{chest_type}:lockpicker")
        
        builder.button(text="🔙 Назад", callback_data="inv_page:loot:0")
        builder.adjust(1)

        await callback.message.edit_text(
            f"{'🗃' if chest_type == 'chest' else '🕋'} <b>КЛАЦ! Відкрито!</b>\n━━━━━━━━━━━━━━━\n" + 
            "\n".join([f"• {r}" for r in rewards]) + f"\n\n📦 Лишилося: {loot[target_chest_key]}",
            reply_markup=builder.as_markup(), parse_mode="HTML"
        )

@router.message(F.dice.emoji == "🎰")
async def handle_slots(message: types.Message, db_pool):
    uid = message.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory FROM capybaras WHERE owner_id = $1", uid)
        if not row: return

        inv = json.loads(row['inventory'] or '{}')
        food = inv.get("food", {})
        mango_count = food.get("mango", 0)

        if mango_count < 1:
            try:
                await message.delete()
            except:
                pass
            
            msg = await message.answer("❌ <b>Тобі треба 🥭 Манго, щоб зіграти в автомати!</b>", parse_mode="HTML")
            await asyncio.sleep(5)
            return await msg.delete()

        food["mango"] -= 1
        
        await conn.execute(
            "UPDATE capybaras SET inventory = $1 WHERE owner_id = $3", 
            json.dumps(inv, ensure_ascii=False), uid
        )

        score = message.dice.value
        await asyncio.sleep(2.1)

        result_text = ""
        reward_items = []

        if score == 64:
            result_text = "🎰 <b>ДЖЕКПОТ!!!</b> 🎰\nТи виграв щось неймовірне!"
            loot = inv.setdefault("loot", {})
            loot["mega_chest"] = loot.get("mega_chest", 0) + 1
            reward_items.append("🕋 Мега-скриня x1")
        elif score in [1, 22, 43]:
            result_text = "✨ <b>ТРИ В РЯД!</b> ✨"
            loot = inv.setdefault("loot", {})
            loot["chest"] = loot.get("chest", 0) + 2
            reward_items.append("🗃 Скриня x2")
        elif score in [16, 32, 48]:
            result_text = "💰 <b>Непогано!</b>"
            food["kiwi"] = food.get("kiwi", 0) + 3
            reward_items.append("🥝 Ківі x3")
        else:
            result_text = "🌊 <b>Порожньо...</b>"

        if reward_items:
            await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv, ensure_ascii=False), uid)
            rewards_str = "\n".join([f"• {item}" for item in reward_items])
            await message.reply(
                f"{result_text}\n━━━━━━━━━━━━━━━\n{rewards_str}\n\n🥭 Лишилося: {food['mango']}",
                parse_mode="HTML"
            )
        else:
            await message.reply(
                f"{result_text}\n<i>Манго 🥭 було смачним, але автомати сьогодні невблаганні.</i>\nЛишилося: {food['mango']}", 
                parse_mode="HTML"
            )