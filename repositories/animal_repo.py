import json
from typing import Optional
from domain.base import Animal, Stats, Item
from config import MOOD_SETS


class AnimalRepository:
    def __init__(self, db_pool):
        self.pool = db_pool

    async def get_by_id(self, user_id: int) -> Optional[Animal]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT c.*, s.name as ship_name 
                FROM capybaras c
                LEFT JOIN ships s ON c.ship_id = s.id
                WHERE c.owner_id = $1
            """, user_id)
            if not row:
                return None
            
            def to_dict(val):
                if isinstance(val, dict): return val
                if isinstance(val, str):
                    try: return json.loads(val)
                    except: return {}
                return {} # Handles the [] case

            inventory = to_dict(row['inventory'])
            equipment_raw = to_dict(row['equipment'])
            state = to_dict(row['state'])
            
            equipment = {"weapon": None, "armor": None}
            for slot in ["weapon", "armor"]:
                item_data = equipment_raw.get(slot)
                if item_data and isinstance(item_data, dict):
                    equipment[slot] = Item(id=item_data.get('name', slot), **item_data)
                elif isinstance(item_data, str) and item_data not in ["Лапки", "Хутро"]:
                    equipment[slot] = Item(id=item_data, name=item_data, type=slot)

            return Animal(
                owner_id=row['owner_id'],
                name=row['name'],
                race=row.get('race', 'capybara'),
                level=row['lvl'],
                exp=row['exp'],
                weight=row['weight'],
                stats=Stats(
                    hp=row['hp'],
                    atk=row['atk'],
                    def_=row['def'],
                    agi=row['agi'],
                    luck=row['luck'],
                    stamina=row['stamina']
                ),
                state=state
                inventory=inventory, 
                equipment=equipment,  
                ship_id=row['ship_id'],
                ship_name=row['ship_name']
            )

    async def upsert(self, animal: Animal):
            async with self.pool.acquire() as conn:
                inv_json = json.dumps(animal.inventory, ensure_ascii=False)
                
                equip_data = {}
                for slot, item in animal.equipment.items():
                    if item:
                        equip_data[slot] = item.model_dump()
                    else:
                        equip_data[slot] = "Лапки" if slot == "weapon" else "Хутро"
                
                equip_json = json.dumps(equip_data, ensure_ascii=False)

                import json
from typing import Optional
from domain.base import Animal, Stats, Item
from config import MOOD_SETS


class AnimalRepository:
    def __init__(self, db_pool):
        self.pool = db_pool

    async def get_by_id(self, user_id: int) -> Optional[Animal]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT c.*, s.name as ship_name 
                FROM capybaras c
                LEFT JOIN ships s ON c.ship_id = s.id
                WHERE c.owner_id = $1
            """, user_id)
            if not row:
                return None
            
            def to_dict(val):
                if isinstance(val, dict): return val
                if isinstance(val, str):
                    try: return json.loads(val)
                    except: return {}
                return {} # Handles the [] case

            inventory = to_dict(row['inventory'])
            equipment_raw = to_dict(row['equipment'])
            state = to_dict(row['state'])
            
            equipment = {"weapon": None, "armor": None}
            for slot in ["weapon", "armor"]:
                item_data = equipment_raw.get(slot)
                if item_data and isinstance(item_data, dict):
                    equipment[slot] = Item(id=item_data.get('name', slot), **item_data)
                elif isinstance(item_data, str) and item_data not in ["Лапки", "Хутро"]:
                    equipment[slot] = Item(id=item_data, name=item_data, type=slot)

            return Animal(
                owner_id=row['owner_id'],
                name=row['name'],
                race=row.get('race', 'capybara'),
                level=row['lvl'],
                exp=row['exp'],
                weight=row['weight'],
                stats=Stats(
                    hp=row['hp'],
                    atk=row['atk'],
                    def_=row['def'],
                    agi=row['agi'],
                    luck=row['luck'],
                    stamina=row['stamina']
                ),
                state=state,
                inventory=inventory, 
                equipment=equipment,  
                ship_id=row['ship_id'],
                ship_name=row['ship_name']
            )

    async def upsert(self, animal: Animal):
            async with self.pool.acquire() as conn:
                inv_json = json.dumps(animal.inventory, ensure_ascii=False)
                
                equip_data = {}
                for slot, item in animal.equipment.items():
                    if item:
                        equip_data[slot] = item.model_dump()
                    else:
                        equip_data[slot] = "Лапки" if slot == "weapon" else "Хутро"
                
                equip_json = json.dumps(equip_data, ensure_ascii=False)

                await conn.execute("""
                    INSERT INTO capybaras (
                        owner_id, name, race, lvl, weight, hp, atk, def, agi, luck, stamina, 
                        inventory, equipment, ship_id
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    ON CONFLICT (owner_id) DO UPDATE SET
                    name = EXCLUDED.name, race = EXCLUDED.race, lvl = EXCLUDED.lvl, 
                    weight = EXCLUDED.weight, hp = EXCLUDED.hp, atk = EXCLUDED.atk, 
                    def = EXCLUDED.def, agi = EXCLUDED.agi, luck = EXCLUDED.luck, 
                    stamina = EXCLUDED.stamina, inventory = EXCLUDED.inventory, 
                    equipment = EXCLUDED.equipment, ship_id = EXCLUDED.ship_id
                """, 
                animal.owner_id, animal.name, animal.race, animal.level, animal.weight,
                animal.stats.hp, animal.stats.atk, animal.stats.def_, 
                animal.stats.agi, animal.stats.luck, animal.stats.stamina,
                inv_json, equip_json, animal.ship_id)
                
    def get_icon(self, mood: str = "chill") -> str:
            race_set = MOOD_SETS.get(self.race, MOOD_SETS["capybara"])
            return race_set.get(mood, race_set.get("chill", "₍ᐢ•(ｪ)•ᐢ₎"))