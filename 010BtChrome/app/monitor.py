from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer, Signal

from app.api_client import BitBrowserAPI
from app.config import MONITOR_INTERVAL_MS
from ui.widgets.api_worker import ApiCaller

logger = logging.getLogger(__name__)


class StatusMonitor(QObject):
    alive_updated = Signal(object)

    def __init__(self, api: BitBrowserAPI, parent=None):
        super().__init__(parent)
        self.api = api
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._fail_count = 0
        self._max_fail = 5
        self._caller: ApiCaller | None = None

    def start(self):
        self._fail_count = 0
        self._timer.start(MONITOR_INTERVAL_MS)

    def stop(self):
        self._timer.stop()

    def _poll(self):
        if not self.api.base_url:
            return
        self._caller = ApiCaller()
        self._caller.finished.connect(self._on_result)
        self._caller.error.connect(self._on_error)
        self._caller.run(self.api.browser_pids_all)

    def _on_result(self, data: dict):
        self._fail_count = 0
        if isinstance(data, dict):
            self.alive_updated.emit(set(data.keys()))

    def _on_error(self, msg: str):
        self._fail_count += 1
        logger.warning("StatusMonitor poll failed (%d/%d): %s", self._fail_count, self._max_fail, msg)
        if self._fail_count >= self._max_fail:
            logger.warning("StatusMonitor reached max failures, stopping")
            self.stop()
