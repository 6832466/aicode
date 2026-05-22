"""
多轮对话会话管理
"""

import json
import uuid
import logging
from pathlib import Path
from typing import Optional

from models.chat_message import ChatSession
from app.constants import chat_history_dir

logger = logging.getLogger(__name__)


class SessionManager:
    """会话管理器 — 持久化到本地 JSON 文件"""

    def __init__(self):
        self._dir = chat_history_dir()
        self._sessions: list[ChatSession] = []
        self._load_all()

    @property
    def sessions(self) -> list[ChatSession]:
        return self._sessions

    def _load_all(self):
        """加载所有会话文件"""
        self._sessions = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._sessions.append(ChatSession.from_dict(data))
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning("加载会话 %s 失败: %s", f.name, e)

    def create(self, name: str = "", system_prompt: str = "", model: str = "") -> ChatSession:
        """创建新会话"""
        sid = uuid.uuid4().hex[:12]
        if not name:
            nums = []
            for s in self._sessions:
                if s.name.startswith("新对话 "):
                    try:
                        nums.append(int(s.name[4:]))
                    except ValueError:
                        pass
            next_num = max(nums) + 1 if nums else 1
            name = f"新对话 {next_num}"
        session = ChatSession(
            id=sid,
            name=name,
            system_prompt=system_prompt,
            model=model,
        )
        self._sessions.insert(0, session)
        self._save(session)
        return session

    def delete(self, session_id: str):
        self._sessions = [s for s in self._sessions if s.id != session_id]
        path = self._path_for(session_id)
        if path.exists():
            path.unlink()

    def rename(self, session_id: str, new_name: str):
        session = self.get(session_id)
        if session:
            session.name = new_name
            self._save(session)

    def get(self, session_id: str) -> Optional[ChatSession]:
        for s in self._sessions:
            if s.id == session_id:
                return s
        return None

    def _save(self, session: ChatSession):
        try:
            path = self._path_for(session.id)
            path.write_text(
                json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("保存会话 %s 失败: %s", session.id, e)

    def save_session(self, session: ChatSession):
        """保存（更新）会话"""
        self._save(session)

    def _path_for(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"
