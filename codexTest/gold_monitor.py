from __future__ import annotations

import json
import logging
import os
import random
import smtplib
import sys
import time
from collections import deque
from dataclasses import dataclass
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

LOCAL_VENDOR = Path(__file__).resolve().parent / ".vendor"
if LOCAL_VENDOR.exists():
    sys.path.insert(0, str(LOCAL_VENDOR))

import requests
from PySide6.QtCore import QPoint, QRect, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Gold Monitor"
CONFIG_NAME = "config.json"
SINGLE_INSTANCE_MUTEX = "Global\\GoldMonitor_Lele_SingleInstance"
_INSTANCE_MUTEX_HANDLE = None


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_PATH = app_dir() / CONFIG_NAME
LOG_PATH = app_dir() / "gold_monitor.log"


DEFAULT_CONFIG: dict[str, Any] = {
    "refresh_interval": 3.0,
    "opacity": 0.86,
    "theme": "aurum_noir",
    "click_through": False,
    "window": {"x": 80, "y": 120, "width": 260, "height": 150},
    "alerts": {
        "cooldown_sec": 300,
        "au_upper": None,
        "au_lower": None,
        "intl_upper": None,
        "intl_lower": None,
    },
    "extreme": {
        "enabled": True,
        "window_sec": 300,
        "threshold": 1.0,
        "cooldown_sec": 180,
        "flash_times": 6,
    },
    "mail": {
        "enabled": False,
        "smtp_host": "",
        "smtp_port": 465,
        "username": "",
        "password": "",
        "to": "",
    },
}


def setup_logging() -> None:
    try:
        logging.basicConfig(
            filename=str(LOG_PATH),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            encoding="utf-8",
        )
    except Exception:
        logging.basicConfig(level=logging.CRITICAL)


def log_exception(context: str) -> None:
    try:
        logging.exception(context)
    except Exception:
        pass


