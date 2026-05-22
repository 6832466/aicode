from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    QUEUED = "待提交"
    SUBMITTING = "提交中"
    SUBMITTED = "已提交"
    RUNNING = "处理中"
    THROTTLED = "限流等待"
    DONE = "已完成"
    FAILED = "失败"
    DOWNLOADING = "下载中"
    DOWNLOADED = "已下载"


@dataclass
class PromptItem:
    index: int
    prompt_text: str          # API-ready: [角色名] → @refname substituted
    references: list[str] = field(default_factory=list)
    duration: int = 10
    ratio: str = "16:9"
    source_row: int = 0
    status: TaskStatus = TaskStatus.QUEUED
    gen_id: str = ""
    task_id: str = ""
    error_message: str = ""
    result_video_path: str = ""
    result_video_url: str = ""
    prefix: str = ""
    suffix: str = ""
    raw_prompt: str = ""      # Original: bracket notation preserved for display
    progress_ratio: float = 0  # 0.0 - 1.0 from API task status
    missing_refs: list[str] = field(default_factory=list)  # ref_names without assets

    @property
    def effective_prompt(self) -> str:
        result = self.prompt_text
        if self.prefix:
            result = self.prefix + "\n" + result
        if self.suffix:
            result = result + "\n" + self.suffix
        return result

    @property
    def display_prompt(self) -> str:
        """For GUI table display — shows original bracket notation."""
        return self.raw_prompt or self.prompt_text


@dataclass
class CharacterAsset:
    ref_name: str
    asset_id: str
    url: str


@dataclass
class BatchLogEntry:
    index: int
    references: list[str]
    prompt: str
    gen_id: str = ""
    task_id: str = ""
    status: str = ""
    time: str = ""
    error: str = ""
    video_path: str = ""


@dataclass
class AppConfig:
    token: str = ""
    team_id: str = "57508622"
    output_dir: str = ""
    prefix_text: str = ""
    suffix_text: str = ""
    resolution: str = "720p"
    generate_audio: bool = True
    poll_interval_sec: int = 15
    session_id: str = ""
    asset_group_id: str = ""
