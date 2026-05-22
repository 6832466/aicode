"""
AI 服务封装 — 统一调用接口
"""

import logging
import time
from typing import Iterator

from PySide6.QtCore import QThread, Signal

from core.api_client import APIClient
from app.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class AIProcessWorker(QThread):
    """后台 AI 处理线程（非流式）"""
    finished = Signal(bool, str)  # success, result/error

    def __init__(self, base_url: str, api_key: str, model: str,
                 messages: list, timeout: int = 120):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.messages = messages
        self.timeout = timeout

    def run(self):
        try:
            client = APIClient(self.base_url, self.api_key, self.model)
            client._timeout = self.timeout
            result = client.chat(self.messages, stream=False)
            self.finished.emit(True, result["content"])
        except Exception as e:
            logger.error("AI process error: %s", e)
            self.finished.emit(False, str(e))


class AIStreamWorker(QThread):
    """后台 AI 流式处理线程"""
    chunk_ready = Signal(str)       # 每个 delta 文本块
    finished = Signal(bool, str)    # success, error message

    def __init__(self, base_url: str, api_key: str, model: str,
                 messages: list, timeout: int = 120):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.messages = messages
        self.timeout = timeout
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            client = APIClient(self.base_url, self.api_key, self.model)
            client._timeout = self.timeout
            stream: Iterator[str] = client.chat(self.messages, stream=True)
            for chunk in stream:
                if self._is_cancelled:
                    self.finished.emit(False, "已取消")
                    return
                self.chunk_ready.emit(chunk)
            self.finished.emit(True, "")
        except Exception as e:
            logger.error("AI stream error: %s", e)
            self.finished.emit(False, str(e))


class AISegmentWorker(QThread):
    """分段流式处理线程 — 对话延续模式 + 段级重试 + 异常隔离"""
    chunk_ready = Signal(str)          # 流式文本块
    segment_done = Signal(int)         # 某段完成
    progress = Signal(int, int)        # current, total
    finished = Signal(bool, str)       # success, error message

    TAIL_CHARS = 400       # 上下文传递的尾部字符数
    MAX_RETRIES = 3        # 每段最多重试次数
    RETRY_DELAY = 3        # 重试间隔基数（秒）

    def __init__(self, base_url: str, api_key: str, model: str,
                 segments: list[str], system_prompt: str, timeout: int = 120):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.segments = segments
        self.system_prompt = system_prompt
        self.timeout = timeout
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            client = APIClient(self.base_url, self.api_key, self.model)
            client._timeout = max(self.timeout, 180)
            total = len(self.segments)
            system_msg = "你是一个专业的文本处理助手，请严格按照用户提供的规则处理文本。只输出处理结果，不要添加解释或开场白。"

            prev_corrected = ""   # 上一段修正结果尾部
            last_chunk = ""        # 上一段最后发出的 chunk（检测尾部换行）
            failed = []

            for idx, segment in enumerate(self.segments):
                if self._is_cancelled:
                    self.finished.emit(False, "已取消")
                    return

                self.progress.emit(idx + 1, total)

                # 构建消息 — 上文修正结果嵌入 user 内容，保持单条 user 消息格式
                if prev_corrected:
                    user_content = (
                        f"{self.system_prompt}\n\n"
                        f"[上文参考] 前一段修正结果的结尾（请保持一致的错别字修正规则和用词风格）：\n"
                        f"---\n{prev_corrected}\n---\n\n"
                        f"需要处理的文本如下：\n{segment}"
                    )
                else:
                    user_content = f"{self.system_prompt}\n\n需要处理的文本如下：\n{segment}"

                messages = [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_content},
                ]

                # 段级重试
                ok = False
                for attempt in range(self.MAX_RETRIES):
                    if self._is_cancelled:
                        self.finished.emit(False, "已取消")
                        return

                    try:
                        if idx > 0 and attempt == 0 and last_chunk and not last_chunk.endswith('\n'):
                            self.chunk_ready.emit('\n')
                        stream = client.chat(messages, stream=True, max_tokens=8192)
                        buf = []
                        for chunk in stream:
                            if self._is_cancelled:
                                self.finished.emit(False, "已取消")
                                return
                            buf.append(chunk)
                            self.chunk_ready.emit(chunk)
                            last_chunk = chunk

                        if buf:
                            full = ''.join(buf)
                            prev_corrected = full[-self.TAIL_CHARS:] if len(full) > self.TAIL_CHARS else full
                            ok = True
                            break
                        else:
                            if attempt < self.MAX_RETRIES - 1:
                                time.sleep(self.RETRY_DELAY)
                    except Exception as e:
                        if attempt < self.MAX_RETRIES - 1:
                            time.sleep(self.RETRY_DELAY * (attempt + 1))
                        else:
                            failed.append(idx + 1)
                            self.chunk_ready.emit(f"\n[第{idx+1}段失败: {e}]\n")

                self.segment_done.emit(idx)
                if idx < total - 1:
                    time.sleep(0.5)

            if failed:
                self.finished.emit(True, f"部分段落失败 (第{failed}段)，可重试")
            else:
                self.finished.emit(True, "")
        except Exception as e:
            logger.error("Segment process error: %s", e)
            self.finished.emit(False, str(e))


class AIService:
    """AI 服务统一入口"""

    @staticmethod
    def get_active_client() -> APIClient | None:
        """获取当前激活的 API 客户端"""
        config = ConfigManager()
        ep = config.get_default_endpoint()
        if not ep:
            return None
        return APIClient(ep.base_url, ep.api_key, ep.model)

    @staticmethod
    def process(
        system_prompt: str,
        user_content: str,
        model: str = "",
        stream: bool = False,
        timeout: int = 120,
        messages: list | None = None,
    ) -> AIProcessWorker | AIStreamWorker:
        """
        创建 AI 处理线程

        Args:
            system_prompt: 系统提示词（messages 为 None 时使用）
            user_content: 用户输入（messages 为 None 时使用）
            model: 模型（空则用默认）
            stream: 是否流式
            timeout: 超时秒数
            messages: 完整的消息列表（传入时忽略 system_prompt/user_content）
        """
        config = ConfigManager()
        ep = config.get_default_endpoint()
        if not ep:
            raise RuntimeError("未配置 API 端点，请先在全局设置中添加")

        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

        if stream:
            return AIStreamWorker(
                ep.base_url, ep.api_key, model or ep.model,
                messages, timeout,
            )
        else:
            return AIProcessWorker(
                ep.base_url, ep.api_key, model or ep.model,
                messages, timeout,
            )
