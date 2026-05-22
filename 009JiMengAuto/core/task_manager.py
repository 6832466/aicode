"""任务管理器 - 支持并发控制和状态管理"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from collections import deque

from PySide6.QtCore import QObject, Signal, QTimer

from data.models import Task, TaskStatus, MaterialInfo, GenerationRecord
from data.excel_handler import read_prompt_excel, read_character_excel, match_materials_for_prompt

logger = logging.getLogger(__name__)

# 状态持久化文件
TASKS_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "tasks_state.json"


class TaskManager(QObject):
    """生成任务队列管理器"""

    # 信号
    task_added = Signal(Task)
    task_removed = Signal(str)  # task_id
    task_updated = Signal(Task)
    tasks_imported = Signal(list)  # list[Task]
    stats_changed = Signal(dict)   # 统计数据变化
    queue_changed = Signal()       # 队列变化

    def __init__(self, max_concurrent: int = 3, parent=None):
        super().__init__(parent)
        self._tasks: dict[str, Task] = {}
        self._queue: deque[str] = deque()  # 待生成队列（task_id）
        self._active: set[str] = set()     # 正在生成的任务ID
        self._max_concurrent = max_concurrent
        self._paused = False
        self._stopped = False

        self._load_state()

    # ── 配置 ──

    def set_max_concurrent(self, n: int):
        """设置最大并发数（范围1~3）"""
        self._max_concurrent = max(1, min(3, n))

    def get_max_concurrent(self) -> int:
        return self._max_concurrent

    # ── CRUD ──

    def add_task(self, task: Task):
        """添加单个任务"""
        self._tasks[task.id] = task
        if task.status == TaskStatus.PENDING:
            self._queue.append(task.id)
        self._save_state()
        self.task_added.emit(task)
        self._update_stats()

    def remove_task(self, task_id: str):
        """删除任务"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._queue = deque([t for t in self._queue if t != task_id])
            self._active.discard(task_id)
            self._save_state()
            self.task_removed.emit(task_id)
            self._update_stats()

    def update_task(self, task_id: str, **kwargs):
        """更新任务字段"""
        task = self._tasks.get(task_id)
        if not task:
            return
        for k, v in kwargs.items():
            if hasattr(task, k):
                setattr(task, k, v)
        task.update_timestamp()
        self._save_state()
        self.task_updated.emit(task)

    def update_task_status(self, task_id: str, status: TaskStatus,
                           jm_task_id: Optional[str] = None,
                           video_url: Optional[str] = None,
                           error_msg: Optional[str] = None):
        """更新任务状态"""
        task = self._tasks.get(task_id)
        if not task:
            return

        old_status = task.status
        task.status = status
        task.error_msg = error_msg

        if jm_task_id:
            task.jm_task_id = jm_task_id
        if video_url:
            task.video_url = video_url

        # 状态变化时的队列处理
        if old_status == TaskStatus.PENDING and status == TaskStatus.GENERATING:
            self._active.add(task_id)
        elif old_status == TaskStatus.GENERATING:
            self._active.discard(task_id)
            # 如果完成，从队列移除
            if task_id in self._queue:
                self._queue = deque([t for t in self._queue if t != task_id])

        task.update_timestamp()
        self._save_state()
        self.task_updated.emit(task)
        self._update_stats()
        self.queue_changed.emit()

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[Task]:
        """获取所有任务，按序号排序"""
        return sorted(self._tasks.values(), key=lambda t: t.seq)

    def get_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        return [t for t in self._tasks.values() if t.status == status]

    def get_pending_tasks(self) -> list[Task]:
        """获取待生成任务"""
        return self.get_tasks_by_status(TaskStatus.PENDING)

    def get_generating_tasks(self) -> list[Task]:
        """获取生成中任务"""
        return self.get_tasks_by_status(TaskStatus.GENERATING)

    def get_completed_tasks(self) -> list[Task]:
        """获取已完成任务（可下载）"""
        return self.get_tasks_by_status(TaskStatus.COMPLETED)

    def clear_all(self):
        """清空所有任务"""
        self._tasks.clear()
        self._queue.clear()
        self._active.clear()
        self._save_state()
        self._update_stats()

    # ── 批量导入 ──

    def import_from_excel(self, prompt_path: str, character_path: Optional[str] = None) -> list[Task]:
        """从 Excel 批量导入任务"""
        prompt_rows = read_prompt_excel(prompt_path)

        # 读取人物对照表
        character_data: dict[str, list[MaterialInfo]] = {}
        if character_path:
            character_data = read_character_excel(character_path)

        imported = []
        for row in prompt_rows:
            # 匹配素材
            materials = match_materials_for_prompt(
                row["prompt"], character_data
            ) if character_data else []

            task = Task(
                seq=row["seq"],
                scene=row["scene"],
                prompt=row["prompt"],
                duration=row["duration"],
                ratio=row["ratio"],
                materials=materials,
                status=TaskStatus.PENDING,
            )
            self.add_task(task)
            imported.append(task)

        logger.info("导入任务: %d 条", len(imported))
        self.tasks_imported.emit(imported)
        return imported

    # ── 队列控制 ──

    def get_queue_size(self) -> int:
        """获取待生成队列大小"""
        return len(self._queue)

    def get_active_count(self) -> int:
        """获取正在生成的任务数"""
        return len(self._active)

    def can_start_more(self) -> bool:
        """是否可以启动更多任务"""
        return not self._paused and not self._stopped and \
               len(self._active) < self._max_concurrent and \
               len(self._queue) > 0

    def get_next_task(self) -> Optional[Task]:
        """从队列获取下一个待处理任务"""
        if self._paused or self._stopped:
            return None

        while self._queue and len(self._active) < self._max_concurrent:
            task_id = self._queue[0]
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING:
                self._queue.popleft()  # 从队列移除
                self._active.add(task_id)
                return task
            else:
                # 无效任务，跳过
                self._queue.popleft()

        return None

    def pause_queue(self):
        """暂停队列"""
        self._paused = True
        self.queue_changed.emit()
        logger.info("队列已暂停")

    def resume_queue(self):
        """继续队列"""
        self._paused = False
        self.queue_changed.emit()
        logger.info("队列已继续")

    def stop_queue(self):
        """停止队列"""
        self._stopped = True
        self._paused = True
        # 将正在生成的任务标记为待生成
        for task_id in list(self._active):
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.GENERATING:
                task.status = TaskStatus.PENDING
                self._queue.appendleft(task_id)  # 放回队列头部
        self._active.clear()
        self._save_state()
        self.queue_changed.emit()
        logger.info("队列已停止")

    def reset_queue(self):
        """重置队列状态"""
        self._paused = False
        self._stopped = False
        # 重建队列
        self._queue.clear()
        self._active.clear()
        for task in self._tasks.values():
            if task.status == TaskStatus.PENDING:
                self._queue.append(task.id)
            elif task.status == TaskStatus.GENERATING:
                task.status = TaskStatus.PENDING
                self._queue.append(task.id)
        self._save_state()
        self.queue_changed.emit()
        logger.info("队列已重置")

    def is_paused(self) -> bool:
        return self._paused

    def is_stopped(self) -> bool:
        return self._stopped

    # ── 统计数据 ──

    def get_stats(self) -> dict[str, int]:
        """获取各状态任务数量"""
        stats = {
            "total": len(self._tasks),
            "pending": 0,
            "generating": 0,
            "completed": 0,
            "failed": 0,
            "downloading": 0,
            "downloaded": 0,
        }
        for t in self._tasks.values():
            stats[t.status.value] = stats.get(t.status.value, 0) + 1
        return stats

    def _update_stats(self):
        """更新统计数据信号"""
        self.stats_changed.emit(self.get_stats())

    # ── 任务历史 ──

    def add_generation_record(self, task_id: str, record: GenerationRecord):
        """添加生成历史记录"""
        task = self._tasks.get(task_id)
        if task:
            task.add_history(record)
            self._save_state()
            self.task_updated.emit(task)

    # ── 持久化 ──

    def _save_state(self):
        """保存任务状态到 JSON"""
        try:
            TASKS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "tasks": [t.to_dict() for t in self._tasks.values()],
                "queue": list(self._queue),
                "max_concurrent": self._max_concurrent,
                "paused": self._paused,
            }
            TASKS_STATE_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("保存任务状态失败: %s", e)

    def _load_state(self):
        """从 JSON 加载任务状态"""
        if not TASKS_STATE_PATH.exists():
            return
        try:
            data = json.loads(TASKS_STATE_PATH.read_text(encoding="utf-8"))
            self._max_concurrent = data.get("max_concurrent", 1)
            self._paused = data.get("paused", False)

            for t_dict in data.get("tasks", []):
                task = Task.from_dict(t_dict)
                self._tasks[task.id] = task

            # 重建队列（只包含pending状态）
            for task_id in data.get("queue", []):
                if task_id in self._tasks:
                    task = self._tasks[task_id]
                    if task.status == TaskStatus.PENDING:
                        self._queue.append(task_id)

            logger.info("加载任务状态: %d 条, 队列 %d 条", len(self._tasks), len(self._queue))
        except Exception as e:
            logger.error("加载任务状态失败: %s", e)