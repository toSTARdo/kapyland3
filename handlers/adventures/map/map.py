import json
import asyncio
import random
import datetime as dt
from aiogram import types, F, Router
from .map_assets import *
from .map_renderer import render_pov, render_world_viewer, get_stamina_icons
from .map_keyboard import get_map_keyboard, get_viewer_keyboard
from handlers.adventures.quests.quests import start_branching_quest

router = Router()

@router.callback_query(F.data == "open_map")
async def render_map(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT stamina, navigation, state, inventory, cooldowns 
            FROM capybaras WHERE owner_id = $1
        """, uid)
        
        if not row: return
        
        nav = json.loads(row['navigation'])
        state = json.loads(row['state'])
        inv = json.loads(row['inventory'])
        cooldowns = json.loads(row['cooldowns']) if row['cooldowns'] else {}
        stamina = row['stamina']

        last_refresh = cooldowns.get("flowers_refresh")
        can_refresh = not last_refresh or dt.datetime.fromisoformat(last_refresh) < dt.datetime.now() - dt.timedelta(days=1)

        if can_refresh:
            new_flowers = {}
            for _ in range(120):
                if len(new_flowers) >= 100: break
                rx, ry = random.randint(0, MAP_WIDTH-1), random.randint(0, MAP_HEIGHT-1)
                tile = FULL_MAP[ry][rx]
                
                if tile not in WATER_TILES:
                    is_forest = tile in FOREST_TILES
                    choices = ["✽", "𓋼"]
                    weights = [20, 80] if is_forest else [80, 20]
                    new_flowers[f"{rx},{ry}"] = random.choices(choices, weights=weights, k=1)[0]
            
            new_trees = {}
            for ry in range(MAP_HEIGHT):
                for rx in range(MAP_WIDTH):
                    if FULL_MAP[ry][rx] in FOREST_TILES:
                        new_trees[f"{rx},{ry}"] = FULL_MAP[ry][rx]
            
            nav["flowers"] = new_flowers
            nav["trees"] = new_trees
            cooldowns["flowers_refresh"] = dt.datetime.now().isoformat()

            await conn.execute("""
                UPDATE capybaras 
                SET navigation = $1, cooldowns = $2 
                WHERE owner_id = $3
            """, json.dumps(nav, ensure_ascii=False), json.dumps(cooldowns), uid)

        px, py = nav.get("x", 75), nav.get("y", 75)
        mode = state.get("mode", "capy")
        discovered = nav.get("discovered", [f"{px},{py}"])
        
        map_display = render_pov(
            px, py, discovered, mode, 
            treasure_maps=inv.get("maps", []), 
            flowers=nav.get("flowers", {}), 
            trees=nav.get("trees", {}),
            totems=nav.get("totems", [])
        )
        
        biome = get_biome_name(py, MAP_HEIGHT)
        text = (f"📍 <b>Карта ({px}, {py})</b> | {get_stamina_icons(stamina)}\n"
                f"🧭 Біом: {biome}\n🔋 Енергія: {stamina}/100\n\n{map_display}")
        
        is_on_tree = f"{px},{py}" in nav.get("trees", {})
        
        await callback.message.edit_text(
            text, 
            reply_markup=get_map_keyboard(px, py, mode, is_on_tree, inv, nav),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("mv:"))
async def handle_move(callback: types.CallbackQuery, db_pool):
    _, direction, x, y, mode = callback.data.split(":")
    nx, ny, uid = int(x), int(y), callback.from_user.id
    
    if direction == "up": ny -= 1
    elif direction == "down": ny += 1
    elif direction == "left": nx -= 1
    elif direction == "right": nx += 1

    if not (0 <= ny < MAP_HEIGHT and 0 <= nx < MAP_WIDTH):
        return await callback.answer("Там лише безодня... ⛔", show_alert=True)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT stamina, zen, navigation, inventory, state FROM capybaras WHERE owner_id = $1", uid)
        
        stamina = row['stamina']
        if stamina < 1: return await callback.answer("Ти занадто втомився... ⚡", show_alert=True)

        nav = json.loads(row['navigation'])
        inv = json.loads(row['inventory'])
        state = json.loads(row['state'])
        zen = row['zen']

        coord_key = f"{nx},{ny}"
        loot_msg = ""
        
        flowers = nav.get("flowers", {})
        if coord_key in flowers:
            icon = flowers[coord_key]
            if icon == "✽":
                item = get_random_plant()
                inv.setdefault("materials", {})[item['id']] = inv["materials"].get(item['id'], 0) + 1
                loot_msg = f"Знайдено: {item['name']} 🌿"
            elif icon == "𓋼":
                item = get_random_mushroom()
                inv.setdefault("food", {})[item['id']] = inv["materials"].get(item['id'], 0) + 1
                loot_msg = f"Знайдено: {item['name']} 🍄"
            
            del flowers[coord_key]
            nav["flowers"] = flowers

        target_tile = FULL_MAP[ny][nx]
        new_mode = mode
        if mode == "ship" and target_tile not in WATER_TILES:
            new_mode = "capy"
        elif mode == "capy" and target_tile in WATER_TILES:
            new_mode = "ship"

        disc_set = set(nav.get("discovered", []))
        old_size = len(disc_set)
        for dy in range(-1, 2):
            for dx in range(-2, 3):
                disc_set.add(f"{nx+dx},{ny+dy}")
        
        if len(disc_set) > old_size + 50: zen += 1

        if coord_key in COORD_QUESTS:
            nav.update({"x": nx, "y": ny, "discovered": list(disc_set)})
            state["mode"] = new_mode
            await conn.execute("UPDATE capybaras SET stamina=stamina-1, navigation=$1, state=$2 WHERE owner_id=$3", 
                               json.dumps(nav), json.dumps(state), uid)
            return await start_branching_quest(callback, COORD_QUESTS[coord_key], db_pool)

        nav.update({"x": nx, "y": ny, "discovered": list(disc_set)})
        state["mode"] = new_mode
        await conn.execute("""
            UPDATE capybaras SET stamina=$1, zen=$2, navigation=$3, inventory=$4, state=$5 WHERE owner_id=$6
        """, stamina-1, zen, json.dumps(nav), json.dumps(inv), json.dumps(state), uid)

        is_at_tree = coord_key in nav.get("trees", {})
        map_display = render_pov(nx, ny, disc_set, new_mode, inv.get("maps"), nav.get("flowers"), nav.get("trees"), nav.get("totems", []))
        
        text = (f"📍 <b>({nx}, {ny})</b> | {get_stamina_icons(stamina-1)}\n"
                f"🧭 Біом: {get_biome_name(ny)} | ✨ Дзен: {zen}\n\n"
                f"{map_display}")
        
        if loot_msg: text += f"\n\n✨ <i>{loot_msg}</i>"

        await callback.message.edit_text(
            text, 
            reply_markup=get_map_keyboard(nx, ny, new_mode, is_at_tree, inv, nav),
            parse_mode="HTML"
        )
        await callback.answer(loot_msg if loot_msg else None)

@router.callback_query(F.data.startswith("view:"))
async def handle_world_viewer(callback: types.CallbackQuery, db_pool):
    _, vx, vy = callback.data.split(":")
    vx, vy = int(vx), int(vy)
    uid = callback.from_user.id
    
    vx = max(0, min(MAP_WIDTH - 1, vx))
    vy = max(0, min(MAP_HEIGHT - 1, vy))
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT navigation FROM capybaras WHERE owner_id = $1", uid)
        if not row: return
        
        nav = row['navigation'] if isinstance(row['navigation'], dict) else json.loads(row['navigation'])
        discovered = nav.get("discovered", [])
        
        display = render_world_viewer(vx, vy, discovered)
                
        await callback.message.edit_text(
            text=f"{display}\n<i>💡 Переміщення в огляді не витрачає енергію. Ви бачите лише розвідані ділянки.</i>",
            reply_markup=get_viewer_keyboard(vx, vy),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("tp_to:"))
async def handle_teleport(callback: types.CallbackQuery, db_pool):
    target_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT navigation, stamina, inventory FROM capybaras WHERE owner_id = $1", uid)
        nav = json.loads(row['navigation']) if isinstance(row['navigation'], str) else row['navigation']
        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        
        if row['stamina'] < 15:
            return await callback.answer("⚡ Недостатньо енергії для стрибка (треба 15)!", show_alert=True)

        totems = nav.get("totems", [])
        target = next((t for t in totems if t['id'] == target_id), None)
        
        if not target:
            return await callback.answer("❌ Тотем не знайдено!", show_alert=True)

        nx, ny = target['x'], target['y']
        nav['x'], nav['y'] = nx, ny
        
        await conn.execute("""
            UPDATE capybaras SET navigation = $1, stamina = stamina - 15 WHERE owner_id = $2
        """, json.dumps(nav), uid)
        
        map_display = render_pov(nx, ny, nav.get("discovered", []), "capy", inv.get("maps", []), nav.get("flowers", {}), nav.get("trees", {}), totems)
        text = (f"🌀 <b>Телепортація успішна!</b>\n📍 Ви прибули до: {target['name']} ({nx}, {ny})\n\n{map_display}")
        
        await callback.message.edit_text(
            text, 
            reply_markup=get_map_keyboard(nx, ny, "capy", f"{nx},{ny}" in nav.get("trees", {}), inv, nav), 
            parse_mode="HTML"
        )

@router.callback_query(F.data == "map_place_totem")
async def handle_place_totem(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT inventory, navigation FROM capybaras WHERE owner_id = $1", uid)
        inv = json.loads(row['inventory']) if isinstance(row['inventory'], str) else row['inventory']
        nav = json.loads(row['navigation']) if isinstance(row['navigation'], str) else row['navigation']
        
        loot = inv.get("loot", {})
        if loot.get("teleport_totem", 0) <= 0:
            return await callback.answer("❌ У вас немає тотема в інвентарі!", show_alert=True)
            
        totems = nav.setdefault("totems", [])
        if len(totems) >= 3:
            return await callback.answer("🗿 На мапі вже встановлено максимум тотемів (3)!", show_alert=True)

        loot["teleport_totem"] -= 1
        if loot["teleport_totem"] <= 0: del loot["teleport_totem"]
        
        new_totem = {
            "id": int(dt.datetime.now().timestamp()),
            "x": nav['x'], "y": nav['y'],
            "name": f"Тотем {len(totems) + 1}"
        }
        totems.append(new_totem)
        
        await conn.execute("""
            UPDATE capybaras SET inventory = $1, navigation = $2 WHERE owner_id = $3
        """, json.dumps(inv), json.dumps(nav), uid)
        
        await callback.answer(f"✅ Тотем встановлено на ({nav['x']}, {nav['y']})", show_alert=True)

@router.callback_query(F.data.startswith("chop:"))
async def handle_chop_tree(callback: types.CallbackQuery, db_pool):
    _, x, y = callback.data.split(":")
    px, py = int(x), int(y)
    uid = callback.from_user.id
    coord_key = f"{px},{py}"

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT stamina, navigation, inventory, state 
            FROM capybaras WHERE owner_id = $1
        """, uid)
        
        if not row: return
        
        stamina = row['stamina']
        nav = json.loads(row['navigation'])
        inv = json.loads(row['inventory'])
        state = json.loads(row['state'])

        if stamina < 5:
            return await callback.answer("⚡ Недостатньо енергії (треба 5)!", show_alert=True)
        
        if coord_key not in nav.get("trees", {}):
            return await callback.answer("🌲 Тут немає дерева, яке можна зрубати!", show_alert=True)

        del nav["trees"][coord_key]
        
        inv.setdefault("materials", {})
        inv["materials"]["wood"] = inv["materials"].get("wood", 0) + 1
        
        await conn.execute("""
            UPDATE capybaras 
            SET stamina = stamina - 5, navigation = $1, inventory = $2 
            WHERE owner_id = $3
        """, json.dumps(nav), json.dumps(inv), uid)

        map_display = render_pov(
            px, py, nav.get("discovered", []), 
            state.get("mode", "capy"), 
            inv.get("maps"), nav.get("flowers"), nav.get("trees"), nav.get("totems", [])
        )
        
        text = (f"📍 <b>({px}, {py})</b> | {get_stamina_icons(stamina-5)}\n"
                f"🪓 Ви зрубали дерево! +1 🪵\n\n{map_display}")

        await callback.message.edit_text(
            text, 
            reply_markup=get_map_keyboard(px, py, state.get("mode", "capy"), False, inv, nav),
            parse_mode="HTML"
        )
        await callback.answer("Ви отримали трохи деревини! 🪵")

