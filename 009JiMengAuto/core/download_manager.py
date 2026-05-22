"""即梦下载器 - aiohttp 批量下载 + 断点续传"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

import aiofiles
import aiohttp
from PySide6.QtCore import QObject, QThread, Signal

from data.models import DownloadTask, DownloadStatus
from utils.helpers import generate_filename

logger = logging.getLogger(__name__)

# 下载状态持久化
DOWNLOADS_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "downloads_state.json"


class DownloadManager(QObject):
    """异步下载管理器"""

    # 信号
    download_added = Signal(DownloadTask)
    download_updated = Signal(DownloadTask)  # 进度更新
    download_completed = Signal(DownloadTask)
    download_failed = Signal(DownloadTask, str)

    def __init__(self, save_dir: str = "D:/Downloads/jm_videos",
                 max_concurrent: int = 3, resume_enabled: bool = True,
                 parent=None):
        super().__init__(parent)
        self._save_dir = Path(save_dir)
        self._max_concurrent = max_concurrent
        self._resume_enabled = resume_enabled
        self._downloads: dict[str, DownloadTask] = {}
        self._thread: Optional[QThread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._running = False
        self._active_tasks: set[str] = set()
        self._stopped = False

        self._load_state()
        self._save_dir.mkdir(parents=True, exist_ok=True)

    # ── 配置 ──

    def set_save_dir(self, path: str):
        self._save_dir = Path(path)
        self._save_dir.mkdir(parents=True, exist_ok=True)
        self._save_state()

    def set_max_concurrent(self, n: int):
        self._max_concurrent = n

    # ── 任务管理 ──

    def add_download(self, url: str, scene: str,
                     task_id: Optional[str] = None,
                     filename: Optional[str] = None) -> DownloadTask:
        """添加下载任务"""
        name = filename or generate_filename(scene)
        dt = DownloadTask(
            url=url,
            scene=scene,
            filename=name,
            task_id=task_id,
            save_path=str(self._save_dir / name),
            status=DownloadStatus.PENDING,
        )
        self._downloads[dt.id] = dt
        self._save_state()
        self.download_added.emit(dt)
        logger.info("添加下载: %s → %s", scene, name)
        return dt

    def remove_download(self, download_id: str):
        if download_id in self._downloads:
            del self._downloads[download_id]
            self._save_state()

    def get_download(self, download_id: str) -> Optional[DownloadTask]:
        return self._downloads.get(download_id)

    def get_all_downloads(self) -> list[DownloadTask]:
        return list(self._downloads.values())

    def get_downloads_by_status(self, status: DownloadStatus) -> list[DownloadTask]:
        return [d for d in self._downloads.values() if d.status == status]

    def clear_completed(self):
        """清空已完成的下载任务"""
        to_remove = [did for did, d in self._downloads.items()
                     if d.status == DownloadStatus.COMPLETED]
        for did in to_remove:
            del self._downloads[did]
        self._save_state()

    # ── 下载控制 ──

    def start_downloads(self, download_ids: list[str]):
        """批量启动下载"""
        if not self._running:
            self._start_loop()

        for did in download_ids:
            task = self._downloads.get(did)
            if task and task.status in (DownloadStatus.PENDING, DownloadStatus.FAILED, DownloadStatus.PAUSED):
                task.status = DownloadStatus.PENDING
                self._active_tasks.add(did)
                asyncio.run_coroutine_threadsafe(
                    self._download_task(did), self._loop
                )

    def pause(self, download_id: str):
        """暂停下载"""
        task = self._downloads.get(download_id)
        if task and task.status == DownloadStatus.DOWNLOADING:
            task.status = DownloadStatus.PAUSED
            self._active_tasks.discard(download_id)
            self._save_state()
            self.download_updated.emit(task)

    def resume(self, download_id: str):
        """继续下载"""
        task = self._downloads.get(download_id)
        if task and task.status == DownloadStatus.PAUSED:
            self.start_downloads([download_id])

    def retry(self, download_id: str):
        """重试下载"""
        task = self._downloads.get(download_id)
        if task:
            task.downloaded_bytes = 0
            task.progress = 0.0
            task.status = DownloadStatus.PENDING
            self._save_state()
            self.download_updated.emit(task)
            self.start_downloads([download_id])

    def stop_all(self):
        """停止所有下载"""
        self._stopped = True
        for did in list(self._active_tasks):
            task = self._downloads.get(did)
            if task and task.status == DownloadStatus.DOWNLOADING:
                task.status = DownloadStatus.PAUSED
                self.download_updated.emit(task)
        self._active_tasks.clear()
        self._save_state()

    # ── 内部：异步引擎 ──

    def _start_loop(self):
        """在 QThread 中启动 asyncio 事件循环"""
        self._thread = QThread()
        self._thread.started.connect(self._run_loop)
        self._thread.finished.connect(self._cleanup_loop)
        self._running = True
        self._stopped = False
        self._thread.start()

    def _run_loop(self):
        """运行事件循环"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _cleanup_loop(self):
        if self._loop and not self._loop.is_closed():
            self._loop.close()
        self._running = False

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)

    async def _download_task(self, download_id: str):
        """执行单个下载"""
        await self._ensure_session()

        task = self._downloads.get(download_id)
        if not task:
            return

        async with self._semaphore:
            if self._stopped:
                return

            task.status = DownloadStatus.DOWNLOADING
            self.download_updated.emit(task)

            temp_path = self._save_dir / f"{task.filename}.tmp"
            headers = {}

            if self._resume_enabled and temp_path.exists():
                task.downloaded_bytes = temp_path.stat().st_size
                headers["Range"] = f"bytes={task.downloaded_bytes}-"

            try:
                async with self._session.get(task.url, headers=headers,
                                             timeout=aiohttp.ClientTimeout(total=600)) as resp:
                    if resp.status == 416:  # Range not satisfiable
                        # 文件已完整下载
                        temp_path.rename(self._save_dir / task.filename)
                        task.status = DownloadStatus.COMPLETED
                        task.progress = 1.0
                        self._save_state()
                        self.download_completed.emit(task)
                        return

                    if resp.status not in (200, 206):
                        task.status = DownloadStatus.FAILED
                        self._save_state()
                        self.download_failed.emit(task, f"HTTP {resp.status}")
                        return

                    total = task.file_size or int(resp.headers.get("Content-Length", 0))
                    if total > 0:
                        task.file_size = total

                    mode = "ab" if (self._resume_enabled and task.downloaded_bytes > 0) else "wb"
                    async with aiofiles.open(temp_path, mode) as f:
                        async for chunk in resp.content.iter_chunked(65536):
                            if self._stopped or task.status == DownloadStatus.PAUSED:
                                return
                            await f.write(chunk)
                            task.downloaded_bytes += len(chunk)
                            if total > 0:
                                task.progress = min(task.downloaded_bytes / total, 1.0)
                            self.download_updated.emit(task)

                # 下载完成
                temp_path.rename(self._save_dir / task.filename)
                task.status = DownloadStatus.COMPLETED
                task.progress = 1.0
                task.save_path = str(self._save_dir / task.filename)
                self._save_state()
                self.download_completed.emit(task)

            except asyncio.CancelledError:
                task.status = DownloadStatus.PAUSED
                self._save_state()
                self.download_updated.emit(task)
            except Exception as e:
                task.status = DownloadStatus.FAILED
                self._save_state()
                self.download_failed.emit(task, str(e))
            finally:
                self._active_tasks.discard(download_id)

    # ── 持久化 ──

    def _save_state(self):
        try:
            DOWNLOADS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "save_dir": str(self._save_dir),
                "max_concurrent": self._max_concurrent,
                "resume_enabled": self._resume_enabled,
                "downloads": [d.to_dict() for d in self._downloads.values()],
            }
            DOWNLOADS_STATE_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("保存下载状态失败: %s", e)

    def _load_state(self):
        if not DOWNLOADS_STATE_PATH.exists():
            return
        try:
            data = json.loads(DOWNLOADS_STATE_PATH.read_text(encoding="utf-8"))
            self._save_dir = Path(data.get("save_dir", self._save_dir))
            self._max_concurrent = data.get("max_concurrent", self._max_concurrent)
            self._resume_enabled = data.get("resume_enabled", self._resume_enabled)
            for d_dict in data.get("downloads", []):
                task = DownloadTask.from_dict(d_dict)
                # 重启后，未完成的恢复为待下载
                if task.status in (DownloadStatus.DOWNLOADING,):
                    task.status = DownloadStatus.PENDING
                self._downloads[task.id] = task
            logger.info("加载下载状态: %d 条", len(self._downloads))
        except Exception as e:
            logger.error("加载下载状态失败: %s", e)

    def close(self):
        """清理资源"""
        self.stop_all()
        if self._thread:
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.quit()
            self._thread.wait(3000)
        if self._session and not self._session.closed:
            self._loop.call_soon_threadsafe(self._session.close)
