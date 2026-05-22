import asyncio
import logging
import os
import re
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .runway_client import RunwayClient
from .models import PromptItem

logger = logging.getLogger(__name__)


class DownloadManager(QObject):
    """Handles video downloads with progress signals."""

    download_started = Signal(int, str)
    download_progress = Signal(int, int, int)
    download_finished = Signal(int, str)
    download_failed = Signal(int, str)

    def __init__(self, client: RunwayClient, output_dir: str = "", parent=None):
        super().__init__(parent)
        self._client = client
        self._output_dir = output_dir

    def set_output_dir(self, path: str):
        self._output_dir = path

    @staticmethod
    def _sanitize_filename(text: str, max_len: int = 50) -> str:
        """Keep Chinese chars, alphanumeric, basic punctuation. Strip unsafe chars."""
        cleaned = re.sub(r'[\\/:*?"<>|]', "", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len]
        return cleaned or "video"

    async def download(self, item: PromptItem) -> bool:
        try:
            if not item.result_video_url:
                logger.warning("No video URL for item %d", item.index)
                self.download_failed.emit(item.index, "No video URL")
                return False

            desc = item.raw_prompt or item.prompt_text
            # Strip bracket markup for clean filename
            desc = re.sub(r'\[([^\]]+)\]', r'\1', desc)
            filename = f"{item.index + 1:03d}_{self._sanitize_filename(desc)}.mp4"
            filepath = os.path.join(self._output_dir, filename)
            os.makedirs(self._output_dir, exist_ok=True)

            self.download_started.emit(item.index, filepath)

            def on_progress(received: int, total: int):
                self.download_progress.emit(item.index, received, total)

            await asyncio.sleep(0.05)

            success = await self._client.download_video(
                item.result_video_url, filepath, progress_callback=on_progress
            )

            if success:
                item.result_video_path = filepath
                self.download_finished.emit(item.index, filepath)
                return True
            else:
                self.download_failed.emit(item.index, "Download failed")
                return False
        except Exception:
            logger.exception("下载第 %d 项视频异常", item.index)
            self.download_failed.emit(item.index, f"下载异常: {item.result_video_url}")
            return False
