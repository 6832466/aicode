"""任务管理器 - 任务队列与线程池"""
import os
import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from PySide6.QtCore import QObject, Signal

from app.core.download_engine import DownloadEngine
from app.core.settings_manager import SettingsManager
from app.utils.file_utils import generate_filename, get_save_path
from app.utils.logger import get_logger

_log = get_logger('TaskManager')


class TaskStatus(Enum):
    WAITING = 'waiting'
    PARSING = 'parsing'
    DOWNLOADING = 'downloading'
    PAUSED = 'paused'
    COMPLETED = 'completed'
    FAILED = 'failed'


@dataclass
class TaskInfo:
    uid: str
    url: str
    platform: str = ''
    video_id: str = ''
    status: TaskStatus = TaskStatus.WAITING
    # 视频信息（解析后填充）
    title: str = ''
    author: str = ''
    duration: str = ''
    cover_url: str = ''
    ext: str = 'mp4'
    size_estimate: int = 0
    # 下载进度
    progress: int = 0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: str = ''
    # 文件
    save_path: str = ''
    filename: str = ''
    # 错误
    error_msg: str = ''
    retry_count: int = 0
    # 内部
    _cancel_flag: threading.Event = field(default_factory=threading.Event)
    _raw_info: dict = field(default_factory=dict)


