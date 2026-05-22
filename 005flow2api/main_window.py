"""Main window — integrates all widgets and signal/slot wiring."""
import os
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QProgressBar, QFileDialog, QLabel, QFrame, QDialog,
    QMessageBox,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, FluentIcon,
    InfoBar, InfoBarPosition,
)

from api_client import Flow2ApiClient
from gemini_cdp import GeminiCDPClient
from server_manager import ServerManager, read_flow2api_config, check_dependencies
from worker import BatchGenerationManager
from downloader import save_single_image, ZipperThread
from widgets import PromptPanel, ImageGrid, LogPanel, SettingsDialog
from config import cfg
from utils import build_full_model_name, ASPECT_RATIO_SIZE_MAP, sanitize_filename, Character


class MainWindow(QMainWindow):
    """Desktop batch image generation tool main window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("批量图片生成工具    微信：rpalele")
        self.resize(1280, 800)
        self.setMinimumSize(960, 600)

        self._client: Flow2ApiClient | GeminiCDPClient | None = None
        self._batch_manager: BatchGenerationManager | None = None
        self._zipper: ZipperThread | None = None
        self._server_manager = ServerManager(self)
        self._batch_cancelled = False
        self._generating = False
        self._success_count = 0
        self._last_full_model = ""
        self._last_image_size = ""

        self._setup_ui()
        self._setup_server()
        self._connect_signals()

        if cfg.server_auto_start.value and cfg.use_local_server.value:
            self._on_toggle_server()

    # ---- UI Setup ----

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.prompt_panel = PromptPanel()

        # Right side
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        # ---- Server control bar ----
        server_bar = QHBoxLayout()
        server_bar.setSpacing(8)

        self.server_status_dot = QLabel()
        self.server_status_dot.setFixedSize(10, 10)
        self._set_status_dot("stopped")
        server_bar.addWidget(self.server_status_dot)

        self.server_status_label = QLabel("API 服务: 未启动")
        self.server_status_label.setStyleSheet("color: #888; font-size: 12px;")
        server_bar.addWidget(self.server_status_label)

        server_bar.addSpacing(12)

        self.server_url_label = QLabel("")
        self.server_url_label.setStyleSheet("color: #5cb85c; font-size: 11px;")
        server_bar.addWidget(self.server_url_label, 1)

        self.api_mode_label = QLabel("")
        self.api_mode_label.setStyleSheet("color: #5bc0de; font-size: 11px; font-weight: bold;")
        server_bar.addWidget(self.api_mode_label)

        self.start_server_btn = PrimaryPushButton("启动 API 服务")
        self.start_server_btn.setFixedHeight(26)
        self.start_server_btn.clicked.connect(self._on_toggle_server)
        server_bar.addWidget(self.start_server_btn)

        self.settings_btn = PushButton("API 设置")
        self.settings_btn.setIcon(FluentIcon.SETTING)
        self.settings_btn.setFixedHeight(26)
        self.settings_btn.clicked.connect(self._on_open_settings)
        server_bar.addWidget(self.settings_btn)

        self.open_admin_btn = PushButton("打开 Gemini")
        self.open_admin_btn.setFixedHeight(26)
        self.open_admin_btn.clicked.connect(self._on_open_admin)
        server_bar.addWidget(self.open_admin_btn)

        self._update_server_bar_mode()

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #ddd;")

        right_layout.addLayout(server_bar)
        right_layout.addWidget(separator)

        # ---- Generation toolbar ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setFormat("就绪")
        toolbar.addWidget(self.progress_bar, 1)

        self.select_all_btn = PushButton("全选")
        self.select_all_btn.setFixedHeight(28)
        self.select_all_btn.clicked.connect(self._on_select_all)
        toolbar.addWidget(self.select_all_btn)

        self.download_selected_btn = PushButton("下载所选")
        self.download_selected_btn.setIcon(FluentIcon.DOWN)
        self.download_selected_btn.setFixedHeight(28)
        self.download_selected_btn.clicked.connect(self._on_download_selected)
        toolbar.addWidget(self.download_selected_btn)

        self.zip_btn = PrimaryPushButton("打包 ZIP")
        self.zip_btn.setIcon(FluentIcon.SAVE_AS)
        self.zip_btn.setFixedHeight(28)
        self.zip_btn.clicked.connect(self._on_zip_all)
        toolbar.addWidget(self.zip_btn)

        self.batch_retry_btn = PushButton("批量重试")
        self.batch_retry_btn.setIcon(FluentIcon.SYNC)
        self.batch_retry_btn.setFixedHeight(28)
        self.batch_retry_btn.clicked.connect(self._on_batch_retry)
        toolbar.addWidget(self.batch_retry_btn)

        self.batch_delete_btn = PushButton("批量删除")
        self.batch_delete_btn.setIcon(FluentIcon.DELETE)
        self.batch_delete_btn.setFixedHeight(28)
        self.batch_delete_btn.clicked.connect(self._on_batch_delete)
        toolbar.addWidget(self.batch_delete_btn)

        right_layout.addLayout(toolbar)

        # Image grid
        self.image_grid = ImageGrid()
        right_layout.addWidget(self.image_grid, 1)

        # Log panel
        self.log_panel = LogPanel()
        right_layout.addWidget(self.log_panel)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.prompt_panel)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 900])
        root.addWidget(splitter)

    # ---- Server management ----

    def _setup_server(self):
        self._server_manager.state_changed.connect(self._on_server_state)
        self._server_manager.log_line.connect(self._on_server_log)
        self._server_manager.server_url_changed.connect(self._on_server_ready)

    def _on_toggle_server(self):
        if self._server_manager.is_running:
            self._server_manager.stop_server()
        elif self._server_manager.state == "starting":
            self._server_manager.stop_server()
        else:
            ok, msg = check_dependencies()
            if not ok:
                self.log_panel.log(msg, "ERROR")
                InfoBar.error(
                    title="依赖缺失",
                    content="playwright 依赖未安装，请查看日志",
                    orient=Qt.Horizontal, isClosable=True,
                    position=InfoBarPosition.BOTTOM_RIGHT, duration=6000, parent=self,
                )
                return
            self._server_manager.start_server()

    def _on_server_state(self, state: str):
        self._set_status_dot(state)
        is_local = cfg.use_local_server.value
        noun = "Chrome" if is_local else "API 服务"
        labels = {
            "stopped": f"{noun}: 未连接" if is_local else "API 服务: 未启动",
            "starting": f"{noun}: 连接中…" if is_local else "API 服务: 启动中…",
            "running": f"{noun}: 已连接" if is_local else "API 服务: 运行中",
            "error": f"{noun}: 连接失败" if is_local else "API 服务: 启动失败",
        }
        self.server_status_label.setText(labels.get(state, state))
        self.server_status_label.setStyleSheet(
            f"font-size: 12px; color: {'#5cb85c' if state == 'running' else '#d9534f' if state == 'error' else '#888'};"
        )

        if is_local:
            if state == "running":
                self.start_server_btn.setText("断开 Chrome")
                self.start_server_btn.setEnabled(True)
            elif state == "starting":
                self.start_server_btn.setText("取消连接")
                self.start_server_btn.setEnabled(True)
            else:
                self.start_server_btn.setText("连接 Chrome")
                self.start_server_btn.setEnabled(True)
                self.server_url_label.setText("")
        else:
            if state == "running":
                self.start_server_btn.setText("停止 API 服务")
                self.start_server_btn.setEnabled(True)
            elif state == "starting":
                self.start_server_btn.setText("取消启动")
                self.start_server_btn.setEnabled(True)
            else:
                self.start_server_btn.setText("启动 API 服务")
                self.start_server_btn.setEnabled(True)
                self.server_url_label.setText("")

    def _on_server_ready(self, url: str):
        self.server_url_label.setText(url)
        cfg.set(cfg.api_base_url, url)
        flow2_cfg = read_flow2api_config()
        if flow2_cfg.get("api_key"):
            cfg.set(cfg.api_key, flow2_cfg["api_key"])
        self._connect_client()

    def _on_server_log(self, line: str):
        self.log_panel.log(f"[SERVER] {line}")

    def _on_open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == SettingsDialog.Accepted:
            self._update_server_bar_mode()
            self._connect_client()
            self.log_panel.log("API 配置已更新", "SUCCESS")

    def _on_open_admin(self):
        if not cfg.use_local_server.value:
            InfoBar.info(
                title="提示", content="远程 API 模式下无需打开 Gemini 页面",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=3000, parent=self,
            )
            return
        webbrowser.open("https://gemini.google.com/app")

    def _update_server_bar_mode(self):
        """Show/hide server controls based on local vs remote mode."""
        is_local = cfg.use_local_server.value
        self.start_server_btn.setVisible(is_local)
        self.open_admin_btn.setVisible(is_local)
        self.server_status_dot.setVisible(is_local)
        if is_local:
            self.api_mode_label.setText("")
            self.open_admin_btn.setText("打开 Gemini")
            if not self._server_manager.is_running:
                self.start_server_btn.setText("连接 Chrome")
        else:
            self.api_mode_label.setText("API 模式: 远程")
        # Refresh state label to show correct nouns (Chrome vs API 服务)
        self._on_server_state(self._server_manager.state)

    def _connect_client(self):
        is_local = cfg.use_local_server.value

        if is_local:
            host = cfg.chrome_debug_host.value
            port = cfg.chrome_debug_port.value
            self._client = GeminiCDPClient(chrome_host=host, chrome_port=port)
            ok, msg = self._client.check_connection()
            if ok:
                self.log_panel.log(f"Chrome CDP 已连接 — {msg}", "SUCCESS")
            else:
                self.log_panel.log(f"Chrome CDP 未连接: {msg}", "WARN")
            return

        # Remote mode — unchanged
        base_url = cfg.api_base_url.value
        api_key = cfg.api_key.value
        session_cookie = cfg.api_session_cookie.value
        user_id = cfg.api_user_id.value

        if not api_key and not session_cookie:
            self.log_panel.log("API Key 或 Session Cookie 未配置，请在 API 设置中填写", "WARN")
            self._client = None
            return

        endpoint_path = cfg.api_endpoint_path.value
        self._client = Flow2ApiClient(base_url, api_key, endpoint_path=endpoint_path,
                                      session_cookie=session_cookie, user_id=user_id)

        auth_info = "Session Cookie" if session_cookie else ("API Key" if api_key else "无认证")
        self.log_panel.log(f"API 客户端已配置 — {base_url}{endpoint_path} | 认证方式: {auth_info}")

    def _set_status_dot(self, state: str):
        colors = {
            "stopped": "#ccc",
            "starting": "#f0ad4e",
            "running": "#5cb85c",
            "error": "#d9534f",
        }
        color = colors.get(state, "#ccc")
        self.server_status_dot.setStyleSheet(
            f"QLabel {{ background-color: {color}; border-radius: 5px; }}"
        )

    # ---- Signals ----

    def _connect_signals(self):
        self.prompt_panel.start_generation.connect(self._on_start_generation)
        self.prompt_panel.parse_requested.connect(self._on_parse_characters)
        self.prompt_panel.reference_cards_requested.connect(self._on_reference_cards)
        # Replace PromptPanel's direct generate connection with a state-aware dispatch
        try:
            self.prompt_panel.generate_btn.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.prompt_panel.generate_btn.clicked.connect(self._on_generate_clicked)

    def _on_generate_clicked(self):
        """Dispatch button click to generate or cancel based on current state."""
        if self._generating:
            self._on_cancel()
        else:
            self.prompt_panel._on_generate()

    # ---- Parse Slot ----

    def _on_parse_characters(self, characters: list, prefix: str, suffix: str, ratio: str, resolution: str):
        if not characters:
            return
        self.image_grid.setup_cards(characters)
        self._connect_card_signals()
        self.prompt_panel.enable_generate(True)
        self.log_panel.log(f"已解析 {len(characters)} 个角色，可编辑或删减后点击「开始生图」", "SUCCESS")

    def _on_reference_cards(self, items: list):
        """Create cards from reference images — each image becomes an independent card."""
        if not items:
            return
        chars = [
            Character(name=name, description="", index=len(self.image_grid.cards) + i)
            for i, (name, _) in enumerate(items)
        ]
        new_cards = self.image_grid.add_cards(chars)
        for card, (name, img_bytes) in zip(new_cards, items):
            card.reference_image = img_bytes
            card.set_thumbnail(img_bytes)
            card.set_state("idle")
        self._connect_card_signals()
        self.prompt_panel.enable_generate(True)
        self.log_panel.log(f"已从参考图创建 {len(items)} 张卡片", "SUCCESS")

    # ---- Generation helpers ----

    def _ensure_can_generate(self, require_server: bool = True) -> bool:
        """Check that no batch is running, server/client are ready. Returns True if OK."""
        if self._generating:
            InfoBar.warning(
                title="任务进行中",
                content="请等待当前批量任务完成或取消后再开始新任务",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=3000, parent=self,
            )
            return False
        if self._batch_manager is not None and self._batch_manager.is_running:
            InfoBar.warning(
                title="任务进行中",
                content="请等待当前批量任务完成或取消后再开始新任务",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=3000, parent=self,
            )
            return False
        if require_server and cfg.use_local_server.value and not self._server_manager.is_running:
            InfoBar.warning(
                title="API 服务未启动",
                content='请先点击「启动 API 服务」或切换到远程 API 模式',
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=4000, parent=self,
            )
            return False
        if self._client is None:
            self._connect_client()
            if self._client is None:
                InfoBar.error(
                    title="连接失败",
                    content="请先配置正确的 API 地址和 Key",
                    orient=Qt.Horizontal, isClosable=True,
                    position=InfoBarPosition.BOTTOM_RIGHT, duration=5000, parent=self,
                )
                return False
        return True

    def _ensure_model_params(self, ratio: str = "square", resolution: str = "2k"):
        """Set fallback model name and image size if not already set."""
        if self._last_full_model:
            return
        is_remote = not cfg.use_local_server.value
        self._last_full_model = build_full_model_name(cfg.model_name.value, ratio, resolution, remote=is_remote)
        self._last_image_size = ASPECT_RATIO_SIZE_MAP.get(ratio, "") if is_remote else ""

    def _create_batch_manager(self) -> BatchGenerationManager:
        """Create a new BatchGenerationManager with signals wired up.

        In local CDP mode, pass connection params so the worker thread creates
        its own GeminiCDPClient (Playwright is not thread-safe).
        """
        is_local = cfg.use_local_server.value
        if is_local:
            mgr = BatchGenerationManager(
                client=None,
                cdp_host=cfg.chrome_debug_host.value,
                cdp_port=cfg.chrome_debug_port.value,
            )
        else:
            mgr = BatchGenerationManager(self._client)
        mgr.item_started.connect(self._on_item_started)
        mgr.item_finished.connect(self._on_item_finished)
        mgr.batch_progress.connect(self._on_batch_progress)
        mgr.all_finished.connect(self._on_all_finished)
        self._batch_manager = mgr
        return mgr

    # ---- Generation Slots ----

    def _on_start_generation(self, characters: list, prefix: str, suffix: str, ratio: str, resolution: str):
        if not self._ensure_can_generate(require_server=True):
            return

        # Gather idle cards from the live grid (respects user deletions/reordering)
        idle_items = []
        for i, card in enumerate(self.image_grid.cards):
            if card.state in ("idle", "error"):
                full_prompt = prefix + card.description + suffix
                idle_items.append((i, full_prompt, card.reference_image))
                card.reset_description_edited()

        if not idle_items:
            InfoBar.info(
                title="提示", content="没有待生成的卡片",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=3000, parent=self,
            )
            return

        is_remote = not cfg.use_local_server.value
        if is_remote:
            model_name = cfg.model_name.value
            self._last_full_model = build_full_model_name(model_name, ratio, resolution, remote=True)
            self._last_image_size = ASPECT_RATIO_SIZE_MAP.get(ratio, "")
        else:
            self._last_full_model = "Gemini (本地)"
            self._last_image_size = ""

        self.progress_bar.setMaximum(len(idle_items))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0 / %d" % len(idle_items))
        if is_remote:
            self.log_panel.log(f"开始批量生成 — {len(idle_items)} 个提示词, 模型: {self._last_full_model}")
        else:
            self.log_panel.log(f"开始批量生成 — {len(idle_items)} 个提示词 (Gemini 本地 CDP)")

        self._success_count = 0
        self._batch_cancelled = False
        self._set_generating(True)
        self._create_batch_manager().start_indexed_batch(
            idle_items, self._last_full_model, self._last_image_size)

    def _connect_card_signals(self):
        """Wire signals for all cards currently in the grid."""
        for card in self.image_grid.cards:
            # Disconnect first to avoid double-connection when re-wiring
            for sig in (card.delete_clicked, card.retry_clicked,
                        card.download_clicked, card.view_clicked,
                        card.copy_clicked, card.description_edited):
                try:
                    sig.disconnect()
                except (TypeError, RuntimeError):
                    pass
            card.delete_clicked.connect(self._on_card_delete)
            card.retry_clicked.connect(self._on_card_retry)
            card.download_clicked.connect(self._on_card_download)
            card.view_clicked.connect(self._on_view_image)
            card.copy_clicked.connect(self._on_card_copy)
            card.description_edited.connect(self._on_card_description_edited)

    def _on_item_started(self, index: int):
        card = self.image_grid.get_card(index)
        if card:
            card.set_state("generating")
            full_prompt = self._read_prefix() + card.description + self._read_suffix()
            if cfg.use_local_server.value:
                self.log_panel.log(f"[{card.name}] 开始生成 (Gemini 本地) | 提示词: {full_prompt}")
            else:
                self.log_panel.log(f"[{card.name}] 开始生成 → 模型: {self._last_full_model} | 提示词: {full_prompt}")

    def _on_item_finished(self, index: int, result):
        card = self.image_grid.get_card(index)
        if not card:
            return
        if result.success and result.image_data:
            card.set_thumbnail(result.image_data)
            card.set_state("done")
            self._success_count += 1
            self.log_panel.log(f"[{card.name}] 生成成功", "SUCCESS")
        else:
            card.set_state("error", result.error_message or "未知错误")
            self.log_panel.log(f"[{card.name}] 生成失败:\n{result.error_message}", "ERROR")

    def _on_batch_progress(self, done: int, total: int):
        self.progress_bar.setValue(done)
        self.progress_bar.setFormat(f"{done} / {total}")

    def _set_generating(self, active: bool):
        self._generating = active
        if active:
            self.prompt_panel.generate_btn.setText("停止生成")
            self.prompt_panel.generate_btn.setStyleSheet(
                "QPushButton { background-color: #d9534f; color: white; }"
                "QPushButton:hover { background-color: #c9302c; }"
            )
        else:
            self.prompt_panel.generate_btn.setText("开始生图")
            self.prompt_panel.generate_btn.setStyleSheet("")

    def _on_all_finished(self):
        self._set_generating(False)
        self._batch_manager = None
        if self._batch_cancelled:
            return
        self.progress_bar.setFormat("完成")
        total = self.progress_bar.maximum()
        self.log_panel.log(f"批量生成结束 — {self._success_count}/{total} 成功", "SUCCESS")

    def _on_cancel(self):
        self._batch_cancelled = True
        if self._batch_manager:
            self._batch_manager.cancel()
            self._batch_manager = None
            self.log_panel.log("用户取消了生成任务", "WARN")
            self._set_generating(False)
        self.progress_bar.setFormat("已取消")

    def _read_prefix(self) -> str:
        return self.prompt_panel.prefix_edit.toPlainText().strip()

    def _read_suffix(self) -> str:
        return self.prompt_panel.suffix_edit.toPlainText().strip()

    # ---- Card action handlers ----

    def _on_card_delete(self, index: int):
        card = self.image_grid.get_card(index)
        if not card:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除角色卡「{card.name}」吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        name = card.name
        self.image_grid.remove_card(index)
        for i, c in enumerate(self.image_grid.cards):
            c.index = i
        self.log_panel.log(f"已删除角色卡: {name}")

    def _on_card_retry(self, index: int):
        if not self._ensure_can_generate(require_server=False):
            return

        card = self.image_grid.get_card(index)
        if not card:
            return

        full_prompt = self._read_prefix() + card.description + self._read_suffix()
        self._ensure_model_params()

        card.reset_description_edited()
        self._set_generating(True)
        self._create_batch_manager().start_single(
            index, full_prompt, self._last_full_model, card.reference_image,
            self._last_image_size)
        self.log_panel.log(f"[{card.name}] 重新生成中…")

    def _on_card_download(self, index: int):
        card = self.image_grid.get_card(index)
        if card and card.image_data:
            save_single_image(self, card.image_data, card.name)
            self.log_panel.log(f"[{card.name}] 图片已保存")

    def _on_card_copy(self, index: int):
        card = self.image_grid.get_card(index)
        if not card:
            return
        full_prompt = self._read_prefix() + card.description + self._read_suffix()
        QGuiApplication.clipboard().setText(full_prompt)
        self.log_panel.log(f"[{card.name}] 完整提示词已复制到剪贴板")

    def _on_card_description_edited(self, index: int, new_desc: str):
        card = self.image_grid.get_card(index)
        if card:
            self.log_panel.log(f"[{card.name}] 描述词已更新")

    # ---- View image ----

    def _on_view_image(self, index: int):
        card = self.image_grid.get_card(index)
        if not card or not card.image_data:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"查看大图 — {card.name}")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        label = QLabel()
        pixmap = QPixmap()
        pixmap.loadFromData(card.image_data)
        scaled = pixmap.scaled(780, 580, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        dialog.exec()

    # ---- Select / Download / ZIP ----

    def _on_select_all(self):
        cards = self.image_grid.cards
        if not cards:
            InfoBar.info(
                title="提示", content="没有角色卡可选择",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=3000, parent=self,
            )
            return
        all_checked = all(c.is_checked for c in cards)
        if all_checked:
            for c in cards:
                c.checkbox.setChecked(False)
            self.log_panel.log("已取消全选")
        else:
            for c in cards:
                c.checkbox.setChecked(True)
            self.log_panel.log(f"已全选 {len(cards)} 张卡片")

    def _on_download_selected(self):
        checked = [c for c in self.image_grid.cards if c.is_checked and c.image_data]
        if not checked:
            InfoBar.info(
                title="提示", content="没有已勾选且已生成的图片可下载",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=3000, parent=self,
            )
            return

        folder = QFileDialog.getExistingDirectory(self, "选择保存目录",
            os.path.join(os.path.expanduser("~"), "Desktop"))
        if not folder:
            return

        saved = 0
        for card in checked:
            if card.image_data:
                fname = f"{sanitize_filename(card.name, 40)}.jpg"
                Path(os.path.join(folder, fname)).write_bytes(card.image_data)
                saved += 1
        self.log_panel.log(f"已保存 {saved} 张图片到 {folder}", "SUCCESS")

    def _on_zip_all(self):
        done_cards = self.image_grid.done_cards
        if not done_cards:
            InfoBar.info(
                title="提示", content="没有可打包的图片",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=3000, parent=self,
            )
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存 ZIP", "images.zip", "ZIP 压缩包 (*.zip)"
        )
        if not save_path:
            return
        items = [(card.name, card.image_data) for card in done_cards]
        self._zipper = ZipperThread(save_path, items)
        self._zipper.finished.connect(self._on_zip_finished)
        self._zipper.error.connect(self._on_zip_error)
        self._zipper.start()
        self.log_panel.log(f"正在打包 {len(items)} 张图片为 ZIP…")

    def _on_zip_finished(self, path: str):
        self.log_panel.log(f"ZIP 已保存: {path}", "SUCCESS")
        InfoBar.success(
            title="打包完成", content=f"ZIP 已保存至: {path}",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT, duration=5000, parent=self,
        )

    def _on_zip_error(self, error: str):
        self.log_panel.log(f"ZIP 打包失败: {error}", "ERROR")
        InfoBar.error(
            title="打包失败", content=error,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT, duration=5000, parent=self,
        )

    # ---- Batch operations ----

    def _on_batch_delete(self):
        checked = [c for c in self.image_grid.cards if c.is_checked]
        if not checked:
            InfoBar.info(
                title="提示", content="请先勾选要删除的卡片",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=3000, parent=self,
            )
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(checked)} 张卡片吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        count = self.image_grid.remove_checked()
        if count > 0:
            for i, c in enumerate(self.image_grid.cards):
                c.index = i
            self.log_panel.log(f"已批量删除 {count} 张卡片")

    def _on_batch_retry(self):
        if not self._ensure_can_generate(require_server=False):
            return

        failed = self.image_grid.failed_cards
        if not failed:
            InfoBar.info(
                title="提示", content="没有生成失败的卡片",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT, duration=3000, parent=self,
            )
            return

        self._ensure_model_params()

        prefix = self._read_prefix()
        suffix = self._read_suffix()
        items = [(self.image_grid.cards.index(c), prefix + c.description + suffix, c.reference_image) for c in failed]
        for c in failed:
            c.reset_description_edited()

        self._set_generating(True)
        self._create_batch_manager().start_indexed_batch(
            items, self._last_full_model, self._last_image_size)

        self.progress_bar.setMaximum(len(items))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0 / {len(items)}")
        self.log_panel.log(f"批量重试 {len(items)} 个失败角色")

    # ---- Cleanup ----

    def closeEvent(self, event):
        if self._batch_manager and self._batch_manager.is_running:
            self._batch_manager.cancel()
        if self._zipper and self._zipper.isRunning():
            self._zipper.quit()
            self._zipper.wait(2000)
        if self._server_manager.is_running:
            self._server_manager.stop_server()
        if isinstance(self._client, GeminiCDPClient):
            self._client.disconnect()
        super().closeEvent(event)
