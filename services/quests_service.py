from repositories.animal_repo import AnimalRepository
from repositories.quests_repo import QuestRepository
from domain.base import QuestNode, QuestProgress, QuestType, Animal
from typing import Optional, Tuple

class QuestService:
    def __init__(self, animal_repo: AnimalRepository, quest_repo: QuestRepository):
        self.repo = animal_repo
        self.quest_repo = quest_repo

    async def start_quest(self, user_id: int, quest_id: str, q_type: QuestType = QuestType.SIDE):
        """Починає новий квест для гравця"""
        progress = await self.quest_repo.get_progress(user_id, quest_id)
        if progress:
            return progress

        new_progress = QuestProgress(
            user_id=user_id,
            quest_id=quest_id,
            quest_type=q_type,
            current_node_id="1" # Початковий вузол за замовчуванням
        )
        await self.quest_repo.save_progress(new_progress)
        return new_progress

    async def process_choice(self, user_id: int, quest_id: str, choice_idx: int) -> Tuple[Optional[str], Optional[QuestNode]]:
        """Обробляє вибір гравця у квесті"""
        animal = await self.repo.get_by_id(user_id)
        progress = await self.quest_repo.get_progress(user_id, quest_id)
        
        if not progress or not animal:
            return "Квест або персонаж не знайдений", None

        node = await self.quest_repo.get_node(quest_id, progress.current_node_id)
        if not node or choice_idx >= len(node.choices):
            return "Помилка вибору", None

        choice = node.choices[choice_idx]

        # Перевірка умов (наприклад, рівень)
        if "min_level" in choice.requirements:
            if animal.level < choice.requirements["min_level"]:
                return f"Твій рівень занадто малий (треба {choice.requirements['min_level']})! ⛔", None

        # Оновлення прогресу
        progress.current_node_id = choice.next_node_id
        
        # Перевірка на завершення (якщо статус win або dead)
        next_node = await self.quest_repo.get_node(quest_id, progress.current_node_id)
        if next_node and next_node.status in ["win", "dead"]:
            progress.is_completed = True

        await self.quest_repo.save_progress(progress)
        
        # Нарахування нагород (спрощено)
        if choice.rewards:
            if "exp" in choice.rewards:
                animal.level += 1 # Дуже спрощено
                await self.repo.upsert(animal)

        return None, next_node

class OnboardingService:
    def __init__(self, animal_repo: AnimalRepository):
        self.repo = animal_repo

    async def register_animal(self, user_id: int, race: str):
        # 1. Створюємо об'єкт через доменну логіку
        new_animal = Animal.create_starter(user_id, race)
        
        # 2. Зберігаємо через репозиторій
        await self.repo.upsert(new_animal)
        return new_animal
