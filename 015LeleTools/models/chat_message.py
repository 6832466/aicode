"""
对话消息数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ChatMessage:
    """单条对话消息"""
    role: str  # "user" or "assistant" or "system"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChatMessage":
        return cls(
            role=d.get("role", "user"),
            content=d.get("content", ""),
            timestamp=d.get("timestamp", ""),
        )

    def to_api_format(self) -> dict:
        """转换为 OpenAI API 格式"""
        return {"role": self.role, "content": self.content}


@dataclass
class ChatSession:
    """对话会话"""
    id: str
    name: str
    messages: list = field(default_factory=list)
    model: str = ""
    system_prompt: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "messages": [m.to_dict() for m in self.messages],
            "model": self.model,
            "system_prompt": self.system_prompt,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChatSession":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            messages=[ChatMessage.from_dict(m) for m in d.get("messages", [])],
            model=d.get("model", ""),
            system_prompt=d.get("system_prompt", ""),
            created_at=d.get("created_at", ""),
        )

    def add_message(self, role: str, content: str) -> ChatMessage:
        msg = ChatMessage(role=role, content=content)
        self.messages.append(msg)
        return msg

    def get_api_messages(self) -> list[dict]:
        """获取发送给 API 的消息列表（含系统提示词）"""
        result = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        for m in self.messages[-20:]:  # 限制上下文
            result.append(m.to_api_format())
        return result
