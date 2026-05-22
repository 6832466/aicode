"""下载 Worker — 在 QThread 中执行视频下载, 带进度信号, 支持按剧分组 + 后台获取播放地址"""
import copy
import time as _time
import json as _json
import logging
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal, QObject, Qt

from hgDown import HEADERS, sanitize_filename, build_episode_url, extract_ssr_data, parse_page_data

logger = logging.getLogger("hongguo")


class DownloadWorker(QThread):
    """单个视频文件下载器"""
    progress = Signal(int, int, str, str)    # bytes_done, bytes_total, speed, eta
    dl_finished = Signal(bool, str, str)      # success, message, filepath (renamed to avoid overriding QThread.finished)

    def __init__(self, url: str, filepath: Path, task_name: str = "", max_retries: int = 3):
        super().__init__()
        self._url = url
        self._filepath = filepath
        self._task_name = task_name
        self._max_retries = max_retries
        self._stop_flag = False

    def run(self):
        if self._filepath.exists():
            self.dl_finished.emit(True, "已存在", str(self._filepath))
            return

        headers = {**HEADERS, "Referer": "https://novelquickapp.com/"}

        for attempt in range(1, self._max_retries + 1):
            if self._stop_flag:
                self.dl_finished.emit(False, "已取消", str(self._filepath))
                return

            try:
                resp = requests.get(self._url, headers=headers, stream=True, timeout=60)
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                last_update = _time.time()
                last_bytes = 0

                self._filepath.parent.mkdir(parents=True, exist_ok=True)
                with open(self._filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if self._stop_flag:
                            f.close()
                            self._filepath.unlink(missing_ok=True)
                            self.dl_finished.emit(False, "已取消", str(self._filepath))
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = _time.time()
                            if now - last_update >= 0.25:
                                elapsed = now - last_update
                                speed = (downloaded - last_bytes) / max(elapsed, 0.001)
                                speed_str = self._format_speed(speed)
                                eta = ""
                                if total > 0 and speed > 0:
                                    eta_sec = int((total - downloaded) / speed)
                                    eta = f"{eta_sec // 60}:{eta_sec % 60:02d}"
                                self.progress.emit(downloaded, total, speed_str, eta)
                                last_update = now
                                last_bytes = downloaded

                if total > 0 and abs(downloaded - total) > 100:
                    logger.warning(f"预期 {total} 字节, 实际 {downloaded} 字节")

                self.progress.emit(downloaded, downloaded, "", "完成")
                self.dl_finished.emit(True, "下载完成", str(self._filepath))
                return

            except Exception as e:
                if attempt < self._max_retries:
                    wait = attempt * 2
                    logger.info(f"重试 {attempt}/{self._max_retries}: {e}")
                    _time.sleep(wait)
                else:
                    logger.error(f"下载失败: {e}")
                    if self._filepath.exists():
                        self._filepath.unlink()
                    self.dl_finished.emit(False, str(e), str(self._filepath))
                    return

    def stop(self):
        self._stop_flag = True

    @staticmethod
    def _format_speed(bytes_per_sec: float) -> str:
        if bytes_per_sec >= 1024 * 1024:
            return f"{bytes_per_sec / 1024 / 1024:.1f} MB/s"
        elif bytes_per_sec >= 1024:
            return f"{bytes_per_sec / 1024:.0f} KB/s"
        return f"{bytes_per_sec:.0f} B/s"


class UrlFetcher(QThread):
    """单集播放地址获取器"""
    url_ready = Signal(int, int, str)   # group_id, task_id, play_url
    fetch_failed = Signal(int, int)     # group_id, task_id

    def __init__(self, group_id: int, task_id: int, vid: str,
                 base_params: dict, page_path: str):
        super().__init__()
        self._group_id = group_id
        self._task_id = task_id
        self._vid = vid
        self._base_params = base_params
        self._page_path = page_path
        self._stop_flag = False

    def run(self):
        if self._stop_flag:
            return
        try:
            session = requests.Session()
            session.headers.update(HEADERS)
            url = build_episode_url(self._base_params, self._vid, self._page_path)
            resp = session.get(url, allow_redirects=True, timeout=30)
            ssr = extract_ssr_data(resp.text)
            if ssr:
                page_data, _ = parse_page_data(ssr)
                if page_data and page_data["series_data"].get("play_url"):
                    play_url = page_data["series_data"]["play_url"]
                    self.url_ready.emit(self._group_id, self._task_id, play_url)
                    return
        except Exception as e:
            logger.warning(f"获取第 {self._task_id} 集播放地址失败: {e}")
        self.fetch_failed.emit(self._group_id, self._task_id)

    def stop(self):
        self._stop_flag = True


@dataclass
class DownloadTask:
    """队列中的下载任务"""
    task_id: int
    group_id: int
    series_name: str
    episode_index: int
    episode_name: str
    url: str = ""
    filepath: Path = field(default_factory=Path)
    status: str = "fetching_url"  # fetching_url, pending, downloading, done, failed
    vid: str = ""
    base_params: dict = field(default_factory=dict)
    page_path: str = ""


@dataclass
class SeriesGroup:
    """一个剧的下载分组"""
    group_id: int
    series_name: str
    cover_url: str
    total_episodes: int
    output_dir: Path


class DownloadQueueManager(QObject):
    """管理并发下载队列, 支持按剧分组 + 后台获取播放地址"""

    # 按剧分组信号
    series_group_added = Signal(int, str, str, int)  # group_id, name, cover_url, total_episodes

    # 任务信号 (带 group_id)
    task_started = Signal(int, int)                      # group_id, task_id (开始获取URL)
    task_downloading = Signal(int, int)                   # group_id, task_id (开始下载)
    task_progress = Signal(int, int, int, int, str, str)  # group_id, task_id, done, total, speed, eta
    task_finished = Signal(int, int, bool, str, str)     # group_id, task_id, success, msg, filepath

    # 全局信号
    queue_updated = Signal()
    series_group_done = Signal(int, int, int)  # group_id, success_count, fail_count
    all_done = Signal(int, int)                # total_success, total_fail

    def __init__(self, max_concurrent: int = 3, max_retries: int = 3):
        super().__init__()
        self._max_concurrent = max_concurrent
        self._max_url_fetchers = max(2, max_concurrent)  # URL 获取并发数
        self._max_retries = max_retries
        self._pending: deque[DownloadTask] = deque()
        self._all_tasks: dict[int, DownloadTask] = {}
        self._active_downloads: dict[int, DownloadWorker] = {}
        self._active_fetchers: dict[int, UrlFetcher] = {}
        self._fetch_queue: deque[tuple] = deque()  # (gid, tid, vid, base_params, page_path)
        self._results: dict[int, tuple[bool, str, str]] = {}
        self._groups: dict[int, SeriesGroup] = {}
        self._group_results: dict[int, dict[str, int]] = {}
        self._next_id = 0
        self._next_group_id = 0

    def add_series_group(self, series_name: str, episodes: list[int],
                         vid_list: list[str], base_params: dict, page_path: str,
                         output_dir: Path, cover_url: str = "", total_episodes: int = 0
                         ) -> tuple[int, list[int]]:
        """添加一个剧的下载分组, 立即入队, 后台多线程获取播放地址。
        返回 (group_id, task_ids)。"""
        try:
            gid = self._next_group_id
            self._next_group_id += 1

            safe_name = sanitize_filename(series_name)
            series_dir = output_dir / safe_name
            series_dir.mkdir(parents=True, exist_ok=True)

            group = SeriesGroup(
                group_id=gid,
                series_name=series_name,
                cover_url=cover_url,
                total_episodes=total_episodes or len(episodes),
                output_dir=series_dir,
            )
            self._groups[gid] = group
            self._group_results[gid] = {"success": 0, "fail": 0, "total": len(episodes)}

            tids = []
            for i, ep in enumerate(episodes):
                vid = vid_list[i] if i < len(vid_list) else ""
                if not vid:
                    logger.warning(f"第 {ep} 集无 vid, 跳过")
                    continue
                tid = self._next_id
                self._next_id += 1
                ep_name = f"第{ep:02d}集.mp4"
                task = DownloadTask(
                    task_id=tid,
                    group_id=gid,
                    series_name=series_name,
                    episode_index=ep,
                    episode_name=ep_name,
                    url="",
                    filepath=series_dir / ep_name,
                    status="fetching_url",
                    vid=vid,
                    base_params=copy.deepcopy(base_params),
                    page_path=page_path,
                )
                self._pending.append(task)
                self._all_tasks[tid] = task
                tids.append(tid)

                # 入队 URL 获取请求 (限制并发, 由 _start_fetchers 调度)
                self._fetch_queue.append((gid, tid, vid, copy.deepcopy(base_params), page_path))

            self.series_group_added.emit(gid, series_name, cover_url, total_episodes)
            self._start_fetchers()
            self._start_next()
            self.queue_updated.emit()
            return gid, tids
        except Exception:
            logger.exception(f"创建下载分组失败: {series_name}")
            raise

    def _start_fetchers(self):
        """启动排队的 URL 获取器 (最多 _max_url_fetchers 个并发)"""
        while len(self._active_fetchers) < self._max_url_fetchers and self._fetch_queue:
            gid, tid, vid, base_params, page_path = self._fetch_queue.popleft()
            if tid not in self._all_tasks:
                continue
            fetcher = UrlFetcher(gid, tid, vid, base_params, page_path)
            fetcher.url_ready.connect(self._on_url_ready, Qt.QueuedConnection)
            fetcher.fetch_failed.connect(self._on_url_fetch_failed, Qt.QueuedConnection)
            self._active_fetchers[tid] = fetcher
            fetcher.start()

    def _on_url_ready(self, group_id: int, task_id: int, play_url: str):
        """播放地址获取成功 -> 更新 task, 开始下载"""
        if task_id in self._active_fetchers:
            fetcher = self._active_fetchers.pop(task_id)
            if fetcher.isRunning():
                fetcher.wait(1000)

        task = self._all_tasks.get(task_id)
        if task:
            task.url = play_url
            task.status = "pending"

        self.task_downloading.emit(group_id, task_id)
        self._start_fetchers()
        self._start_next()
        self.queue_updated.emit()

    def _on_url_fetch_failed(self, group_id: int, task_id: int):
        """播放地址获取失败"""
        if task_id in self._active_fetchers:
            fetcher = self._active_fetchers.pop(task_id)
            if fetcher.isRunning():
                fetcher.wait(1000)

        task = self._all_tasks.get(task_id)
        if task:
            task.status = "failed"
            task.url = ""

        self._results[task_id] = (False, "获取播放地址失败", "")
        self.task_finished.emit(group_id, task_id, False, "获取播放地址失败", "")
        self._start_fetchers()
        self.queue_updated.emit()

        if group_id in self._group_results:
            self._group_results[group_id]["fail"] += 1
        self._check_group_done(group_id)

        if not self._active_downloads and not self._pending and not self._active_fetchers:
            self._emit_all_done()

    def _start_next(self):
        """启动等待中的下载任务 (有 URL 的 pending 任务)"""
        # 找出所有有 URL 的 pending 任务
        ready_tasks = [t for t in self._pending if t.url and t.status == "pending"]
        while len(self._active_downloads) < self._max_concurrent and ready_tasks:
            task = ready_tasks[0]
            self._pending.remove(task)
            task.status = "downloading"

            worker = DownloadWorker(task.url, task.filepath, task.episode_name, self._max_retries)
            worker.progress.connect(
                lambda done, total, speed, eta, tid=task.task_id, gid=task.group_id:
                    self.task_progress.emit(gid, tid, done, total, speed, eta),
                Qt.QueuedConnection
            )
            worker.dl_finished.connect(
                lambda success, msg, fp, tid=task.task_id, gid=task.group_id:
                    self._on_task_finished(gid, tid, success, msg, fp),
                Qt.QueuedConnection
            )

            self._active_downloads[task.task_id] = worker
            self.task_started.emit(task.group_id, task.task_id)
            worker.start()
            self.queue_updated.emit()

            # 更新就绪任务列表
            ready_tasks = [t for t in self._pending if t.url and t.status == "pending"]

    def _on_task_finished(self, group_id: int, task_id: int, success: bool, message: str, filepath: str):
        self._results[task_id] = (success, message, filepath)
        if task_id in self._active_downloads:
            worker = self._active_downloads.pop(task_id)
            if worker.isRunning():
                worker.wait(1000)

        self.task_finished.emit(group_id, task_id, success, message, filepath)
        self.queue_updated.emit()

        if group_id in self._group_results:
            if success:
                self._group_results[group_id]["success"] += 1
            else:
                self._group_results[group_id]["fail"] += 1

        self._start_next()
        self._check_group_done(group_id)

        if not self._active_downloads and not self._pending and not self._active_fetchers:
            self._emit_all_done()

    def _emit_all_done(self):
        total_success = sum(r["success"] for r in self._group_results.values())
        total_fail = sum(r["fail"] for r in self._group_results.values())
        self.all_done.emit(total_success, total_fail)

    def _check_group_done(self, group_id: int):
        stats = self._group_results.get(group_id)
        if not stats:
            return
        total = stats.get("total", 0)
        done = stats["success"] + stats["fail"]
        if total > 0 and done >= total:
            self.series_group_done.emit(group_id, stats["success"], stats["fail"])

    def set_max_concurrent(self, n: int):
        self._max_concurrent = max(1, min(n, 5))
        self._max_url_fetchers = max(2, n)
        self._start_next()

    def set_max_retries(self, n: int):
        self._max_retries = max(0, min(n, 10))

    def cancel_task(self, task_id: int):
        if task_id in self._active_downloads:
            self._active_downloads[task_id].stop()
            self._active_downloads[task_id].wait(2000)
        if task_id in self._active_fetchers:
            self._active_fetchers[task_id].stop()
            self._active_fetchers[task_id].wait(2000)
            del self._active_fetchers[task_id]
        self._fetch_queue = deque(
            item for item in self._fetch_queue if item[1] != task_id
        )
        self._pending = deque(t for t in self._pending if t.task_id != task_id)
        self._results[task_id] = (False, "已取消", "")
        self._start_fetchers()
        self.queue_updated.emit()

    def cancel_group(self, group_id: int):
        for tid in list(self._active_downloads.keys()):
            self.cancel_task(tid)
        for tid in list(self._active_fetchers.keys()):
            self.cancel_task(tid)
        self._fetch_queue = deque(
            item for item in self._fetch_queue if item[0] != group_id
        )
        self._pending = deque(t for t in self._pending if t.group_id != group_id)
        self.queue_updated.emit()

    def cancel_all(self):
        for tid in list(self._active_downloads.keys()):
            self.cancel_task(tid)
        for tid in list(self._active_fetchers.keys()):
            self.cancel_task(tid)
        self._fetch_queue.clear()
        self._pending.clear()
        self.queue_updated.emit()

    def retry_task(self, group_id: int, episode_index: int):
        """重试失败的任务 — 重新入队获取URL"""
        task = None
        for t in self._all_tasks.values():
            if t.group_id == group_id and t.episode_index == episode_index:
                task = t
                break
        if not task or not task.vid:
            logger.warning(f"无法重试: group={group_id}, ep={episode_index}, 缺少 vid")
            return
        # 清理旧结果
        self._results.pop(task.task_id, None)
        # 修正分组统计
        if group_id in self._group_results:
            self._group_results[group_id]["fail"] = max(0, self._group_results[group_id]["fail"] - 1)
        # 重置任务状态
        task.status = "fetching_url"
        task.url = ""
        # 重新入队
        self._fetch_queue.append((group_id, task.task_id, task.vid,
                                   copy.deepcopy(task.base_params), task.page_path))
        self._start_fetchers()
        self.queue_updated.emit()

    def get_active_count(self) -> int:
        return len(self._active_downloads) + len(self._active_fetchers)

    def get_pending_count(self) -> int:
        return len(self._pending)

    def get_task_by_id(self, task_id: int) -> DownloadTask | None:
        return self._all_tasks.get(task_id)

    def get_group_info(self, group_id: int) -> SeriesGroup | None:
        return self._groups.get(group_id)

    def get_group_tasks(self, group_id: int) -> list[DownloadTask]:
        """获取某个分组的所有任务"""
        return [t for t in self._all_tasks.values() if t.group_id == group_id]
