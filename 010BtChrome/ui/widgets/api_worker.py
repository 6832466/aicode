from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)

# 防止 ApiCaller 在线程运行期间被 GC
_pending: set[ApiCaller] = set()


class _Worker(QObject):
    """在 QThread 中执行 API 调用。"""
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, fn, args, kwargs, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:
            logger.exception("API call error")
            self.error.emit(str(e))


class ApiCaller(QObject):
    """后台 QThread 执行 API 调用，通过信号返回结果到主线程。"""

    finished = Signal(object)
    error = Signal(str)

    def run(self, fn, *args, **kwargs):
        _pending.add(self)

        self._thread = QThread()
        self._worker = _Worker(fn, args, kwargs)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self.finished)
        self._worker.error.connect(self.error)

        # worker 完成后退出线程事件循环
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        # 线程真正结束后再清理
        self._thread.finished.connect(self._on_thread_finished)

        self._thread.start()

    def _on_thread_finished(self):
        _pending.discard(self)
        self._thread.deleteLater()
        self.deleteLater()
