"""历史记录数据库 - SQLite 操作"""
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("hongguo")

DB_FILE = Path(__file__).parent.parent / ".hongguo_history.db"


class HistoryDatabase:
    def __init__(self, db_path: Path = DB_FILE):
        self._db_path = db_path
        self._create_table()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _create_table(self):
        try:
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        series_id TEXT NOT NULL,
                        series_name TEXT NOT NULL,
                        cover_url TEXT DEFAULT '',
                        episodes_downloaded TEXT DEFAULT '[]',
                        total_episodes INTEGER DEFAULT 0,
                        quality TEXT DEFAULT '720P',
                        download_date TEXT DEFAULT '',
                        status TEXT DEFAULT 'completed',
                        local_path TEXT DEFAULT ''
                    )
                """)
        except sqlite3.Error:
            logger.exception("创建历史表失败")

    def insert(self, series_id: str, series_name: str, cover_url: str = "",
               episodes: list[int] = None, total_episodes: int = 0,
               quality: str = "720P", status: str = "completed",
               local_path: str = "") -> int:
        """插入一条历史记录, 返回 id"""
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO downloads
                       (series_id, series_name, cover_url, episodes_downloaded,
                        total_episodes, quality, download_date, status, local_path)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        series_id,
                        series_name,
                        cover_url,
                        json.dumps(episodes or []),
                        total_episodes,
                        quality,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        status,
                        local_path,
                    ),
                )
                return cur.lastrowid
        except (sqlite3.Error, json.JSONEncodeError):
            logger.exception(f"插入历史记录失败: {series_name}")
            return -1

    def get_all(self, limit: int = 100, offset: int = 0) -> list[dict]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM downloads ORDER BY id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            logger.exception("查询历史记录失败")
            return []

    def search(self, keyword: str, limit: int = 100) -> list[dict]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM downloads WHERE series_name LIKE ? ORDER BY id DESC LIMIT ?",
                    (f"%{keyword}%", limit),
                ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            logger.exception(f"搜索历史记录失败: {keyword}")
            return []

    def delete(self, record_id: int) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM downloads WHERE id = ?", (record_id,))
                return conn.total_changes > 0
        except sqlite3.Error:
            logger.exception(f"删除历史记录失败: id={record_id}")
            return False

    def clear_all(self):
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM downloads")
        except sqlite3.Error:
            logger.exception("清空历史记录失败")

    def get_count(self) -> int:
        try:
            with self._connect() as conn:
                return conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
        except sqlite3.Error:
            logger.exception("查询历史记录数量失败")
            return 0

    def update_status(self, record_id: int, status: str, local_path: str = ""):
        try:
            with self._connect() as conn:
                params = [status]
                if local_path:
                    params.append(local_path)
                    conn.execute(
                        "UPDATE downloads SET status = ?, local_path = ? WHERE id = ?",
                        (*params, record_id),
                    )
                else:
                    conn.execute(
                        "UPDATE downloads SET status = ? WHERE id = ?",
                        (status, record_id),
                    )
        except sqlite3.Error:
            logger.exception(f"更新历史记录状态失败: id={record_id}")
