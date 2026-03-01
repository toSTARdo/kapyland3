import asyncio
import json
import random
import datetime
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.combat.battles import run_battle_logic
from config import ARTIFACTS

router = Router()

@router.callback_query(F.data == "open_chest")
async def handle_open_chest(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
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
        
        chests = loot.get("chest", 0)
        keys = loot.get("key", 0)
        lockpickers = loot.get("lockpicker", 0)

        if chests < 1:
            return await callback.answer("❌ У тебе немає скрині!", show_alert=True)
        
        method = None
        if keys >= 1:
            method = "key"
        elif lockpickers >= 1:
            method = "lockpicker"
        else:
            return await callback.answer("❌ Тобі потрібен ключ або відмичка!", show_alert=True)

        if method == "lockpicker":
            loot["lockpicker"] -= 1
            dice = random.random()
            
            if dice > 0.8:
                await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv), uid)
                builder = InlineKeyboardBuilder()
                if chests > 0 and (keys > 0 or loot["lockpicker"] > 0):
                    builder.button(text="🔄 Спробувати ще раз", callback_data="open_chest")
                builder.button(text="🔙 Назад", callback_data="open_adventure_main")
                builder.adjust(1)
                return await callback.message.edit_text(
                    "🔧 <b>ХРУСЬ!</b>\n━━━━━━━━━━━━━━━\nВідмичка зламалася. Замок виявився міцнішим.",
                    reply_markup=builder.as_markup(), parse_mode="HTML"
                )
            elif dice > 0.55:
                return await callback.answer("⚠️ Замок заклинило! Спробуй ще раз.", show_alert=True)

        loot["chest"] -= 1
        if method == "key":
            loot["key"] -= 1

        if random.random() < 0.02:
            await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", json.dumps(inv), uid)
            await callback.message.edit_text("💥 <b>ОТ БЛЯХА!</b>\n━━━━━━━━━━━━━━━\nЦе був Мімік!")
            return asyncio.create_task(run_battle_logic(callback, bot_type="mimic"))

        rewards = []
        
        food_pool = [
            {"key": "tangerines", "name": "🍊 Мандарин", "chance": 50, "amt": (3, 7)},
            {"key": "watermelon_slices", "name": "🍉 Скибочка кавуна", "chance": 30, "amt": (2, 4)},
            {"key": "mango", "name": "🥭 Манго", "chance": 15, "amt": (1, 2)},
            {"key": "kiwi", "name": "🥝 Ківі", "chance": 5, "amt": (1, 1)}
        ]
        
        for _ in range(2):
            f = random.choices(food_pool, weights=[i['chance'] for i in food_pool])[0]
            count = random.randint(*f['amt'])
            food[f['key']] = food.get(f['key'], 0) + count
            rewards.append(f"{f['name']} x{count}")

        if random.random() < 0.4:
            t_count = random.randint(1, 3)
            loot["lottery_ticket"] = loot.get("lottery_ticket", 0) + t_count
            rewards.append(f"🎟️ Квиток x{t_count}")

        treasure_maps = loot.setdefault("treasure_maps", [])
        if random.random() < 0.2:
            map_id = random.randint(100, 999)
            treasure_maps.append({
                "type": "treasure", 
                "id": map_id, 
                "pos": f"{random.randint(0,149)},{random.randint(0,149)}"
            })
            rewards.append(f"🗺️ Карта #{map_id}")

        if random.random() < 0.05:
            defeated = stats.get("bosses_defeated", 0)
            next_boss = defeated + 1
            if next_boss <= 20 and not any(m.get("boss_num") == next_boss for m in treasure_maps):
                treasure_maps.append({
                    "type": "boss_den", 
                    "boss_num": next_boss, 
                    "pos": f"{next_boss},{next_boss}",
                    "discovered": datetime.datetime.now().isoformat()
                })
                rewards.append(f"💀 Карта лігва №{next_boss}")

        if random.random() < 0.15:
            rarity = random.choices(["Epic", "Legendary"], weights=[1, 1])[0]
            pool = ARTIFACTS.get(rarity, [{"name": "Іржавий ніж"}])
            item = random.choice(pool)
            
            storage = inv.setdefault("equipment_storage", [])
            storage.append({
                "name": item["name"], 
                "rarity": rarity, 
                "stats": item.get("stats", {})
            })
            rewards.append(f"✨ {rarity}: {item['name']}")

        await conn.execute("""
            UPDATE capybaras 
            SET inventory = $1, state = $2, stats_track = $3 
            WHERE owner_id = $4
        """, json.dumps(inv), json.dumps(state), json.dumps(stats), uid)

        builder = InlineKeyboardBuilder()
        if loot["chest"] > 0:
            if loot.get("key", 0) > 0:
                builder.button(text=f"🔑 Ще одну ({loot['key']})", callback_data="open_chest")
            elif loot.get("lockpicker", 0) > 0:
                builder.button(text=f"🔧 Відмичкою ({loot['lockpicker']})", callback_data="open_chest")
        
        builder.button(text="🔙 Назад", callback_data="open_adventure")
        builder.adjust(1)

        loot_list = "\n".join([f"• {r}" for r in rewards])
        await callback.message.edit_text(
            f"🔓 <b>КЛАЦ! Скриню відкрито!</b>\n━━━━━━━━━━━━━━━\n{loot_list}\n\n📦 Лишилося скринь: {loot['chest']}",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )