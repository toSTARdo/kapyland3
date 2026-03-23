import json
import datetime
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware, types
from config import ACHIEVEMENTS

class CapyGuardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.Update, Dict[str, Any]], Awaitable[Any]],
        event: types.Update,
        data: Dict[str, Any],
    ) -> Any:
        
        payload = event.message or event.callback_query
        if not payload:
            return await handler(event, data)

        user_id = payload.from_user.id

        if event.callback_query:
            msg = event.callback_query.message
            user_click_id = event.callback_query.from_user.id
            owner_id = None
            if msg.reply_to_message:
                owner_id = msg.reply_to_message.from_user.id
            elif "ID:" in (msg.text or msg.caption or ""):
                try:
                    owner_id = int(msg.text.split("ID:")[1].strip().split()[0])
                except:
                    pass

            if owner_id and owner_id != user_click_id:
                return await event.callback_query.answer("Ах ти підступна капібара! 🐾 Це не твій профіль!", show_alert=True)

        is_game_command = False
        if event.message and event.message.text:
            text = event.message.text
            game_triggers = ["/", "⚔️", "🗺️", "🧼", "📜", "🎣", "🍎", "💤"]
            if any(text.startswith(trigger) for trigger in game_triggers):
                is_game_command = True
        
        if event.callback_query:
            is_game_command = True

        if not is_game_command:
            return await handler(event, data)

        db_pool = data.get("db_pool")
        if not db_pool:
            return await handler(event, data)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT state, stats_track, inventory, stamina, max_stamina, achievements, unlocked_titles,
                       wins, total_fights, lvl, weight, atk, def, agi, luck, zen, hunger
                FROM capybaras WHERE owner_id = $1
            """, user_id)
            
            if not row:
                return await handler(event, data)

            state = row['state'] if isinstance(row['state'], dict) else (json.loads(row['state']) if row['state'] else {})
            stats_track = row['stats_track'] if isinstance(row['stats_track'], dict) else (json.loads(row['stats_track']) if row['stats_track'] else {})
            inventory = row['inventory'] if isinstance(row['inventory'], dict) else (json.loads(row['inventory']) if row['inventory'] else {})

            meta = {
                "stamina": row["stamina"],
                "MAX_STAMINA": row["max_stamina"],
                "last_regen": state.get("last_regen"),
                "status": state.get("status", "active"),
                "wake_up": state.get("wake_up"),
                "stats_track": stats_track,
                "achievements": row["achievements"] or [],
                "unlocked_titles": row["unlocked_titles"] or ["Новачок"],
                "inventory": inventory,
                "wins": row["wins"],
                "total_fights": row["total_fights"],
                "level": row["lvl"],
                "weight": row["weight"],
                "atk": row["atk"],
                "def": row["def"],
                "agi": row["agi"],
                "luck": row["luck"],
                "zen": row["zen"],
                "hunger": row["hunger"],
                "last_clean_check_date": state.get("last_clean_check_date"),
                "clean_days": state.get("clean_days", 0),
                "is_muted": state.get("is_muted", False)
            }

            now = datetime.datetime.now(datetime.timezone.utc)
            stamina = meta.get("stamina", 100)
            MAX_STAMINA = meta.get("max_stamina", 100)
            last_regen_str = meta.get("last_regen")
            
            needs_update = False

            if stamina >= MAX_STAMINA:
                meta["last_regen"] = now.isoformat()
            elif last_regen_str:
                last_regen = datetime.datetime.fromisoformat(last_regen_str)
                if last_regen.tzinfo is None:
                    last_regen = last_regen.replace(tzinfo=datetime.timezone.utc)
                
                regen_points = (int((now - last_regen).total_seconds() // 60) // 14)
                if regen_points > 0:
                    meta["stamina"] = min(MAX_STAMINA, stamina + regen_points)
                    meta["last_regen"] = (last_regen + datetime.timedelta(minutes=regen_points * 14)).isoformat()
                    needs_update = True
            else:
                meta["last_regen"] = now.isoformat()

            if meta.get("status") == "sleep":
                wake_up_str = meta.get("wake_up")
                if wake_up_str:
                    wake_time = datetime.datetime.fromisoformat(wake_up_str)
                    if wake_time.tzinfo is None:
                        wake_time = wake_time.replace(tzinfo=datetime.timezone.utc)
                    
                    if now >= wake_time:
                        meta["status"] = "active"
                        meta["stamina"] = MAX_STAMINA
                        needs_update = True

            self.update_stats_track(meta, event)
            ach_changed = await self.check_achievements(meta, user_id, payload)
            
            if ach_changed:
                needs_update = True
                
            needs_update = True 

            if needs_update:
                state["last_regen"] = meta["last_regen"]
                state["status"] = meta["status"]
                state["last_clean_check_date"] = meta.get("last_clean_check_date")
                state["clean_days"] = meta.get("clean_days")
                
                await conn.execute("""
                    UPDATE capybaras 
                    SET state = $1, stats_track = $2, inventory = $3, 
                        stamina = $4, achievements = $5, unlocked_titles = $6, 
                        wins = $7, total_fights = $8
                    WHERE owner_id = $9
                """, 
                json.dumps(state), json.dumps(meta["stats_track"]), json.dumps(meta["inventory"]),
                meta["stamina"], meta["achievements"], meta["unlocked_titles"],
                meta["wins"], meta["total_fights"], user_id)

        if meta.get("status") != "sleep":
            return await handler(event, data)

        if event.message and event.message.text:
            safe_commands = ["/start", "🐾 Профіль", "⚙️ Налаштування", "🎒 Інвентар", "🎟️ Лотерея"]
            if event.message.text in safe_commands:
                return await handler(event, data)

        if event.callback_query:
            call_data = event.callback_query.data
            safe_callbacks = [
                "profile", "inv_page", "profile_back", "settings",
                "change_name_start", "toggle_layout", "stats_page", "gacha_spin", 
                "gacha_guaranteed_10", "equip:", "sell_item:", "inv_pagination:", "inv_page:", "wakeup_now"
            ]
            if any(call_data.startswith(cb) for cb in safe_callbacks):
                return await handler(event, data)

        warning = "💤 Твоя капібара бачить десятий сон... Не турбуй її."
        if event.callback_query:
            return await event.callback_query.answer(warning, show_alert=True)
        return await event.message.answer(warning)

    def update_stats_track(self, meta: dict, event: types.Update):
        stats = meta.setdefault("stats_track", {})
        now = datetime.datetime.now(datetime.timezone.utc)
        stats["total_clicks"] = stats.get("total_clicks", 0) + 1

        today_date = now.date().isoformat()
        last_clean_check = meta.get("last_clean_check_date")
        
        if last_clean_check != today_date:
            if not meta.get("is_muted", False):
                meta["clean_days"] = meta.get("clean_days", 0) + 1
                meta["last_clean_check_date"] = today_date

        if event.callback_query:
            call_data = event.callback_query.data
            if call_data.startswith("brew:") or call_data.startswith("confirm_brew:"):
                stats["potions_brewed"] = stats.get("potions_brewed", 0) + 1
            if "fish" in call_data:
                stats["fish_caught"] = stats.get("fish_caught", 0) + 1
            if call_data.startswith("use_potion:"):
                stats["potions_used"] = stats.get("potions_used", 0) + 1
            if "win" in call_data:
                meta["wins"] = meta.get("wins", 0) + 1
                meta["total_fights"] = meta.get("total_fights", 0) + 1
            elif "lose" in call_data:
                meta["total_fights"] = meta.get("total_fights", 0) + 1

        if event.message and event.message.text:
            text = event.message.text
            if "⚔️" in text:
                stats["pvp_fights"] = stats.get("pvp_fights", 0) + 1
            if "🍎" in text or "🍉" in text:
                stats["fed_total"] = stats.get("fed_total", 0) + 1

        meta["speed"] = meta.get("agi", 0)
        s_atk = meta.get("atk", 0)
        s_def = meta.get("def", 0)
        s_agi = meta.get("agi", 0)
        s_luk = meta.get("luck", 0)
        meta["avg_stats"] = round((s_atk + s_def + s_agi + s_luk) / 4, 2)

    async def check_achievements(self, meta: dict, user_id: int, payload: types.Update):
        acquired = meta.setdefault("achievements", [])
        unlocked_titles = meta.setdefault("unlocked_titles", ["Новачок"])
        needs_save = False

        for ach_id, config in ACHIEVEMENTS.items():
            if ach_id not in acquired:
                if config["condition"](meta):
                    acquired.append(ach_id)
                    needs_save = True

                    chest_count = config.get("reward_chest", 0)
                    if chest_count > 0:
                        inv = meta.setdefault("inventory", {})
                        if isinstance(inv, str):
                            try:
                                inv = json.loads(inv)
                            except json.JSONDecodeError:
                                inv = {}
                        loot = inv.setdefault("loot", {})
                        loot["chest"] = loot.get("chest", 0) + chest_count

                    title = config.get("reward_title")
                    if title and title not in unlocked_titles:
                        unlocked_titles.append(title)

                    try:
                        alert = (
                            f"🏆 <b>НОВЕ ДОСЯГНЕННЯ!</b>\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"🌟 <b>{config['name']}</b>\n"
                            f"📜 <i>{config['desc']}</i>\n\n"
                            f"🎁 Нагорода: <b>{chest_count} 🗃</b> та титул «<b>{title}</b>»"
                        )
                        bot = payload.message.bot if payload.message else payload.callback_query.message.bot
                        await bot.send_message(user_id, alert, parse_mode="HTML")
                    except Exception:
                        pass
        return needs_save