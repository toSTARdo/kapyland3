import asyncio
import json
import random
import datetime
from aiogram import Router, types, html, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InputMediaPhoto
from config import BOSSES_COORDS, IMAGES_URLS
from core.combat.battles import run_battle_logic

router = Router()

@router.callback_query(F.data == "fish")
async def handle_fishing(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT stamina, inventory, fishing_stats 
            FROM capybaras WHERE owner_id = $1
        """, uid)
        
        if not row:
            return await callback.answer("❌ Капібару не знайдено.")

        stamina = row['stamina']
        
        def to_dict(data):
            if isinstance(data, dict): return data
            if isinstance(data, str): return json.loads(data)
            return {}

        inventory = to_dict(row['inventory'])
        fishing_stats = to_dict(row['fishing_stats'])

        equipment_list = inventory.get("equipment", [])
        
        if not isinstance(equipment_list, list):
            equipment_list = []

        rod_item = next(
            (item for item in equipment_list if "вудочка" in item.get("name", "").lower()), 
            None
        )

        tackle_item = next(
            (item for item in equipment_list if "рибальські снасті" in item.get("name", "").lower()), 
            None
        )

        if rod_item or tackle_item:
            return await callback.answer("❌ Спочатку екіпіруй вудочку або снасті! 🎣", show_alert=True)
            
        rod_lvl = rod_item.get("lvl", 0)

        if stamina < 10:
            return await callback.answer("🪫 Тобі треба відпочити! (Мінімум 10⚡)", show_alert=True)

        if rod_lvl >= 3 and random.random() < 0.02:
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE capybaras SET stamina = stamina - 5 WHERE owner_id = $1", uid)
            
            await callback.message.answer(
                "🌊 <b>ВОДА ПОЧЕРВОНІЛА...</b>\n"
                "Щось величезне вхопило твою наживку і тягне тебе на дно! "
                "Це легендарна Акула Селахія🦈! Страх смерті страхом смерті, але вона красуня...",
                parse_mode="HTML"
            )
            
            return asyncio.create_task(run_battle_logic(callback, db_pool, bot_type="secret_shark"))

        loot_pool = [
            {"name": "🦴 Стара кістка", "min_w": 0.1, "max_w": 0.4, "chance": 12, "type": "trash"},
            {"name": "📰 Промокла газета", "min_w": 0.05, "max_w": 0.1, "chance": 12, "type": "trash"},
            {"name": "🥫 Іржава бляшанка", "min_w": 0.1, "max_w": 0.3, "chance": 10, "type": "trash"},

            {"name": "🐟 Океанічний карась", "min_w": 0.3, "max_w": 1.5, "chance": 15, "type": "materials", "key": "carp"},
            {"name": "🐠 Уробороокеанський Окунь", "min_w": 0.2, "max_w": 0.8, "chance": 10, "type": "materials", "key": "perch"},
            {"name": "🐡 Риба-пупупу", "min_w": 0.5, "max_w": 2.0, "chance": 5, "type": "materials", "key": "pufferfish"},
            {"name": "🐙 Восьмирук", "min_w": 1.0, "max_w": 5.0, "chance": 4, "type": "materials", "key": "octopus"},
            {"name": "🦀 Бокохід", "min_w": 0.2, "max_w": 1.2, "chance": 5, "type": "materials", "key": "crab"},
            {"name": "🪼 Медуза", "min_w": 0.1, "max_w": 0.5, "chance": 8, "type": "materials", "key": "jellyfish"},
            {"name": "🗡️🐟 Риба-меч", "min_w": 15.0, "max_w": 50.0, "chance": 2, "type": "materials", "key": "swordfish"},
            {"name": "🦈 Маленька акула", "min_w": 10.0, "max_w": 40.0, "chance": 1, "type": "materials", "key": "shark"},
            
            {"name": "🍉 Скибочка кавуна", "min_w": 1, "max_w": 1, "chance": 20, "type": "food", "key": "watermelon_slices"},
            {"name": "🍊 Мандарин", "min_w": 0.5, "max_w": 0.5, "chance": 8, "type": "food", "key": "tangerines"},
            {"name": "🥭 Манго", "min_w": 0.5, "max_w": 0.5, "chance": 2, "type": "food", "key": "mango"},
            {"name": "🥝 Ківі", "min_w": 0.5, "max_w": 0.5, "chance": 2, "type": "food", "key": "kiwi"},
            {"name": "🍈 Диня", "min_w": 5.0, "max_w": 5.0, "chance": 4, "type": "food", "key": "melon"},
            
            {"name": "🗃 Скриня", "min_w": 5.0, "max_w": 10.0, "chance": 2, "type": "loot", "key": "chest"},
            {"name": "🗝️ Ключ", "min_w": 0.1, "max_w": 0.2, "chance": 2, "type": "loot", "key": "key"},
            {"name": "🎟️ Лотерейний квиток", "min_w": 0.01, "max_w": 0.01, "chance": 1, "type": "loot", "key": "lottery_ticket"},
            {"name": "🫙 Стара мапа", "min_w": 0.1, "max_w": 0.1, "chance": 2, "type": "treasure_map", "key": "treasure_maps"}
        ]

        found_mythic = False
        if rod_lvl >= 5 and random.random() < 0.03:
            item = {"name": "🔮 Перлина Ехвазу", "min_w": 0.5, "max_w": 0.5, "type": "loot", "key": "pearl_of_ehwaz"}
            found_mythic = True
        else:
            item = random.choices(loot_pool, weights=[i['chance'] for i in loot_pool])[0]
        
        weight_bonus = 1 + (rod_lvl * 0.15)
        fish_weight = round(random.uniform(item['min_w'], item['max_w'] * weight_bonus), 2)

        inventory_note = ""
        stamina -= 10
                
        if item['type'] != "trash":
            fishing_stats["total_weight"] = round(fishing_stats.get("total_weight", 0) + fish_weight, 2)
            fishing_stats["max_weight"] = max(fishing_stats.get("max_weight", 0), fish_weight)

            if item['type'] == "treasure_map":
                loot_dir = inventory.setdefault("loot", {})
                maps_list = loot_dir.setdefault("treasure_maps", [])

                if random.random() < 0.1:
                        stats_track = inventory.get("stats_track", {})
                        defeated = stats_track.get("bosses_defeated", 0)
                        next_boss = defeated + 1
                        
                        if next_boss <= 20 and not any(m.get("boss_num") == next_boss for m in maps_list):
                            coords = BOSSES_COORDS.get(next_boss)
                            maps_list.append({
                                "type": "boss_den", 
                                "boss_num": next_boss, 
                                "x": coords["x"], 
                                "y": coords["y"], 
                                "discovered": str(datetime.date.today())
                            })
                            inventory_note = f"💀 <b>Знайдено карту лігва Боса №{next_boss}!</b>"
                        else:
                            m_id = random.randint(100, 999)
                            t_x, t_y = random.randint(0, 149), random.randint(0, 149)
                            maps_list.append({
                                "type": "treasure", 
                                "id": m_id, 
                                "x": t_x, 
                                "y": t_y,
                                "discovered": str(datetime.date.today())
                            })
                            inventory_note = f"🗺️ <b>Ви знайшли карту скарбів #{m_id}!</b> ({t_x}, {t_y})"
                else:
                    m_id = random.randint(100, 999)
                    maps_list.append({"type": "treasure", "id": m_id, "pos": f"{random.randint(0,149)},{random.randint(0,149)}"})
                    inventory_note = f"🗺️ <b>Ви виловили карту скарбів #{m_id}!</b>"
            else:
                folder = item['type']
                target_folder = inventory.setdefault(folder, {})
                target_folder[item['key']] = target_folder.get(item['key'], 0) + 1
                inventory_note = f"📦 <i>{item['name']} додано в {folder}!</i>"
        else:
            inventory_note = "🗑️ <i>Це просто сміття. Ви викинули його назад.</i>"

        await conn.execute("""
            UPDATE capybaras 
            SET stamina = $1, 
                inventory = $2, 
                fishing_stats = $3 
            WHERE owner_id = $4
        """, stamina, json.dumps(inventory, ensure_ascii=False), json.dumps(fishing_stats), uid)

    stars = "⭐" * rod_lvl
    builder = InlineKeyboardBuilder()
    builder.button(text="🎣 Закинути ще раз", callback_data="fish")
    builder.button(text="🔙 Назад", callback_data="open_adventure_main")
    builder.adjust(1)

    new_media = InputMediaPhoto(
        media=IMAGES_URLS["fishing"],
        caption=(
            f"🎣 <b>Риболовля {stars}</b>\n━━━━━━━━━━━━━━━\n"
            f"Твій улов: <b>{item['name']}</b> ({fish_weight} кг)\n\n"
            f"{inventory_note}\n"
            f"🔋 Енергія: {stamina}/100"
        ),
        parse_mode="HTML"
    )

    await callback.message.edit_media(media=new_media, reply_markup=builder.as_markup())