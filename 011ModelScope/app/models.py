from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from typing import Optional
import json


class ModelType(Enum):
    LLM = "llm"
    MULTIMODAL = "multimodal"
    IMAGE = "image"

    @property
    def display_name(self) -> str:
        from app.config import MODEL_TYPE_NAMES
        return MODEL_TYPE_NAMES.get(self.value, self.value)


class ChatRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ModelConfig:
    """Model configuration"""
    model_id: str                           # Full model ID like "Qwen/Qwen3-235B-A22B-Instruct"
    name: str                               # User-friendly name
    model_type: ModelType = ModelType.LLM
    enabled: bool = True
    priority: int = 3                       # 1-5, higher = more priority
    notes: str = ""
    groups: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "model_type": self.model_type.value,
            "enabled": self.enabled,
            "priority": self.priority,
            "notes": self.notes,
            "groups": self.groups,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModelConfig":
        return cls(
            model_id=d["model_id"],
            name=d["name"],
            model_type=ModelType(d.get("model_type", "llm")),
            enabled=d.get("enabled", True),
            priority=d.get("priority", 3),
            notes=d.get("notes", ""),
            groups=d.get("groups", []),
        )


@dataclass
class QuotaInfo:
    """Quota information from API response headers"""
    model_id: str
    daily_limit: int = 0
    daily_remaining: int = 0
    model_limit: int = 0
    model_remaining: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def daily_used(self) -> int:
        return max(0, self.daily_limit - self.daily_remaining)

    @property
    def model_used(self) -> int:
        return max(0, self.model_limit - self.model_remaining)

    @property
    def daily_percent(self) -> float:
        if self.daily_limit == 0:
            return 0.0
        return (self.daily_remaining / self.daily_limit) * 100

    @property
    def model_percent(self) -> float:
        if self.model_limit == 0:
            return 0.0
        return (self.model_remaining / self.model_limit) * 100

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "QuotaInfo":
        return cls(**d)


@dataclass
class ChatMessage:
    """Single chat message"""
    role: ChatRole
    content: str
    timestamp: str = ""
    model_id: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_openai_format(self) -> dict:
        return {"role": self.role.value, "content": self.content}

    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "model_id": self.model_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChatMessage":
        return cls(
            role=ChatRole(d["role"]),
            content=d["content"],
            timestamp=d.get("timestamp", ""),
            model_id=d.get("model_id", ""),
        )


@dataclass
class ChatSession:
    """Chat session with history"""
    session_id: str
    title: str = "新对话"
    model_id: str = ""
    messages: list[ChatMessage] = field(default_factory=list)
    system_prompt: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def add_message(self, role: ChatRole, content: str, model_id: str = ""):
        msg = ChatMessage(role=role, content=content, model_id=model_id)
        self.messages.append(msg)
        self.updated_at = datetime.now().isoformat()
        if self.title == "新对话" and role == ChatRole.USER:
            self.title = content[:30] + ("..." if len(content) > 30 else "")

    def to_openai_messages(self) -> list[dict]:
        result = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        for msg in self.messages:
            result.append(msg.to_openai_format())
        return result

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "model_id": self.model_id,
            "messages": [m.to_dict() for m in self.messages],
            "system_prompt": self.system_prompt,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChatSession":
        return cls(
            session_id=d["session_id"],
            title=d.get("title", "新对话"),
            model_id=d.get("model_id", ""),
            messages=[ChatMessage.from_dict(m) for m in d.get("messages", [])],
            system_prompt=d.get("system_prompt", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


@dataclass
class ImageGeneration:
    """Image generation record"""
    prompt: str
    model_id: str
    image_url: str = ""
    local_path: str = ""
    size: str = "1024x1024"
    seed: int = -1
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ImageGeneration":
        return cls(**d)


@dataclass
class BatchTask:
    """Batch processing task"""
    task_id: str
    name: str
    model_ids: list[str]
    inputs: list[str]
    status: str = "pending"  # pending, running, paused, completed, failed
    total: int = 0
    completed: int = 0
    failed: int = 0
    results: list[dict] = field(default_factory=list)
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if self.total == 0:
            self.total = len(self.inputs)

    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed + self.failed) / self.total * 100

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BatchTask":
        return cls(**d)


def load_models_config() -> list[ModelConfig]:
    """Load models configuration from JSON file."""
    from app.config import models_config_path

    path = models_config_path()
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [ModelConfig.from_dict(m) for m in data]
    except Exception:
        return []


def save_models_config(models: list[ModelConfig]) -> None:
    """Save models configuration to JSON file."""
    from app.config import models_config_path

    path = models_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [m.to_dict() for m in models]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class ApiKeyEntry:
    """API Key entry with encrypted storage"""
    name: str
    encrypted_key: str = ""  # Base64 encoded encrypted key
    active: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "encrypted_key": self.encrypted_key,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ApiKeyEntry":
        return cls(
            name=d["name"],
            encrypted_key=d.get("encrypted_key", ""),
            active=d.get("active", False),
        )


@dataclass
class PromptTemplate:
    """Prompt template for reuse"""
    id: str
    name: str
    category: str
    content: str
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "content": self.content,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PromptTemplate":
        return cls(
            id=d["id"],
            name=d["name"],
            category=d.get("category", "默认"),
            content=d["content"],
            created_at=d.get("created_at", ""),
        )


@dataclass
class UsageStats:
    """API usage statistics"""
    date: str
    model_id: str
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "UsageStats":
        return cls(**d)


def get_default_models() -> list[ModelConfig]:
    """Get default model configurations."""
    from app.config import FREE_MODELS, short_model_name

    models = []
    for model_type, model_ids in FREE_MODELS.items():
        for model_id in model_ids:
            models.append(ModelConfig(
                model_id=model_id,
                name=short_model_name(model_id),
                model_type=ModelType(model_type),
            ))
    return models