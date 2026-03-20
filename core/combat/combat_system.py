import random
import math
from aiogram import html
from uuid import uuid4
# Припускаємо, що ці константи є в config
from config import UNITS_PER_HEART, BASE_HEARTS, BASE_HIT_CHANCE, STAT_WEIGHTS, BASE_BLOCK_CHANCE
from core.combat.special_abilities import ABILITY_REGISTRY 

class Fighter:
    def __init__(self, capy: dict, config_data: dict, color: str = "🔸"):
        self.name = capy.get("kapy_name", "Капібара")
        self.weight = float(capy.get("weight", 20.0))
        self.color = color
        self.race = capy.get("race", "capybara") 
        
        stats = capy.get("stats", {})
        self.sting_effect = capy.get("state", {}).get("has_sting_effect", False)
        self.lvl = capy.get("lvl", 0)
        self.atk = stats.get("attack", 0)
        self.def_ = stats.get("defense", 0)
        self.agi = stats.get("agility", 0)
        self.luck = stats.get("luck", 0)

        self.weapon = capy.get("weapon_full", {"name": "Лапки", "lvl": 0})
        self.armor = capy.get("armor_full", {"name": "Хутро", "lvl": 0})
        
        w_name = self.weapon.get("name", "Лапки")
        a_name = self.armor.get("name", "Хутро")
        
        self.weapon_data = config_data["WEAPONS"].get(w_name, {
            "texts": ["вдаряє лапками {defen}"], "hit_bonus": 0, "power": 1
        })
        self.armor_data = config_data["ARMOR"].get(a_name, {
            "text": "отримала удар", "defense": 0
        })

        self._ability_state = {}
        # Додаємо рівні до захисту
        self.def_ += self.weapon.get("lvl", 0)
        self.def_ += self.armor.get("lvl", 0)

        self.cat_reflex_active = False
        self.capy_zen_rounds = 0

        inventory = capy.get("inventory", {})
        eq_dict = inventory.get("equipment", {})
        has_cat_life = any(item.get("name") == "Котяче життя" for item in eq_dict.values())

        loot = inventory.get("loot", {})
        self.has_lachryma = int(loot.get("lachryma", 0)) > 0

        extra_hp = 2 if has_cat_life else 0
        self.max_hp = (capy.get("max_hp", 3) * UNITS_PER_HEART) + extra_hp
        self.hp = self.max_hp
        self.adrenaline_active = False

    def update_adrenaline(self) -> str:
        if self.adrenaline_active or self.hp <= 0:
            return ""
        if 0 < self.hp <= 2:
            bonus_chance = 0.2 if self.sting_effect else 0
            chance = 0.05 + (self.lvl * 0.01) + bonus_chance
            if random.random() < min(0.60, chance):
                self.adrenaline_active = True
                return f"\n❤️‍🔥 {html.bold(self.name)}: Адреналінове серце активоване!"
        return ""

    def get_hit_chance(self) -> float:
        # Базовий шанс влучання
        chance = BASE_HIT_CHANCE + (self.atk * STAT_WEIGHTS["atk_to_hit"]) + self.weapon_data.get("hit_bonus", 0)
        if self.adrenaline_active: chance *= 1.5
        return max(0.3, min(0.95, chance))

    def get_dodge_chance(self) -> float:
        base_dodge = self.agi * STAT_WEIGHTS["agi_to_dodge"]
        weight_penalty = max(0, (self.weight - 20) / 20) * 0.01
        chance = base_dodge - weight_penalty
        if self.adrenaline_active: chance *= 1.5
        return max(0.02, min(0.7, chance))

    def get_block_chance(self) -> float:
        base_block = BASE_BLOCK_CHANCE + (self.def_ * STAT_WEIGHTS["def_to_block"]) + self.armor_data.get("defense", 0)
        if self.capy_zen_rounds > 0 and self.color in ["🟢", "🔴"]:
            base_block += 0.15 
        return max(0.05, min(0.8, base_block))

    def get_hp_display(self) -> str:
        total_hearts = self.max_hp // UNITS_PER_HEART
        temp_hp = self.hp
        display = "" if total_hearts < 5 else "\n"
        for i in range(1, total_hearts + 1):
            if temp_hp >= 2:
                display += "❤️‍🔥" if self.adrenaline_active else "❤️"
                temp_hp -= 2
            elif temp_hp == 1:
                display += "💔"; temp_hp -= 1
            else:
                display += "🖤"
            if i % 5 == 0 and i != total_hearts: display += "\n"
        return f"{display}\n({self.hp}/{self.max_hp})"

