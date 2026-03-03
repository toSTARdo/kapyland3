import random
from aiogram import html
from config import WEAPON

#HELPERS
def set_val(obj, attr, val):
    setattr(obj, attr, val)
    return 0

def mod_val(obj, attr, val):
    setattr(obj, attr, max(0, getattr(obj, attr, 0) + val))
    return 0

def heal(obj, val):
    setattr(obj, 'hp', min(obj.max_hp, obj.hp + val))
    return 0

#CORE DECORATOR
def weapon_ability(base_prob):
    def decorator(func_list):
        state = {'current_idx': 0} 
        def wrapper(att, targets, round_num):
            w_data = att.weapon_data
            w_name = att.weapon.get("name", "Лапки")
            
            weapon_cfg = WEAPON.get(w_name, {})
            special_texts = weapon_cfg.get("special_text", [])
            
            rarity = weapon_cfg.get("rarity", w_data.get("rarity", "common"))
            pattern = weapon_cfg.get("pattern", w_data.get("pattern", "sequential"))
            is_aoe = weapon_cfg.get("is_aoe", w_data.get("is_aoe", False))

            lvl_bonus = att.weapon.get("lvl", 0) * 0.05
            luck_bonus = att.luck * 0.02
            chance = base_prob + luck_bonus + lvl_bonus
            
            if random.random() > chance:
                return 0, False, []

            limit = {"common": 1, "rare": 2, "epic": 4, "legendary": 6, "mythic": 6}.get(rarity, 1)
            available = func_list[:limit]
            
            if not isinstance(targets, list): 
                targets = [targets]
                
            total_dmg, logs = 0, []

            if pattern == "sequential":
                idx = state['current_idx'] % len(available)
                active_indices = [idx]
                state['current_idx'] += 1
                
            elif pattern == "chaotic":
                idx = random.randrange(len(available))
                active_indices = [idx]
                
            elif pattern == "ultimate":
                active_indices = list(range(len(available)))

            for i in active_indices:
                action = available[i]
                txt = special_texts[i] if i < len(special_texts) else "✨ Спрацював ефект зброї!"
                
                current_targets = targets if is_aoe else [random.choice(targets)]
                for t in current_targets:
                    res_val = action(att, t)
                    total_dmg += res_val if isinstance(res_val, (int, float)) else 0
                    logs.append(txt)
                    
            return total_dmg, True, logs
        return wrapper
    return decorator

