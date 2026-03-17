import json
import os
import logging
from typing import Optional, List, Dict
from domain.base import QuestNode, QuestProgress, QuestType

logger = logging.getLogger(__name__)

class QuestRepository:
    def __init__(self, db_pool, quests_dir: str = "data"):
        self.pool = db_pool
        self.quests_dir = quests_dir
        # Кеш для завантажених квестів: {quest_id: {node_id: QuestNode}}
        self._quest_cache: Dict[str, Dict[str, QuestNode]] = {}

    def _load_quest_data(self, quest_id: str) -> Dict[str, QuestNode]:
        """Завантажує квест із JSON файлу та кешує його"""
        if quest_id in self._quest_cache:
            return self._quest_cache[quest_id]

        # Шукаємо файл (наприклад, data/prolog_narrative_tree.json)
        # Для простоти припустимо, що quest_id відповідає частині назви файлу
        # Або можна зробити чіткий мапінг
        file_map = {
            "prologue": "prolog_narrative_tree.json",
            "quest1": "quest1_narrative_tree.json"
        }
        
        file_name = file_map.get(quest_id, f"{quest_id}_narrative_tree.json")
        file_path = os.path.join(self.quests_dir, file_name)

        if not os.path.exists(file_path):
            logger.error(f"Quest file not found: {file_path}")
            return {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Обробка структури (у ваших файлах вузли лежать у 'nodes' або 'QUEST_PLOTS')
                nodes_data = data.get('nodes', [])
                
                # Якщо це структура з QUEST_PLOTS (як у quest1)
                if not nodes_data and 'QUEST_PLOTS' in data:
                    quest_plot = data['QUEST_PLOTS'].get(quest_id, {})
                    stages = quest_plot.get('stages', {})
                    # Конвертуємо stages у список QuestNode
                    nodes_dict = {}
                    for s_id, s_data in stages.items():
                        # Адаптація під вашу модель Choice
                        choices = []
                        for opt in s_data.get('options', []):
                            choices.append({
                                "text": opt.get('text', ''),
                                "next_node_id": str(opt.get('next', '')),
                                "requirements": {"risk": opt.get('risk', 0)},
                                "rewards": {"reward_str": opt.get('reward', '')}
                            })
                        
                        nodes_dict[str(s_id)] = QuestNode(
                            id=str(s_id),
                            quest_id=quest_id,
                            text=s_data.get('text', ''),
                            choices=choices
                        )
                    self._quest_cache[quest_id] = nodes_dict
                    return nodes_dict

                # Стандартна структура (як у prologue)
                nodes_dict = {
                    str(n['id']): QuestNode(quest_id=quest_id, **n) 
                    for n in nodes_data
                }
                self._quest_cache[quest_id] = nodes_dict
                return nodes_dict

        except Exception as e:
            logger.error(f"Error loading quest {quest_id}: {e}")
            return {}

    async def get_node(self, quest_id: str, node_id: str) -> Optional[QuestNode]:
        """Отримує конкретний вузол квесту"""
        nodes = self._load_quest_data(quest_id)
        return nodes.get(str(node_id))

    async def get_progress(self, user_id: int, quest_id: str) -> Optional[QuestProgress]:
        """Отримує прогрес гравця у конкретному квесті з БД"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_quests WHERE user_id = $1 AND quest_id = $2",
                user_id, quest_id
            )
            if not row:
                return None
            
            return QuestProgress(
                user_id=row['user_id'],
                quest_id=row['quest_id'],
                quest_type=QuestType(row['quest_type']),
                current_node_id=row['current_node_id'],
                is_completed=row.get('is_completed', False)
            )

    async def save_progress(self, progress: QuestProgress):
        """Зберігає прогрес у БД"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_quests (user_id, quest_id, quest_type, current_node_id, is_completed)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, quest_id) DO UPDATE SET
                current_node_id = EXCLUDED.current_node_id,
                is_completed = EXCLUDED.is_completed,
                updated_at = CURRENT_TIMESTAMP
            """, progress.user_id, progress.quest_id, progress.quest_type.value, 
                 progress.current_node_id, progress.is_completed)

    async def get_all_active(self, user_id: int) -> List[QuestProgress]:
        """Отримує всі незавершені квести гравця"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM user_quests WHERE user_id = $1 AND is_completed = FALSE",
                user_id
            )
            return [
                QuestProgress(
                    user_id=r['user_id'],
                    quest_id=r['quest_id'],
                    quest_type=QuestType(r['quest_type']),
                    current_node_id=r['current_node_id']
                ) for r in rows
            ]