class CombatEngine:
    @staticmethod
    def get_linear_slope(s: float) -> float:
        r = random.random()
        if abs(s) < 1e-6:
            return r
        return (math.sqrt(max(0, (1 - s)**2 + 4 * s * r)) - (1 - s)) / (2 * s)

    @staticmethod
    def resolve_turn(att: Fighter, defe: Fighter, round_num: int) -> str:
        if att.capy_zen_rounds > 0: att.capy_zen_rounds -= 1
        
        adren_notif = att.update_adrenaline() + defe.update_adrenaline()
        race_logs = []

        current_block_chance = defe.get_block_chance()
        if att.race == "bat" and (random.random() < 0.6 or att.has_lachryma):
            current_block_chance *= 0.5
            race_logs.append(f"🔊 {html.bold(att.name)} оминає захист ворога!")
        
        if random.random() < defe.get_dodge_chance():
            if defe.race == "cat":
                defe.cat_reflex_active = True
                race_logs.append(f"🐾 {html.bold(defe.name)} готує контрудар!")
            return f"⚡ {html.bold(defe.name)} спритно ухилився!{adren_notif}\n<i>{chr(10).join(race_logs)}</i>"

        base_chance = 0.50
        bonus_points = (att.atk) + (att.weapon_data.get("hit_bonus", 0) * 100) + (att.weapon.get("lvl", 0))

        if random.random() < s:
            if random.random() < current_block_chance:
                armor_msg = defe.armor_data.get("text", "заблокував удар")
                return f"🔰 {html.bold(defe.name)} {armor_msg}!{adren_notif}"

            final_dmg = 1.0
            
            current_luck = att.luck
            if att.race == "raccoon" and att.hp < defe.hp:
                current_luck *= 2 if not att.has_lachryma else 4
                race_logs.append(f"🎰 Азарт єнота!")

            crit_chance = current_luck * STAT_WEIGHTS["luck_to_crit"]
            if att.cat_reflex_active:
                crit_chance += 0.20
                att.cat_reflex_active = False

            crit_text = ""
            if random.random() < crit_chance:
                final_dmg += 1.0
                crit_text = "💥 "

            special_key = att.weapon_data.get("special")
            if special_key in ABILITY_REGISTRY:
                res_dmg, is_active, logs = ABILITY_REGISTRY[special_key](att, defe, round_num)
                if is_active:
                    final_dmg += res_dmg
                    race_logs.extend(logs)

            defe.hp = max(0.0, round(defe.hp - final_dmg, 1))

            raw_text = random.choice(att.weapon_data["texts"])
            attack_verb = raw_text.replace("{defen}", html.bold(defe.name))
            prefix = "❤️‍🔥 " if att.adrenaline_active else ""
            
            capy_notif = ""
            if defe.race == "capybara" and final_dmg > 0:
                if random.random() < 0.25 or defe.has_lachryma:
                    defe.capy_zen_rounds = 2
                    capy_notif = f"\n🪷 {html.bold(defe.name)} зловив дзен!"

            msg = (f"{prefix}{crit_text}{att.color} {html.bold(att.name)} {attack_verb}!\n"
                   f"➔ Шкода: {html.bold('-' + str(final_dmg) + ' HP')}")
            
            if race_logs: msg += f"\n<i>{chr(10).join(race_logs)}</i>"
            return msg + capy_notif + adren_notif

        return f"💨 {att.color} {html.bold(att.name)} промахнувся!{adren_notif}"