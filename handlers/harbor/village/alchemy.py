import json
import asyncio
import random
from aiogram import types, F, Router
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import load_game_data, DISPLAY_NAMES, IMAGES_URLS
from utils.helpers import get_main_menu_chunk
from handlers.harbor.village.forge import apply_pagination

router = Router()

RECIPES = load_game_data("data/potion_craft.json")

def find_item_in_inventory(inv, item_key):
    for category in ["food", "materials", "plants", "loot"]:
        cat_dict = inv.get(category, {})
        if item_key in cat_dict:
            return category, cat_dict[item_key]
    return None, 0

@router.callback_query(F.data.startswith("open_alchemy"))
async def process_open_alchemy(callback: types.CallbackQuery, db_pool):
    user_id = callback.from_user.id
    
    current_page = 0
    if ":" in callback.data:
        parts = callback.data.split(":")
        try:
            if "pg" in parts:
                current_page = int(parts[parts.index("pg") + 1])
            else:
                current_page = int(parts[1])
        except (ValueError, IndexError):
            current_page = 0

    async with db_pool.acquire() as conn:
        user_info = await conn.fetchrow(
            """
            SELECT c.inventory, u.quicklinks 
            FROM capybaras c 
            JOIN users u ON c.owner_id = u.tg_id 
            WHERE c.owner_id = $1
            """, user_id
        )
        
        if not user_info: return
        
        inv = json.loads(user_info['inventory']) if isinstance(user_info['inventory'], str) else user_info['inventory']
        show_quicklinks = user_info['quicklinks'] if user_info['quicklinks'] is not None else True

    # 2. Prepare the list of all recipe items for pagination
    recipe_items = []
    for r_id, r_data in RECIPES.items():
        can_brew = True
        for ing, req_count in r_data.get('ingredients', {}).items():
            _, owned = find_item_in_inventory(inv, ing)
            if owned < req_count:
                can_brew = False
                break
        
        prefix = "🟢" if can_brew else "🔴"
        btn_text = f"{prefix} {r_data.get('emoji', '🧪')} {r_data.get('name')}"
        # We store (suffix, text) as expected by your apply_pagination function
        recipe_items.append((r_id, btn_text))

    builder = InlineKeyboardBuilder()

    # 3. Apply pagination (Show 5 recipes per page for example)
    # Note: We use "brew" as callback_prefix for clicks, 
    # and "open_alchemy" as nav_prefix for switching pages.
    apply_pagination(
        builder=builder,
        all_items=recipe_items,
        page=current_page,
        per_page=5, 
        item_prefix="brew",
        nav_prefix="open_alchemy"
    )

    # 4. Standard menu buttons
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_village"))
    
    # 5. Quicklinks (Note: your get_main_menu_chunk uses ":p" suffix, keep it separate)
    if show_quicklinks:
        get_main_menu_chunk(builder, page=0, callback_prefix="open_alchemy")

    text = (
        "🧪 <b>Лавка Лінивця Омо</b>\n\n"
        "🦥 <i>«П-р-и-в-і-т... Щ-о...\nс-ь-о-г-о-д-н-і в-а-р-и-т-и-м-е-м-о?»</i>"
    )
    
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(media=IMAGES_URLS["alchemy"], caption=text, parse_mode="HTML"),
            reply_markup=builder.as_markup()
        )
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    
    await callback.answer()

