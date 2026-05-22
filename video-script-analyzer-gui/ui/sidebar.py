# -*- coding: utf-8 -*-
"""侧边栏 — 全 Fluent 控件"""
import os
import json
import traceback
import requests
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QScrollArea,
    QFileDialog, QFrame, QMessageBox, QPushButton,
)
from qfluentwidgets import (
    LineEdit, PushButton, PrimaryPushButton, TransparentPushButton,
    StrongBodyLabel, CaptionLabel, EditableComboBox, InfoBar, InfoBarPosition,
    TextEdit, FluentIcon,
)

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

DEFAULT_CONFIG = {
    "base_url": "https://www.geeknow.top/v1",
    "api_key": "",
    "model": "gemini-3-pro-preview",
    "custom_prompt": "",
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            import sys
            print(f"[WARN] 配置文件JSON解析失败: {e}，使用默认配置", file=sys.stderr)
        except OSError as e:
            import sys
            print(f"[WARN] 配置文件读取失败: {e}，使用默认配置", file=sys.stderr)
    return dict(DEFAULT_CONFIG)


def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except OSError as e:
        import sys
        print(f"[ERROR] 配置文件写入失败: {e}", file=sys.stderr)
        raise
    except Exception as e:
        import sys
        import traceback
        print(f"[ERROR] 保存配置异常: {e}\n{traceback.format_exc()}", file=sys.stderr)
        raise


class TestConnectionWorker(QThread):
    result_ready = Signal(bool, str)

    def __init__(self, base_url, api_key, model):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def run(self):
        try:
            import json as json_mod
            api_url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "你好"}],
                "max_tokens": 50
            }
            resp = requests.post(
                api_url,
                data=json_mod.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json; charset=utf-8"
                },
                timeout=60, verify=False
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content.strip():
                    preview = content.strip()[:80].replace("\n", " ")
                    self.result_ready.emit(True, f"模型回复: {preview}…")
                else:
                    self.result_ready.emit(False, "模型返回了空内容，请检查模型名称")
            elif resp.status_code == 401:
                self.result_ready.emit(False, "认证失败 — 请检查 API Key")
            elif resp.status_code == 404:
                self.result_ready.emit(False, "接口不存在 — 请检查 Base URL")
            else:
                self.result_ready.emit(False, f"HTTP {resp.status_code}: {resp.text[:80]}")
        except requests.exceptions.Timeout:
            self.result_ready.emit(False, f"连接超时 (60s)\nURL: {self.base_url}/chat/completions\n请检查网络或 Base URL 是否正确")
        except requests.exceptions.ConnectionError as e:
            self.result_ready.emit(False, f"无法连接到服务器\nURL: {self.base_url}\n详情: {e}")
        except Exception as e:
            tb = traceback.format_exc()
            self.result_ready.emit(False, f"错误: {e}\n{tb[:300]}")


