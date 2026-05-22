"""
日志管理器 — batch_history.json 读写
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import data_dir
from app.models import BatchLogEntry


class LogManager:
    """批量处理历史记录"""

    LOG_FILE = "batch_history.json"

    def __init__(self):
        self._path = data_dir() / self.LOG_FILE
        self._entries: list[dict] = self._load()

    def _load(self) -> list:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self):
        self._path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_entry(self, entry: BatchLogEntry):
        record = {
            "task_id": entry.task_id,
            "file_name": entry.file_name,
            "mode": entry.mode,
            "state": entry.state,
            "srt_path": entry.srt_path,
            "error": entry.error,
            "processed_at": entry.processed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": entry.duration_seconds,
        }
        self._entries.append(record)
        self._save()

    def get_all(self) -> list:
        return list(self._entries)

    def clear(self):
        self._entries.clear()
        self._save()

    def count(self) -> int:
        return len(self._entries)