@router.callback_query(F.data.startswith("brew:"))
async def preview_recipe(callback: types.CallbackQuery, db_pool):
    recipe_id = callback.data.split(":")[1]
    recipe = RECIPES.get(recipe_id)
    user_id = callback.from_user.id

    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw

    ing_text = ""
    can_brew = True
    for ing, req_count in recipe['ingredients'].items():
        _, owned = find_item_in_inventory(inv, ing)
        status = "✅" if owned >= req_count else "❌"
        ing_text += f"\n{status} {DISPLAY_NAMES.get(ing, ing)}: <b>{owned}/{req_count}</b>"
        if owned < req_count: can_brew = False

    effect_desc = "???"
    if "plus_stamina" in recipe: effect_desc = f"⚡ +{recipe['plus_stamina']} Енергії"
    elif "plus_max_hp" in recipe: effect_desc = f"❤️ +{recipe['plus_max_hp']} Макс. HP"
    elif recipe.get("effect") == "stats_reset": effect_desc = "🌀 Скидання характеристик"

    text = (
        f"{recipe.get('emoji', '🧪')} <b>{recipe.get('name')}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<i>{recipe.get('description')}</i>\n"
        f"{ing_text}\n\n"
        f"✨ Результат: <b>{effect_desc}</b>"
    )

    builder = InlineKeyboardBuilder()
    if can_brew:
        builder.button(text="🥘 Варити!", callback_data=f"confirm_brew:{recipe_id}")
    builder.button(text="⬅️ Назад", callback_data="open_alchemy")
    builder.adjust(1)

    await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("confirm_brew:"))
