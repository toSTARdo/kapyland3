import json
from datetime import datetime, timezone, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
    
    status, result_data = await sleep_db_operation(uid, db_pool) 
    
    if status == "no_capy":
        return await (event.answer("❌ У тебе немає капібари!", show_alert=True) if isinstance(event, types.CallbackQuery) else event.answer("❌ У тебе немає капібари!"))
    
    if status == "already_sleeping":
        time_str = format_time(result_data)
        text = f"💤 Вже спить! Прокинеться через: {time_str}"
        if isinstance(event, types.CallbackQuery):
            return await event.answer(text, show_alert=True)
        return await event.answer(text)

    if status == "success":
        builder = InlineKeyboardBuilder()
        builder.button(text="☀️ Прокинутися зараз", callback_data="wakeup_now")
        
        text = (
            "💤 <b>Капібара згорнулася калачиком...</b>\n"
            "Вона буде спати 2 години, щоб повністю відновити 100% ⚡.\n\n"
            "<i>У цей час вона не зможе битися або подорожувати.</i>"
        )
        
        if isinstance(event, types.CallbackQuery):
            await event.answer("Капібара лягла спати 😴", show_alert=False)
            if event.message.photo:
                await event.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await event.message.edit_text(text=text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "wakeup_now")
async def cmd_wakeup(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    status, gain = await wakeup_db_operation(uid, db_pool)
    
    if status == "error":
        return await callback.answer("❌ Ти вже не спиш!", show_alert=True)
    
    alert_msg = f"☀️ Пробудження! Відновлено {gain}⚡ стаміни."
    if status == "overslept":
        alert_msg = "😴 Капібара повністю виспалася! 100⚡"

    builder = InlineKeyboardBuilder()
    builder.button(text="👤 До профілю", callback_data="open_profile")
    
    try:
        await callback.answer(alert_msg, show_alert=True)

        if callback.message.photo:
            await callback.message.edit_caption(
                caption=callback.message.caption,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                text=callback.message.text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
    except Exception as e:
        pass

async def sleep_db_operation(tg_id: int, db_pool):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT state FROM capybaras WHERE owner_id = $1", tg_id)
        if not row: return "no_capy", None
        
        state = json.loads(row['state']) if isinstance(row['state'], str) else (row['state'] or {})
        if state.get("status") == "sleep":
            return "already_sleeping", state.get("wake_up")

        now = datetime.now(timezone.utc)
        wake_up_time = now + timedelta(hours=2)
        
        state.update({
            "status": "sleep",
            "sleep_start": now.isoformat(),
            "wake_up": wake_up_time.isoformat()
        })
        
        await conn.execute("UPDATE capybaras SET state = $1 WHERE owner_id = $2", json.dumps(state), tg_id)
        return "success", None

async def wakeup_db_operation(tg_id: int, db_pool):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT state, stamina FROM capybaras WHERE owner_id = $1", tg_id)
        if not row: return "error", 0
        
        state = json.loads(row['state']) if isinstance(row['state'], str) else (row['state'] or {})
        if state.get("status") != "sleep":
            return "error", 0

        start_time = datetime.fromisoformat(state.get("sleep_start", datetime.now(timezone.utc).isoformat()))
        if start_time.tzinfo is None: start_time = start_time.replace(tzinfo=timezone.utc)
            
        now = datetime.now(timezone.utc)
        duration_minutes = (now - start_time).total_seconds() / 60
        current_stamina = row["stamina"] or 0

        if duration_minutes >= 120:
            new_stamina, status_result = 100, "overslept"
        else:
            gained = int(duration_minutes * (100 / 120))
            new_stamina, status_result = min(100, current_stamina + gained), "success"

        actual_gain = new_stamina - current_stamina
        state.update({"status": "active"})
        state.pop("sleep_start", None); state.pop("wake_up", None)

        await conn.execute(
            "UPDATE capybaras SET state = $1, stamina = $2 WHERE owner_id = $3", 
            json.dumps(state), new_stamina, tg_id
        )
        return status_result, max(0, actual_gain)