class Sidebar(QScrollArea):
    folder_selected = Signal(str)
    files_selected = Signal(list)
    analyze_all_requested = Signal()
    stop_requested = Signal()
    config_changed = Signal(dict)
    error_occurred = Signal(str)
    export_files_requested = Signal()
    merge_export_requested = Signal()

    def _log_error(self, context, exc):
        tb = traceback.format_exc()
        self.error_occurred.emit(f"{context}: {exc}\n{tb[:800]}")

    def __init__(self, parent=None):
        try:
            super().__init__(parent)
            self.config = load_config()
            self._test_worker = None

            self.setFixedWidth(350)
            self.setWidgetResizable(True)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

            container = QWidget()
            self.setWidget(container)
            layout = QVBoxLayout(container)
            layout.setContentsMargins(12, 16, 12, 16)
            layout.setSpacing(10)
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(None, "侧边栏初始化失败", f"构建侧边栏时出错:\n\n{e}\n\n{tb[:500]}")
            raise

        # ═══ API 配置 ═══
        layout.addWidget(StrongBodyLabel("API 配置"))

        layout.addWidget(CaptionLabel("Base URL"))
        self.base_url_input = LineEdit()
        self.base_url_input.setText(self.config.get("base_url", ""))
        self.base_url_input.setPlaceholderText("https://api.example.com/v1")
        layout.addWidget(self.base_url_input)

        layout.addWidget(CaptionLabel("API Key"))
        key_wrapper = QWidget()
        key_layout = QHBoxLayout(key_wrapper)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(6)

        self.api_key_input = LineEdit()
        self.api_key_input.setText(self.config.get("api_key", ""))
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.setEchoMode(LineEdit.Password)
        key_layout.addWidget(self.api_key_input)

        self.show_key_btn = TransparentPushButton(FluentIcon.VIEW, "")
        self.show_key_btn.setToolTip("显示/隐藏 API Key")
        self.show_key_btn.clicked.connect(self._toggle_key_visibility)
        key_layout.addWidget(self.show_key_btn)
        layout.addWidget(key_wrapper)

        layout.addWidget(CaptionLabel("模型名称"))
        self.model_combo = EditableComboBox()
        self.model_combo.addItems([
            "gemini-3-pro-preview", "gemini-3.1-pro-high",
            "gemini-2.5-pro-preview", "gpt-4o", "gpt-4o-mini",
        ])
        self.model_combo.setCurrentText(self.config.get("model", "gemini-3-pro-preview"))
        layout.addWidget(self.model_combo)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.test_btn = PushButton(FluentIcon.SEND, "测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        self.save_btn = PrimaryPushButton(FluentIcon.SAVE, "保存配置")
        self.save_btn.clicked.connect(self._save_config)
        btn_row.addWidget(self.test_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addWidget(self._divider())

        # ═══ 自定义指令 ═══
        layout.addWidget(StrongBodyLabel("自定义分析指令"))
        layout.addWidget(CaptionLabel("留空使用系统默认指令"))
        self.prompt_edit = TextEdit()
        self.prompt_edit.setPlaceholderText("在此输入自定义分析指令...")
        self.prompt_edit.setAcceptRichText(False)
        self.prompt_edit.setMaximumHeight(320)
        cp = self.config.get("custom_prompt", "")
        if cp:
            self.prompt_edit.setPlainText(cp)
        layout.addWidget(self.prompt_edit)
        layout.addWidget(self._divider())

        # ═══ 视频源 ═══
        layout.addWidget(StrongBodyLabel("视频源"))
        src_btn_row = QHBoxLayout()
        src_btn_row.setSpacing(8)
        self.folder_btn = PushButton(FluentIcon.FOLDER, "选择文件夹")
        self.folder_btn.clicked.connect(self._select_folder)
        self.files_btn = PushButton(FluentIcon.FOLDER_ADD, "选择文件")
        self.files_btn.clicked.connect(self._select_files)
        src_btn_row.addWidget(self.folder_btn)
        src_btn_row.addWidget(self.files_btn)
        src_btn_row.addStretch()
        layout.addLayout(src_btn_row)
        layout.addWidget(self._divider())

        # ═══ 操作按钮 ═══
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.analyze_all_btn = PrimaryPushButton(FluentIcon.PLAY, "批量分析")
        self.analyze_all_btn.clicked.connect(self.analyze_all_requested.emit)
        action_row.addWidget(self.analyze_all_btn)

        self.stop_btn = QPushButton("  停止  ")
        self.stop_btn.setMinimumHeight(36)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f4; color: #d13438;
                border: 1px solid #d13438; border-radius: 6px;
                padding: 8px 20px; font-size: 14px; font-weight: 500;
            }
            QPushButton:hover { background: #ffe5e5; }
            QPushButton:disabled { color: #ccc; border-color: #ccc; }
        """)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        action_row.addWidget(self.stop_btn)
        layout.addLayout(action_row)
        layout.addWidget(self._divider())

        # ═══ 导出 ═══
        layout.addWidget(StrongBodyLabel("导出剧本"))
        export_row = QHBoxLayout()
        export_row.setSpacing(8)
        self.export_files_btn = PushButton(FluentIcon.DOCUMENT, "导出独立分镜")
        self.export_files_btn.clicked.connect(self.export_files_requested.emit)
        self.merge_export_btn = PushButton(FluentIcon.SAVE_AS, "合并分镜导出")
        self.merge_export_btn.clicked.connect(self.merge_export_requested.emit)
        export_row.addWidget(self.export_files_btn)
        export_row.addWidget(self.merge_export_btn)
        export_row.addStretch()
        layout.addLayout(export_row)

        layout.addStretch()

        # Auto-save on any config change
        self.base_url_input.textChanged.connect(self._auto_save)
        self.api_key_input.textChanged.connect(self._auto_save)
        self.model_combo.currentTextChanged.connect(self._auto_save)
        self.prompt_edit.textChanged.connect(self._auto_save)

    def _auto_save(self, *args):
        try:
            self.config = {
                "base_url": self.base_url_input.text().strip(),
                "api_key": self.api_key_input.text().strip(),
                "model": self.model_combo.currentText().strip(),
                "custom_prompt": self.prompt_edit.toPlainText().strip(),
            }
            save_config(self.config)
            self.config_changed.emit(self.config)
        except Exception as e:
            self._log_error("自动保存配置异常", e)

    def _divider(self):
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        return div

    def _toggle_key_visibility(self):
        try:
            if self.api_key_input.echoMode() == LineEdit.Password:
                self.api_key_input.setEchoMode(LineEdit.Normal)
                self.show_key_btn.setIcon(FluentIcon.HIDE)
            else:
                self.api_key_input.setEchoMode(LineEdit.Password)
                self.show_key_btn.setIcon(FluentIcon.VIEW)
        except Exception as e:
            self._log_error("切换密钥可见性异常", e)

    def _save_config(self):
        try:
            self.config = {
                "base_url": self.base_url_input.text().strip(),
                "api_key": self.api_key_input.text().strip(),
                "model": self.model_combo.currentText().strip(),
                "custom_prompt": self.prompt_edit.toPlainText().strip(),
            }
            save_config(self.config)
            self.config_changed.emit(self.config)
            InfoBar.success("已保存", "配置已保存（含自定义指令）",
                           duration=2000, parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_error("保存配置异常", e)

    def get_config(self):
        try:
            return {
                "base_url": self.base_url_input.text().strip(),
                "api_key": self.api_key_input.text().strip(),
                "model": self.model_combo.currentText().strip(),
                "custom_prompt": self.prompt_edit.toPlainText().strip(),
            }
        except Exception as e:
            self._log_error("获取配置异常", e)
            return {}

    def _test_connection(self):
        try:
            base_url = self.base_url_input.text().strip()
            api_key = self.api_key_input.text().strip()
            if not base_url:
                InfoBar.warning("缺少信息", "请输入 Base URL",
                              duration=2000, parent=self, position=InfoBarPosition.TOP)
                return
            if not api_key:
                InfoBar.warning("缺少信息", "请输入 API Key",
                              duration=2000, parent=self, position=InfoBarPosition.TOP)
                return

            self.test_btn.setEnabled(False)
            self.test_btn.setText("测试中…")

            if self._test_worker and self._test_worker.isRunning():
                self._test_worker.quit()
                self._test_worker.wait(2000)

            model = self.model_combo.currentText().strip()
            self._test_worker = TestConnectionWorker(base_url, api_key, model)
            self._test_worker.result_ready.connect(self._on_test_result)
            self._test_worker.finished.connect(self._on_worker_finished)
            self._test_worker.start()
        except Exception as e:
            self._log_error("测试连接异常", e)
            self.test_btn.setEnabled(True)
            self.test_btn.setText("测试连接")

    def _on_test_result(self, success, message):
        try:
            if success:
                QMessageBox.information(self, "连接成功", message)
            else:
                QMessageBox.warning(self, "连接失败", message)
        except Exception as e:
            self._log_error("测试结果显示异常", e)

    def _on_worker_finished(self):
        try:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("测试连接")
            if self._test_worker:
                self._test_worker.deleteLater()
                self._test_worker = None
        except Exception as e:
            self._log_error("测试线程清理异常", e)

    def _select_folder(self):
        try:
            folder = QFileDialog.getExistingDirectory(self, "选择视频文件夹")
            if folder:
                self.folder_selected.emit(folder)
        except Exception as e:
            self._log_error("选择文件夹异常", e)

    def _select_files(self):
        try:
            files, _ = QFileDialog.getOpenFileNames(self, "选择视频文件", "", "MP4 视频 (*.mp4);;所有文件 (*.*)")
            if files:
                self.files_selected.emit(list(files))
        except Exception as e:
            self._log_error("选择文件异常", e)

    def set_processing(self, active):
        try:
            self.analyze_all_btn.setEnabled(not active)
            self.stop_btn.setEnabled(active)
            if active:
                self.analyze_all_btn.setText("处理中…")
            else:
                self.analyze_all_btn.setText("批量分析")
        except Exception as e:
            self._log_error("设置处理状态异常", e)
