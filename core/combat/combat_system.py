import random
from aiogram import html
from config import UNITS_PER_HEART, BASE_HEARTS, BASE_HIT_CHANCE, STAT_WEIGHTS, BASE_BLOCK_CHANCE

from core.combat.special_abilities import ABILITY_REGISTRY 

class Fighter:
    def __init__(self, capy: dict, config_data: dict, color: str = "🔸"):
        self.name = capy.get("kapy_name", "Капібара")
        self.weight = float(capy.get("weight", 20.0))
        self.color = color
        
        stats = capy.get("stats", {})
        self.atk = stats.get("attack", 0)
        self.def_ = stats.get("defense", 0)
        self.agi = stats.get("agility", 0)
        self.luck = stats.get("luck", 0)

        self.w_name = capy.get("equipped_weapon", "Лапки")
        self.a_name = capy.get("equipped_armor", "Хутро")
        
        self.weapon_data = config_data["WEAPONS"].get(self.w_name, {
            "texts": ["вдаряє лапками {defen}"], "hit_bonus": 0, "power": 1
        })
        self.armor_data = config_data["ARMOR"].get(self.a_name, {
            "text": "отримала удар", "defense": 0
        })

        inventory = capy.get("inventory", {})
        storage = inventory.get("equipment", [])
        
        has_cat_life = any(item.get("name") == "Котяче життя" for item in storage)
        
        extra_hp = 2 if has_cat_life else 0
        self.max_hp = (BASE_HEARTS * UNITS_PER_HEART) + extra_hp
        self.hp = self.max_hp

    def get_hp_display(self) -> str:
        display = ""
        temp_hp = self.hp
        total_hearts = self.max_hp // UNITS_PER_HEART
        
        for _ in range(total_hearts):
            if temp_hp >= 2:
                display += "❤️"
                temp_hp -= 2
            elif temp_hp == 1:
                display += "💔"
                temp_hp -= 1
            else:
                display += "🖤"
        return f"{display} ({self.hp}/{self.max_hp})"

    def get_hit_chance(self) -> float:
        chance = BASE_HIT_CHANCE + (self.atk * STAT_WEIGHTS["atk_to_hit"]) + self.weapon_data.get("hit_bonus", 0)
        return chance

    def get_dodge_chance(self) -> float:
        base_dodge = self.agi * STAT_WEIGHTS["agi_to_dodge"]
        weight_penalty = max(0, (self.weight - 20) / 5) * 0.01
        chance = base_dodge - weight_penalty
        return max(0.02, chance)

    def get_block_chance(self) -> float:
        return BASE_BLOCK_CHANCE + (self.def_ * STAT_WEIGHTS["def_to_block"]) + self.armor_data.get("defense", 0)


class CombatEngine:
    @staticmethod
    def resolve_turn(att: Fighter, defe: Fighter, round_num: int) -> str:
        if random.random() > att.get_hit_chance():
            return f"💨 {att.color} {html.bold(att.name)} промахнувся!"

        if random.random() < defe.get_dodge_chance():
            return f"⚡ {html.bold(defe.name)} спритно ухилився від атаки!"

        if random.random() < defe.get_block_chance():
            armor_msg = defe.armor_data.get("text", "заблокував удар")
            return f"🔰 {html.bold(defe.name)} {armor_msg}!"

        base_damage = 1
        crit_bonus = 0
        crit_text = ""
        
        if random.random() < (att.luck * 0.05):
            crit_bonus = 1
            crit_text = "💥 "

        ability_damage = 0
        ability_logs = []
        special_key = att.weapon_data.get("special")
        
        if special_key in ABILITY_REGISTRY:
            res_dmg, is_active, logs = ABILITY_REGISTRY[special_key](att, defe, round_num)
            
            if is_active:
                ability_damage = res_dmg
                ability_logs = logs

        total_damage = base_damage + crit_bonus + ability_damage
        total_damage = round(total_damage, 1) 
        
        defe.hp = max(0, round(defe.hp - total_damage, 1))
        
        raw_text = random.choice(att.weapon_data["texts"])
        attack_verb = raw_text.replace("{defen}", html.bold(defe.name))
        
        msg = (f"{crit_text}{att.color} {html.bold(att.name)} {attack_verb}!\n"
               f"➔ Шкода: {html.bold('-' + str(total_damage) + ' HP')}")
        
        if ability_logs:
            special_msg = "\n" + "\n".join(ability_logs)
            msg += f"\n<i>{special_msg}</i>"

        return msg