def safe_call(context: str, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        log_exception(context)
        return None


THEMES: dict[str, dict[str, Any]] = {
    "aurum_noir": {
        "name": "Aurum Noir 黑金",
        "font": '"Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI"',
        "price_font": '"Bahnschrift", "Segoe UI Variable", "Microsoft YaHei UI"',
        "card_bg": "rgba(18, 17, 15, 242)",
        "border": "rgba(226, 182, 93, 118)",
        "title": "#f3d38d",
        "text": "#fff6dd",
        "symbol": "#a99b84",
        "muted": "#7c7468",
        "accent": "#d9a441",
        "up": "#ff5b5f",
        "down": "#38c781",
        "shadow": (0, 0, 0, 150),
    },
    "platinum_mist": {
        "name": "Platinum Mist 铂雾",
        "font": '"Aptos", "Segoe UI Variable", "Microsoft YaHei UI"',
        "price_font": '"Segoe UI Variable Display", "Aptos Display", "Microsoft YaHei UI"',
        "card_bg": "rgba(247, 250, 252, 236)",
        "border": "rgba(255, 255, 255, 190)",
        "title": "#334155",
        "text": "#111827",
        "symbol": "#6b7280",
        "muted": "#94a3b8",
        "accent": "#8b9bb4",
        "up": "#dc3f45",
        "down": "#1f9d67",
        "shadow": (35, 45, 66, 62),
    },
    "deep_terminal": {
        "name": "Deep Terminal 深盘",
        "font": '"Cascadia Code", "Consolas", "Microsoft YaHei UI"',
        "price_font": '"Cascadia Mono", "Cascadia Code", "Consolas"',
        "card_bg": "rgba(7, 13, 18, 240)",
        "border": "rgba(65, 214, 171, 105)",
        "title": "#94f2d3",
        "text": "#e7fff7",
        "symbol": "#7a9a92",
        "muted": "#5c746e",
        "accent": "#41d6ab",
        "up": "#ff626e",
        "down": "#2ee68f",
        "shadow": (0, 14, 10, 128),
    },
    "champagne_blush": {
        "name": "Champagne Blush 香槟",
        "font": '"Aptos", "Segoe UI Variable", "Microsoft YaHei UI"',
        "price_font": '"Georgia", "Cambria", "Microsoft YaHei UI"',
        "card_bg": "rgba(255, 248, 238, 239)",
        "border": "rgba(225, 183, 139, 145)",
        "title": "#8a5643",
        "text": "#2d211b",
        "symbol": "#93796b",
        "muted": "#b59d91",
        "accent": "#c88f55",
        "up": "#d94d59",
        "down": "#26966e",
        "shadow": (89, 55, 32, 72),
    },
    "sapphire_ice": {
        "name": "Sapphire Ice 蓝冰",
        "font": '"Segoe UI Variable", "Aptos", "Microsoft YaHei UI"',
        "price_font": '"Bahnschrift SemiCondensed", "Segoe UI Variable Display", "Microsoft YaHei UI"',
        "card_bg": "rgba(10, 25, 47, 238)",
        "border": "rgba(116, 192, 255, 112)",
        "title": "#a9d8ff",
        "text": "#eef8ff",
        "symbol": "#86a5bf",
        "muted": "#5f7b93",
        "accent": "#74c0ff",
        "up": "#ff6673",
        "down": "#35d391",
        "shadow": (7, 19, 37, 132),
    },
    "jade_porcelain": {
        "name": "Jade Porcelain 玉瓷",
        "font": '"Microsoft YaHei UI", "Aptos", "Segoe UI Variable"',
        "price_font": '"Segoe UI Variable Display", "Microsoft YaHei UI"',
        "card_bg": "rgba(239, 248, 244, 238)",
        "border": "rgba(123, 181, 164, 128)",
        "title": "#176c5f",
        "text": "#17352f",
        "symbol": "#63857d",
        "muted": "#8ca8a1",
        "accent": "#2e9d84",
        "up": "#d54e5a",
        "down": "#18865f",
        "shadow": (34, 77, 65, 64),
    },
    "carbon_violet": {
        "name": "Carbon Violet 碳紫",
        "font": '"Segoe UI Variable", "Aptos", "Microsoft YaHei UI"',
        "price_font": '"Aptos Display", "Segoe UI Variable Display", "Microsoft YaHei UI"',
        "card_bg": "rgba(23, 22, 31, 241)",
        "border": "rgba(176, 146, 255, 104)",
        "title": "#d9ccff",
        "text": "#f7f3ff",
        "symbol": "#9d94b6",
        "muted": "#756d88",
        "accent": "#b092ff",
        "up": "#ff6875",
        "down": "#42d99a",
        "shadow": (17, 12, 31, 140),
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        backup = CONFIG_PATH.with_suffix(".broken.json")
        try:
            CONFIG_PATH.replace(backup)
        except Exception:
            pass
        data = {}
    return deep_merge(DEFAULT_CONFIG, data)


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def to_float_or_none(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Quote:
    symbol: str
    price: float


def make_app_icon_pixmap(size: int = 64, accent: str = "#d9a441") -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pad = max(4, size // 10)
    accent_color = QColor(accent)
    painter.setBrush(accent_color)
    painter.setPen(QPen(accent_color.darker(135), max(1, size // 32)))
    painter.drawEllipse(pad, pad, size - pad * 2, size - pad * 2)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Segoe UI", max(12, int(size * 0.42)), QFont.Weight.Bold))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "G")
    painter.end()
    return pix


def make_app_icon(accent: str = "#d9a441") -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_app_icon_pixmap(size, accent))
    return icon


class PriceWorker(QThread):
    quote = Signal(str, float)
    fetch_error = Signal(str)

    def __init__(self, interval: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.interval = max(0.8, float(interval))
        self.session = requests.Session()
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            try:
                au = self._fetch_au()
                intl = self._fetch_intl()
                if au is not None:
                    self.quote.emit("AU", au)
                if intl is not None:
                    self.quote.emit("INTL", intl)

                end = time.time() + self.interval + random.uniform(0.08, 0.7)
                while self._running and time.time() < end:
                    self.msleep(100)
            except Exception:
                log_exception("Price worker loop failed")
                self.msleep(1000)

    def _fetch_au(self) -> float | None:
        url = "https://ms.jr.jd.com/gw2/generic/CreatorSer/pc/m/pcQueryGoldProduct"
        params = {"reqData": '{"goldType":"2"}'}
        headers = {"Origin": "https://jdjr.jd.com", "Referer": "https://jdjr.jd.com/"}
        try:
            res = self.session.get(url, params=params, headers=headers, timeout=2)
            res.raise_for_status()
            return float(res.json()["resultData"]["data"]["priceValue"])
        except Exception as exc:
            self.fetch_error.emit(f"AU: {exc}")
            return None

    def _fetch_intl(self) -> float | None:
        url = "https://ms.jr.jd.com/gw2/generic/CaiFuPC/pc/m/getQuoteExtendUseUniqueCodeWithCache"
        payload = {"ticket": "jd-jr-pc", "uniqueCode": "WG-XAUUSD"}
        try:
            res = self.session.post(url, json=payload, timeout=2)
            res.raise_for_status()
            return float(json.loads(res.json()["resultData"]["data"])["lastPrice"])
        except Exception as exc:
            self.fetch_error.emit(f"INTL: {exc}")
            return None


class SettingsDialog(QDialog):
    def __init__(self, config: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gold Monitor 设置")
        self.setWindowIcon(make_app_icon(THEMES.get(config.get("theme", "aurum_noir"), THEMES["aurum_noir"])["accent"]))
        self.setModal(True)
        self.setMinimumWidth(430)
        self.config = config
        self.theme = THEMES.get(config.get("theme", "aurum_noir"), THEMES["aurum_noir"])

        alerts = config["alerts"]
        extreme = config["extreme"]

        self.interval = self._double_spin(0.8, 120.0, config["refresh_interval"], " 秒")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setSingleStep(1)
        self.opacity_slider.setPageStep(5)
        self.opacity_slider.setValue(int(float(config["opacity"]) * 100))
        self.opacity_value = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_value.setObjectName("valueText")
        self.opacity_slider.valueChanged.connect(lambda value: self.opacity_value.setText(f"{value}%"))
        self.theme_selector = QComboBox()
        for key, theme in THEMES.items():
            self.theme_selector.addItem(theme["name"], key)
        theme_index = max(0, self.theme_selector.findData(config.get("theme", "aurum_noir")))
        self.theme_selector.setCurrentIndex(theme_index)
        self.theme_selector.currentIndexChanged.connect(self._on_theme_changed)
        self.click_through = QCheckBox("启用鼠标穿透模式")
        self.click_through.setChecked(bool(config.get("click_through", False)))
        self.alert_cooldown = self._spin(10, 86400, alerts["cooldown_sec"], " 秒")
        self.au_upper = self._nullable_double(alerts["au_upper"])
        self.au_lower = self._nullable_double(alerts["au_lower"])
        self.intl_upper = self._nullable_double(alerts["intl_upper"])
        self.intl_lower = self._nullable_double(alerts["intl_lower"])
        self.extreme_enabled = QCheckBox("启用")
        self.extreme_enabled.setChecked(bool(extreme["enabled"]))
        self.extreme_window = self._spin(30, 7200, extreme["window_sec"], " 秒")
        self.extreme_threshold = self._double_spin(0.01, 9999.0, extreme["threshold"], "", 2, 0.1)
        self.extreme_cooldown = self._spin(10, 86400, extreme["cooldown_sec"], " 秒")
        self.flash_times = self._spin(2, 30, extreme["flash_times"], " 次")

        base_form = self._form()
        base_form.addRow("刷新间隔", self.interval)
        base_form.addRow("透明度", self._opacity_control())
        base_form.addRow("当前皮肤", self.theme_selector)
        base_form.addRow("穿透模式", self.click_through)

        alert_form = self._form()
        alert_form.addRow("提醒冷却", self.alert_cooldown)
        alert_form.addRow("AU 上破", self.au_upper)
        alert_form.addRow("AU 下破", self.au_lower)
        alert_form.addRow("国际金上破", self.intl_upper)
        alert_form.addRow("国际金下破", self.intl_lower)

        extreme_form = self._form()
        extreme_form.addRow("异动监测", self.extreme_enabled)
        extreme_form.addRow("异动窗口", self.extreme_window)
        extreme_form.addRow("异动阈值", self.extreme_threshold)
        extreme_form.addRow("异动冷却", self.extreme_cooldown)
        extreme_form.addRow("闪烁次数", self.flash_times)

        ok = QPushButton("保存")
        cancel = QPushButton("取消")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self._section("基础显示", base_form))
        layout.addWidget(self._section("价格提醒", alert_form))
        layout.addWidget(self._section("异动监测", extreme_form))
        layout.addLayout(buttons)
        self._apply_theme()
        self._center_on_screen(parent)

    def _on_theme_changed(self) -> None:
        key = self.theme_selector.currentData()
        self.theme = THEMES.get(key, THEMES["aurum_noir"])
        self.setWindowIcon(make_app_icon(self.theme["accent"]))
        self._apply_theme()

    def _center_on_screen(self, parent: QWidget | None) -> None:
        try:
            self.adjustSize()
            screen = parent.screen() if parent and parent.screen() else QGuiApplication.primaryScreen()
            if not screen:
                return
            center = screen.availableGeometry().center()
            frame = self.frameGeometry()
            frame.moveCenter(center)
            self.move(frame.topLeft())
        except Exception:
            log_exception("Center settings dialog failed")

    def _form(self) -> QFormLayout:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        return form

    def _section(self, title: str, content: QFormLayout) -> QFrame:
        frame = QFrame()
        frame.setObjectName("section")
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)
        layout.addWidget(title_label)
        layout.addLayout(content)
        return frame

    def _opacity_control(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.opacity_slider, 1)
        layout.addWidget(self.opacity_value)
        return widget

    def _apply_theme(self) -> None:
        theme = self.theme
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {theme["card_bg"]};
                color: {theme["text"]};
                font-family: {theme["font"]};
            }}
            QFrame#section {{
                background: rgba(255, 255, 255, 18);
                border: 1px solid {theme["border"]};
                border-radius: 12px;
            }}
            QLabel {{
                color: {theme["symbol"]};
                font-size: 12px;
            }}
            QLabel#sectionTitle {{
                color: {theme["title"]};
                font-size: 14px;
                font-weight: 700;
            }}
            QCheckBox {{
                color: {theme["text"]};
                spacing: 8px;
            }}
            QSpinBox, QDoubleSpinBox, QComboBox {{
                min-height: 28px;
                padding: 3px 8px;
                color: {theme["text"]};
                background: rgba(255, 255, 255, 30);
                border: 1px solid {theme["border"]};
                border-radius: 8px;
                selection-background-color: {theme["accent"]};
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: rgba(255, 255, 255, 42);
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {theme["accent"]};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                width: 16px;
                height: 16px;
                margin: -5px 0;
                background: {theme["title"]};
                border: 1px solid {theme["border"]};
                border-radius: 8px;
            }}
            QLabel#valueText {{
                min-width: 42px;
                color: {theme["text"]};
                font-weight: 700;
            }}
            QPushButton {{
                min-width: 72px;
                min-height: 30px;
                padding: 4px 14px;
                color: {theme["text"]};
                background: rgba(255, 255, 255, 24);
                border: 1px solid {theme["border"]};
                border-radius: 8px;
            }}
            QPushButton#primary {{
                color: white;
                background: {theme["accent"]};
                border-color: {theme["accent"]};
                font-weight: 700;
            }}
            """
        )

    def _spin(self, minimum: int, maximum: int, value: int, suffix: str = "") -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(int(value))
        spin.setSuffix(suffix)
        return spin

    def _double_spin(
        self,
        minimum: float,
        maximum: float,
        value: float,
        suffix: str = "",
        decimals: int = 2,
        step: float = 0.1,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(float(value))
        spin.setSuffix(suffix)
        return spin

    def _nullable_double(self, value: float | None) -> QDoubleSpinBox:
        spin = self._double_spin(-999999.0, 999999.0, value if value is not None else 0.0)
        spin.setSpecialValueText("关闭")
        spin.setValue(value if value is not None else spin.minimum())
        return spin

    def _nullable_value(self, spin: QDoubleSpinBox) -> float | None:
        if spin.value() <= spin.minimum() + 0.000001:
            return None
        return spin.value()

    def updated_config(self) -> dict[str, Any]:
        config = deep_merge(DEFAULT_CONFIG, self.config)
        config["refresh_interval"] = self.interval.value()
        config["opacity"] = self.opacity_slider.value() / 100
        config["theme"] = self.theme_selector.currentData()
        config["click_through"] = self.click_through.isChecked()
        config["alerts"]["cooldown_sec"] = self.alert_cooldown.value()
        config["alerts"]["au_upper"] = self._nullable_value(self.au_upper)
        config["alerts"]["au_lower"] = self._nullable_value(self.au_lower)
        config["alerts"]["intl_upper"] = self._nullable_value(self.intl_upper)
        config["alerts"]["intl_lower"] = self._nullable_value(self.intl_lower)
        config["extreme"]["enabled"] = self.extreme_enabled.isChecked()
        config["extreme"]["window_sec"] = self.extreme_window.value()
        config["extreme"]["threshold"] = self.extreme_threshold.value()
        config["extreme"]["cooldown_sec"] = self.extreme_cooldown.value()
        config["extreme"]["flash_times"] = self.flash_times.value()
        return config


class AboutDialog(QDialog):
    def __init__(self, theme: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle("关于 Gold Monitor")
        self.setWindowIcon(make_app_icon(theme["accent"]))
        self.setModal(True)
        self.setFixedWidth(340)

        icon = QLabel()
        icon.setPixmap(make_app_icon(theme["accent"]).pixmap(56, 56))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Gold Monitor")
        title.setObjectName("aboutTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        author = QLabel("作者：乐乐")
        author.setObjectName("aboutText")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)

        wechat = QLabel("微信：rpalele")
        wechat.setObjectName("aboutText")
        wechat.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ok = QPushButton("知道了")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(ok)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(author)
        layout.addWidget(wechat)
        layout.addSpacing(4)
        layout.addLayout(button_row)
        self._apply_theme()

    def _apply_theme(self) -> None:
        theme = self.theme
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {theme["card_bg"]};
                color: {theme["text"]};
                font-family: {theme["font"]};
            }}
            QLabel#aboutTitle {{
                color: {theme["title"]};
                font-size: 20px;
                font-weight: 800;
            }}
            QLabel#aboutText {{
                color: {theme["text"]};
                font-size: 13px;
            }}
            QPushButton {{
                min-width: 82px;
                min-height: 30px;
                padding: 4px 14px;
                color: white;
                background: {theme["accent"]};
                border: 1px solid {theme["accent"]};
                border-radius: 8px;
                font-weight: 700;
            }}
            """
        )


