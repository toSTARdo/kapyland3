import json
import datetime
from datetime import datetime, timezone, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command

router = Router()

def format_time(wake_up_str: str) -> str:
    if not wake_up_str:
        return "невідомо"
    now = datetime.now(timezone.utc)
    wake_up = datetime.fromisoformat(wake_up_str)
    if wake_up.tzinfo is None:
        wake_up = wake_up.replace(tzinfo=timezone.utc)
    
    diff = wake_up - now
    if diff.total_seconds() <= 0:
        return "ось-ось"
    
    minutes, seconds = divmod(int(diff.total_seconds()), 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours}г {minutes}хв"
    return f"{minutes}хв"

@router.callback_query(F.data == "sleep_capy")
@router.message(Command("sleep"))
async def cmd_sleep(event: types.Message | types.CallbackQuery, db_pool):
    uid = event.from_user.id
    message = event.message if isinstance(event, types.CallbackQuery) else event
    
    if isinstance(event, types.CallbackQuery):
        await event.answer()

    status, result_data = await sleep_db_operation(uid, db_pool) 
    
    if status == "no_capy":
        return await message.answer("❌ У тебе немає капібари!")
    
    if status == "already_sleeping":
        time_str = format_time(result_data)
        return await message.answer(f"💤 Капібара вже бачить сни. Прокинеться через: <b>{time_str}</b>", parse_mode="HTML")

    if status == "success":
        await message.answer(
            "💤 <b>Капібара згорнулася калачиком...</b>\n"
            "Вона буде спати 2 години, щоб повністю відновити 100% ⚡.\n\n"
            "<i>У цей час вона не зможе битися або подорожувати.</i>",
            parse_mode="HTML"
        )

async def sleep_db_operation(tg_id: int, db_pool):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT state, stamina, stats_track, inventory, achievements, unlocked_titles,
                   wins, total_fights, lvl, weight, atk, def as def_, agi, luck, zen, hunger
            FROM capybaras WHERE owner_id = $1
        """, tg_id)
        
        if not row:
            return "no_capy", None
        
        state = json.loads(row['state']) if isinstance(row['state'], str) else (row['state'] or {})
        
        if state.get("status") == "sleep":
            return "already_sleeping", state.get("wake_up")

        now = datetime.now(timezone.utc)
        wake_up_time = now + timedelta(hours=2)
        
        state["status"] = "sleep"
        state["sleep_start"] = now.isoformat()
        state["wake_up"] = wake_up_time.isoformat()
        
        await conn.execute(
            "UPDATE capybaras SET state = $1 WHERE owner_id = $2", 
            json.dumps(state), tg_id
        )
        return "success", None

@router.callback_query(F.data == "wakeup_now")
async def cmd_wakeup(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    status, gain = await wakeup_db_operation(uid, db_pool)
    
    if status == "error":
        return await callback.answer("Сталася помилка або капібари не існує.", show_alert=True)
    
    msg = f"🥥 Капібарі на голову впав кокос і вона проснулася! Вона відновила {gain}⚡ стаміни."
    if status == "overslept":
        msg = "😴 Капібара відіспала кінську голову! Стаміна: 100⚡."

    try:
        if callback.message.caption or callback.message.photo:
            await callback.message.edit_caption(caption=msg, reply_markup=None)
        else:
            await callback.message.edit_text(msg, reply_markup=None)
    except Exception as e:
        await callback.message.answer(msg)
        
    await callback.answer()

async def wakeup_db_operation(tg_id: int, db_pool):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT state, stamina FROM capybaras WHERE owner_id = $1", tg_id)
        if not row: return "error", 0
        
        state = json.loads(row['state']) if isinstance(row['state'], str) else (row['state'] or {})
        
        if state.get("status") != "sleep":
            return "error", 0

        try:
            start_time = datetime.fromisoformat(state["sleep_start"])
        except (KeyError, ValueError):
            start_time = datetime.now(timezone.utc)

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
            
        now = datetime.now(timezone.utc)
        duration_minutes = (now - start_time).total_seconds() / 60
        
        current_stamina = row["stamina"] or 0

        if duration_minutes >= 120:
            actual_gain = 100 - current_stamina 
            new_stamina = 100
            status_result = "overslept"
        else:
            recovery_rate = 100 / 120 
            gained_stamina = int(duration_minutes * recovery_rate)
            new_stamina = min(100, current_stamina + gained_stamina)
            actual_gain = new_stamina - current_stamina
            status_result = "success"

        state["status"] = "active"
        state.pop("sleep_start", None)
        state.pop("wake_up", None)

        await conn.execute(
            "UPDATE capybaras SET state = $1, stamina = $2 WHERE owner_id = $3", 
            json.dumps(state), new_stamina, tg_id
        )
        
        return status_result, max(0, actual_gain)