async def process_confirm_brew(callback: types.CallbackQuery, db_pool):
    recipe_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    recipe = RECIPES.get(recipe_id)

    async with db_pool.acquire() as conn:
        inv_raw = await conn.fetchval("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw

        for ing, count in recipe['ingredients'].items():
            cat, owned = find_item_in_inventory(inv, ing)
            if not cat or owned < count:
                return await callback.answer("❌ Недостатньо інгредієнтів!", show_alert=True)
            inv[cat][ing] -= count

        potions = inv.setdefault("potions", {})
        potions[recipe_id] = potions.get(recipe_id, 0) + 1

        await conn.execute("UPDATE capybaras SET inventory = $1 WHERE owner_id = $2", 
                           json.dumps(inv, ensure_ascii=False), user_id)

    await callback.answer(f"✨ {recipe.get('name')} готове!")
    await process_open_alchemy(callback, db_pool)

@router.callback_query(F.data.startswith("use_potion:"))
async def process_drink_potion(callback: types.CallbackQuery, db_pool):
    potion_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    recipe = RECIPES.get(potion_id)
    
    if not recipe: 
        return await callback.answer("❌ Рецепт не знайдено!", show_alert=True)
    
    async with db_pool.acquire() as conn:
        # Отримуємо повні дані персонажа
        row = await conn.fetchrow("""
            SELECT inventory, stamina, max_stamina, max_hp, atk, def, agi, luck, zen, race, state
            FROM capybaras WHERE owner_id = $1
        """, user_id)
        
        if not row: return

        # Парсимо JSON поля
        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        state = json.loads(row['state']) if isinstance(row['state'], str) else (row['state'] or {})
        
        stamina = row['stamina']
        max_stamina = row["max_stamina"]
        zen = row['zen']
        
        # Перевірка наявності зілля в інвентарі
        potions = inv.get("potions", {})
        if potions.get(potion_id, 0) <= 0:
            return await callback.answer("❌ Пляшка порожня!", show_alert=True)
        
        alert_text = "Смак дивний..."
        update_fields = {}
        effect = recipe.get("effect")

        current_hp = row['max_hp']
        # --- ЛОГІКА ЕФЕКТІВ ---
        if effect == "plus_max_hp":
            new_hp = current_hp + 1
            update_fields["max_hp"] = new_hp
            alert_text = f"🧬 Древня життєва сила! Ваше здоров'я назавжди збільшено: {current_hp*2} ➔ {new_hp*2} ❤️HP"

        # 1. Ефект збільшення МАКСИМАЛЬНОЇ енергії (Тропічний Пунш)
        elif effect == "increase_stamina":
            # Встановлюємо ліміт (наприклад, не більше 300)
            STAMINA_CAP = 300
            if max_stamina < STAMINA_CAP:
                new_max = min(max_stamina + 20, STAMINA_CAP)
                update_fields["max_stamina"] = new_max
                max_stamina = new_max # Оновлюємо локальну змінну для розрахунку поточної енергії
                alert_text = f"🍹 Тропічний драйв! Макс. ліміт енергії тепер {new_max}⚡"
            else:
                alert_text = "🍹 Ви вже на піку енергійності! Макс. ліміт не змінено."

            # Навіть якщо ліміт не зріс, пунш все одно відновлює поточну стаміну
            plus = recipe.get("plus_stamina", 0)
            if plus > 0:
                stamina = min(stamina + plus, max_stamina)
                update_fields["stamina"] = stamina
                alert_text += f"\n🔋 Відновлено: +{plus} енергії."

        # 2. Звичайне відновлення стаміни (Чай, Мед тощо)
        elif "plus_stamina" in recipe:
            plus = recipe["plus_stamina"]
            stamina = min(stamina + plus, max_stamina)
            update_fields["stamina"] = stamina
            alert_text = f"⚡ Енергію відновлено на +{plus}!"

        # 3. Скидання характеристик
        elif effect == "stats_reset":
            recovered = (
                max(0, row['atk']) + 
                max(0, row['def']) + 
                max(0, row['agi']) + 
                max(0, row['luck'])
            )
            update_fields.update({
                "atk": 0, "def": 0, "agi": 0, "luck": 0, 
                "zen": zen + recovered
            })
            alert_text = f"🌀 Характеристики скинуто! Повернуто {recovered} очок Zen."

        # 4. Ефект Метаморфози (Зміна раси)
        elif effect == "metamorphosis":
            race_config = {
                "capybara": {"atk": 0, "agi": 0, "def": 10, "luck": 0, "name": "Капібара"},
                "raccoon":  {"atk": 10, "agi": 0, "def": 0, "luck": 0, "name": "Єнот"},
                "cat":      {"atk": 0, "agi": 0, "def": 0, "luck": 10, "name": "Кіт"},
                "bat":      {"atk": 0, "agi": 10, "def": 0, "luck": 0, "name": "Кажан"}
            }
            
            current_race = row['race']
            available_races = [r for r in race_config.keys() if r != current_race]
            new_race = random.choice(available_races)
            stats_cfg = race_config[new_race]

            # Повертаємо поточні вкладені очки (мінус база 10)
            recovered = (
                max(0, row['atk']) + 
                max(0, row['def']) + 
                max(0, row['agi']) + 
                max(0, row['luck']) - 10
            )

            update_fields.update({
                "race": new_race,
                "atk": stats_cfg["atk"],
                "def": stats_cfg["def"],
                "agi": stats_cfg["agi"],
                "luck": stats_cfg["luck"],
                "zen": zen + recovered
            })
            alert_text = f"🎭 Метаморфоза: Ви тепер {stats_cfg['name']}!\n🌀 {recovered} очок Zen повернуто."

        # 5. Ефект Sting (Адреналін)
        elif effect == "sting":
            state["has_sting_effect"] = True
            update_fields["state"] = json.dumps(state, ensure_ascii=False)
            alert_text = "🐝 Жало спрацювало! +20% до шансу адреналіну в наступному бою."

        # --- ОНОВЛЕННЯ ІНВЕНТАРЮ ---
        potions[potion_id] -= 1
        if potions[potion_id] <= 0:
            del potions[potion_id]
        
        inv["potions"] = potions
        update_fields["inventory"] = json.dumps(inv, ensure_ascii=False)

        # --- ВИКОНАННЯ UPDATE В БД ---
        if update_fields:
            keys = list(update_fields.keys())
            values = list(update_fields.values())
            # Створюємо рядок "key1 = $1, key2 = $2..."
            set_clause = ", ".join([f'"{key}" = ${i+1}' for i, key in enumerate(keys)])
            query = f"UPDATE capybaras SET {set_clause} WHERE owner_id = ${len(keys)+1}"
            
            await conn.execute(query, *values, user_id)

    # Відправляємо фідбек
    await callback.answer(alert_text, show_alert=True)
    
    # Оновлюємо сторінку інвентарю
    try:
        from handlers.hold.inventory.navigator import render_inventory_page 
        await render_inventory_page(callback.message, user_id, db_pool, page="potions", is_callback=True)
    except Exception:
        await callback.message.delete()