class GoldCard(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.theme_key = self.config.get("theme", "aurum_noir")
        self.theme = THEMES.get(self.theme_key, THEMES["aurum_noir"])
        self.up_color = QColor(self.theme["up"])
        self.down_color = QColor(self.theme["down"])
        self.muted_color = QColor(self.theme["muted"])
        self.text_color = QColor(self.theme["text"])
        self.prev_prices: dict[str, float | None] = {"AU": None, "INTL": None}
        self.prices: dict[str, float | None] = {"AU": None, "INTL": None}
        self.histories = {"AU": deque(), "INTL": deque()}
        self.triggered: dict[tuple[str, str], bool] = {}
        self.last_alert_ts: dict[tuple[str, str], float] = {}
        self.extreme_last_ts = {"AU": 0.0, "INTL": 0.0}
        self.drag_offset: QPoint | None = None
        self.flash_remaining = 0
        self.flash_color = QColor("#ffffff")
        self.flash_on = False

        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._start_worker()

        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self._flash_tick)

    def _setup_window(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon(self.theme["accent"]))
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(float(self.config["opacity"]))
        rect = self.config["window"]
        self.setGeometry(QRect(int(rect["x"]), int(rect["y"]), int(rect["width"]), int(rect["height"])))
        self._apply_click_through()

    def _setup_ui(self) -> None:
        self.card = QWidget(self)
        self.card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)
        self.shadow = shadow

        self.title = QLabel("Gold Monitor")
        self.title.setObjectName("title")
        self.status = QLabel("连接中...")
        self.status.setObjectName("status")

        self.au_symbol = QLabel("沪金 AU")
        self.au_symbol.setObjectName("symbol")
        self.au_price = QLabel("--.--")
        self.au_price.setObjectName("price")
        self.au_arrow = QLabel("•")
        self.au_arrow.setObjectName("arrow")

        self.intl_symbol = QLabel("国际金 XAU")
        self.intl_symbol.setObjectName("symbol")
        self.intl_price = QLabel("--.--")
        self.intl_price.setObjectName("price")
        self.intl_arrow = QLabel("•")
        self.intl_arrow.setObjectName("arrow")

        top = QHBoxLayout()
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(self.status)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)
        layout.addLayout(top)
        layout.addLayout(self._row(self.au_symbol, self.au_price, self.au_arrow))
        layout.addLayout(self._row(self.intl_symbol, self.intl_price, self.intl_arrow))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(self.card)
        self._apply_theme()

    def _row(self, symbol: QLabel, price: QLabel, arrow: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(symbol)
        row.addStretch(1)
        row.addWidget(price)
        row.addWidget(arrow)
        return row

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(self._make_icon(), self)
        self.tray.setContextMenu(self._build_context_menu())
        self.tray.activated.connect(lambda reason: safe_call("Tray activation failed", self._tray_activated, reason))
        self.tray.show()

    def _build_context_menu(self) -> QMenu:
        menu = QMenu()
        skin_menu = menu.addMenu("切换皮肤")
        group = QActionGroup(menu)
        group.setExclusive(True)
        for key, theme in THEMES.items():
            action = QAction(theme["name"], group)
            action.setCheckable(True)
            action.setChecked(key == self.theme_key)
            action.triggered.connect(lambda checked=False, theme_key=key: safe_call("Theme switch failed", self.set_theme, theme_key))
            skin_menu.addAction(action)
        menu.addSeparator()
        click_through = QAction("鼠标穿透模式", menu)
        click_through.setCheckable(True)
        click_through.setChecked(bool(self.config.get("click_through", False)))
        click_through.triggered.connect(lambda enabled: safe_call("Click-through switch failed", self.set_click_through, enabled))
        menu.addAction(click_through)
        settings = QAction("设置", self)
        settings.triggered.connect(lambda: safe_call("Open settings failed", self.open_settings))
        about = QAction("关于软件", self)
        about.triggered.connect(lambda: safe_call("Open about failed", self.open_about))
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(settings)
        menu.addAction(about)
        menu.addSeparator()
        menu.addAction(quit_action)
        return menu

    def _make_icon(self) -> QIcon:
        return make_app_icon(self.theme["accent"])

    def _theme_stylesheet(self, flash_bg: str | None = None) -> str:
        theme = self.theme
        card_bg = flash_bg or theme["card_bg"]
        return f"""
            QWidget#card {{
                background: {card_bg};
                border: 1px solid {theme["border"]};
                border-radius: 14px;
            }}
            QLabel {{
                color: {theme["text"]};
                font-family: {theme["font"]};
                letter-spacing: 0px;
            }}
            QLabel#title {{
                font-size: 13px;
                font-weight: 700;
                color: {theme["title"]};
            }}
            QLabel#symbol {{
                font-size: 12px;
                color: {theme["symbol"]};
            }}
            QLabel#price {{
                font-family: {theme["price_font"]};
                font-size: 28px;
                font-weight: 700;
                color: {theme["text"]};
            }}
            QLabel#arrow {{
                font-size: 18px;
                font-weight: 700;
            }}
            QLabel#status {{
                font-size: 11px;
                color: {theme["muted"]};
            }}
        """

    def _apply_theme(self) -> None:
        self.theme_key = self.config.get("theme", "aurum_noir")
        self.theme = THEMES.get(self.theme_key, THEMES["aurum_noir"])
        self.up_color = QColor(self.theme["up"])
        self.down_color = QColor(self.theme["down"])
        self.muted_color = QColor(self.theme["muted"])
        self.text_color = QColor(self.theme["text"])
        self.card.setStyleSheet(self._theme_stylesheet())
        shadow_color = QColor(*self.theme["shadow"])
        self.shadow.setColor(shadow_color)
        self.tray.setIcon(self._make_icon()) if hasattr(self, "tray") else None
        self.setWindowIcon(self._make_icon())
        self._render_price("AU")
        self._render_price("INTL")

    def set_theme(self, theme_key: str) -> None:
        if theme_key not in THEMES:
            return
        self.config["theme"] = theme_key
        self._apply_theme()
        if hasattr(self, "tray"):
            self.tray.setContextMenu(self._build_context_menu())
        save_config(self.config)

    def set_click_through(self, enabled: bool) -> None:
        self.config["click_through"] = bool(enabled)
        self._apply_click_through()
        if hasattr(self, "tray"):
            self.tray.setContextMenu(self._build_context_menu())
        save_config(self.config)

    def _apply_click_through(self) -> None:
        enabled = bool(self.config.get("click_through", False))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if sys.platform != "win32":
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            gwl_exstyle = -20
            ws_ex_layered = 0x00080000
            ws_ex_transparent = 0x00000020
            get_window_long = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
            set_window_long = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
            style = get_window_long(hwnd, gwl_exstyle)
            style |= ws_ex_layered
            if enabled:
                style |= ws_ex_transparent
            else:
                style &= ~ws_ex_transparent
            set_window_long(hwnd, gwl_exstyle, style)
        except Exception:
            pass

    def _start_worker(self) -> None:
        try:
            self.worker = PriceWorker(float(self.config["refresh_interval"]), self)
            self.worker.quote.connect(lambda symbol, price: safe_call("Quote update failed", self.on_quote, symbol, price))
            self.worker.fetch_error.connect(lambda message: safe_call("Fetch error update failed", self.on_fetch_error, message))
            self.worker.start()
        except Exception:
            log_exception("Start worker failed")

    def _restart_worker(self) -> None:
        try:
            self.worker.stop()
            self.worker.wait(2500)
        except Exception:
            log_exception("Stop worker failed")
        self._start_worker()

    def on_quote(self, symbol: str, price: float) -> None:
        try:
            self.prev_prices[symbol] = self.prices[symbol]
            self.prices[symbol] = price
            self._render_price(symbol)
            self._check_alert(symbol, price)
            self._track_extreme(symbol, price)
            self.status.setText(time.strftime("%H:%M:%S"))
        except Exception:
            log_exception("Quote handling failed")

    def on_fetch_error(self, message: str) -> None:
        try:
            logging.warning("Fetch failed: %s", message)
            self.status.setText("重试中")
        except Exception:
            log_exception("Fetch error handling failed")

    def _render_price(self, symbol: str) -> None:
        label = self.au_price if symbol == "AU" else self.intl_price
        arrow = self.au_arrow if symbol == "AU" else self.intl_arrow
        price = self.prices[symbol]
        prev = self.prev_prices[symbol]
        if price is None:
            return
        label.setText(f"{price:.2f}")
        if prev is None:
            arrow.setText("•")
            arrow.setStyleSheet(f"color: {self.muted_color.name()};")
            return
        if price > prev:
            arrow.setText("↑")
            arrow.setStyleSheet(f"color: {self.up_color.name()};")
        elif price < prev:
            arrow.setText("↓")
            arrow.setStyleSheet(f"color: {self.down_color.name()};")
        else:
            arrow.setText("•")
            arrow.setStyleSheet(f"color: {self.muted_color.name()};")

    def _check_alert(self, symbol: str, price: float) -> None:
        alerts = self.config["alerts"]
        upper = to_float_or_none(alerts["au_upper" if symbol == "AU" else "intl_upper"])
        lower = to_float_or_none(alerts["au_lower" if symbol == "AU" else "intl_lower"])
        title = "沪金提醒" if symbol == "AU" else "国际金提醒"
        self._check_one_threshold(symbol, "upper", upper, price, price >= (upper or float("inf")), title, "上破")
        self._check_one_threshold(symbol, "lower", lower, price, price <= (lower or float("-inf")), title, "下破")

    def _check_one_threshold(
        self,
        symbol: str,
        direction: str,
        target: float | None,
        price: float,
        crossed: bool,
        title: str,
        action: str,
    ) -> None:
        if target is None:
            return
        key = (symbol, direction)
        now = time.time()
        cooldown = float(self.config["alerts"]["cooldown_sec"])
        if crossed and not self.triggered.get(key, False):
            if now - self.last_alert_ts.get(key, 0.0) >= cooldown:
                body = f"{symbol} {action} {target:.2f}，当前价格：{price:.2f}"
                self._notify(f"{title} - {action}", body)
                self._send_alert_email(f"{title} - {action}", body)
                self.last_alert_ts[key] = now
            self.triggered[key] = True
        if direction == "upper" and price < target:
            self.triggered[key] = False
        if direction == "lower" and price > target:
            self.triggered[key] = False

    def _track_extreme(self, symbol: str, price: float) -> None:
        extreme = self.config["extreme"]
        if not extreme["enabled"]:
            return
        now = time.time()
        history = self.histories[symbol]
        history.append((now, price))
        cutoff = now - float(extreme["window_sec"])
        while history and history[0][0] < cutoff:
            history.popleft()
        if len(history) < 2:
            return
        delta = price - history[0][1]
        if abs(delta) < float(extreme["threshold"]):
            return
        if now - self.extreme_last_ts[symbol] < float(extreme["cooldown_sec"]):
            return
        self.extreme_last_ts[symbol] = now
        color = self.up_color if delta > 0 else self.down_color
        self._notify("黄金异动", f"{symbol} {float(extreme['window_sec']) / 60:.1f} 分钟变动 {delta:+.2f}")
        self._start_flash(color, int(extreme["flash_times"]))

    def _start_flash(self, color: QColor, times: int) -> None:
        try:
            self.flash_color = color
            self.flash_remaining = max(2, times * 2)
            self.flash_on = False
            self.flash_timer.start(180)
        except Exception:
            log_exception("Start flash failed")

    def _flash_tick(self) -> None:
        try:
            self.flash_on = not self.flash_on
            self.flash_remaining -= 1
            if self.flash_on:
                self.card.setStyleSheet(self._theme_stylesheet(self.flash_color.name()))
            else:
                self._apply_theme()
            if self.flash_remaining <= 0:
                self.flash_timer.stop()
                self._apply_theme()
        except Exception:
            log_exception("Flash tick failed")
            self.flash_timer.stop()
            self._apply_theme()

    def _setup_ui_style_only(self) -> None:
        self._apply_theme()

    def _notify(self, title: str, message: str) -> None:
        try:
            if self.tray.isVisible():
                self.tray.showMessage(title, message, self.tray.icon(), 6000)
        except Exception:
            log_exception("Tray notification failed")

    def _send_alert_email(self, subject: str, body: str) -> None:
        mail = self.config["mail"]
        if not mail.get("enabled"):
            return
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = mail["username"]
            msg["To"] = mail["to"]
            with smtplib.SMTP_SSL(mail["smtp_host"], int(mail["smtp_port"]), timeout=8) as smtp:
                smtp.login(mail["username"], mail["password"])
                smtp.sendmail(mail["username"], [mail["to"]], msg.as_string())
        except Exception as exc:
            self._notify("邮件发送失败", str(exc))

    def open_settings(self) -> None:
        try:
            dlg = SettingsDialog(self.config, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.config = dlg.updated_config()
                self.setWindowOpacity(float(self.config["opacity"]))
                self._apply_theme()
                self._apply_click_through()
                if hasattr(self, "tray"):
                    self.tray.setContextMenu(self._build_context_menu())
                self._save_position()
                save_config(self.config)
                self._restart_worker()
        except Exception:
            log_exception("Settings dialog failed")
            self._notify("设置保存失败", "已记录到 gold_monitor.log")

    def open_about(self) -> None:
        try:
            AboutDialog(self.theme, self).exec()
        except Exception:
            log_exception("About dialog failed")

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.raise_()

    def contextMenuEvent(self, event) -> None:
        menu = self._build_context_menu()
        chosen = menu.exec(QCursor.pos())
        if chosen:
            event.accept()

    def mousePressEvent(self, event) -> None:
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
        except Exception:
            log_exception("Mouse press failed")

    def mouseMoveEvent(self, event) -> None:
        try:
            if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self.drag_offset)
                event.accept()
        except Exception:
            log_exception("Mouse move failed")

    def mouseReleaseEvent(self, event) -> None:
        try:
            if self.drag_offset is not None:
                self.drag_offset = None
                self._save_position()
                save_config(self.config)
                event.accept()
        except Exception:
            log_exception("Mouse release failed")

    def resizeEvent(self, event) -> None:
        try:
            super().resizeEvent(event)
            self._save_position()
        except Exception:
            log_exception("Resize failed")

    def _save_position(self) -> None:
        try:
            geo = self.geometry()
            self.config["window"] = {"x": geo.x(), "y": geo.y(), "width": geo.width(), "height": geo.height()}
        except Exception:
            log_exception("Save window position failed")

    def paintEvent(self, event) -> None:
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(self.rect().adjusted(8, 8, -8, -8), 14, 14)
            painter.fillPath(path, QColor(255, 255, 255, 1))
        except Exception:
            log_exception("Paint failed")

    def closeEvent(self, event) -> None:
        try:
            self._save_position()
            save_config(self.config)
            if hasattr(self, "worker"):
                self.worker.stop()
                self.worker.wait(2500)
            if hasattr(self, "tray"):
                self.tray.hide()
        except Exception:
            log_exception("Close failed")
        super().closeEvent(event)


def enable_dpi() -> None:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
    try:
        from ctypes import windll

        windll.shell32.SetCurrentProcessExplicitAppUserModelID("Lele.GoldMonitor.Desktop")
        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            from ctypes import windll

            windll.shell32.SetCurrentProcessExplicitAppUserModelID("Lele.GoldMonitor.Desktop")
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def acquire_single_instance_lock() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        global _INSTANCE_MUTEX_HANDLE
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        _INSTANCE_MUTEX_HANDLE = kernel32.CreateMutexW(None, True, SINGLE_INSTANCE_MUTEX)
        already_exists = kernel32.GetLastError() == 183
        return bool(_INSTANCE_MUTEX_HANDLE) and not already_exists
    except Exception:
        return True


def main() -> int:
    setup_logging()
    if not acquire_single_instance_lock():
        return 0

    try:
        enable_dpi()
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setWindowIcon(make_app_icon(THEMES["aurum_noir"]["accent"]))
        app.setQuitOnLastWindowClosed(False)

        def excepthook(exc_type, exc_value, exc_traceback):
            logging.exception("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

        sys.excepthook = excepthook

        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.warning(None, APP_NAME, "系统托盘不可用，提醒气泡可能无法显示。")

        card = GoldCard()
        card.show()
        return app.exec()
    except Exception:
        log_exception("Application startup failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
