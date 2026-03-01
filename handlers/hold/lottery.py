import asyncio
import json
import random
import datetime

from aiogram import Router, types, html, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import RARITY_META, ARTIFACTS, LOTTERY_BANNERS, load_game_data

GACHA_ITEMS = ARTIFACTS
router = Router()

def is_eligible_for_lega(last_lega_str: str) -> bool:
    if not last_lega_str:
        return True

    if isinstance(last_lega_str, str):
        try:
            last_lega_str = datetime.datetime.fromisoformat(last_lega_str)
        except:
            return True
            
    return datetime.datetime.now() >= last_lega_str + datetime.timedelta(days=7)

@router.message(F.text.startswith("🎟️"))
@router.callback_query(F.data.startswith("lottery_menu"))
async def cmd_lottery_start(event: types.Message | types.CallbackQuery, db_pool):
    uid = event.from_user.id
    is_callback = isinstance(event, types.CallbackQuery)
    
    banner_idx = 0
    if is_callback and "_" in event.data:
        try: banner_idx = int(event.data.rsplit("_", 1)[-1])
        except: banner_idx = 0

    lottery_img = LOTTERY_BANNERS[banner_idx % len(LOTTERY_BANNERS)]
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT inventory, last_weekly_lega FROM capybaras WHERE owner_id = $1", 
            uid
        )
    
    inventory = (json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']) or {}
    tickets = inventory.get("loot", {}).get("lottery_ticket", 0)
    can_get_lega = is_eligible_for_lega(row.get('last_weekly_lega'))

    builder = InlineKeyboardBuilder()
    
    if banner_idx == 0:
        label = "LEGENDARY" if can_get_lega else "EPIC"
        text = (
            f"🎰 <b>ГАЗИНО «ФОРТУНА КАПІ»</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Твої квитки: <b>{tickets}</b> 🎟\n"
            f"<i>Гортай банери, щоб побачити акції!</i>"
        )
        builder.row(types.InlineKeyboardButton(text="🏴‍☠️ Крутити (1🎟 / 5кг)", callback_data="gacha_spin"))
        builder.row(types.InlineKeyboardButton(text=f"🔥 10+1 / 100% {label}", callback_data="gacha_guaranteed_10"))
    else:
        text = (
            f"🎰 <b>ГАЗИНО «ФОРТУНА КАПІ»</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🚧 <b>[COMING SOON]</b>\n"
            f"<i>Цей розіграш ще готується кухарями-капібарами.</i>"
        )
        builder.row(types.InlineKeyboardButton(text="⏳ В розробці...", callback_data="none"))

    prev_idx = (banner_idx - 1) % len(LOTTERY_BANNERS)
    next_idx = (banner_idx + 1) % len(LOTTERY_BANNERS)
    
    builder.row(
        types.InlineKeyboardButton(text="◀️", callback_data=f"lottery_menu_{prev_idx}"),
        types.InlineKeyboardButton(text=f"{banner_idx + 1} / {len(LOTTERY_BANNERS)}", callback_data="none"),
        types.InlineKeyboardButton(text="▶️", callback_data=f"lottery_menu_{next_idx}")
    )
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="open_inventory_main"))

    if is_callback:
        input_media = types.InputMediaPhoto(media=lottery_img, caption=text, parse_mode="HTML")
        try: await event.message.edit_media(media=input_media, reply_markup=builder.as_markup())
        except:
            await event.message.delete()
            await event.message.answer_photo(photo=lottery_img, caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await event.answer()
    else:
        await event.answer_photo(photo=lottery_img, caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "gacha_spin")
async def handle_gacha_spin(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, weight FROM capybaras WHERE owner_id = $1", uid)
        inventory = (json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']) or {}
        weight = row['weight']
        
        loot = inventory.setdefault("loot", {})
        tickets = loot.get("lottery_ticket", 0)
        
        if tickets > 0:
            loot["lottery_ticket"] -= 1
            pay_msg = "🎟 Використано квиток!"
        elif weight >= 5.1:
            weight -= 5.0
            pay_msg = "⚖️ Списано 5 кг ваги!"
        else:
            return await callback.answer("❌ Ти занадто худий! Треба хоча б 10 кг.", show_alert=True)

        await callback.message.edit_caption(caption=f"🌀 {pay_msg}\n<i>Крутимо барабан...</i>", parse_mode="HTML")
        await asyncio.sleep(1.0)
        
        rarity_key = random.choices(["Common", "Rare", "Epic", "Legendary"], weights=[60, 25, 12, 3], k=1)[0]
        item = random.choice(GACHA_ITEMS[rarity_key])
        
        equipment = inventory.setdefault("equipment", [])
        equipment.append({"name": item["name"], "type": item["type"], "rarity": rarity_key, "lvl": 0})
        
        await conn.execute(
            "UPDATE capybaras SET inventory = $1, weight = $2 WHERE owner_id = $3",
            json.dumps(inventory), weight, uid
        )

    res_text = (
        f"🎉 <b>ТВІЙ ПРИЗ!</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"Предмет: <b>{item['name']}</b>\n"
        f"{RARITY_META[rarity_key]['emoji']} Рідкість: <b>{RARITY_META[rarity_key]['label']}</b>\n"
        f"⚖️ Поточна вага: <b>{weight:.1f} кг</b>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🔄 Крутити ще", callback_data="gacha_spin"))
    builder.row(types.InlineKeyboardButton(text="⬅️ До Газино", callback_data="lottery_menu"))

    await callback.message.edit_caption(caption=res_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "gacha_guaranteed_10")
async def handle_bulk_spin(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    now = datetime.datetime.now()
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, last_weekly_lega FROM capybaras WHERE owner_id = $1", uid)
        inventory = (json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']) or {}
        
        loot = inventory.setdefault("loot", {})
        if loot.get("lottery_ticket", 0) < 10:
            return await callback.answer(f"❌ Треба 🎟️x10!", show_alert=True)
        
        can_get_lega = is_eligible_for_lega(row.get('last_weekly_lega'))
        equipment = inventory.setdefault("equipment", [])
        owned_names = [i["name"] for i in equipment if isinstance(i, dict)]
        
        results_icons = []
        watermelons_gain = 0
        used_weekly_bonus = False

        for i in range(11):
            if i == 10:
                if can_get_lega:
                    rarity = "Legendary"
                    used_weekly_bonus = True
                else: rarity = "Epic"
            else:
                r = random.random()
                if r < 0.03: rarity = "Legendary"
                elif r < 0.15: rarity = "Epic"
                elif r < 0.40: rarity = "Rare"
                else: rarity = "Common"

            item = random.choice(GACHA_ITEMS[rarity])
            prefix = RARITY_META[rarity]["emoji"]

            if item["name"] in owned_names:
                gain = {"Common": 1, "Rare": 2, "Epic": 3, "Legendary": 5}.get(rarity, 1)
                food = inventory.setdefault("food", {})
                food["watermelon_slices"] = food.get("watermelon_slices", 0) + gain
                watermelons_gain += gain
                results_icons.append(f"{prefix} <s>{item['name']}</s> 🍉+{gain}")
            else:
                equipment.append({"name": item["name"], "type": item["type"], "rarity": rarity, "lvl": 0})
                owned_names.append(item["name"])
                results_icons.append(f"{prefix} <b>{item['name']}</b>")

        loot["lottery_ticket"] -= 10
        
        if used_weekly_bonus:
            sql = "UPDATE capybaras SET inventory = $1, last_weekly_lega = $2 WHERE owner_id = $3"
            params = [json.dumps(inventory), now, uid]
        else:
            sql = "UPDATE capybaras SET inventory = $1 WHERE owner_id = $2"
            params = [json.dumps(inventory), uid]
            
        await conn.execute(sql, *params)
        
    res_list = "\n".join(results_icons)
    text = (
        f"🎰 <b>МЕГА КУШ: 10 + 1 БОНУС</b>\n"
        f"________________________________\n\n"
        f"{res_list}\n"
        f"________________________________\n"
        f"🍉 Нарізано з повторок: <b>{watermelons_gain}</b>\n"
        f"🎟️ Залишилось квитків: <b>{loot['lottery_ticket']}</b>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎰 Знову (🎟️x10)", callback_data="gacha_guaranteed_10")
    builder.button(text="🔙 Назад", callback_data="lottery_menu")
    builder.adjust(1)

    await callback.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()