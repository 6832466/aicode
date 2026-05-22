import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

from app.models import BatchTask
from app.config import batch_tasks_path
from app.modelscope_client import get_client

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class TaskProgress:
    """Progress info for a single model in batch task"""
    model_id: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    status: str = "pending"  # pending, running, completed, failed
    current_prompt: str = ""

    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed + self.failed) / self.total * 100

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TaskProgress":
        return cls(**d)


class BatchProcessor:
    """Manages batch processing tasks with pause/resume/stop support"""

    def __init__(self):
        self._task: Optional[BatchTask] = None
        self._progress: dict[str, TaskProgress] = {}  # model_id -> progress
        self._status: TaskStatus = TaskStatus.PENDING
        self._pause_event: Optional[asyncio.Event] = None
        self._stop_flag: bool = False
        self._max_concurrent: int = 3
        self._results: list[dict] = []
        self._completed_prompts: set[tuple[str, str]] = set()  # (model_id, prompt)

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def task(self) -> Optional[BatchTask]:
        return self._task

    @property
    def progress(self) -> dict[str, TaskProgress]:
        return self._progress

    @property
    def results(self) -> list[dict]:
        return self._results

    def create_task(self, name: str, model_ids: list[str], prompts: list[str]) -> BatchTask:
        """Create a new batch task"""
        task_id = str(uuid.uuid4())[:8]
        self._task = BatchTask(
            task_id=task_id,
            name=name,
            model_ids=model_ids,
            inputs=prompts,
            total=len(prompts) * len(model_ids),
        )
        self._progress = {
            model_id: TaskProgress(model_id=model_id, total=len(prompts))
            for model_id in model_ids
        }
        self._results = []
        self._completed_prompts = set()
        self._status = TaskStatus.PENDING
        self._stop_flag = False
        return self._task

    async def start(self) -> bool:
        """Start processing the task"""
        if not self._task:
            return False
        if self._status == TaskStatus.RUNNING:
            return True

        self._status = TaskStatus.RUNNING
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._stop_flag = False
        self._task.started_at = datetime.now().isoformat()

        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def _process_model(model_id: str):
            progress = self._progress[model_id]
            progress.status = "running"
            client = get_client()

            for prompt in self._task.inputs:
                if self._stop_flag:
                    progress.status = "stopped"
                    break

                # Skip already completed prompts (resume support)
                key = (model_id, prompt)
                if key in self._completed_prompts:
                    continue

                # Wait if paused
                await self._pause_event.wait()

                if self._stop_flag:
                    progress.status = "stopped"
                    break

                progress.current_prompt = prompt[:50]
                try:
                    async with semaphore:
                        messages = [{"role": "user", "content": prompt}]
                        response = await client.chat_completion(
                            model_id=model_id,
                            messages=messages,
                            max_tokens=2048,
                        )

                    self._results.append({
                        "model_id": model_id,
                        "prompt": prompt,
                        "response": response.content,
                        "success": True,
                        "timestamp": datetime.now().isoformat(),
                    })
                    self._completed_prompts.add(key)
                    progress.completed += 1

                except Exception as e:
                    logger.error(f"Batch task error for {model_id}: {e}")
                    self._results.append({
                        "model_id": model_id,
                        "prompt": prompt,
                        "response": str(e),
                        "success": False,
                        "timestamp": datetime.now().isoformat(),
                    })
                    progress.failed += 1

                await asyncio.sleep(0.1)  # Small delay to avoid rate limiting

            if progress.completed + progress.failed >= progress.total:
                progress.status = "completed" if progress.failed == 0 else "failed"
                progress.current_prompt = ""

        tasks = [_process_model(mid) for mid in self._task.model_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

        self._task.completed = sum(p.completed for p in self._progress.values())
        self._task.failed = sum(p.failed for p in self._progress.values())
        self._task.results = self._results

        if self._stop_flag:
            self._status = TaskStatus.STOPPED
        elif self._task.completed + self._task.failed >= self._task.total:
            self._status = TaskStatus.COMPLETED if self._task.failed == 0 else TaskStatus.FAILED
            self._task.finished_at = datetime.now().isoformat()

        self._save_task()
        return True

    def pause(self):
        """Pause the task"""
        if self._status == TaskStatus.RUNNING and self._pause_event:
            self._pause_event.clear()
            self._status = TaskStatus.PAUSED

    def resume(self):
        """Resume the paused task"""
        if self._status == TaskStatus.PAUSED and self._pause_event:
            self._pause_event.set()
            self._status = TaskStatus.RUNNING

    def stop(self):
        """Stop the task"""
        self._stop_flag = True
        if self._pause_event:
            self._pause_event.set()
        self._status = TaskStatus.STOPPED

    def _save_task(self):
        """Save task to file"""
        path = batch_tasks_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = self._task.to_dict() if self._task else {}
            data["progress"] = {k: v.to_dict() for k, v in self._progress.items()}
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save batch task: {e}")

    def load_task(self) -> Optional[BatchTask]:
        """Load last task from file"""
        path = batch_tasks_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._task = BatchTask.from_dict(data)
            self._progress = {
                k: TaskProgress.from_dict(v)
                for k, v in data.get("progress", {}).items()
            }
            self._results = data.get("results", [])
            self._completed_prompts = set()
            for r in self._results:
                if r.get("success"):
                    self._completed_prompts.add((r["model_id"], r["prompt"]))
            self._status = TaskStatus(self._task.status)
            return self._task
        except Exception as e:
            logger.warning(f"Failed to load batch task: {e}")
            return None


# Singleton
_processor_instance: Optional[BatchProcessor] = None


def get_batch_processor() -> BatchProcessor:
    """Get the singleton batch processor instance."""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = BatchProcessor()
    return _processor_instance
