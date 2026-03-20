import random
from aiogram import html
import math
from uuid import uuid4
from config import UNITS_PER_HEART, BASE_HEARTS, BASE_HIT_CHANCE, STAT_WEIGHTS, BASE_BLOCK_CHANCE
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
        self.def_ += self.weapon.get("lvl", 0)
        self.def_ += self.armor.get("lvl", 0)

        # Race specific tracking
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
        chance = get_linear_slope(self.atk + self.weapon_data.get("hit_bonus", 0)*100 + self.weapon.get("lvl", 0))
        #chance = BASE_HIT_CHANCE + (self.atk * STAT_WEIGHTS["atk_to_hit"]) + self.weapon_data.get("hit_bonus", 0)
        print(f"{chance} | from weapon: {self.weapon_data.get("hit_bonus", 0)}")
        if self.adrenaline_active: chance *= 2.0
        return chance

    def get_dodge_chance(self) -> float:
        base_dodge = self.agi * STAT_WEIGHTS["agi_to_dodge"]
        weight_penalty = max(0, (self.weight - 20) / 20) * 0.01
        chance = base_dodge - weight_penalty
        if self.adrenaline_active: chance *= 2.0
        return max(0.02, chance)

    def get_block_chance(self) -> float:
        base_block = BASE_BLOCK_CHANCE + (self.def_ * STAT_WEIGHTS["def_to_block"]) + self.armor_data.get("defense", 0)
        if self.capy_zen_rounds > 0 and self.color in ["🟢", "🔴"]:
            base_block += 0.15 # 15% bonus block for Zen Capybara
        return base_block

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
        race_logs = [] # To store messages about race abilities working

        # 1. Bat Passive: Sonar
        current_block_chance = defe.get_block_chance()
        if att.race == "bat" and (random.random() < 0.6 or att.has_lachryma):
            current_block_chance *= 0.5
            race_logs.append(f"🔊 {html.bold(att.name)} оминає захист ворога!")
            # We don't log this every time to avoid spam, or log only on successful pierce
        
        # 2. Resolve Dodge
        if random.random() < defe.get_dodge_chance():
            if defe.race == "cat":
                defe.cat_reflex_active = True
                race_logs.append(f"🐾 {html.bold(defe.name)} готує контрудар!")
            return f"⚡ {html.bold(defe.name)} спритно ухилився!{adren_notif}\n<i>{chr(10).join(race_logs)}</i>"

        # 3. Resolve Hit
        if random.random() > att.get_hit_chance():
            return f"💨 {att.color} {html.bold(att.name)} промахнувся!{adren_notif}"

        # 4. Resolve Block
        if random.random() < current_block_chance:
            armor_msg = defe.armor_data.get("text", "заблокував удар")
            return f"🔰 {html.bold(defe.name)} {armor_msg}!{adren_notif}"

        # 5. Damage Calculation
        base_damage = 1
        
        # Raccoon Passive: Trash Luck
        current_luck = att.luck
        if att.race == "raccoon" and att.hp < defe.hp:
            current_luck *= 2 if not att.has_lachryma else 4
            race_logs.append(f"🎰 {html.bold(att.name)} відчуває азарт погоні!")

        # Cat Passive: Counter-crit
        crit_chance = current_luck * STAT_WEIGHTS["luck_to_crit"]
        if att.cat_reflex_active:
            crit_chance += 0.20 if not att.has_lachryma else 0.40
            att.cat_reflex_active = False
            race_logs.append(f"🐱 Котячі рефлекси спрацювали!")

        crit_bonus = 1 if random.random() < crit_chance else 0
        crit_text = "💥 " if crit_bonus > 0 else ""

        # Special Abilities
        ability_damage = 0
        ability_logs = []
        special_key = att.weapon_data.get("special")
        if special_key in ABILITY_REGISTRY:
            res_dmg, is_active, logs = ABILITY_REGISTRY[special_key](att, defe, round_num)
            if is_active:
                ability_damage = res_dmg
                ability_logs = logs

        total_damage = round(base_damage + crit_bonus + ability_damage, 1)
        defe.hp = max(0, round(defe.hp - total_damage, 1))

        # 6. Capybara Passive: Zen
        capy_notif = ""
        if defe.race == "capybara" and total_damage > 0:
            if random.random() < 0.25 or defe.has_lachryma:
                defe.capy_zen_rounds = 2
                capy_notif = f"\n🪷 {html.bold(defe.name)} зловив дзен (Блок +15%)!"

        raw_text = random.choice(att.weapon_data["texts"])
        attack_verb = raw_text.replace("{defen}", html.bold(defe.name))
        
        prefix = "❤️‍🔥 " if att.adrenaline_active else ""
        msg = (f"{prefix}{crit_text}{att.color} {html.bold(att.name)} {attack_verb}!\n"
               f"➔ Шкода: {html.bold('-' + str(total_damage) + ' HP')}")
        
        # Combine all additional logs
        all_extra = []
        if race_logs: all_extra.extend(race_logs)
        if ability_logs: all_extra.extend(ability_logs)
        
        if all_extra:
            msg += f"\n<i>{chr(10).join(all_extra)}</i>"

        return msg + capy_notif + adren_notif