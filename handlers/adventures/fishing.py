import asyncio
import json
import random
import datetime
from aiogram import Router, types, html, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InputMediaPhoto
from config import BOSSES_COORDS, IMAGES_URLS
from core.combat.battles import run_battle_logic
from handlers.adventures.map.map_assets import get_random_plant, get_random_mushroom, get_biome_name
from utils.helpers import get_main_menu_chunk

router = Router()

def to_dict(data):
    if isinstance(data, dict): return data
    if isinstance(data, str): 
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return {}
    return {}

@router.callback_query(F.data.startswith("fish"))
async def handle_fishing(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    # 1. Парсимо сторінку чанка (меню)
    menu_page = 0
    if ":p" in callback.data:
        menu_page = int(callback.data.split(":p")[1])
    
    async with db_pool.acquire() as conn:
        # Додано JOIN з таблицею users для отримання налаштування row (quicklinks)
        row = await conn.fetchrow("""
            SELECT c.stamina, c.inventory, c.fishing_stats, c.stats_track, c.navigation, 
                   s.node_id, u.quicklinks
            FROM capybaras c
            JOIN users u ON c.owner_id = u.tg_id
            LEFT JOIN story_progress s ON c.owner_id = s.user_id AND s.quest_id = 'main'
            WHERE c.owner_id = $1
        """, uid)
        
        if not row:
            return await callback.answer("❌ Капібару не знайдено.")

        # Отримуємо стан швидких посилань
        show_quicklinks = row['quicklinks'] if row['quicklinks'] is not None else True

        # Перевірка: чи ми на потрібному етапі сюжету 'main'
        if row['node_id'] == "set_sail":
            inventory = to_dict(row['inventory'])
            loot_dir = inventory.setdefault("loot", {})
            maps_list = loot_dir.setdefault("treasure_maps", [])

            coords = BOSSES_COORDS.get(1, {'x': 10, 'y': 10})
            boss_map = {
                "type": "boss_den", 
                "boss_num": 1, 
                "pos": f"{coords['x']},{coords['y']}",
                "discovered": str(datetime.date.today())
            }

            if not any(m.get("boss_num") == 1 for m in maps_list):
                maps_list.append(boss_map)

            await conn.execute("""
                UPDATE capybaras 
                SET inventory = $1, stamina = GREATEST(stamina - 10, 0) 
                WHERE owner_id = $2
            """, json.dumps(inventory, ensure_ascii=False), uid)
            
            await conn.execute("""
                UPDATE story_progress 
                SET node_id = 'island_landing' 
                WHERE user_id = $1 AND quest_id = 'main'
            """, uid)

            await callback.answer("📜 Ти щось виловив!")
            
            from handlers.onboarding import render_story_node
            return await render_story_node(callback.message, "island_landing", "main", db_pool)

        stamina = row['stamina']
        inventory = to_dict(row['inventory'])
        fishing_stats = to_dict(row['fishing_stats'])
        stats_track = to_dict(row['stats_track']) if row['stats_track'] else {}
        navigation = to_dict(row['navigation']) # Отримуємо навігацію

        # Визначаємо поточний біом
        py = navigation.get("y", 75)
        biome = get_biome_name(py)
        biome_id = str(biome.get("id", 1))

        equipment_dict = inventory.get("equipment", {})
        if not isinstance(equipment_dict, dict):
            equipment_dict = {}

        keywords = ["вудочка", "посилена вудочка", "металева вудочка"]

        # 1. Find the item
        rod_item = next((
            item for item in equipment_dict.values() 
            if isinstance(item, dict) and any(key in item.get("name", "").lower() for key in keywords)
        ), None)

        # 2. Calculate bonus if an item was found
        bonus_chance = 0.0
        if rod_item:
            name = rod_item.get("name", "").lower()
            # Find the index of the first keyword that appears in the name
            match_index = next((i for i, key in enumerate(keywords) if key in name), 0)
            bonus_chance = match_index * 0.1
        tackle_item = next((item for item in equipment_dict.values() if isinstance(item, dict) and "снасті" in item.get("name", "").lower()), None)

        if not rod_item:
            return await callback.answer("❌ Спочатку екіпіруй вудочку або снасті! 🎣", show_alert=True)
            
        rod_lvl = rod_item.get("lvl", 0) if rod_item else 0
        tackle_lvl = tackle_item.get("lvl", 0) if tackle_item else 0

        catch_multiplier = 1
        multi_note = ""

        if tackle_lvl > 0 and random.random() < (tackle_lvl * 0.03):
            catch_multiplier = 3
            multi_note = " 🔥 <b>ПОТРІЙНИЙ УЛОВ! (x3)</b>"
        elif rod_lvl > 0 and random.random() < (rod_lvl * 0.05):
            catch_multiplier = 2
            multi_note = " ✨ <b>ПОДВІЙНИЙ УЛОВ! (x2)</b>"

        if stamina < 10 and callback.message in ["🎣 Закинути ще раз", "🔙 Назад"]:
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
            return asyncio.create_task(run_battle_logic(callback, db_pool, bot_type="secret_shark", is_boss=True))

        loot_pool = [
            {"name": "🦴 Стара кістка", "min_w": 0.1, "max_w": 0.4, "chance": 12, "type": "materials", "key": "bone"},
            {"name": "📰 Промокла газета", "min_w": 0.05, "max_w": 0.1, "chance": 12, "type": "materials", "key": "paper"},
            {"name": "🥫 Іржава бляшанка", "min_w": 0.1, "max_w": 0.3, "chance": 10, "type": "materials", "key": "can"},
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
            {"name": "🗝️ Ключ", "min_w": 0.1, "max_w": 0.2, "chance": 4, "type": "loot", "key": "key"},
            {"name": "🎟️ Лотерейний квиток", "min_w": 0.01, "max_w": 0.01, "chance": 1, "type": "loot", "key": "lottery_ticket"},
            {"name": "🫙 Стара мапа", "min_w": 0.1, "max_w": 0.1, "chance": 2, "type": "treasure_map", "key": "treasure_maps"}
        ]

        # ВИПРАВЛЕНО: Додані коми між елементами списку Біому 2
        BIOME_LOOT = {
            "1": [
                {"name": "🥥 Кокос", "min_w": 0.8, "max_w": 1.2, "chance": 10, "type": "materials", "key": "coconut"},
                {"name": "🪸 Корал", "min_w": 0.8, "max_w": 1.2, "chance": 10, "type": "materials", "key": "coral"}
            ],
            "2": [
                {"name": "🐚 Мушля-Шхуна", "min_w": 1.0, "max_w": 3.0, "chance": 2, "type": "materials", "key": "shell"},
                {"name": "🦐 Креветка-боксер", "min_w": 0.5, "max_w": 0.5, "chance": 8, "type": "materials", "key": "mantis_shrimp"},
                {"name": "🐊 Крокодилоподібний ящур", "min_w": 0.1, "max_w": 0.1, "chance": 5, "type": "materials", "key": "lizard"}
            ],
            "3": [
                {"name": "🧊 Древній лід", "min_w": 0.1, "max_w": 0.3, "chance": 3, "type": "materials", "key": "ice_crystal"},
                {"name": "🦑 Зоряний кракен", "min_w": 0.5, "max_w": 300.0, "chance": 8, "type": "materials", "key": "kraken"},
                {"name": "🐳 Кит", "min_w": 50.0, "max_w": 500.0, "chance": 5, "type": "materials", "key": "whale"},
                {"name": "💀 Череп", "min_w": 50.0, "max_w": 500.0, "chance": 5, "type": "materials", "key": "skull"}
            ]
        }

        item = None
        # ВИПРАВЛЕНО: Логіка міфічних предметів (заповнено min_w, max_w та name)
        if rod_lvl >= 5 and random.random() < 0.05 + bonus_chance:
            roll = random.random()
            if roll < 0.45:
                plant = get_random_plant()
                item = {"name": f"🌿 {plant['name']}", "min_w": 0.1, "max_w": 0.5, "chance": 0, "type": "materials", "key": plant["id"]}
            elif roll < 0.9:
                plant = get_random_plant()
                item = {"name": f"🌿 {plant['name']}", "min_w": 0.1, "max_w": 0.5, "chance": 0, "type": "materials", "key": plant["id"]}
            else:
                item = {"name": "🕋 Мега-скриня", "min_w": 5.0, "max_w": 10.0, "chance": 0, "type": "loot", "key": "mega_chest"}

        # ДОДАНО: Логіка біомного луту (10% шанс, якщо не випало міфічне)
        if not item:
            if random.random() < 0.10 and biome_id in BIOME_LOOT:
                biome_pool = BIOME_LOOT[biome_id]
                item = random.choices(biome_pool, weights=[i['chance'] for i in biome_pool])[0]
                # Додамо емодзі біому до назви для візуального ефекту (опціонально)
                item_copy = item.copy() 
                item_copy["name"] = f"{biome['emoji']} {item['name']}"
                item = item_copy
            else:
                item = random.choices(loot_pool, weights=[i['chance'] for i in loot_pool])[0]
        
        weight_bonus = 1 + (rod_lvl * 0.15)
        fish_weight = round(random.uniform(item['min_w'], item['max_w'] * weight_bonus), 2)

        inventory_note = ""
        stamina -= 10
                
        total_catch_weight = round(fish_weight * catch_multiplier, 2)
        fishing_stats["total_weight"] = round(fishing_stats.get("total_weight", 0) + total_catch_weight, 2)
        fishing_stats["max_weight"] = max(fishing_stats.get("max_weight", 0), fish_weight)

        if item['type'] == "treasure_map":
            loot_dir = inventory.setdefault("loot", {})
            maps_list = loot_dir.setdefault("treasure_maps", [])
            
            # --- НОВИЙ БЛОК: Додаємо Слоїк у матеріали ---
            materials = inventory.setdefault("materials", {})
            materials["jar"] = materials.get("jar", 0) + 1 if random.random() < 0.1 else 0
            # ---------------------------------------------

            if random.random() < 0.1:
                defeated = stats_track.get("bosses_defeated", 0)
                next_boss = defeated + 1
                
                if next_boss <= 20 and not any(m.get("boss_num") == next_boss for m in maps_list):
                    coords = BOSSES_COORDS.get(next_boss)
                    maps_list.append({
                        "type": "boss_den", 
                        "boss_num": next_boss, 
                        "pos": f"{coords['x']},{coords['y']}",
                        "discovered": str(datetime.date.today())
                    })
                    inventory_note = f"💀 <b>Знайдено карту Боса №{next_boss} та старий Слоїк!</b>"
                else:
                    m_id = random.randint(100, 999)
                    t_x, t_y = random.randint(0, 149), random.randint(0, 149)
                    maps_list.append({
                        "type": "treasure", 
                        "id": m_id, 
                        "pos": f"{t_x},{t_y}",
                        "discovered": str(datetime.date.today())
                    })
                    inventory_note = f"🗺️ <b>Ви знайшли карту #{m_id} у Слоїку!</b> ({t_x}, {t_y})"
            else:
                m_id = random.randint(100, 999)
                maps_list.append({"type": "treasure", "id": m_id, "pos": f"{random.randint(0,149)},{random.randint(0,149)}"})
                # Оновлюємо текст, щоб гравець розумів, звідки взявся слоїк
                inventory_note = f"🗺️ <b>Ви виловили карту #{m_id} прямо у cлоїку!</b>"
        else:
            folder = item['type']
            target_folder = inventory.setdefault(folder, {})
            target_folder[item['key']] = target_folder.get(item['key'], 0) + catch_multiplier
            inventory_note = f"📦 <i>{item['name']} (x{catch_multiplier}) додано в {folder}!</i>"

        await conn.execute("""
            UPDATE capybaras 
            SET stamina = $1, 
                inventory = $2, 
                fishing_stats = $3 
            WHERE owner_id = $4
        """, stamina, json.dumps(inventory, ensure_ascii=False), json.dumps(fishing_stats), uid)

        # 2. Формування клавіатури
        stars = "⭐" * rod_lvl
        builder = InlineKeyboardBuilder()
        
        # Зберігаємо сторінку чанка в callback_data кнопки "ще раз", 
        # щоб при повторній риболовлі меню залишалося на тій же сторінці
        builder.button(text="🎣 Закинути ще раз", callback_data=f"fish:p{menu_page}")
        builder.button(text="🔙 Назад", callback_data="open_adventure_main")
        builder.adjust(1)

        # 3. Додаємо чанк навігації
        if show_quicklinks:
            get_main_menu_chunk(builder, page=menu_page, callback_prefix="fish")

        # 4. Рендеринг результату
        new_media = InputMediaPhoto(
            media=IMAGES_URLS["fishing"],
            caption=(
                f"🎣 <b>Риболовля {stars}</b>\n━━━━━━━━━━━━━━━\n"
                f"Твій улов: <b>{item['name']}</b> ({fish_weight} кг){multi_note}\n\n"
                f"{inventory_note}\n"
                f"🔋 Енергія: {stamina}/100"
            ),
            parse_mode="HTML"
        )

        try:
            await callback.message.edit_media(media=new_media, reply_markup=builder.as_markup())
        except Exception:
            # Якщо сталась помилка (наприклад, медіа те саме), оновлюємо лише кнопки
            await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        
        await callback.answer()