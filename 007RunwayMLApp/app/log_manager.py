import json
from datetime import datetime, timezone
from pathlib import Path

from .models import BatchLogEntry


class LogManager:
    """Read/write batch log JSON for history tracking."""

    @staticmethod
    def load(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {"completed": [], "failed": [], "taskIds": [], "lastIndex": -1}
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def save(log: dict, path: str):
        Path(path).write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def append_entry(entry: BatchLogEntry, path: str):
        log = LogManager.load(path)
        record = {
            "index": entry.index,
            "references": entry.references,
            "prompt": entry.prompt[:120],
            "genId": entry.gen_id,
            "taskId": entry.task_id,
            "time": entry.time or datetime.now(timezone.utc).isoformat(),
            "error": entry.error,
            "videoPath": entry.video_path,
        }
        if entry.status == "failed":
            log["failed"].append(record)
        else:
            log["completed"].append(record)
        log["lastIndex"] = max(log["lastIndex"], entry.index)
        LogManager.save(log, path)