ABILITY_DATA = {
    # COMMON (0.1)
    "hook_snag": (0.1, [lambda a, d: mod_val(d, 'agi', -1), lambda a, d: mod_val(a, 'agi', 1)]),
    "wooden_leg": (0.1, [lambda a, d: mod_val(d, 'atk', -1)]),
    "heavy_swing": (0.1, [lambda a, d: 1]),
    "mop_wash": (0.1, [lambda a, d: mod_val(d, 'luck', -2)]),
    "yorshik_scrub": (0.1, [lambda a, d: mod_val(d, 'def_', -1)]),

    # RARE (0.15 - 0.2)
    "entangle_debuff": (0.15, [lambda a, d: mod_val(d, 'agi', -2), lambda a, d: mod_val(d, 'atk', -1)]),
    "drunk_fury": (0.15, [lambda a, d: mod_val(a, 'atk', 1.5), lambda a, d: mod_val(a, 'def_', -1)]),
    "bleed_chance": (0.15, [lambda a, d: mod_val(a, 'luck', 1), lambda a, d: 1]),
    "precision_strike": (0.15, [lambda a, d: mod_val(d, 'def_', -1.5), lambda a, d: mod_val(a, 'luck', 1)]),
    "parry": (0.2, [lambda a, d: mod_val(a, 'def_', 1), lambda a, d: mod_val(a, 'agi', 1)]),
    "curse_mark": (0.15, [lambda a, d: set_val(d, 'luck', 0), lambda a, d: mod_val(d, 'def_', -1)]),
    "cannon_splash": (0.15, [lambda a, d: 1, lambda a, d: mod_val(d, 'agi', -1)]),

    # EPIC (0.2)
    "life_steal": (0.2, [lambda a, d: heal(a, 1), lambda a, d: mod_val(d, 'atk', -0.5), lambda a, d: mod_val(a, 'luck', 1), lambda a, d: 1]),
    "confuse_hit": (0.2, [lambda a, d: 1, lambda a, d: mod_val(d, 'luck', -2), lambda a, d: mod_val(a, 'agi', 1), lambda a, d: mod_val(d, 'def_', -1)]),
    "freeze_debuff": (0.2, [lambda a, d: mod_val(d, 'agi', -2), lambda a, d: mod_val(d, 'def_', -0.5), lambda a, d: mod_val(a, 'def_', 0.5), lambda a, d: mod_val(d, 'atk', -1)]),
    "fear_debuff": (0.2, [lambda a, d: mod_val(d, 'atk', -2), lambda a, d: mod_val(d, 'luck', -1), lambda a, d: mod_val(a, 'atk', 1), lambda a, d: mod_val(d, 'agi', -1)]),
    "energy_surge": (0.2, [lambda a, d: mod_val(a, 'agi', 2), lambda a, d: mod_val(a, 'luck', 1), lambda a, d: mod_val(a, 'atk', 1), lambda a, d: set_val(a, 'hp', max(1, a.hp - 0.5)) or 1]),
    "owl_crit": (0.2, [lambda a, d: 1.5, lambda a, d: mod_val(d, 'def_', -1), lambda a, d: mod_val(a, 'agi', 1), lambda a, d: mod_val(a, 'luck', 2)]),
    "auto_attack": (0.2, [lambda a, d: mod_val(a, 'atk', 0.5), lambda a, d: mod_val(d, 'def_', -1), lambda a, d: mod_val(a, 'def_', 1), lambda a, d: 1]),
    "rage_boost": (0.2, [lambda a, d: mod_val(a, 'atk', 0.5), lambda a, d: mod_val(a, 'luck', 0.5), lambda a, d: mod_val(d, 'atk', -0.5), lambda a, d: mod_val(a, 'def_', 1)]),
    "ghost_strike": (0.2, [lambda a, d: 1, lambda a, d: mod_val(a, 'agi', 2), lambda a, d: set_val(d, 'luck', 0), lambda a, d: heal(a, 1)]),
    "crit_5": (0.2, [lambda a, d: 2, lambda a, d: mod_val(a, 'luck', 1), lambda a, d: mod_val(d, 'agi', -1), lambda a, d: mod_val(a, 'atk', 1)]),

    # LEGENDARY (0.3 - 0.4)
    "cat_life": (0.3, [lambda a, d: heal(a, 1), lambda a, d: mod_val(a, 'agi', 1), lambda a, d: mod_val(a, 'luck', 1), lambda a, d: mod_val(d, 'luck', -1.5), lambda a, d: mod_val(d, 'agi', -1.5), lambda a, d: mod_val(a, 'atk', 1.5)]),
    "tea_mastery": (0.4, [lambda a, d: mod_val(a, 'def_', 1.0), lambda a, d: mod_val(a, 'luck', 3), lambda a, d: mod_val(d, 'agi', -2), lambda a, d: heal(a, 1), lambda a, d: mod_val(a, 'atk', 1.5), lambda a, d: 1.5]),
    "double_strike": (0.3, [lambda a, d: 1, lambda a, d: mod_val(a, 'atk', 1), lambda a, d: mod_val(a, 'agi', 1), lambda a, d: mod_val(d, 'def_', -1), lambda a, d: 1.5, lambda a, d: set_val(d, 'agi', 0)]),
    "crit_20": (0.3, [lambda a, d: mod_val(a, 'luck', 2), lambda a, d: mod_val(a, 'atk', 2), lambda a, d: mod_val(a, 'def_', 2), lambda a, d: 3, lambda a, d: set_val(a, 'hp', a.max_hp), lambda a, d: set_val(d, 'luck', 0)]),
    "pierce_armor": (0.3, [lambda a, d: set_val(d, 'def_', 0), lambda a, d: 1, lambda a, d: mod_val(a, 'atk', 1), lambda a, d: mod_val(a, 'luck', 1), lambda a, d: mod_val(d, 'atk', -1.5), lambda a, d: mod_val(d, 'agi', -1)]),
    "heavy_weight": (0.3, [lambda a, d: mod_val(a, 'agi', -1), lambda a, d: mod_val(a, 'atk', 2.5), lambda a, d: mod_val(a, 'def_', 2), lambda a, d: mod_val(d, 'def_', -1.5), lambda a, d: 2, lambda a, d: mod_val(a, 'luck', 1)]),
    "range_attack": (0.3, [lambda a, d: mod_val(a, 'luck', 2), lambda a, d: mod_val(a, 'agi', 2), lambda a, d: mod_val(d, 'agi', -1.5), lambda a, d: mod_val(d, 'atk', -1), lambda a, d: mod_val(a, 'atk', 1.5), lambda a, d: mod_val(d, 'def_', -1.5)]),
    "stun_chance": (0.3, [lambda a, d: set_val(d, 'agi', 0), lambda a, d: mod_val(d, 'atk', -1), lambda a, d: mod_val(d, 'def_', -2), lambda a, d: mod_val(a, 'luck', 1), lambda a, d: 1.5, lambda a, d: mod_val(a, 'def_', 1.5)]),
    "latex_choke": (0.3, [lambda a, d: mod_val(d, 'atk', -2), lambda a, d: mod_val(d, 'agi', -2), lambda a, d: set_val(d, 'luck', 0), lambda a, d: mod_val(a, 'luck', 2), lambda a, d: set_val(d, 'def_', 0), lambda a, d: 1]),
    "scissor_sever": (0.3, [lambda a, d: mod_val(d, 'def_', -3), lambda a, d: mod_val(a, 'agi', 2), lambda a, d: 2, lambda a, d: mod_val(d, 'atk', -1), lambda a, d: mod_val(a, 'luck', 1), lambda a, d: set_val(d, 'def_', 0)]),
    "gaulish_might": (0.3, [lambda a, d: mod_val(a, 'atk', 2), lambda a, d: mod_val(a, 'def_', 2), lambda a, d: mod_val(d, 'agi', -1.5), lambda a, d: 1.5, lambda a, d: heal(a, 1), lambda a, d: mod_val(d, 'def_', -1)]),
    "getsuga_tensho": (0.3, [lambda a, d: mod_val(a, 'agi', 3), lambda a, d: 1, lambda a, d: mod_val(d, 'def_', -2), lambda a, d: mod_val(a, 'luck', 2), lambda a, d: mod_val(d, 'atk', -1), lambda a, d: 2]),

    # MYTHIC (0.25 - 0.5)
    "odin_spear": (0.4, [lambda a, d: mod_val(a, 'def_', 3), lambda a, d: 2, lambda a, d: heal(a, 2), lambda a, d: 2, lambda a, d: mod_val(d, 'agi', -2), lambda a, d: mod_val(a, 'luck', 2)]),
    "vampire_drill": (0.35, [lambda a, d: set_val(d, 'def_', 0), lambda a, d: heal(a, d.max_hp * 0.1), lambda a, d: 1.5, lambda a, d: mod_val(a, 'atk', 1), lambda a, d: mod_val(d, 'atk', -1)]),
    "panther_hide": (0.45, [lambda a, d: mod_val(a, 'agi', 4), lambda a, d: set_val(a, 'max_hp', a.max_hp + 5) or heal(a, 5), lambda a, d: mod_val(a, 'luck', 3), lambda a, d: 1, lambda a, d: set_val(d, 'luck', 0)]),
    "ea_sword": (0.3, [lambda a, d: 3, lambda a, d: set_val(d, 'def_', 0) or set_val(d, 'agi', 0), lambda a, d: mod_val(a, 'atk', 2), lambda a, d: heal(a, a.max_hp)]),
    "yin_yang_staff": (0.5, [lambda a, d: mod_val(a, 'atk', 5) or mod_val(a, 'def_', -2), lambda a, d: mod_val(a, 'def_', 5) or mod_val(a, 'atk', -2), lambda a, d: set_val(d, 'hp', max(1, d.hp // 2)), lambda a, d: set_val(a, 'luck', 10)]),
    "student_lunch": (0.25, [lambda a, d: set_val(a, 'hp', 1), lambda a, d: 10, lambda a, d: mod_val(a, 'luck', 5), lambda a, d: set_val(d, 'agi', 0)]),
    "spas_axe": (0.4, [lambda a, d: mod_val(a, 'agi', 5) or mod_val(a, 'atk', 3), lambda a, d: set_val(a, 'def_', 99), lambda a, d: 2, lambda a, d: heal(a, 3), lambda a, d: set_val(d, 'luck', 0)]),
    "ancestor_spirit": (0.4, [lambda a, d: 1.5, lambda a, d: mod_val(a, 'def_', 2), lambda a, d: mod_val(a, 'agi', 2), lambda a, d: mod_val(a, 'atk', 2), lambda a, d: heal(a, 1)])
}

ABILITY_REGISTRY = {
    name: weapon_ability(prob)(funcs) 
    for name, (prob, funcs) in ABILITY_DATA.items()
}
ABILITY_REGISTRY["none"] = lambda a, t, r: (0, False, [])