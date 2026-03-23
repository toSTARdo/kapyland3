import json
import random
import math

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import IMAGES_URLS, KANJI_DICT

router = Router()


class ShipCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_kanji = State()


class ShipActions(StatesGroup):
    waiting_for_invite_id = State()
    waiting_for_new_name = State()


SHIP_BONUSES = {
    "tangerines": {"name": "🍊 Мандарини", "bonus": "EXP/Weight", "desc": "Досвід та вага"},
    "mushroom":   {"name": "🍄‍🟫 Гриби",    "bonus": "Combat",    "desc": "ATK/DEF/AGI"},
    "kiwi":       {"name": "🥝 Ківі",       "bonus": "Luck",      "desc": "Удача"},
    "melon":      {"name": "🍈 Дині",       "bonus": "Fishing",   "desc": "Шанс риболовлі"},
    "mango":      {"name": "🥭 Манго",      "bonus": "Stamina",   "desc": "Відновлення/Економія"},
}

# Maps food inventory key → cargo DB key (single source of truth)
FOOD_TO_CARGO_KEY = {
    "tangerines": "tangerines",
    "mushroom":   "mushroom",
    "kiwi":       "kiwi",
    "melon":      "melon",
    "mango":      "mango",
}


@router.callback_query(F.data == "ship_treasury")
async def ship_upgrade_vault(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        ship = await conn.fetchrow("""
            SELECT s.id, s.name, s.cargo
            FROM ships s
            JOIN capybaras c ON s.id = c.ship_id
            WHERE c.owner_id = $1
        """, uid)
        row = await conn.fetchrow("SELECT inventory FROM capybaras WHERE owner_id = $1", uid)

    if not ship:
        return await callback.answer("❌ Корабель не знайдено!", show_alert=True)

    inv   = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
    cargo = json.loads(ship['cargo'])    if isinstance(ship['cargo'], str)    else (ship['cargo'] or {})
    user_food = inv.get("food", {})

    text    = f"🏗 <b>Модернізація «{ship['name']}»</b>\n━━━━━━━━━━━━━━━\n"
    builder = InlineKeyboardBuilder()

    for food_key, info in SHIP_BONUSES.items():
        cargo_key = FOOD_TO_CARGO_KEY[food_key]
        in_hold   = int(cargo.get(cargo_key, 0))
        lvl       = int(math.sqrt(in_hold))
        bonus_val = lvl * 5
        next_lvl_req = (lvl + 1) ** 2

        text += (
            f"{info['name']} | <b>Lvl {lvl}</b> (+{bonus_val}%)\n"
            f"└ <i>{info['desc']}</i>: <code>{in_hold}/{next_lvl_req}</code>\n"
        )

        user_has = user_food.get(food_key, 0)
        if user_has > 0:
            builder.button(
                text=f"📥 Вкласти {info['name']} ({user_has})",
                callback_data=f"ship_dep_menu:{food_key}"
            )

    builder.button(text="🔙 Назад", callback_data="ship_main")
    builder.adjust(1)

    await callback.message.edit_caption(
        caption=text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("ship_dep_menu:"))
async def ship_deposit_menu(callback: types.CallbackQuery, db_pool):
    food_key = callback.data.split(":")[1]
    uid      = callback.from_user.id

    if food_key not in SHIP_BONUSES:
        return await callback.answer("❌ Невідомий ресурс!", show_alert=True)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory FROM capybaras WHERE owner_id = $1", uid)

    inv      = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
    user_has = inv.get("food", {}).get(food_key, 0)

    if user_has <= 0:
        return await callback.answer("❌ У тебе немає цього ресурсу!", show_alert=True)

    info    = SHIP_BONUSES[food_key]
    builder = InlineKeyboardBuilder()
    for amount in [1, 5, 10, 50]:
        if user_has >= amount:
            builder.button(
                text=f"📥 {amount} шт.",
                callback_data=f"ship_deposit:{food_key}:{amount}"
            )
    builder.button(
        text=f"📥 Все ({user_has})",
        callback_data=f"ship_deposit:{food_key}:all"
    )
    builder.button(text="🔙 Назад", callback_data="ship_treasury")
    builder.adjust(2)

    await callback.message.edit_caption(
        caption=(
            f"📥 <b>Вкласти {info['name']}</b>\n"
            f"У тебе: <b>{user_has} шт.</b>\n\n"
            f"Скільки покласти в трюм?"
        ),
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("ship_deposit:"))
async def handle_ship_deposit(callback: types.CallbackQuery, db_pool):
    parts      = callback.data.split(":")
    food_key   = parts[1]
    raw_amount = parts[2]
    uid        = callback.from_user.id
    cargo_key  = FOOD_TO_CARGO_KEY.get(food_key, food_key)

    async with db_pool.acquire() as conn:
        row      = await conn.fetchrow("SELECT inventory FROM capybaras WHERE owner_id = $1", uid)
        inv      = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        user_has = inv.get("food", {}).get(food_key, 0)
        amount   = user_has if raw_amount == "all" else int(raw_amount)

        if amount <= 0 or user_has < amount:
            return await callback.answer("❌ Недостатньо ресурсів!")

        inv["food"][food_key] -= amount

        async with conn.transaction():
            await conn.execute(
                "UPDATE capybaras SET inventory = $1 WHERE owner_id = $2",
                json.dumps(inv, ensure_ascii=False), uid
            )
            await conn.execute(f"""
                UPDATE ships SET cargo = jsonb_set(
                    COALESCE(cargo, '{{}}'),
                    '{{{cargo_key}}}',
                    (COALESCE((cargo->>'{cargo_key}')::int, 0) + $1)::text::jsonb
                )
                WHERE id = (SELECT ship_id FROM capybaras WHERE owner_id = $2)
            """, amount, uid)

    await callback.answer(f"📥 Вкладено {amount} шт.!")
    await ship_upgrade_vault(callback, db_pool)


@router.callback_query(F.data == "ship_engine")
async def ship_engine_room(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        ship = await conn.fetchrow("""
            SELECT s.name, s.engine
            FROM ships s JOIN capybaras c ON s.id = c.ship_id
            WHERE c.owner_id = $1
        """, uid)

    if not ship:
        return await callback.answer("❌ Корабель не знайдено!", show_alert=True)

    engine = ship['engine'] if isinstance(ship['engine'], dict) else json.loads(ship['engine'] or '{}')

    if not engine:
        status_text = "❌ <b>Двигун відсутній</b>\nСлот порожній. Потрібен T-двигун."
    else:
        status_text = (
            f"🚀 <b>Модель:</b> {engine.get('name', 'хом\'як в колесі')}\n"
            f"⚡️ <b>Потужність:</b> +{engine.get('power', 0)}\n"
            f"🛠 <b>Стан:</b> {engine.get('durability', 100)}%"
        )

    text    = f"⚙️ <b>Машинне відділення «{ship['name']}»</b>\n━━━━━━━━━━━━━━━\n{status_text}"
    builder = InlineKeyboardBuilder()

    if not engine:
        builder.button(text="🔧 Встановити двигун", callback_data="ship_install_engine")
    else:
        builder.button(text="🔋 Ремонт", callback_data="ship_repair_engine")

    builder.button(text="🔙 Назад", callback_data="ship_main")
    builder.adjust(1)

    await callback.message.edit_caption(
        caption=text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ship_install_engine")
async def install_t_item(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        row       = await conn.fetchrow("SELECT inventory FROM capybaras WHERE owner_id = $1", uid)
        inventory = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        inv_items = inventory.get("equipment", [])

        engine_to_install = next((i for i in inv_items if isinstance(i, dict) and i.get("type") == "T-engine"), None)

        if not engine_to_install:
            return await callback.answer("🚨 У тебе немає T-двигуна в інвентарі!", show_alert=True)

        inv_items.remove(engine_to_install)

        await conn.execute("""
            UPDATE ships SET engine = $1
            WHERE id = (SELECT ship_id FROM capybaras WHERE owner_id = $2)
        """, json.dumps(engine_to_install, ensure_ascii=False), uid)

        await conn.execute(
            "UPDATE capybaras SET inventory = $1 WHERE owner_id = $2",
            json.dumps(inventory, ensure_ascii=False), uid
        )

    await callback.answer("⚙️ T-двигун встановлено!", show_alert=True)
    await ship_engine_room(callback, db_pool)


@router.callback_query(F.data.startswith("ship_crew:"))
async def show_ship_crew(callback: types.CallbackQuery, db_pool):
    ship_id = int(callback.data.split(":")[1])
    async with db_pool.acquire() as conn:
        crew = await conn.fetch("""
            SELECT u.username, c.lvl FROM users u
            JOIN capybaras c ON u.tg_id = c.owner_id
            WHERE c.ship_id = $1 ORDER BY c.lvl DESC
        """, ship_id)

    if not crew:
        text = "🐾 <b>Екіпаж:</b>\n━━━━━━━━━━━━━━━\n<i>На кораблі нікого немає...</i>"
    else:
        rows = "\n".join(
            f"{i+1}. {m['username'] or 'Анонім'} (Lvl {m['lvl']})"
            for i, m in enumerate(crew)
        )
        text = f"🐾 <b>Екіпаж:</b>\n━━━━━━━━━━━━━━━\n{rows}"

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="ship_main")

    await callback.message.edit_caption(
        caption=text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ship_create_init")
async def ship_create_start(callback: types.CallbackQuery, state: FSMContext, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        arc_status = await conn.fetchval("""
            SELECT is_completed FROM story_progress
            WHERE user_id = $1 AND quest_id = 'ship_arc'
        """, uid)

        if not arc_status:
            return await callback.answer(
                "📜 Тобі ще зарано будувати власний корабель! "
                "Спочатку заверши сюжетну лінію у порту Кап-таун.",
                show_alert=True
            )

        row = await conn.fetchrow("SELECT inventory FROM capybaras WHERE owner_id = $1", uid)
        if not row:
            return await callback.answer("❌ Капібару не знайдено!", show_alert=True)

        inventory = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        wood_count = inventory.get("materials", {}).get("wood", 0)

        if wood_count < 10:
            return await callback.answer(
                f"❌ Тобі потрібно 10 🪵 Дерева! (Зараз у тебе: {wood_count})",
                show_alert=True
            )

    await state.set_state(ShipCreation.waiting_for_name)
    await callback.message.edit_caption(
        caption=(
            "🔨 <b>Верф готова до роботи!</b>\n\n"
            "Напиши назву свого майбутнього корабля:"
        ),
        reply_markup=InlineKeyboardBuilder()
            .button(text="❌ Скасувати", callback_data="ship_main")
            .as_markup(),
        parse_mode="HTML"
    )


@router.message(ShipCreation.waiting_for_name)
async def ship_name_received(message: types.Message, state: FSMContext):
    ship_name = message.text.strip()
    if len(ship_name) > 30:
        return await message.answer("⚠️ Назва занадто довга! Спробуй коротшу.")

    await state.update_data(name=ship_name)
    await state.set_state(ShipCreation.waiting_for_kanji)

    builder      = InlineKeyboardBuilder()
    random_kanji = random.sample(list(KANJI_DICT.items()), min(10, len(KANJI_DICT)))
    for kanji, mean in random_kanji:
        builder.button(text=f"{kanji} ({mean})", callback_data=f"set_kanji:{kanji}")
    builder.adjust(2)

    await message.answer(
        f"🚢 Назва «{ship_name}» прийнята!\nТепер обери <b>Прапор-канджі</b>:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(ShipCreation.waiting_for_kanji, F.data.startswith("set_kanji:"))
async def ship_final_confirm(callback: types.CallbackQuery, state: FSMContext, db_pool):
    kanji     = callback.data.split(":")[1]
    data      = await state.get_data()
    ship_name = data.get('name')
    uid       = callback.from_user.id

    if not ship_name:
        await state.clear()
        return await callback.answer("❌ Сесія застаріла, почни знову.", show_alert=True)

    async with db_pool.acquire() as conn:
        try:
            res = await conn.execute("""
                UPDATE capybaras
                SET inventory = jsonb_set(
                    inventory,
                    '{materials, wood}',
                    ((inventory->'materials'->>'wood')::int - 10)::text::jsonb
                )
                WHERE owner_id = $1
                AND (inventory->'materials'->>'wood')::int >= 10
            """, uid)

            if res == "UPDATE 0":
                return await callback.answer("❌ Недостатньо дерева! Потрібно 10 🪵", show_alert=True)

            ship_meta = {"flag": kanji, "captain_id": uid}
            ship_id   = await conn.fetchval("""
                INSERT INTO ships (name, lvl, gold, meta)
                VALUES ($1, 1, 0, $2) RETURNING id
            """, ship_name, json.dumps(ship_meta, ensure_ascii=False))

            await conn.execute(
                "UPDATE capybaras SET ship_id = $1 WHERE owner_id = $2",
                ship_id, uid
            )

            await state.clear()
            await callback.message.edit_caption(
                caption=(
                    f"🎊 <b>Вітаємо, Капітане!</b>\n\n"
                    f"Корабель {kanji} <b>«{ship_name}»</b> успішно збудовано "
                    f"з 10 🪵 і спущено на воду!"
                ),
                parse_mode="HTML"
            )

        except Exception as e:
            if "unique constraint" in str(e).lower():
                await callback.answer("❌ Корабель з такою назвою вже існує!", show_alert=True)
            else:
                raise


@router.callback_query(F.data == "ship_search_players")
async def ship_invite_list(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        candidates = await conn.fetch("""
            SELECT u.tg_id, u.username, c.lvl
            FROM users u
            JOIN capybaras c ON u.tg_id = c.owner_id
            WHERE c.ship_id IS NULL AND u.tg_id != $1
            ORDER BY c.lvl DESC LIMIT 10
        """, uid)
        ship = await conn.fetchrow(
            "SELECT id, name FROM ships WHERE (meta->>'captain_id')::bigint = $1", uid
        )

    if not ship:
        return await callback.answer("❌ Тільки капітан може шукати екіпаж!", show_alert=True)

    text    = "🔍 <b>Пошук матросів у таверні</b>\n\nЦі капібари зараз без корабля. Обери когось, щоб запросити до себе:"
    builder = InlineKeyboardBuilder()

    if candidates:
        for p in candidates:
            name = (p['username'] or 'Анонім')[:15]
            builder.row(types.InlineKeyboardButton(
                text=f"⚓ {name} (Lvl {p['lvl']})",
                callback_data=f"ship_send_invite:{p['tg_id']}"
            ))
    else:
        text += "\n\n<i>Наразі всі капібари при ділі...</i>"

    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="ship_main"))

    await callback.message.edit_caption(
        caption=text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("ship_send_invite:"))
async def send_invite_to_player(callback: types.CallbackQuery, db_pool):
    target_id  = int(callback.data.split(":")[1])
    captain_id = callback.from_user.id

    async with db_pool.acquire() as conn:
        ship = await conn.fetchrow(
            "SELECT id, name FROM ships WHERE (meta->>'captain_id')::bigint = $1", captain_id
        )
        if not ship:
            return await callback.answer("❌ Тільки капітан може запрошувати!", show_alert=True)

        already_on_ship = await conn.fetchval(
            "SELECT ship_id FROM capybaras WHERE owner_id = $1", target_id
        )
        if already_on_ship:
            return await callback.answer("❌ Цей гравець вже на кораблі!", show_alert=True)

    invite_kb = InlineKeyboardBuilder()
    invite_kb.button(text="✅ Прийняти", callback_data=f"ship_accept:{ship['id']}")
    invite_kb.button(text="❌ Відхилити", callback_data="ship_reject")

    try:
        await callback.bot.send_message(
            target_id,
            f"📨 Капітан корабля <b>«{ship['name']}»</b> запрошує тебе до свого екіпажу!",
            reply_markup=invite_kb.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer("✅ Запит надіслано!", show_alert=True)
    except Exception:
        await callback.answer("🚨 Не вдалося надіслати (гравець заблокував бота)", show_alert=True)


@router.callback_query(F.data == "ship_reject")
async def reject_invite(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Ти відхилив запрошення.")
    await callback.answer()


@router.message(ShipActions.waiting_for_invite_id)
async def process_ship_invite(message: types.Message, state: FSMContext, db_pool):
    if not message.text.isdigit():
        return await message.answer("⚠️ Введи коректний числовий ID.")

    target_id  = int(message.text)
    captain_id = message.from_user.id

    async with db_pool.acquire() as conn:
        captain_ship = await conn.fetchrow(
            "SELECT id, name FROM ships WHERE (meta->>'captain_id')::bigint = $1", captain_id
        )
        if not captain_ship:
            return await message.answer("❌ Тільки капітан може запрошувати людей.")

        target_capy = await conn.fetchrow(
            "SELECT ship_id FROM capybaras WHERE owner_id = $1", target_id
        )
        if not target_capy:
            return await message.answer("❌ Цього гравця не знайдено в базі.")
        if target_capy['ship_id']:
            return await message.answer("❌ Цей гравець вже є членом іншого екіпажу.")

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Прийняти", callback_data=f"ship_accept:{captain_ship['id']}")
    builder.button(text="❌ Відхилити", callback_data="ship_reject")

    try:
        await message.bot.send_message(
            target_id,
            f"📨 Вас запрошують на корабель <b>«{captain_ship['name']}»</b>!\n"
            f"Капітан: {message.from_user.full_name}",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await message.answer(f"✅ Запит надіслано гравцеві <code>{target_id}</code>")
        await state.clear()
    except Exception:
        await message.answer("❌ Не вдалося надіслати повідомлення (можливо, бот заблокований).")


@router.callback_query(F.data.startswith("ship_accept:"))
async def accept_invite(callback: types.CallbackQuery, db_pool):
    ship_id = int(callback.data.split(":")[1])
    uid     = callback.from_user.id

    async with db_pool.acquire() as conn:
        already = await conn.fetchval(
            "SELECT ship_id FROM capybaras WHERE owner_id = $1", uid
        )
        if already:
            return await callback.answer("❌ Ти вже на кораблі!", show_alert=True)

        crew_count = await conn.fetchval(
            "SELECT COUNT(*) FROM capybaras WHERE ship_id = $1", ship_id
        )
        if crew_count >= 10:
            return await callback.answer("❌ На кораблі більше немає кают! (Макс. 10)", show_alert=True)

        await conn.execute(
            "UPDATE capybaras SET ship_id = $1 WHERE owner_id = $2", ship_id, uid
        )

    await callback.message.edit_text("⛵ Вітаємо на борту! Тепер ти член екіпажу.")
    await callback.answer()


@router.callback_query(F.data == "ship_leave_confirm")
async def confirm_leave(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🏃 Так, покинути борт", callback_data="ship_leave_execute")
    builder.button(text="🔙 Скасувати",           callback_data="ship_main")
    builder.adjust(1)

    await callback.message.edit_caption(
        caption=(
            "⚠️ <b>Ти впевнений?</b>\n"
            "При виході з екіпажу ти втратиш доступ до трюму та машинного відділення."
        ),
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ship_leave_execute")
async def execute_leave(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        is_captain = await conn.fetchval(
            "SELECT id FROM ships WHERE (meta->>'captain_id')::bigint = $1", uid
        )
        if is_captain:
            return await callback.answer(
                "❌ Капітан не може покинути свій корабель! "
                "Розпусти його в налаштуваннях.",
                show_alert=True
            )
        await conn.execute("UPDATE capybaras SET ship_id = NULL WHERE owner_id = $1", uid)

    await callback.message.edit_caption(
        caption="🌊 Ти зійшов на берег. Тепер ти знову вільний плавець.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "ship_settings")
async def ship_settings_menu(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        ship = await conn.fetchrow(
            "SELECT name FROM ships WHERE (meta->>'captain_id')::bigint = $1", uid
        )

    if not ship:
        return await callback.answer("❌ Ти не капітан!", show_alert=True)

    text = (
        f"⚙️ <b>Керування кораблем «{ship['name']}»</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "Тут ти можеш змінити назву або повністю розпустити екіпаж і затопити судно."
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Змінити назву",        callback_data="ship_rename_init")
    builder.button(text="💥 Розпустити корабель",  callback_data="ship_disband_confirm")
    builder.button(text="🔙 Назад",                callback_data="ship_main")
    builder.adjust(1)

    await callback.message.edit_caption(
        caption=text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ship_disband_confirm")
async def confirm_disband(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔥 Так, затопити судно", callback_data="ship_disband_execute")
    builder.button(text="🔙 Скасувати",           callback_data="ship_settings")
    builder.adjust(1)

    await callback.message.edit_caption(
        caption=(
            "⚠️ <b>УВАГА!</b>\n\n"
            "Ти збираєшся розпустити свій корабель. "
            "Усі матроси залишаться без борту, а золото в трюмі буде втрачено назавжди!\n\n"
            "Ти впевнений?"
        ),
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "ship_disband_execute")
async def execute_disband(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        ship = await conn.fetchrow(
            "SELECT id FROM ships WHERE (meta->>'captain_id')::bigint = $1", uid
        )
        if not ship:
            return await callback.answer("❌ Корабель не знайдено.", show_alert=True)

        await conn.execute("UPDATE capybaras SET ship_id = NULL WHERE ship_id = $1", ship['id'])
        await conn.execute("DELETE FROM ships WHERE id = $1", ship['id'])

    await callback.message.edit_caption(
        caption=(
            "🌊 <b>Корабель пішов на дно...</b>\n\n"
            "Екіпаж розпущено, а ти знову вільний капітан без судна."
        ),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "ship_rename_init")
async def rename_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ShipActions.waiting_for_new_name)
    await callback.message.edit_caption(
        caption="📝 Введи нову назву для свого корабля:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(ShipActions.waiting_for_new_name)
async def rename_process(message: types.Message, state: FSMContext, db_pool):
    new_name = message.text.strip()
    if len(new_name) > 30:
        return await message.answer("⚠️ Назва занадто довга!")

    uid = message.from_user.id
    async with db_pool.acquire() as conn:
        updated = await conn.execute(
            "UPDATE ships SET name = $1 WHERE (meta->>'captain_id')::bigint = $2",
            new_name, uid
        )

    if updated == "UPDATE 0":
        return await message.answer("❌ Корабель не знайдено або ти не капітан.")

    await message.answer(
        f"✅ Тепер твій корабель називається <b>«{new_name}»</b>!",
        parse_mode="HTML"
    )
    await state.clear()