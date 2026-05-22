from __future__ import annotations

import ctypes
import logging
import os
import subprocess

from PySide6.QtCore import QSettings, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    TitleLabel,
)

from app.api_client import BitBrowserAPI
from app.config import (
    DEFAULT_BROWSER_PATH,
    REQUEST_TIMEOUT,
    SETTINGS_KEY_API_URL,
    SETTINGS_KEY_BROWSER_PATH,
    SETTINGS_KEY_REQUEST_TIMEOUT,
    SETTINGS_SCOPE,
)
from ui.widgets.api_worker import ApiCaller

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    connection_changed = Signal(bool)

    def __init__(self, api: BitBrowserAPI, parent=None):
        super().__init__(parent)
        self.api = api

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        # ═══ API 连接 ═══
        title = TitleLabel("连接设置")
        layout.addWidget(title)

        # API 地址
        url_label = BodyLabel("本地 API 地址")
        self.url_input = LineEdit()
        self.url_input.setPlaceholderText("http://127.0.0.1:54345")
        layout.addWidget(url_label)
        layout.addWidget(self.url_input)

        # 超时
        timeout_label = BodyLabel("请求超时")
        self.timeout_spin = SpinBox()
        self.timeout_spin.setRange(5, 60)
        self.timeout_spin.setValue(REQUEST_TIMEOUT)
        self.timeout_spin.setSuffix(" 秒")
        layout.addWidget(timeout_label)
        layout.addWidget(self.timeout_spin)

        # API 按钮
        self.test_btn = PrimaryPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        layout.addWidget(self.test_btn)

        self.save_btn = PushButton("保存设置")
        self.save_btn.clicked.connect(self._save_settings)
        layout.addWidget(self.save_btn)

        # ═══ 比特浏览器主程序 ═══
        app_title = TitleLabel("比特浏览器")
        app_title.setStyleSheet("font-size: 16px; margin-top: 8px;")
        layout.addWidget(app_title)

        path_label = BodyLabel("主程序路径")
        layout.addWidget(path_label)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.path_input = LineEdit()
        self.path_input.setPlaceholderText("选择比特浏览器主程序 exe 路径")
        path_row.addWidget(self.path_input, 1)

        self.browse_btn = PushButton(FluentIcon.FOLDER, "浏览")
        self.browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)

        self.launch_btn = PrimaryPushButton(FluentIcon.PLAY, "启动比特浏览器 (管理员)")
        self.launch_btn.clicked.connect(self._launch_browser)
        self.launch_btn.setStyleSheet("font-size: 14px; font-weight: 600; min-height: 32px;")
        layout.addWidget(self.launch_btn)

        tip = BodyLabel("打开浏览器窗口需要管理员权限，请使用上方按钮启动")
        tip.setStyleSheet("color: #ef4444; font-size: 12px; margin-top: 4px;")
        layout.addWidget(tip)

        layout.addStretch()

    # ------------------------------------------------------------------
    # 设置加载/保存
    # ------------------------------------------------------------------

    def load_settings(self):
        s = QSettings(SETTINGS_SCOPE)
        url = s.value(SETTINGS_KEY_API_URL, "")
        timeout = s.value(SETTINGS_KEY_REQUEST_TIMEOUT, REQUEST_TIMEOUT, type=int)
        self.timeout_spin.setValue(timeout)

        if url:
            self.url_input.setText(url)
            self.api.configure(url, timeout=timeout)

        path = s.value(SETTINGS_KEY_BROWSER_PATH, "")
        if not path and os.path.exists(DEFAULT_BROWSER_PATH):
            path = DEFAULT_BROWSER_PATH
        if path:
            self.path_input.setText(path)

    def _save_settings(self):
        s = QSettings(SETTINGS_SCOPE)

        # 保存 API URL
        url = self.url_input.text().strip()
        s.setValue(SETTINGS_KEY_API_URL, url)

        timeout = self.timeout_spin.value()
        s.setValue(SETTINGS_KEY_REQUEST_TIMEOUT, timeout)
        self.api.configure(url, timeout=timeout)

        # 保存浏览器路径
        browser_path = self.path_input.text().strip()
        if browser_path:
            s.setValue(SETTINGS_KEY_BROWSER_PATH, browser_path)

        InfoBar.success("已保存", "设置已保存，正在测试连接…", parent=self)
        self._test_connection()

    # ------------------------------------------------------------------
    # 连接测试
    # ------------------------------------------------------------------

    def _test_connection(self):
        url = self.url_input.text().strip()
        if not url:
            InfoBar.warning("提示", "请输入 API 地址", parent=self)
            return

        self.api.configure(url)
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中…")

        c = ApiCaller()
        c.finished.connect(self._on_test_result)
        c.error.connect(self._on_test_error)
        c.run(self.api.health)

    def _on_test_result(self, ok: bool):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")
        if ok:
            InfoBar.success("连接成功", "比特浏览器本地服务已连接", parent=self)
            self.connection_changed.emit(True)
        else:
            InfoBar.error("连接失败", "请检查 API 地址是否正确", parent=self)
            self.connection_changed.emit(False)

    def _on_test_error(self, msg: str):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")
        InfoBar.error("连接失败", msg, parent=self)
        self.connection_changed.emit(False)

    # ------------------------------------------------------------------
    # 比特浏览器路径
    # ------------------------------------------------------------------

    def _browse_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择比特浏览器主程序", "", "可执行文件 (*.exe)"
        )
        if path:
            self.path_input.setText(path)

    def _launch_browser(self):
        exe = self.path_input.text().strip()
        if not exe:
            InfoBar.warning("提示", "请先设置比特浏览器主程序路径", parent=self)
            return
        if not os.path.exists(exe):
            InfoBar.error("路径无效", "文件不存在，请检查主程序路径", parent=self)
            return

        exe_name = os.path.basename(exe).lower()
        already_running = False
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                text=True,
            )
            already_running = exe_name in output.lower()
        except subprocess.SubprocessError:
            pass

        if already_running:
            from qfluentwidgets import MessageBox

            msg = MessageBox(
                "以管理员身份重启",
                "检测到比特浏览器已在运行。\n\n"
                "打开浏览器窗口需要管理员权限，\n"
                "是否关闭当前进程并以管理员身份重新启动？",
                self,
            )
            if not msg.exec():
                return
            # 关闭已有进程
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", exe_name],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=10,
                )
            except subprocess.SubprocessError:
                pass
            QTimer.singleShot(1500, lambda: self._do_launch(exe))
            return

        self._do_launch(exe)

    def _do_launch(self, exe: str):
        try:
            # 使用 ShellExecute 以管理员权限启动（比特浏览器需要提权）
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, None, None, 1
            )
            if ret <= 32:
                errors = {
                    2: "文件不存在，请检查主程序路径",
                    3: "路径无效，请检查主程序路径",
                    5: "需要管理员权限才能启动比特浏览器",
                    1223: "已取消管理员授权，请重试",
                }
                raise OSError(errors.get(ret, f"启动失败，错误码: {ret}"))
            InfoBar.success("正在启动", "比特浏览器已启动，正在自动连接…", parent=self)

            # 等待几秒后自动测试连接
            QTimer.singleShot(5000, self._test_connection)
        except Exception as e:
            InfoBar.error("启动失败", str(e), parent=self)
