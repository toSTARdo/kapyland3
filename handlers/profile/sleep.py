import json
from datetime import datetime, timezone, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from handlers.profile.view import get_profile_kb, get_profile_text

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
    
    status, result_data = await sleep_db_operation(uid, db_pool) 
    
    if status == "no_capy":
        msg = "❌ У тебе немає капібари!"
        if isinstance(event, types.CallbackQuery):
            return await event.answer(msg, show_alert=True)
        return await event.answer(msg)
    
    if status == "already_sleeping":
        time_str = format_time(result_data)
        msg = f"💤 Капібара вже бачить сни. Прокинеться через: {time_str}"
        if isinstance(event, types.CallbackQuery):
            return await event.answer(msg, show_alert=True)
        return await event.answer(msg, parse_mode="HTML")

    if status == "success":
        from repositories.animal_repo import AnimalRepository # переконайся, що імпорт є

        repo = AnimalRepository(db_pool)
        animal = await repo.get_by_id(uid)
        new_kb = get_profile_kb(animal)
        alert_msg = "💤 Капібара лягла спати!"
        
        if isinstance(event, types.CallbackQuery):
            await event.answer(alert_msg, show_alert=True)
            
            if event.message.photo:
                await event.message.edit_caption(
                    caption=event.message.caption,
                    reply_markup=new_kb,
                    parse_mode="HTML"
                )
            else:
                await event.message.edit_text(
                    text=event.message.text,
                    reply_markup=new_kb,
                    parse_mode="HTML"
                )
        else:
            text = (
                "💤 <b>Капібара згорнулася калачиком...</b>\n"
                "Вона буде спати 2 години, щоб повністю відновити 100% ⚡.\n\n"
                "<i>У цей час вона не зможе битися або подорожувати.</i>"
            )
            await event.answer(text, reply_markup=new_kb, parse_mode="HTML")
            
@router.callback_query(F.data == "wakeup_now")
async def cmd_wakeup(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    status, gain = await wakeup_db_operation(uid, db_pool)
    
    if status == "error":
        return await callback.answer("❌ Ти вже не спиш!", show_alert=True)
    
    from repositories.animal_repo import AnimalRepository
    repo = AnimalRepository(db_pool)
    animal = await repo.get_by_id(uid)
    
    if not animal:
        return await callback.answer("❌ Помилка завантаження даних.")

    alert_msg = f"🥥 Капібарі на голову впав кокос і вона проснулася! Вона відновила {gain}⚡ стаміни."
    if status == "overslept":
        alert_msg = "😴 Капібара відіспала кінську голову! Стаміна: 100⚡." 

    async with db_pool.acquire() as conn:
        quicklinks = await conn.fetchval("SELECT quicklinks FROM users WHERE tg_id = $1", uid)
    if quicklinks is None: quicklinks = True

    new_text = get_profile_text(animal)
    new_kb = get_profile_kb(animal, show_quicklinks=quicklinks)
    
    try:
        await callback.answer(alert_msg, show_alert=True)

        if callback.message.photo:
            await callback.message.edit_caption(
                caption=new_text,
                reply_markup=new_kb,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                text=new_text,
                reply_markup=new_kb,
                parse_mode="HTML"
            )
    except Exception as e:
        print(f"Error updating profile: {e}")

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
        row = await conn.fetchrow("SELECT state, stamina, max_stamina FROM capybaras WHERE owner_id = $1", tg_id)
        if not row: return "error", 0
        
        MAX_STAMINA = row["max_stamina"]
        state = json.loads(row['state']) if isinstance(row['state'], str) else (row['state'] or {})
        if state.get("status") != "sleep":
            return "error", 0

        start_time_str = state.get("sleep_start", datetime.now(timezone.utc).isoformat())
        start_time = datetime.fromisoformat(start_time_str)
        if start_time.tzinfo is None: start_time = start_time.replace(tzinfo=timezone.utc)
            
        now = datetime.now(timezone.utc)
        duration_minutes = (now - start_time).total_seconds() / 60
        current_stamina = row["stamina"] or 0

        if duration_minutes >= 120:
            new_stamina, status_result = MAX_STAMINA, "overslept"
        else:
            gained = int(duration_minutes * (100 / 120))
            new_stamina, status_result = min(MAX_STAMINA, current_stamina + gained), "success"

        actual_gain = new_stamina - current_stamina
        state.update({"status": "active"})
        state.pop("sleep_start", None)
        state.pop("wake_up", None)

        await conn.execute(
            "UPDATE capybaras SET state = $1, stamina = $2 WHERE owner_id = $3", 
            json.dumps(state), new_stamina, tg_id
        )
        return status_result, max(0, actual_gain)