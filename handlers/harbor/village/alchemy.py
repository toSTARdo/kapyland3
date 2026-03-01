import json
import asyncio
from aiogram import types, F, Router
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import load_game_data, DISPLAY_NAMES, IMAGES_URLS

router = Router()

RECIPES = load_game_data("data/potion_craft.json")

def find_item_in_inventory(inv, item_key):
    for category in ["food", "materials", "plants", "loot"]:
        cat_dict = inv.get(category, {})
        if item_key in cat_dict:
            return category, cat_dict[item_key]
    return None, 0

@router.callback_query(F.data == "open_alchemy")
async def process_open_alchemy(callback: types.CallbackQuery, db_pool):
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory FROM capybaras WHERE owner_id = $1", user_id)
        if not row: return
        
        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']

        builder = InlineKeyboardBuilder()
        for r_id, r_data in RECIPES.items():
            can_brew = True
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
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_village"))
        builder.adjust(1)

        text = (
            "🧪 <b>Лавка Лінивця Омо</b>\n\n"
            "🦥 <i>«П-р-и-в-і-т... Щ-о...\nс-ь-о-г-о-д-н-і в-а-р-и-т-и-м-е-м-о?»</i>"
        )
        
        await callback.message.edit_media(
            media=InputMediaPhoto(media=IMAGES_URLS["alchemy"], caption=text, parse_mode="HTML"),
            reply_markup=builder.as_markup()
        )

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
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, stamina, max_stamina, stats, points FROM capybaras WHERE owner_id = $1", user_id)
        if not row: return

        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        stats = json.loads(row['stats']) if isinstance(row['stats'], str) else row['stats']
        stamina, max_stamina, points = row['stamina'], row['max_stamina'], row['points']
        
        potions = inv.get("potions", {})
        if potions.get(potion_id, 0) <= 0:
            return await callback.answer("❌ Пляшка порожня!", show_alert=True)
        
        alert_text = "Смак дивний."
        update_fields = {}

        if "plus_stamina" in recipe:
            stamina = min(stamina + recipe["plus_stamina"], max_stamina)
            update_fields["stamina"] = stamina
            alert_text = f"⚡ Енергію відновлено на +{recipe['plus_stamina']}!"

        elif "plus_max_hp" in recipe:
            stats["max_hp"] = stats.get("max_hp", 10) + recipe["plus_max_hp"]
            update_fields["stats"] = json.dumps(stats, ensure_ascii=False)
            alert_text = f"🧬 Макс. HP зросло на +{recipe['plus_max_hp']}!"

        elif recipe.get("effect") == "stats_reset":
            recovered = sum([max(0, stats.get(s, 1) - 1) for s in ["attack", "defense", "agility", "luck"]])
            stats = {"max_hp": stats.get("max_hp", 10), "attack": 1, "defense": 1, "agility": 1, "luck": 1}
            update_fields["stats"] = json.dumps(stats, ensure_ascii=False)
            update_fields["points"] = points + recovered
            alert_text = "🌀 Характеристики скинуто!"

        potions[potion_id] -= 1
        if potions[potion_id] <= 0: del potions[potion_id]
        update_fields["inventory"] = json.dumps(inv, ensure_ascii=False)

        keys = list(update_fields.keys())
        values = list(update_fields.values())
        set_clause = ", ".join([f"{key} = ${i+1}" for i, key in enumerate(keys)])
        query = f"UPDATE capybaras SET {set_clause} WHERE owner_id = ${len(keys)+1}"
        await conn.execute(query, *values, user_id)

    await callback.answer(alert_text, show_alert=True)
    try:
        from handlers.inventory.navigator import render_inventory_page 
        await render_inventory_page(callback.message, user_id, page="potions", is_callback=True)
    except:
        await callback.message.delete()