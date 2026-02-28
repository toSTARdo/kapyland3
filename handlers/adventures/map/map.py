import json
import asyncio
import random
from aiogram import types, F, Router
from .map_assets import *
from .map_renderer import render_pov, get_stamina_icons
from .map_keyboard import get_map_keyboard, get_viewer_keyboard
from handlers.adventures.quests.quests import start_branching_quest

router = Router()

@router.callback_query(F.data == "open_map")
async def render_map(callback: types.CallbackQuery, db_pool):
    uid = callback.from_user.id
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT stamina, navigation, state, inventory 
            FROM capybaras WHERE owner_id = $1
        """, uid)
        
        if not row: return
        
        nav = json.loads(row['navigation'])
        state = json.loads(row['state'])
        inv = json.loads(row['inventory'])
        stamina = row['stamina']
        
        px, py = nav.get("x", 75), nav.get("y", 75)
        mode = state.get("mode", "capy")
        discovered = nav.get("discovered", [f"{px},{py}"])
        
        map_display = render_pov(
            px, py, discovered, mode, 
            treasure_maps=inv.get("maps", []), 
            flowers=nav.get("flowers", {}), 
            trees=nav.get("trees", {})
        )
        
        biome = get_biome_name(py)
        text = (f"📍 <b>Карта ({px}, {py})</b> | {get_stamina_icons(stamina)}\n"
                f"🧭 Біом: {biome}\n🔋 Енергія: {stamina}/100\n\n{map_display}")
        
        await callback.message.edit_text(
            text, 
            reply_markup=get_map_keyboard(px, py, mode, f"{px},{py}" in nav.get("trees", {})), 
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("mv:"))
async def handle_move(callback: types.CallbackQuery, db_pool):
    _, direction, x, y, mode = callback.data.split(":")
    x, y, uid = int(x), int(y), callback.from_user.id
    
    nx, ny = x, y
    if direction == "up": ny -= 1
    elif direction == "down": ny += 1
    elif direction == "left": nx -= 1
    elif direction == "right": nx += 1

    if not (0 <= ny < MAP_HEIGHT and 0 <= nx < MAP_WIDTH):
        return await callback.answer("Край світу! ⛔", show_alert=True)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT stamina, zen, navigation, inventory, state 
            FROM capybaras WHERE owner_id = $1
        """, uid)
        
        stamina = row['stamina']
        zen = row['zen']
        nav = json.loads(row['navigation'])
        inv = json.loads(row['inventory'])
        state = json.loads(row['state'])

        if stamina < 1:
            return await callback.answer("Енергія на нулі! ⚡", show_alert=True)

        target_tile = FULL_MAP[ny][nx]
        new_mode = mode
        if mode == "ship" and target_tile not in WATER_TILES:
            new_mode = "capy"
            await callback.answer("Висадка на берег! 🐾")
        elif mode == "capy" and target_tile in WATER_TILES:
            new_mode = "ship"
            await callback.answer("На борт! ⚓")

        disc_set = set(nav.get("discovered", []))
        new_count = 0
        for dy in range(-1, 2):
            for dx in range(-2, 3):
                sc = f"{nx+dx},{ny+dy}"
                if sc not in disc_set:
                    disc_set.add(sc)
                    new_count += 1
        
        if (len(disc_set) // 500) > (len(nav.get("discovered", [])) // 500):
            zen += 1

        coord_key = f"{nx},{ny}"
        if coord_key in COORD_QUESTS:
            nav.update({"x": nx, "y": ny, "discovered": list(disc_set)})
            state["mode"] = new_mode
            await conn.execute("""
                UPDATE capybaras SET stamina = stamina - 1, navigation = $1, state = $2 WHERE owner_id = $3
            """, json.dumps(nav), json.dumps(state), uid)
            return await start_branching_quest(callback, COORD_QUESTS[coord_key], db_pool)

        nav.update({"x": nx, "y": ny, "discovered": list(disc_set)})
        state["mode"] = new_mode
        
        await conn.execute("""
            UPDATE capybaras 
            SET stamina = stamina - 1, zen = $1, navigation = $2, state = $3 
            WHERE owner_id = $4
        """, zen, json.dumps(nav), json.dumps(state), uid)

        map_display = render_pov(nx, ny, disc_set, new_mode, inv.get("maps"), nav.get("flowers"), nav.get("trees"))
        text = (f"📍 <b>Карта ({nx}, {ny})</b> | {get_stamina_icons(stamina-1)}\n"
                f"🧭 Біом: {get_biome_name(ny)} | ✨ Дзен: {zen}\n\n{map_display}")

        await callback.message.edit_text(
            text, 
            reply_markup=get_map_keyboard(nx, ny, new_mode, coord_key in nav.get("trees", {})),
            parse_mode="HTML"
        )

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