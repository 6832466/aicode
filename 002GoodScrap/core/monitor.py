"""PriceMonitor - orchestrate fetching, alerting, and signal emission."""
import traceback
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from .config import ConfigManager
from .fetcher import PriceFetcher, PriceData
from .alerter import AlertManager


class PriceMonitor(QObject):
    price_updated = Signal(object, object)  # au: PriceData|None, xau: PriceData|None
    alert_message = Signal(str, str, str)  # title, message, metal

    def __init__(self, config: ConfigManager, parent: QObject | None = None):
        super().__init__(parent)
        self._config = config
        self._fetcher = PriceFetcher()
        self._alerter = AlertManager(self._get_config)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._running = False

    def _get_config(self) -> dict[str, Any]:
        return self._config.data

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._poll()
            interval = self._config.get("refresh_interval", 5) * 1000
            self._timer.start(max(interval, 2000))

    def stop(self) -> None:
        self._running = False
        self._timer.stop()

    def set_interval(self, seconds: int) -> None:
        self._timer.setInterval(max(seconds * 1000, 2000))

    def _poll(self) -> None:
        if not self._running:
            return
        try:
            results = self._fetcher.fetch_all()
        except Exception:
            traceback.print_exc()
            return

        au = results.get("AU")
        xau = results.get("XAU")

        try:
            if au and au.price > 0:
                self._check_alerts("AU", au.price)
        except Exception:
            traceback.print_exc()

        try:
            if xau and xau.price > 0:
                self._check_alerts("XAU", xau.price)
        except Exception:
            traceback.print_exc()

        self.price_updated.emit(au, xau)

    def _check_alerts(self, metal: str, price: float) -> None:
        name = "沪金9999" if metal == "AU" else "国际金"

        # -- threshold --
        direction = self._alerter.check_thresholds(metal, price)
        if direction:
            label = "上破" if direction == "upper" else "下破"
            self.alert_message.emit("阈值提醒", f"{name} {label}阈值 {price:.2f}", metal)

        # -- volatility --
        direction = self._alerter.check_volatility(metal, price)
        if direction:
            label = "急涨" if direction == "up" else "急跌"
            self.alert_message.emit("异动提醒", f"{name} {label}预警 {price:.2f}", metal)