@router.callback_query(F.data.startswith("map_pickup_totem:"))
async def handle_pickup_totem(callback: types.CallbackQuery, db_pool):
    totem_id = callback.data.split(":")[1]
    uid = callback.from_user.id
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT navigation, inventory FROM capybaras WHERE owner_id = $1
        """, uid)
        
        if not row: return
        
        nav = json.loads(row['navigation'])
        inv = json.loads(row['inventory'])
        
        placed_totems = nav.get("totems", [])
        
        totem_to_remove = next((t for t in placed_totems if str(t['id']) == totem_id), None)
        
        if not totem_to_remove:
            return await callback.answer("Тотем не знайдено! 🤔", show_alert=True)
            
        nav["totems"] = [t for t in placed_totems if str(t['id']) != totem_id]
        
        if "loot" not in inv: inv["loot"] = {}
        inv["loot"]["teleport_totem"] = inv["loot"].get("teleport_totem", 0) + 1
        
        await conn.execute("""
            UPDATE capybaras SET navigation = $1, inventory = $2 WHERE owner_id = $3
        """, json.dumps(nav), json.dumps(inv), uid)
        
        await callback.answer("🗿 Тотем успішно повернуто в сумку!")
        
        px, py = nav.get("x"), nav.get("y")
        mode = "ship" if row.get("state") and json.loads(row["state"]).get("mode") == "ship" else "capy"
        
        await render_map(callback, db_pool)