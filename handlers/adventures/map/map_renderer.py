from .map_assets import MAP_WIDTH, MAP_HEIGHT, FOREST_TILES, FOG_ICON, get_biome_name
from config import FULL_MAP, PLAYER_ICON, SHIP_ICON

def get_stamina_icons(stamina):
    if stamina > 66: return "⚡⚡⚡"
    if stamina > 33: return "⚡⚡ ●"
    if stamina > 0: return "⚡ ● ●"
    return " ● ● ●"

def render_pov(px, py, discovered_list, mode="capy", treasure_maps=None, flowers=None, trees=None, totems=None):
    win_w, win_h = 15, 8
    icon = SHIP_ICON if mode == "ship" else PLAYER_ICON
    
    start_x = max(0, min(MAP_WIDTH - win_w, px - win_w // 2))
    start_y = max(0, min(MAP_HEIGHT - win_h, py - win_h // 2))
    
    discovered_set = set(discovered_list)
    
    totem_coords = {f"{t['x']},{t['y']}" for t in totems} if totems else set()

    current_biome = get_biome_name(py)
    is_snowy_biome = current_biome['id'] == 3
    
    boss_coords = set()
    treasure_coords = set()
    tomb_coords = set()

    if treasure_maps:
        for m in treasure_maps:
            pos = m.get('pos')
            m_type = m.get("type")
            if not pos: continue
            
            if m_type == "boss_den":
                boss_coords.add(pos)
            elif m_type == "tomb":
                tomb_coords.add(pos)
            else:
                treasure_coords.add(pos)
                
    flower_coords = flowers if flowers else {}
    tree_coords = trees if trees else {}
    
    rows = ["═" * win_w]
    
    for y in range(start_y, start_y + win_h):
        display_row = []
        for x in range(start_x, start_x + win_w):
            c_str = f"{x},{y}"
            
            if x == px and y == py:
                display_row.append(icon)
            
            elif c_str not in discovered_set:
                display_row.append(FOG_ICON)
            
            elif c_str in tomb_coords:
                display_row.append("♰")
            elif c_str in totem_coords:
                display_row.append("☥")
            elif c_str in boss_coords:
                display_row.append("𖤍")
            elif c_str in flower_coords:
                display_row.append(flower_coords[c_str])
            elif c_str in tree_coords:
                display_row.append(tree_coords[c_str])
            elif c_str in treasure_coords:
                display_row.append("X")
                
            else:
                tile = FULL_MAP[y][x]
                
                if is_snowy_biome and tile not in FOREST_TILES:
                    snow_seed = hash(f"{x}_{y}_{px}_{py}")
                    if (snow_seed % 12) == 0:
                        display_row.append("❅")
                        continue

                if tile in FOREST_TILES and c_str not in tree_coords:
                    display_row.append("𖧧")
                else:
                    display_row.append(tile)
                    
        rows.append("".join(display_row))
    
    rows.append("═" * win_w)
    return "\n".join(rows)

def render_world_viewer(view_x, view_y, discovered_list, win_w, win_h):
    # Центруємо вікно, не виходячи за межі карти
    start_x = max(0, min(MAP_WIDTH - win_w, view_x - win_w // 2))
    start_y = max(0, min(MAP_HEIGHT - win_h, view_y - win_h // 2))
    
    discovered_set = set(discovered_list)
    # Динамічна рамка під розмір вікна
    border = "═" * win_w
    rows = [f"🌐 <b>Огляд світу ({view_x}, {view_y})</b>", border]
    
    for y in range(start_y, start_y + win_h):
        line = []
        for x in range(start_x, start_x + win_w):
            c_str = f"{x},{y}"
            if x == view_x and y == view_y:
                line.append("📍") # Маркер фокусу
            elif c_str in discovered_set:
                line.append(FULL_MAP[y][x])
            else:
                line.append(FOG_ICON)
        rows.append("".join(line))
    
    rows.append(border)
    return "\n".join(rows)
