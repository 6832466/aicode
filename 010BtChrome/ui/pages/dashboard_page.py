from __future__ import annotations

import logging

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon,
    InfoBar,
    PrimaryPushButton,
    PushButton,
    TitleLabel,
)

from app.api_client import BitBrowserAPI
from app.utils import extract_rows, extract_total
from ui.widgets.api_worker import ApiCaller

logger = logging.getLogger(__name__)


class StatCard(CardWidget):
    """统计卡片"""

    def __init__(self, title: str, value: str = "—", icon=None, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        if icon:
            self.icon_label = BodyLabel(icon)
            layout.addWidget(self.icon_label)

        self.title_label = BodyLabel(title)
        self.title_label.setStyleSheet("color: #64748b; font-size: 13px;")
        layout.addWidget(self.title_label)

        self.value_label = TitleLabel(value)
        self.value_label.setStyleSheet("font-size: 32px; font-weight: 600;")
        layout.addWidget(self.value_label)

    def set_value(self, value: str):
        self.value_label.setText(value)


class DashboardPage(QWidget):
    def __init__(self, api: BitBrowserAPI, parent=None):
        super().__init__(parent)
        self.api = api

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        # 标题
        title = TitleLabel("首页")
        layout.addWidget(title)

        # 连接状态
        self.conn_card = CardWidget()
        conn_layout = QHBoxLayout(self.conn_card)
        self.conn_label = BodyLabel("⚡ 未连接")
        self.conn_label.setStyleSheet("color: #ef4444; font-size: 14px;")
        conn_layout.addWidget(self.conn_label)
        conn_layout.addStretch()

        self.btn_test = PushButton("测试连接")
        self.btn_test.clicked.connect(self._test_connection)
        conn_layout.addWidget(self.btn_test)

        self.btn_open_settings = PushButton("设置")
        self.btn_open_settings.clicked.connect(self._open_settings)
        conn_layout.addWidget(self.btn_open_settings)

        layout.addWidget(self.conn_card)

        # 统计行
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)

        self.card_total = StatCard("浏览器总数", "—")
        stats_layout.addWidget(self.card_total)

        self.card_open = StatCard("在线数量", "—")
        stats_layout.addWidget(self.card_open)

        self.card_groups = StatCard("分组数量", "—")
        stats_layout.addWidget(self.card_groups)

        layout.addLayout(stats_layout)

        # 快速操作
        actions_label = TitleLabel("快速操作")
        actions_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(actions_label)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)

        self.btn_new_browser = PrimaryPushButton(FluentIcon.ADD, "新建浏览器")
        self.btn_new_browser.clicked.connect(self._open_browser_page)
        actions_layout.addWidget(self.btn_new_browser)

        self.btn_refresh = PushButton(FluentIcon.SYNC, "刷新数据")
        self.btn_refresh.clicked.connect(self.refresh_data)
        actions_layout.addWidget(self.btn_refresh)

        layout.addLayout(actions_layout)
        layout.addStretch()

        # 连接状态引用（由 main_window 设置）
        self._main_window = parent

    def set_connected(self, connected: bool):
        if connected:
            self.conn_label.setText("✅ 已连接")
            self.conn_label.setStyleSheet("color: #22c55e; font-size: 14px;")
        else:
            self.conn_label.setText("⚡ 未连接")
            self.conn_label.setStyleSheet("color: #ef4444; font-size: 14px;")

    def refresh_data(self):
        if not self.api.base_url:
            self.conn_label.setText("⚡ 未连接 — 请先在设置页配置 API 地址")
            self.conn_label.setStyleSheet("color: #ef4444; font-size: 14px;")
            InfoBar.warning("提示", "请先在设置页配置 API 地址", parent=self)
            return

        # 获取统计
        c1 = ApiCaller()
        c1.finished.connect(self._on_browser_count)
        c1.error.connect(lambda e: InfoBar.error("获取浏览器统计失败", e, parent=self))
        c1.run(self.api.browser_list, 0, 1)

        c2 = ApiCaller()
        c2.finished.connect(self._on_group_count)
        c2.error.connect(lambda e: InfoBar.error("获取分组统计失败", e, parent=self))
        c2.run(self.api.group_list, 0, 1)

        c3 = ApiCaller()
        c3.finished.connect(self._on_alive_count)
        c3.error.connect(lambda e: InfoBar.error("获取在线统计失败", e, parent=self))
        c3.run(self.api.browser_pids_all)

    def _on_browser_count(self, data: dict):
        total = extract_total(data)
        self.card_total.set_value(str(total))

    def _on_group_count(self, data: dict):
        rows = extract_rows(data)
        self.card_groups.set_value(str(len(rows)))

    def _on_alive_count(self, data: dict):
        count = len(data) if isinstance(data, dict) else 0
        self.card_open.set_value(str(count))

    def _test_connection(self):
        if not self.api.base_url:
            InfoBar.warning("提示", "请先在设置页配置 API 地址", parent=self)
            return
        c = ApiCaller()
        c.finished.connect(self._on_test_result)
        c.error.connect(lambda e: InfoBar.error("连接失败", e, parent=self))
        c.run(self.api.health)

    def _on_test_result(self, ok: bool):
        self.set_connected(ok)
        if ok:
            InfoBar.success("连接成功", "比特浏览器本地服务已连接", parent=self)
        else:
            InfoBar.error("连接失败", "请检查 API 地址是否正确", parent=self)

    def _open_settings(self):
        if self._main_window:
            self._main_window.switchTo(self._main_window.settings_page)

    def _open_browser_page(self):
        if self._main_window:
            self._main_window.switchTo(self._main_window.browser_page)

    def showEvent(self, event):
        super().showEvent(event)
        if self.api.base_url:
            self.refresh_data()
