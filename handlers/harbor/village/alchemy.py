import json
import asyncio
from aiogram import types, F, Router
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import load_game_data, DISPLAY_NAMES, IMAGES_URLS
from database.postgres_db import get_db_connection

router = Router()

# Завантаження рецептів
RECIPES = load_game_data("data/craft.json")

def find_item_in_inventory(inv, item_key):
    """Шукає предмет у всіх можливих категоріях інвентарю."""
    for category in ["food", "materials", "plants", "loot"]:
        cat_dict = inv.get(category, {})
        if item_key in cat_dict:
            return category, cat_dict[item_key]
    return None, 0

@router.callback_query(F.data == "open_alchemy")
async def process_open_alchemy(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT meta FROM capybaras WHERE owner_id = $1", user_id)
        if not row: return await callback.answer("Капібару не знайдено!")
        
        meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
        inv = meta.get('inventory', {})

        builder = InlineKeyboardBuilder()
        for r_id, r_data in RECIPES.items():
            can_brew = True
            # Перевірка наявності інгредієнтів
            for ing, req_count in r_data.get('ingredients', {}).items():
                _, owned = find_item_in_inventory(inv, ing)
                if owned < req_count:
                    can_brew = False
                    break
            
            prefix = "🟢" if can_brew else "🔴"
            builder.button(
                text=f"{prefix} {r_data.get('emoji', '🧪')} {r_data.get('name')}",
                callback_data=f"brew:{r_id}"
            )

        builder.row(types.InlineKeyboardButton(text="📜 Всі рецепти", callback_data="all_recipes"))
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_port"))
        builder.adjust(1)

        text = (
            "🧪 <b>Лавка Лінивця Омо</b>\n\n"
            "🦥 <i>«П-р-и-в-і-т... Щ-о...\nс-ь-о-г-о-д-н-і в-а-р-и-т-і-м-е-м-о?»</i>"
        )
        
        await callback.message.edit_media(
            media=InputMediaPhoto(media=IMAGES_URLS["alchemy"], caption=text, parse_mode="HTML"),
            reply_markup=builder.as_markup()
        )
    finally:
        await conn.close()

@router.callback_query(F.data.startswith("brew:"))
async def preview_recipe(callback: types.CallbackQuery):
    recipe_id = callback.data.split(":")[1]
    recipe = RECIPES.get(recipe_id)
    if not recipe: return await callback.answer("Рецепт зник!")
    
    user_id = callback.from_user.id
    conn = await get_db_connection()
    row = await conn.fetchrow("SELECT meta FROM capybaras WHERE owner_id = $1", user_id)
    meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
    inv = meta.get('inventory', {})
    await conn.close()

    ing_text = ""
    can_brew = True
    
    for ing, req_count in recipe['ingredients'].items():
        _, owned = find_item_in_inventory(inv, ing)
        display_name = DISPLAY_NAMES.get(ing, ing)
        status = "✅" if owned >= req_count else "❌"
        ing_text += f"\n{status} {display_name}: <b>{owned}/{req_count}</b>"
        if owned < req_count: can_brew = False

    # Формування опису ефекту
    effect_desc = "???"
    if "plus_stamina" in recipe: effect_desc = f"⚡ +{recipe['plus_stamina']} Енергії"
    elif "plus_max_hp" in recipe: effect_desc = f"❤️ +{recipe['plus_max_hp']} Макс. HP (Назавжди)"
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
async def process_confirm_brew(callback: types.CallbackQuery):
    recipe_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    recipe = RECIPES.get(recipe_id)

    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT meta FROM capybaras WHERE owner_id = $1", user_id)
        meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
        inv = meta.setdefault("inventory", {})

        # Фінальна перевірка інгредієнтів
        for ing, count in recipe['ingredients'].items():
            cat, owned = find_item_in_inventory(inv, ing)
            if not cat or owned < count:
                return await callback.answer("❌ Інгредієнти втекли з казана!", show_alert=True)
            inv[cat][ing] -= count

        # Додавання зілля
        potions = inv.setdefault("potions", {})
        potions[recipe_id] = potions.get(recipe_id, 0) + 1

        await conn.execute("UPDATE capybaras SET meta = $1 WHERE owner_id = $2", 
                           json.dumps(meta, ensure_ascii=False), user_id)

        await callback.answer(f"✨ {recipe.get('name')} готове!")
        await process_open_alchemy(callback)
        
    finally:
        await conn.close()

@router.callback_query(F.data.startswith("use_potion:"))
async def process_drink_potion(callback: types.CallbackQuery):
    potion_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    recipe = RECIPES.get(potion_id)
    
    if not recipe: return await callback.answer("❌ Невідоме зілля")

    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT meta FROM capybaras WHERE owner_id = $1", user_id)
        meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
        
        inv = meta.get("inventory", {})
        potions = inv.get("potions", {})
        
        if potions.get(potion_id, 0) <= 0:
            return await callback.answer("❌ Пляшка порожня!", show_alert=True)
        
        alert_text = "Гм... Смак дивний."
        
        # --- ЕФЕКТИ ---
        if "plus_stamina" in recipe:
            meta["stamina"] = min(meta.get("stamina", 0) + recipe["plus_stamina"], meta.get("max_stamina", 100))
            alert_text = f"Ви випили {recipe['name']}! +{recipe['plus_stamina']}⚡"

        elif "plus_max_hp" in recipe:
            stats = meta.setdefault("stats", {})
            stats["max_hp"] = int(stats.get("max_hp", 10)) + recipe["plus_max_hp"]
            alert_text = f"🧬 Максимальне HP зросло на +{recipe['plus_max_hp']}!"

        elif recipe.get("effect") == "stats_reset":
            stats = meta.get("stats", {})
            # Повертаємо очки за атаку, деф, агілу та лак
            total_points = sum([
                max(0, stats.get("attack", 1) - 1),
                max(0, stats.get("defense", 1) - 1),
                max(0, stats.get("agility", 1) - 1),
                max(0, stats.get("luck", 1) - 1)
            ])
            meta["stats"] = {
                "max_hp": stats.get("max_hp", 10), # HP не скидаємо
                "attack": 1, "defense": 1, "agility": 1, "luck": 1
            }
            meta["points"] = meta.get("points", 0) + total_points
            alert_text = "🌀 Характеристики скинуто! Очки повернуто."

        # Видалення зілля після використання
        potions[potion_id] -= 1
        if potions[potion_id] <= 0: del potions[potion_id]

        await conn.execute("UPDATE capybaras SET meta = $1 WHERE owner_id = $2",
                           json.dumps(meta, ensure_ascii=False), user_id)

        await callback.answer(alert_text, show_alert=True)

        # Оновлення сторінки інвентарю
        try:
            from handlers.inventory import render_inventory_page 
            await render_inventory_page(callback.message, user_id, page="potions", is_callback=True)
        except ImportError:
            await callback.message.delete()

    finally:
        await conn.close()