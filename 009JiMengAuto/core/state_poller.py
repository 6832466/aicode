"""状态轮询器 - 通过 dreamina CLI 查询生成状态"""

import asyncio
import logging
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal, QThread, QTimer

from data.models import Task, TaskStatus, GenerationRecord
from core.dreamina_cli import DreaminaCLI

logger = logging.getLogger(__name__)


class StatePoller(QObject):
    """状态轮询器 - 定期查询生成状态"""

    # 信号
    status_updated = Signal(str, str, str)  # task_id, status, video_url
    poll_error = Signal(str, str)           # task_id, error_msg
    poll_finished = Signal(str)             # task_id（轮询结束）

    def __init__(self, cli: DreaminaCLI, interval: int = 30, timeout: int = 1800, parent=None):
        super().__init__(parent)
        self._cli = cli
        self._interval = interval
        self._timeout = timeout
        self._polling_tasks: dict[str, dict] = {}  # task_id -> {start_time, jm_task_id}
        self._stopped = False

    def set_interval(self, seconds: int):
        """设置轮询间隔"""
        self._interval = max(10, seconds)

    def set_timeout(self, seconds: int):
        """设置超时时间"""
        self._timeout = max(60, seconds)

    def add_task_to_poll(self, task: Task):
        """添加任务到轮询队列"""
        if task.jm_task_id:
            self._polling_tasks[task.id] = {
                "start_time": time.time(),
                "jm_task_id": task.jm_task_id,
                "seq": task.seq,
                "scene": task.scene,
            }
            logger.info("添加轮询任务: %s (%s), jm_task_id=%s",
                        task.scene, task.id, task.jm_task_id)

    def remove_task_from_poll(self, task_id: str):
        """移除轮询任务"""
        if task_id in self._polling_tasks:
            del self._polling_tasks[task_id]

    def get_polling_count(self) -> int:
        """获取正在轮询的任务数"""
        return len(self._polling_tasks)

    def stop(self):
        """停止所有轮询"""
        self._stopped = True

    def reset(self):
        """重置状态"""
        self._stopped = False
        self._polling_tasks.clear()

    def poll_once(self, task_id: str) -> Optional[dict]:
        """单次轮询指定任务"""
        info = self._polling_tasks.get(task_id)
        if not info:
            return None

        jm_task_id = info["jm_task_id"]
        start_time = info["start_time"]

        # 检查超时
        elapsed = time.time() - start_time
        if elapsed > self._timeout:
            return {
                "status": "failed",
                "error": f"生成超时（{self._timeout}秒）",
                "timeout": True,
            }

        # 通过 CLI 查询结果
        result = self._cli.query_result(jm_task_id)

        if result.get("ok"):
            gen_status = result.get("gen_status", "unknown")
            video_url = result.get("video_url")

            # 状态映射
            status_map = {
                "pending": "generating",
                "processing": "generating",
                "submitted": "generating",
                "success": "completed",
                "completed": "completed",
                "failed": "failed",
                "error": "failed",
            }
            mapped_status = status_map.get(gen_status.lower(), "generating")

            return {
                "status": mapped_status,
                "video_url": video_url,
                "gen_status": gen_status,
            }
        else:
            # 查询失败，记录错误但继续轮询
            error = result.get("error", "查询失败")
            return {
                "status": "generating",  # 继续等待
                "error": error,
                "query_failed": True,
            }


class PollWorker(QObject):
    """轮询工作线程"""

    status_updated = Signal(str, str, str)  # task_id, status, video_url
    poll_error = Signal(str, str)           # task_id, error_msg
    poll_finished = Signal(str)             # task_id
    log_message = Signal(str)               # 日志消息

    def __init__(self, poller: StatePoller, parent=None):
        super().__init__(parent)
        self._poller = poller
        self._stopped = False

    def stop(self):
        """停止轮询"""
        self._stopped = True

    def run(self):
        """执行轮询循环"""
        while not self._stopped and self._poller.get_polling_count() > 0:
            for task_id in list(self._poller._polling_tasks.keys()):
                if self._stopped:
                    break

                info = self._poller._polling_tasks[task_id]
                self.log_message.emit(f"轮询 {info['scene']}: jm_task_id={info['jm_task_id']}")

                result = self._poller.poll_once(task_id)

                if result:
                    status = result.get("status")
                    video_url = result.get("video_url", "")
                    error = result.get("error", "")

                    if status in ("completed", "failed"):
                        # 轮询结束
                        self.status_updated.emit(task_id, status, video_url)
                        if error:
                            self.poll_error.emit(task_id, error)
                        self.poll_finished.emit(task_id)
                        self._poller.remove_task_from_poll(task_id)
                        self.log_message.emit(f"{info['scene']} 轮询结束: {status}")

                    elif result.get("timeout"):
                        # 超时
                        self.status_updated.emit(task_id, "failed", "")
                        self.poll_error.emit(task_id, error)
                        self.poll_finished.emit(task_id)
                        self._poller.remove_task_from_poll(task_id)

                    elif result.get("query_failed"):
                        # 查询失败，记录但继续
                        self.log_message.emit(f"{info['scene']} 查询失败: {error}")

            # 等待下一次轮询
            if not self._stopped and self._poller.get_polling_count() > 0:
                time.sleep(self._poller._interval)

        self.log_message.emit("轮询线程结束")


class PollThread(QObject):
    """轮询线程管理"""

    status_updated = Signal(str, str, str)
    poll_error = Signal(str, str)
    poll_finished = Signal(str)
    log_message = Signal(str)
    all_finished = Signal()

    def __init__(self, poller: StatePoller, parent=None):
        super().__init__(parent)
        self._poller = poller
        self._thread: Optional[QThread] = None
        self._worker: Optional[PollWorker] = None

    def start(self):
        """启动轮询线程"""
        if self._thread and self._thread.isRunning():
            return

        self._thread = QThread()
        self._worker = PollWorker(self._poller)
        self._worker.moveToThread(self._thread)

        # 连接信号
        self._thread.started.connect(self._worker.run)
        self._worker.status_updated.connect(self.status_updated)
        self._worker.poll_error.connect(self.poll_error)
        self._worker.poll_finished.connect(self.poll_finished)
        self._worker.log_message.connect(self.log_message)

        # 线程结束时发出信号
        self._thread.finished.connect(self._on_thread_finished)

        self._thread.start()
        logger.info("轮询线程已启动")

    def stop(self):
        """停止轮询线程"""
        if self._worker:
            self._worker.stop()
        self._poller.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(5000)
        logger.info("轮询线程已停止")

    def _on_thread_finished(self):
        """线程结束回调"""
        self.all_finished.emit()
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None