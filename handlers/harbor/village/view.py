from aiogram import Router, types, F
from aiogram.filters import Command, or_f
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import IMAGES_URLS

router = Router()

@router.callback_query(F.data == "open_village")
@router.message(F.text.lower().contains("містечко"))
async def open_village(event: types.Message | types.CallbackQuery):
    is_callback = isinstance(event, types.CallbackQuery)
    message = event.message if is_callback else event
    
    village_text = (
        "🛖 <b>Містечко Пух-Пух</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🏠 Тут пахне свіжою деревиною та апельсиновим соком. Життя вирує!\n\n"
        "⚗️ <b>Лавка Омо</b> — магічні зілля та еліксири\n"
        "🔨 <b>Кузня Ківі</b> — сталь, молот та крафт\n"
        "🎪 <b>Базар</b> — обмін скарбами"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⚗️ Лавка Омо", callback_data="open_alchemy"))
    builder.row(types.InlineKeyboardButton(text="🔨 Кузня Ківі", callback_data="open_forge"))
    builder.row(types.InlineKeyboardButton(text="🎪 Базар", callback_data="open_bazaar"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад до Порту", callback_data="open_port_main"))

    if is_callback:
        try:
            await message.edit_caption(
                caption=village_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception:
            await message.delete()
            await message.answer_photo(
                photo=IMAGES_URLS["village_main"],
                caption=village_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        await event.answer()
    else:
        await message.answer_photo(
            photo=IMAGES_URLS["village_main"],
            caption=village_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )


#--------TEMPORALY---------!
from aiogram import Router, F
from aiogram.types import CallbackQuery
import json
import time
from datetime import date, datetime, timedelta

def get_circle_bar(current, total, length=14):
    """Генерує моноширинний прогрес-бар з кружечків"""
    if total <= 0: return "<code>○○○○○○○○○○○○○○</code>"
    
    # Скільки кружечків заповнено (●)
    filled = int(length * current / total)
    filled = max(0, min(length, filled))
    
    bar = "●" * filled + "○" * (length - filled)
    return f"<code>{bar}</code>"

@router.callback_query(F.data == "claim_daily")
async def claim_reward_handler(callback: CallbackQuery, db_pool):
    uid = callback.from_user.id
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT inventory, stats_track FROM capybaras WHERE owner_id = $1", 
            uid
        )
        
        if not row:
            return await callback.answer("Помилка: профіль не знайдено.")

        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        stats = json.loads(row['stats_track']) if isinstance(row['stats_track'], str) else row['stats_track']
        
        last_claim = stats.get("last_daily_claim")
        
        # 1. ПЕРЕВІРКА: Чи вже забирав сьогодні?
        if last_claim == today_str:
            return await callback.answer("⏳ Ти вже забрав сьогоднішній подарунок!", show_alert=True)

        # 2. РОЗРАХУНОК СТРАЙКУ (14 днів)
        streak = stats.get("daily_streak", 0)
        if last_claim == yesterday_str:
            streak = (streak % 14) + 1
        else:
            streak = 1

        # 3. ВИЗНАЧЕННЯ НАГОРОД
        rewards_list = []
        inv.setdefault("loot", {})
        inv.setdefault("food", {})

        # Щоденний квиток
        ticket_count = 1 if streak <= 7 else 2
        inv["loot"]["lottery_ticket"] = inv["loot"].get("lottery_ticket", 0) + ticket_count
        
        ticket_text = f"🎟 <b>{ticket_count}x Лотерейний квиток</b>"
        if streak > 7:
            ticket_text += " (Бонус 2-го тижня!)"
        rewards_list.append(ticket_text)

        # --- ДОДАТКОВІ НАГОРОДИ ---
        if streak in [3, 6, 9]:
            inv["food"]["tangerines"] = inv["food"].get("tangerines", 0) + 3
            rewards_list.append("🍊 <b>3x Мандаринки</b>")
        
        if streak == 7:
            inv["loot"]["chest"] = inv["loot"].get("chest", 0) + 1
            rewards_list.append("🗃 <b>Звичайна скриня</b>")
            
        if streak in [10, 12]:
            inv["food"]["melon"] = inv["food"].get("melon", 0) + 1
            rewards_list.append("🍈 <b>Стигла Диня</b>")
            
        if streak == 13:
            inv["food"]["kiwi"] = inv["food"].get("kiwi", 0) + 5
            rewards_list.append("🥝 <b>5x Ківі</b>")
            
        if streak == 14:
            inv["loot"]["mega_chest"] = inv["loot"].get("mega_chest", 0) + 1
            rewards_list.append("🕋 <b>МЕГА-СКРИНЯ</b>")

        # ЗБЕРЕЖЕННЯ
        stats["last_daily_claim"] = today_str
        stats["daily_streak"] = streak
        
        await conn.execute("""
            UPDATE capybaras 
            SET inventory = $1, stats_track = $2, last_seen = $3 
            WHERE owner_id = $4
        """, 
        json.dumps(inv, ensure_ascii=False), 
        json.dumps(stats, ensure_ascii=False), 
        datetime.now(), 
        uid)

        # ВІЗУАЛІЗАЦІЯ
        bar_visual = get_circle_bar(streak, 14, length=14)
        rewards_text = "\n".join([f"— {r}" for r in rewards_list])
        
        final_caption = (
            f"✅ <b>Нагороду отримано!</b>\n\n"
            f"Прогрес: <b>{streak} / 14 днів</b>\n"
            f"{bar_visual}\n\n"
            f"<b>Твій пакунок:</b>\n{rewards_text}\n\n"
            f"<i>Заходь завтра, щоб продовжити серію!</i>"
        )

        try:
            await callback.message.edit_caption(caption=final_caption, parse_mode="HTML")
        except Exception:
            await callback.message.answer(final_caption, parse_mode="HTML")
            
        await callback.answer("Посилку відкрито!")