class TaskManager(QObject):
    task_added = Signal(str)
    task_updated = Signal(str)
    task_removed = Signal(str)
    task_status_changed = Signal(str, object)
    task_progress = Signal(str, int, int, int, str)
    parse_finished = Signal(str, bool)

    def __init__(self, settings: SettingsManager, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._engine = DownloadEngine(
            ffmpeg_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     '..', '..', '..', 'eaglepy310', 'ffmpeg', 'bin', 'ffmpeg.exe')
        )
        self._refresh_proxy()
        self._tasks: dict[str, TaskInfo] = {}
        self._queue: list[str] = []
        self._lock = threading.Lock()
        self._active_count = 0
        self._running = True
        self._pending_parse: list[tuple[str, str]] = []
        self._auto_start = False  # 用户点了"全部开始"后，后续解析完自动入队

        self._scheduler = threading.Thread(target=self._scheduler_loop, daemon=True, name='Scheduler')
        self._scheduler.start()

        self._parse_thread = threading.Thread(target=self._parse_loop, daemon=True, name='ParseThread')
        self._parse_thread.start()

        _log.info('TaskManager 已初始化')

    @property
    def tasks(self) -> dict:
        return self._tasks

    def _refresh_proxy(self):
        mode = self._settings.get('network.proxy_mode', 'system')
        url = self._settings.get('network.proxy_url', '')
        self._engine.set_proxy(mode, url)

    def update_proxy(self):
        self._refresh_proxy()

    def add_task(self, url: str) -> str:
        import uuid
        from app.utils.link_utils import detect_platform, extract_video_id
        uid = str(uuid.uuid4())[:8]
        platform = detect_platform(url) or 'unknown'
        video_id = extract_video_id(url)

        task = TaskInfo(uid=uid, url=url, platform=platform, video_id=video_id)
        with self._lock:
            self._tasks[uid] = task
            self._pending_parse.append((uid, url))

        _log.info(f'添加任务: {uid} platform={platform}')
        self.task_added.emit(uid)
        return uid

    def add_batch(self, urls: list[str]) -> list[str]:
        return [self.add_task(url) for url in urls]

    def start_task(self, uid: str):
        _log.info(f'start_task: {uid}')
        try:
            with self._lock:
                if uid not in self._tasks:
                    _log.warning(f'start_task: uid={uid} 不存在')
                    return
                task = self._tasks[uid]
                old_status = task.status

                # 未解析的任务不允许开始下载
                if not task._raw_info.get('download_url'):
                    if task.status in (TaskStatus.WAITING, TaskStatus.PARSING):
                        _log.warning(f'start_task: uid={uid} 尚未解析完成，拒绝开始下载')
                        return
                    # FAILED/PAUSED 但没有 download_url，也拒绝
                    _log.warning(f'start_task: uid={uid} 无有效下载链接，拒绝开始下载')
                    return

                if task.status == TaskStatus.PAUSED:
                    task.status = TaskStatus.WAITING
                    task._cancel_flag.clear()
                elif task.status == TaskStatus.FAILED:
                    task.status = TaskStatus.WAITING
                    task.retry_count = 0
                    task._cancel_flag.clear()
                elif task.status == TaskStatus.WAITING:
                    pass  # 已在等待
                else:
                    _log.debug(f'start_task: uid={uid} 状态={old_status} 不处理')
                    return
                if task.status == TaskStatus.WAITING and uid not in self._queue:
                    self._queue.append(uid)
                _log.info(f'start_task: uid={uid} {old_status.value} -> {task.status.value}')
            # 锁外发射信号
            self.task_status_changed.emit(uid, task.status)
            self.task_updated.emit(uid)
        except Exception as e:
            _log.exception(f'start_task 异常: {e}')

    def pause_task(self, uid: str):
        _log.info(f'pause_task: {uid}')
        try:
            with self._lock:
                if uid not in self._tasks:
                    return
                task = self._tasks[uid]
                if task.status in (TaskStatus.DOWNLOADING, TaskStatus.WAITING):
                    old = task.status
                    task.status = TaskStatus.PAUSED
                    task._cancel_flag.set()
                    if uid in self._queue:
                        self._queue.remove(uid)
                    if old == TaskStatus.DOWNLOADING:
                        self._active_count = max(0, self._active_count - 1)
                    _log.info(f'pause_task: uid={uid} {old.value} -> paused')
            self.task_status_changed.emit(uid, task.status)
            self.task_updated.emit(uid)
        except Exception as e:
            _log.exception(f'pause_task 异常: {e}')

    def remove_task(self, uid: str):
        _log.info(f'remove_task: {uid}')
        try:
            with self._lock:
                if uid not in self._tasks:
                    return
                task = self._tasks[uid]
                task._cancel_flag.set()
                if uid in self._queue:
                    self._queue.remove(uid)
                if task.status == TaskStatus.DOWNLOADING:
                    self._active_count = max(0, self._active_count - 1)
                del self._tasks[uid]
            self.task_removed.emit(uid)
        except Exception as e:
            _log.exception(f'remove_task 异常: {e}')

    def pause_all(self):
        _log.info('pause_all')
        with self._lock:
            self._auto_start = False  # 清除自动开始标记
            for uid in list(self._queue):
                self._queue.remove(uid)
            for uid, task in self._tasks.items():
                if task.status == TaskStatus.DOWNLOADING:
                    task.status = TaskStatus.PAUSED
                    task._cancel_flag.set()
                    self._active_count = max(0, self._active_count - 1)
                    self.task_status_changed.emit(uid, task.status)
                    self.task_updated.emit(uid)
                elif task.status == TaskStatus.WAITING:
                    task.status = TaskStatus.PAUSED
                    task._cancel_flag.set()
                    self.task_status_changed.emit(uid, task.status)
                    self.task_updated.emit(uid)

    def start_all(self):
        _log.info('start_all')
        changed = []
        with self._lock:
            self._auto_start = True  # 标记: 后续解析完的任务自动入队
            for uid, task in self._tasks.items():
                # 未解析的不入队，靠 _auto_start 标志在解析完后自动入队
                if not task._raw_info.get('download_url'):
                    continue
                if task.status == TaskStatus.WAITING:
                    if uid not in self._queue:
                        self._queue.append(uid)
                        changed.append(uid)
                elif task.status == TaskStatus.PAUSED:
                    task.status = TaskStatus.WAITING
                    task._cancel_flag.clear()
                    if uid not in self._queue:
                        self._queue.append(uid)
                    changed.append(uid)
                elif task.status == TaskStatus.FAILED:
                    task.status = TaskStatus.WAITING
                    task.retry_count = 0
                    task._cancel_flag.clear()
                    if uid not in self._queue:
                        self._queue.append(uid)
                    changed.append(uid)
        for uid in changed:
            self.task_updated.emit(uid)

    def rename_task(self, uid: str, new_name: str):
        with self._lock:
            if uid in self._tasks:
                task = self._tasks[uid]
                if task.status == TaskStatus.COMPLETED and task.save_path and os.path.exists(task.save_path):
                    new_path = os.path.join(os.path.dirname(task.save_path), new_name)
                    os.rename(task.save_path, new_path)
                    task.save_path = new_path
                    task.filename = new_name
                    self.task_updated.emit(uid)

    def _parse_loop(self):
        _log.info('解析线程启动')
        while self._running:
            try:
                with self._lock:
                    if self._pending_parse:
                        uid, url = self._pending_parse.pop(0)
                    else:
                        uid, url = None, None

                if uid and url:
                    self._do_parse(uid, url)
                else:
                    time.sleep(0.1)
            except Exception as e:
                _log.exception(f'_parse_loop 异常: {e}')
                time.sleep(1)

    def _do_parse(self, uid: str, url: str):
        _log.info(f'解析: {uid}')
        try:
            with self._lock:
                if uid not in self._tasks:
                    return
                task = self._tasks[uid]
                task.status = TaskStatus.PARSING
            self.task_status_changed.emit(uid, task.status)
            self.task_updated.emit(uid)

            # 带超时的解析 (防止快手 DrissionPage 等卡死)
            info = [None]
            parse_error = [None]

            def _run_parse():
                try:
                    info[0] = self._engine.parse_video(url)
                except Exception as e:
                    parse_error[0] = e

            parse_thread = threading.Thread(target=_run_parse, daemon=True)
            parse_thread.start()
            parse_thread.join(timeout=60)  # 单次解析最多等60秒

            if parse_thread.is_alive():
                _log.warning(f'解析超时: {uid} (60秒), 跳过')
                info[0] = None  # 超时当失败处理
            elif parse_error[0]:
                raise parse_error[0]

            with self._lock:
                if uid not in self._tasks:
                    return
                task = self._tasks[uid]
                if info[0]:
                    task.title = info[0].get('title', '')
                    task.author = info[0].get('author', '')
                    task.duration = info[0].get('duration', '')
                    task.cover_url = info[0].get('cover_url', '')
                    task.ext = info[0].get('ext', 'mp4')
                    task.size_estimate = info[0].get('size_estimate', 0)
                    task._raw_info = info[0]
                    parsed_platform = info[0].get('platform', '')
                    if parsed_platform:
                        task.platform = parsed_platform
                    parsed_id = info[0].get('video_id', '')
                    if parsed_id:
                        task.video_id = parsed_id
                    elif not task.video_id:
                        task.video_id = parsed_id
                    task.status = TaskStatus.WAITING
                    # 如果用户已点击"全部开始"，自动加入下载队列
                    if self._auto_start and uid not in self._queue:
                        self._queue.append(uid)
                        _log.info(f'自动入队: {uid} (_auto_start=True)')
                    _log.info(f'解析成功: {uid} title={task.title} platform={task.platform}')
                else:
                    task.status = TaskStatus.FAILED
                    task.error_msg = '链接解析超时或失败，视频可能不存在或已失效'
                    _log.warning(f'解析失败: {uid}')

            self.task_status_changed.emit(uid, task.status)
            self.task_updated.emit(uid)
            self.parse_finished.emit(uid, info[0] is not None)
        except Exception as e:
            _log.exception(f'_do_parse 异常: {uid} {e}')
            with self._lock:
                if uid in self._tasks:
                    self._tasks[uid].status = TaskStatus.FAILED
                    self._tasks[uid].error_msg = f'解析异常: {str(e)}'
            self.task_status_changed.emit(uid, TaskStatus.FAILED)
            self.task_updated.emit(uid)
            self.parse_finished.emit(uid, False)

    def _scheduler_loop(self):
        _log.info('调度线程启动')
        while self._running:
            try:
                with self._lock:
                    max_concurrent = self._settings.max_concurrent
                    can_start = max_concurrent - self._active_count

                for _ in range(can_start):
                    uid_to_start = None
                    with self._lock:
                        available = [u for u in self._queue
                                     if u in self._tasks
                                     and self._tasks[u].status == TaskStatus.WAITING]
                        if not available:
                            break
                        uid_to_start = available[0]
                        self._queue.remove(uid_to_start)
                        task = self._tasks[uid_to_start]
                        task.status = TaskStatus.DOWNLOADING
                        task._cancel_flag.clear()
                        self._active_count += 1

                    if uid_to_start:
                        self.task_status_changed.emit(uid_to_start, TaskStatus.DOWNLOADING)
                        self.task_updated.emit(uid_to_start)
                        t = threading.Thread(target=self._do_download, args=(uid_to_start,),
                                           daemon=True, name=f'DL-{uid_to_start}')
                        t.start()

                time.sleep(0.5)
            except Exception as e:
                _log.exception(f'_scheduler_loop 异常: {e}')
                time.sleep(1)

    def _do_download(self, uid: str):
        _log.info(f'下载开始: {uid}')
        try:
            with self._lock:
                if uid not in self._tasks:
                    return
                task = self._tasks[uid]

            # 安全检查: 未解析的任务拒绝下载
            video_info = task._raw_info if task._raw_info and task._raw_info.get('download_url') else None
            if not video_info:
                _log.error(f'下载拒绝: {uid} 尚未解析或下载链接无效')
                with self._lock:
                    if uid in self._tasks:
                        task = self._tasks[uid]
                        task.status = TaskStatus.FAILED
                        task.error_msg = '尚未解析完成，请等待解析后再开始下载'
                        self._active_count = max(0, self._active_count - 1)
                self.task_status_changed.emit(uid, TaskStatus.FAILED)
                self.task_updated.emit(uid)
                return

            template = self._settings.naming_template
            filename = generate_filename(
                template, title=task.title, platform=task.platform,
                fmt=task.ext or 'mp4', video_id=task.video_id)
            full_filename = f"{filename}.{task.ext or 'mp4'}"
            save_dir = self._settings.save_path
            if self._settings.sub_by_platform and task.platform:
                from app.utils.link_utils import source_to_folder
                save_dir = os.path.join(save_dir, source_to_folder(task.platform))
            if self._settings.sub_by_date:
                import datetime
                save_dir = os.path.join(save_dir, datetime.datetime.now().strftime('%Y-%m-%d'))
            os.makedirs(save_dir, exist_ok=True)

            save_path = os.path.join(save_dir, full_filename)
            from app.utils.file_utils import resolve_filename_conflict
            save_path = resolve_filename_conflict(save_path)

            with self._lock:
                if uid not in self._tasks:
                    return
                task = self._tasks[uid]
                task.save_path = save_path
                task.filename = os.path.basename(save_path)

            result = self._engine.download(
                video_info,
                save_dir,
                os.path.basename(save_path),
                progress_callback=lambda p, s, d, t, e=None: self._on_progress(uid, p, s, d, t, e),
            )

            with self._lock:
                if uid not in self._tasks:
                    return
                task = self._tasks[uid]
                if result and os.path.exists(result):
                    task.status = TaskStatus.COMPLETED
                    task.progress = 100
                    task.save_path = result
                    self._update_stats(task)
                    _log.info(f'下载完成: {uid}')
                elif task.status != TaskStatus.PAUSED:
                    auto_retry = self._settings.get('download.auto_retry', True)
                    max_retries = self._settings.get('download.retry_count', 3)
                    if auto_retry and task.retry_count < max_retries:
                        task.retry_count += 1
                        task.status = TaskStatus.WAITING
                        task._cancel_flag.clear()
                        self._queue.append(uid)
                        _log.info(f'下载重试: {uid} #{task.retry_count}')
                        self._active_count = max(0, self._active_count - 1)
                        self.task_status_changed.emit(uid, task.status)
                        self.task_updated.emit(uid)
                        time.sleep(1)  # 重试前短暂等待
                        return
                    task.status = TaskStatus.FAILED
                    if not task.error_msg:
                        task.error_msg = '下载失败'
                    _log.warning(f'下载失败: {uid}')

                self._active_count = max(0, self._active_count - 1)

            self.task_status_changed.emit(uid, task.status)
            self.task_updated.emit(uid)
        except Exception as e:
            _log.exception(f'_do_download 异常: {uid} {e}')
            with self._lock:
                if uid in self._tasks:
                    task = self._tasks[uid]
                    task.status = TaskStatus.FAILED
                    task.error_msg = str(e)
                    self._active_count = max(0, self._active_count - 1)
            self.task_status_changed.emit(uid, TaskStatus.FAILED)
            self.task_updated.emit(uid)

    def _on_progress(self, uid: str, percent: int, speed: float,
                     downloaded: int, total: int, error: str = None):
        try:
            speed_str = ''
            with self._lock:
                if uid not in self._tasks:
                    return
                task = self._tasks[uid]
                if error:
                    task.error_msg = error
                    return
                task.progress = percent
                task.downloaded_bytes = downloaded
                task.total_bytes = total
                task.speed = self._format_speed(speed)
                speed_str = task.speed
            self.task_progress.emit(uid, percent, downloaded, total, speed_str)
        except Exception as e:
            _log.exception(f'_on_progress 异常: {e}')

    def _format_speed(self, speed: float) -> str:
        if speed <= 0:
            return ''
        if speed < 1024:
            return f'{speed:.0f} B/s'
        elif speed < 1024 * 1024:
            return f'{speed / 1024:.1f} KB/s'
        return f'{speed / (1024 * 1024):.1f} MB/s'

    def _update_stats(self, task: TaskInfo):
        import datetime
        stats = self._settings.get('stats')
        today = datetime.date.today().isoformat()
        if stats.get('today_date') != today:
            stats['today_date'] = today
            stats['today_count'] = 0
            stats['today_size'] = 0
        stats['total_count'] = stats.get('total_count', 0) + 1
        stats['total_size'] = stats.get('total_size', 0) + task.total_bytes
        stats['today_count'] = stats.get('today_count', 0) + 1
        stats['today_size'] = stats.get('today_size', 0) + task.total_bytes
        self._settings.set('stats', stats)

        completed = self._settings.get('completed_downloads', [])
        completed.append({
            'uid': task.uid,
            'title': task.title,
            'url': task.url,
            'platform': task.platform,
            'author': task.author,
            'save_path': task.save_path,
            'filename': task.filename,
            'size': task.total_bytes,
            'timestamp': time.time(),
        })
        self._settings.set('completed_downloads', completed)

    def stop(self):
        _log.info('TaskManager 停止')
        self._running = False
        self.pause_all()
