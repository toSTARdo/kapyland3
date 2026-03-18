from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

# --- Stats ---
class Stats(BaseModel):
    hp: int = 10
    max_hp: int = 10
    atk: int = 1
    def_: int = Field(0, alias="def")
    agi: int = 1
    luck: int = 0
    stamina: int = 100

# --- Items ---
class Item(BaseModel):
    id: str = "unknown"
    name: str = "Strange item"
    type: str = "item" # Provide a default
    rarity: str = "Common"
    lvl: int = 0
    bonus_atk: int = 0
    bonus_def: int = 0
    description: str = "What is it?"
    count: int = 1
    desc: str = "Предмет"

# --- Animal ---
class Animal(BaseModel):
    owner_id: int
    name: str = "Безіменна булочка"
    race: str = "capybara"
    level: int = 1
    exp: int = 0
    weight: float = 20.0
    stats: Stats
    hunger: int = 3
    state:  Dict[str, Any] 
    cleanness: int = 3
    
    # FIXED: Using default_factory to prevent shared memory issues
    inventory: Dict[str, Dict[str, Any]] = Field(default_factory=lambda: {
        "equipment": {},      # Keys: "Name_Lvl" -> Dict
        "loot": {},           # Keys: "item_id" -> count (int)
        "food": {},           # Keys: "item_id" -> count (int)
        "treasure_maps": {},
        "potions": {},
        "materials": {}
    })
    
    # Active slots for stats calculation
    equipment: Dict[str, Optional[Item]] = Field(default_factory=lambda: {
        "weapon": None, 
        "armor": None,
        "artifact": None
    })
    
    ship_id: Optional[int] = None
    ship_name: Optional[str] = None

    def add_item(self, item: Item, category: str = "equipment"):
        """
        Handles adding items to the dictionary inventory.
        Automatically stacks or creates new entries.
        """
        cat_dict = self.inventory.setdefault(category, {})
        
        if category == "equipment":
            # Key format: Sword_0
            item_key = f"{item.name}_{item.lvl}"
            if item_key in cat_dict:
                cat_dict[item_key]["count"] += item.count
            else:
                cat_dict[item_key] = item.model_dump()
        else:
            # Simple stacking for loot/food/materials (id -> count)
            cat_dict[item.id] = cat_dict.get(item.id, 0) + item.count

    @classmethod
    def create_starter(cls, owner_id: int, race: str):
        races = {
            "capybara": Stats(hp=4, atk=0, agi=0, def_=10, luck=0),
            "racoon":   Stats(hp=3, atk=10, agi=0, def_=0, luck=0),
            "cat":      Stats(hp=3, atk=0, agi=0, def_=0, luck=10),
            "bat":      Stats(hp=2, atk=0, agi=10, def_=0, luck=0)
        }
        return cls(
            owner_id=owner_id,
            race=race,
            stats=races.get(race, races["capybara"])
        )

# --- Narrative ---
class QuestType(str, Enum):
    MAIN = "main"
    SIDE = "side"
    EVENT = "event"

class Choice(BaseModel):
    text: str
    next_node_id: str
    requirements: Dict[str, Any] = {}
    rewards: Dict[str, Any] = {}

class QuestNode(BaseModel):
    id: str
    quest_id: str
    text: str
    choices: List[Choice]
    status: Optional[str] = None # "dead", "win"
    title: Optional[str] = None

class QuestProgress(BaseModel):
    user_id: int
    quest_id: str
    quest_type: QuestType
    current_node_id: str
    is_completed: bool = False
