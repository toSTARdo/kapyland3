import random
from aiogram import html
import math
from uuid import uuid4
from config import UNITS_PER_HEART, STAT_WEIGHTS, BASE_BLOCK_CHANCE
from core.combat.special_abilities import ABILITY_REGISTRY 

def get_linear_slope(s: float) -> float:
    r = random.random()
    if abs(s) < 1e-6:
        return r
    return (math.sqrt(max(0, (1 - s)**2 + 4 * s * r)) - (1 - s)) / (2 * s)

class Fighter:
    def __init__(self, capy: dict, config_data: dict, color: str = "🔸"):
        self.name = capy.get("kapy_name", "Капібара")
        self.weight = float(capy.get("weight", 20.0))
        self.color = color
        self.race = capy.get("race", "capybara") 
        
        stats = capy.get("stats", {})
        self.lvl = capy.get("lvl", 0)
        self.atk = stats.get("attack", 0)
        self.def_ = stats.get("defense", 0)
        self.agi = stats.get("agility", 0)
        self.luck = stats.get("luck", 0)

        self.weapon = capy.get("weapon_full", {"name": "Лапки", "lvl": 0})
        self.armor = capy.get("armor_full", {"name": "Хутро", "lvl": 0})
        
        w_name = self.weapon.get("name", "Лапки")
        a_name = self.armor.get("name", "Хутро")
        self.weapon_data = config_data["WEAPONS"].get(w_name, {"texts": ["б'є {defen}"], "hit_bonus": 0, "power": 1})
        self.armor_data = config_data["ARMOR"].get(a_name, {"text": "заблокувала", "defense": 0})

        self.total_def = self.def_ + self.weapon.get("lvl", 0) + self.armor.get("lvl", 0)
        
        self.cat_reflex_active = False
        self.capy_zen_rounds = 0
        self.adrenaline_active = False
        self.has_lachryma = int(capy.get("inventory", {}).get("loot", {}).get("lachryma", 0)) > 0

        has_cat_life = any(item.get("name") == "Котяче життя" for item in capy.get("inventory", {}).get("equipment", {}).values())
        self.max_hp = (capy.get("max_hp", 3) * UNITS_PER_HEART) + (2 if has_cat_life else 0)
        self.hp = self.max_hp

    def get_hit_roll(self) -> float:
        s = (self.atk * 0.1) + (self.weapon_data.get("hit_bonus", 0) * 0.4) * (1 + self.weapon_data.get("lvl", 0) * 0.3)
        roll = get_linear_slope(s)
        return roll * 1.5 if self.adrenaline_active else roll

    def get_dodge_roll(self) -> float:
        weight_penalty = max(0.5, 1.0 - (self.weight - 20) / 100)
        s = (self.agi * 0.15) * weight_penalty
        roll = get_linear_slope(s)
        return roll * 1.5 if self.adrenaline_active else roll

    def get_block_roll(self) -> float:
        s = (self.total_def * 0.1) + (self.armor_data.get("defense", 0) * 0.5)
        # RACE EFFECT: Capybara Zen (Temporary massive block boost)
        if self.capy_zen_rounds > 0: s += 2.0 
        return get_linear_slope(s)

    def get_luck_roll(self) -> float:
        s = (self.luck * 0.2)
        # RACE EFFECT: Cat Reflex (Dodging an attack sets a flag that significantly biases the luck slope for a counter-crit)
        if self.cat_reflex_active: s += 3.0 
        return get_linear_slope(s)

    def update_adrenaline(self) -> str:
        if self.adrenaline_active or self.hp <= 0: return ""
        if 0 < self.hp <= 2:
            chance = 0.05 + (self.lvl * 0.01)
            if random.random() < min(0.60, chance):
                self.adrenaline_active = True
                return f"\n❤️‍🔥 {html.bold(self.name)}: Адреналінове серце!"
        return ""

    def get_hp_display(self) -> str:
        temp_hp = self.hp
        total_hearts = self.max_hp // UNITS_PER_HEART
        display = "" if total_hearts < 5 else "\n"

        for i in range(1, total_hearts + 1):
            if temp_hp >= 2:
                display += "❤️‍🔥" if self.adrenaline_active else "❤️"
                temp_hp -= 2
            elif temp_hp == 1:
                display += "💔"
                temp_hp -= 1
            else:
                display += "🖤"    

            if i % 5 == 0 and i != total_hearts:
                display += "\n"
       

        return f"{display}\n({self.hp}/{self.max_hp})" 

class CombatEngine:
    @staticmethod
    def resolve_turn(att: Fighter, defe: Fighter, round_num: int) -> str:
        if att.capy_zen_rounds > 0: att.capy_zen_rounds -= 1
        adren_notif = att.update_adrenaline() + defe.update_adrenaline()
        race_logs = []

        # RACE EFFECT: Bat Sonar (Passive chance to halve defender's block chance by piercing defense)
        current_block_threshold = 0.75
        if att.race == "bat" and (random.random() < 0.6 or att.has_lachryma):
            current_block_threshold = 0.90
            race_logs.append("🔊 Сонар оминає захист!")

        if defe.get_dodge_roll() > att.get_hit_roll():
            # RACE EFFECT: Cat Reflex Activation (Successful dodge triggers the reflexive state for next turn)
            if defe.race == "cat":
                defe.cat_reflex_active = True
                race_logs.append("🐾 Готує контрудар!")
            return f"⚡ {html.bold(defe.name)} ухилився!{adren_notif}\n<i>{' '.join(race_logs)}</i>"

        if defe.get_block_roll() > current_block_threshold:
            armor_msg = defe.armor_data.get("text", "заблокував")
            return f"🔰 {html.bold(defe.name)} {armor_msg}!{adren_notif}"

        ability_damage = 0
        ability_logs = []
        special_key = att.weapon_data.get("special")
        if special_key in ABILITY_REGISTRY:
            res_dmg, is_active, logs = ABILITY_REGISTRY[special_key](att, defe, round_num)
            if is_active:
                ability_damage = res_dmg
                ability_logs = logs

        is_crit = att.get_luck_roll() > 0.8
        crit_bonus = 1 if is_crit else 0
        crit_text = "💥 " if is_crit else ""
        
        #if att.race == "raccoon" and att.hp < defe.hp and att.get_luck_roll() > 0.8:
        #    ability_damage += 1
        #    race_logs.append("🎰 Удача єнота!")

        base_damage = 1
        total_damage = round(base_damage + crit_bonus + ability_damage, 0)
    

        defe.hp = max(0, round(defe.hp - total_damage, 1))

        # RACE EFFECT: Capybara Zen Activation (Taking damage has a chance to trigger a 2-round defensive state)
        capy_notif = ""
        if defe.race == "capybara" and total_damage > 0:
            if random.random() < 0.25 or defe.has_lachryma:
                defe.capy_zen_rounds = 2
                capy_notif = f"\n🪷 {html.bold(defe.name)} зловив дзен!"

        if att.cat_reflex_active: att.cat_reflex_active = False

        raw_text = random.choice(att.weapon_data["texts"])
        attack_verb = raw_text.replace("{defen}", html.bold(defe.name))
        prefix = "❤️‍🔥 " if att.adrenaline_active else ""
        
        res = (f"{prefix}{crit_text}{att.color} {html.bold(att.name)} {attack_verb}!\n"
               f"➔ Шкода: {html.bold('-' + str(total_damage) + ' HP')}")
        
        all_extra = race_logs + ability_logs
        if all_extra:
            res += f"\n<i>{chr(10).join(all_extra)}</i>"

        return res + capy_notif + adren_notif