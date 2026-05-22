from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SendStatus(Enum):
    PENDING = "待发送"
    SENDING = "发送中"
    SENT = "已发送"
    FAILED = "发送失败"


class ChatMode(Enum):
    AUTO = "自动判断"
    EXPERT = "专家模式"
    THINK = "思考模式"
    FAST = "快速模式"


@dataclass
class SendMessage:
    id: int
    content: str
    status: SendStatus = SendStatus.PENDING
    mode: ChatMode = ChatMode.AUTO
    send_time: Optional[datetime] = None
    retry_count: int = 0
    reply_id: Optional[int] = None
    create_time: datetime = field(default_factory=datetime.now)
    forced_mode: Optional[ChatMode] = None  # user-forced override


@dataclass
class ReplyMessage:
    id: int
    send_id: int
    content: str
    collect_time: datetime = field(default_factory=datetime.now)
    elapsed_seconds: int = 0
    mode: ChatMode = ChatMode.EXPERT


@dataclass
class AppConfig:
    expert_rounds: int = 3
    send_interval: int = 10
    reply_timeout: int = 120
    max_retries: int = 3
    browser_path: str = ""
    doubao_url: str = "https://www.doubao.com/chat/"
    save_path: str = ""
    first_mode: ChatMode = ChatMode.EXPERT   # mode for first N rounds
    second_mode: ChatMode = ChatMode.THINK   # mode after N rounds
    system_prompt: str = ""
