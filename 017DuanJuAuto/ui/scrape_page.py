"""采集页面 —— 漫剧列表 + 批量/单条提取 + 进度日志。"""
import os
import html as _html
import tempfile
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor

from qfluentwidgets import (
    TitleLabel, BodyLabel, CaptionLabel,
    LineEdit, PushButton, PrimaryPushButton, TransparentPushButton,
    SimpleCardWidget, ProgressBar, SwitchButton,
    FluentIcon, InfoBar, InfoBarPosition,
)

from core.config import app_config
from core.scraper import BrowserThread, TOTAL_STEPS

MAX_LOG_LINES = 500

TABLE_COLUMNS = ["剧名", "漫剧ID", "制作方", "发布状态", "创建时间", "男女频", "分类"]


class ScrapePage(QWidget):
    _log_signal = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scrapePage")
        self._browser_thread: BrowserThread | None = None
        self._list_data: list[dict] = []
        self._filtered_rows: list[dict] = []
        self._current_page = 1
        self._page_size = 10
        self._extract_queue: list[dict] = []
        self._extract_idx = 0
        self._list_loading = False
        self._extracting = False
        self._in_batch = False
        self._output_dir = ""
        self._headless = app_config.silent_mode.value
        self._selected_keys: set[str] = set()

        self._log_signal.connect(self._append_log)
        self._filter_timer = QTimer()
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._apply_local_filter)
        self._build_ui()

    # ── Browser thread management ──

    def _ensure_browser_thread(self) -> BrowserThread:
        user_data_dir = app_config.user_data_dir.value or os.path.join(
            tempfile.gettempdir(), "playwright_chrome_profile")
        if self._browser_thread and self._browser_thread.headless != self._headless:
            self._browser_thread.shutdown()
            self._browser_thread.wait(5000)
            self._browser_thread = None
        if not self._browser_thread:
            self._browser_thread = BrowserThread(user_data_dir, self._headless)
            self._browser_thread.log_message.connect(self._on_log)
            self._browser_thread.progress_update.connect(self._on_progress)
            self._browser_thread.finished.connect(self._on_browser_finished)
            self._browser_thread.page_loaded.connect(self._on_page_loaded)
            self._browser_thread.list_loaded.connect(self._on_list_loaded)
            self._browser_thread.login_expired.connect(self._on_login_expired)
            self._browser_thread.start()
        return self._browser_thread

    def _on_silent_changed(self, checked: bool):
        self._headless = checked
        app_config.set(app_config.silent_mode, checked)
        if not self._list_loading and not self._extracting and self._browser_thread:
            self._browser_thread.shutdown()
            self._browser_thread.wait(5000)
            self._browser_thread = None

    # ── UI build ──

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title_row = QHBoxLayout()
        title = TitleLabel("漫剧素材采集")
        title_row.addWidget(title)
        title_row.addStretch()

        self._silent_switch = SwitchButton("后台静默运行")
        self._silent_switch.checkedChanged.connect(self._on_silent_changed)
        self._silent_switch.setChecked(self._headless)
        title_row.addWidget(self._silent_switch)
        root.addLayout(title_row)

        # ── List Card ──
        list_card = SimpleCardWidget()
        self._list_card = list_card
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(16, 12, 16, 12)
        list_layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.addWidget(BodyLabel("漫剧列表"))

        self._local_search = LineEdit()
        self._local_search.setPlaceholderText("本地筛选...")
        self._local_search.setFixedWidth(200)
        self._local_search.textChanged.connect(self._on_filter_text_changed)
        toolbar.addWidget(self._local_search)

        toolbar.addStretch()

        self._refresh_btn = PrimaryPushButton(FluentIcon.SYNC, "刷新列表")
        self._refresh_btn.clicked.connect(self._on_refresh_list)
        toolbar.addWidget(self._refresh_btn)

        select_all_btn = PushButton("全选")
        select_all_btn.clicked.connect(self._on_select_all)
        toolbar.addWidget(select_all_btn)

        deselect_all_btn = PushButton("取消")
        deselect_all_btn.clicked.connect(self._on_deselect_all)
        toolbar.addWidget(deselect_all_btn)

        self._batch_extract_btn = PrimaryPushButton(FluentIcon.CLOUD, "提取选中")
        self._batch_extract_btn.clicked.connect(self._on_batch_extract)
        self._batch_extract_btn.setEnabled(False)
        toolbar.addWidget(self._batch_extract_btn)

        list_layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setColumnCount(len(TABLE_COLUMNS) + 2)
        self._table.setHorizontalHeaderLabels(["", "操作"] + TABLE_COLUMNS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setColumnWidth(0, 36)
        self._table.setColumnWidth(1, 80)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for ci, w in [(3, 160), (4, 90), (5, 75), (6, 120), (7, 55), (8, 90)]:
            self._table.setColumnWidth(ci, w)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(42)
        list_layout.addWidget(self._table, stretch=1)

        pagination_row = QHBoxLayout()
        pagination_row.addStretch()

        self._prev_btn = PushButton("上一页")
        self._prev_btn.setFixedWidth(72)
        self._prev_btn.clicked.connect(self._on_prev_page)
        pagination_row.addWidget(self._prev_btn)

        self._page_label = CaptionLabel("第 1/1 页")
        self._page_label.setFixedWidth(80)
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination_row.addWidget(self._page_label)

        self._next_btn = PushButton("下一页")
        self._next_btn.setFixedWidth(72)
        self._next_btn.clicked.connect(self._on_next_page)
        pagination_row.addWidget(self._next_btn)

        pagination_row.addStretch()
        list_layout.addLayout(pagination_row)

        self._list_count_label = CaptionLabel("共 0 条漫剧 | 已选择 0 条")
        list_layout.addWidget(self._list_count_label)

        # ── Progress Card ──
        progress_card = SimpleCardWidget()
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(20, 12, 20, 12)
        progress_layout.setSpacing(6)

        progress_header = QHBoxLayout()
        progress_header.addWidget(BodyLabel("采集进度"))
        progress_header.addStretch()
        self._stop_btn = PushButton(FluentIcon.CLOSE, "停止")
        self._stop_btn.setFixedWidth(88)
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        progress_header.addWidget(self._stop_btn)
        progress_header.addSpacing(8)
        self._status_label = CaptionLabel("就绪 — 请先刷新列表")
        progress_header.addWidget(self._status_label)
        progress_layout.addLayout(progress_header)

        self._progress_bar = ProgressBar()
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._progress_bar)

        root.addWidget(progress_card)

        # ── Log Card ──
        log_card = SimpleCardWidget()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(12, 12, 12, 12)
        log_layout.setSpacing(8)

        log_header = QHBoxLayout()
        log_header.addWidget(BodyLabel("运行日志"))
        clear_btn = PushButton(FluentIcon.DELETE, "清空")
        clear_btn.clicked.connect(self._clear_log)
        log_header.addStretch()
        log_header.addWidget(clear_btn)
        log_layout.addLayout(log_header)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setPlaceholderText("运行日志…")
        self._log_edit.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self._log_edit, stretch=1)

        root.addWidget(list_card)
        root.addWidget(progress_card)
        root.addWidget(log_card, stretch=1)

    def _apply_list_height(self):
        if hasattr(self, '_list_card'):
            self._list_card.setMaximumHeight(self.height() // 2)
            self._list_card.setMinimumHeight(self.height() // 2)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_list_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_list_height()

    # ── List operations ──

    def _on_refresh_list(self):
        if self._extracting:
            InfoBar.warning(
                title="提示", content="正在提取中，请等待完成后再刷新列表",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self.window(),
            )
            return

        self._list_loading = True
        self._stop_btn.setEnabled(True)
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("加载中...")
        self._batch_extract_btn.setEnabled(False)
        self._status_label.setText("正在加载漫剧列表...")
        self._progress_bar.setValue(0)
        self._list_data.clear()
        self._filtered_rows.clear()
        self._selected_keys.clear()
        self._current_page = 1
        self._table.setRowCount(0)
        self._update_count_label()
        self._log("正在加载漫剧列表...")
        self._output_dir = app_config.output_dir.value

        bt = self._ensure_browser_thread()
        bt.submit_list_scrape()

    def _on_progress(self, step: int, desc: str):
        if self._list_loading:
            self._status_label.setText(desc)
        else:
            pct = int(step / TOTAL_STEPS * 100) if TOTAL_STEPS > 0 else 0
            self._progress_bar.setValue(pct)
            self._status_label.setText(desc)

    def _on_page_loaded(self, new_rows: list):
        if not new_rows:
            return
        self._list_data.extend(new_rows)
        filter_text = self._local_search.text()
        if filter_text:
            ft = filter_text.lower()
            self._filtered_rows.extend([r for r in new_rows if ft in str(r).lower()])
        else:
            self._filtered_rows.extend(new_rows)
        self._render_current_page()

    def _on_list_loaded(self, rows: list):
        self._list_data = rows
        filter_text = self._local_search.text()
        if filter_text:
            ft = filter_text.lower()
            self._filtered_rows = [r for r in rows if ft in str(r).lower()]
        else:
            self._filtered_rows = rows
        self._render_current_page()

    def _on_browser_finished(self, success: bool, message: str):
        if self._list_loading:
            self._on_list_finished(success, message)
        elif self._in_batch:
            self._on_batch_item_finished(success, message)
        else:
            self._on_extract_finished(success, message)

    def _on_list_finished(self, success: bool, message: str):
        self._list_loading = False
        self._update_stop_btn()
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("刷新列表")
        self._update_count_label()
        self._render_current_page()
        if success:
            self._status_label.setText(f"列表加载完成 — {message}")
        else:
            self._status_label.setText("列表加载失败")
            if "登录" in message:
                self._status_label.setText("登录已过期 — 请关闭静默模式重试")
            InfoBar.error(
                title="加载失败", content=message,
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=5000, parent=self.window(),
            )

    def _on_extract_finished(self, success: bool, message: str):
        self._extracting = False
        self._selected_keys.clear()
        self._update_stop_btn()
        self._refresh_btn.setEnabled(True)
        self._render_current_page()
        self._progress_bar.setValue(100 if success else 0)
        if success:
            self._status_label.setText("提取完成")
            InfoBar.success(
                title="提取完成", content=f"数据已保存到: {message}",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=5000, parent=self.window(),
            )
        elif "已取消" in message:
            self._status_label.setText("已取消")
        elif "登录已过期" in message:
            self._status_label.setText("需要重新登录")
            self._silent_switch.setChecked(False)
        else:
            self._status_label.setText("提取失败")
            InfoBar.error(
                title="提取失败", content=message,
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=5000, parent=self.window(),
            )

    def _render_current_page(self):
        self._table.setRowCount(0)
        total = len(self._filtered_rows)
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        if self._current_page > total_pages:
            self._current_page = total_pages
        start = (self._current_page - 1) * self._page_size
        end = min(start + self._page_size, total)
        page_rows = self._filtered_rows[start:end]

        self._table.setRowCount(len(page_rows))
        for ri, row in enumerate(page_rows):
            key = row.get("_detail_url") or row.get("_name", "")
            cb = QCheckBox()
            if key in self._selected_keys:
                cb.setChecked(True)
            cb.stateChanged.connect(lambda state, k=key: self._on_checkbox_toggled(k, state))
            cb.stateChanged.connect(self._update_count_label)
            self._table.setCellWidget(ri, 0, self._wrap_center(cb))

            extract_btn = TransparentPushButton("提取")
            extract_btn.setFixedHeight(28)
            extract_btn.setStyleSheet("QPushButton { font-size: 11px; padding: 1px 6px; }")
            extract_btn.clicked.connect(lambda checked, r=row: self._on_extract_single(r))
            if self._extracting:
                extract_btn.setEnabled(False)
            self._table.setCellWidget(ri, 1, self._wrap_center(extract_btn))

            name = row.get("_name", "")
            info_text = row.get("剧集信息", "")
            manju_id = ""
            for line in info_text.split("\n"):
                if "漫剧ID:" in line or "ID:" in line:
                    manju_id = line.split(":", 1)[-1].strip()
                    break
            if not manju_id:
                manju_id = row.get("_detail_url", "").rsplit("/", 1)[-1].split("?")[0]

            values = [
                name,
                manju_id,
                row.get("抖音发布账号", ""),
                row.get("抖音发布状态", ""),
                row.get("创建时间", ""),
                row.get("男女频", ""),
                row.get("分类", ""),
            ]
            for ci, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._table.setItem(ri, ci + 2, item)

        self._update_pagination_controls()
        self._update_count_label()

    def _update_pagination_controls(self):
        total = max(1, len(self._filtered_rows))
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        self._page_label.setText(f"第 {self._current_page}/{total_pages} 页")
        self._prev_btn.setEnabled(self._current_page > 1)
        self._next_btn.setEnabled(self._current_page < total_pages)

    def _on_prev_page(self):
        if self._current_page > 1:
            self._current_page -= 1
            self._render_current_page()

    def _on_next_page(self):
        total_pages = max(1, (len(self._filtered_rows) + self._page_size - 1) // self._page_size)
        if self._current_page < total_pages:
            self._current_page += 1
            self._render_current_page()

    @staticmethod
    def _wrap_center(widget):
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(widget)
        return w

    def _on_filter_text_changed(self, text: str):
        self._filter_timer.start(200)

    def _apply_local_filter(self):
        text = self._local_search.text()
        if text:
            ft = text.lower()
            self._filtered_rows = [r for r in self._list_data if ft in str(r).lower()]
        else:
            self._filtered_rows = self._list_data
        self._current_page = 1
        self._render_current_page()

    def _on_select_all(self):
        for ri in range(self._table.rowCount()):
            cb = self._table.cellWidget(ri, 0)
            if cb:
                cb_widget = cb.findChild(QCheckBox)
                if cb_widget:
                    cb_widget.setChecked(True)
        self._update_count_label()

    def _on_deselect_all(self):
        for ri in range(self._table.rowCount()):
            cb = self._table.cellWidget(ri, 0)
            if cb:
                cb_widget = cb.findChild(QCheckBox)
                if cb_widget:
                    cb_widget.setChecked(False)
        self._update_count_label()

    def _update_count_label(self, *_):
        total = len(self._filtered_rows)
        self._list_count_label.setText(
            f"共 {len(self._list_data)} 条漫剧 | 筛选 {total} 条 | 已选 {len(self._selected_keys)} 条"
        )
        self._batch_extract_btn.setEnabled(len(self._selected_keys) > 0)

    def _get_selected_rows(self) -> list[dict]:
        return [r for r in self._list_data
                if (r.get("_detail_url") or r.get("_name", "")) in self._selected_keys]

    def _on_checkbox_toggled(self, key: str, state: int):
        if state == Qt.CheckState.Checked.value:
            self._selected_keys.add(key)
        else:
            self._selected_keys.discard(key)

    # ── Extraction ──

    def _ensure_output_dir(self) -> str:
        if self._output_dir and os.path.isdir(self._output_dir):
            return self._output_dir
        config_dir = app_config.output_dir.value
        if config_dir and os.path.isdir(config_dir):
            self._output_dir = config_dir
            return self._output_dir
        path = QFileDialog.getExistingDirectory(self, "选择 Excel 保存目录")
        if path:
            self._output_dir = path
        return path

    def _on_extract_single(self, row: dict):
        if self._list_loading or self._extracting:
            InfoBar.warning(
                title="提示", content="正在处理中，请等待当前任务完成",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self.window(),
            )
            return
        output_dir = self._ensure_output_dir()
        if not output_dir:
            return
        name = row.get("_name", "")
        detail_url = row.get("_detail_url", "")
        if not name:
            return

        self._log(f"开始提取: {name}")
        self._start_extract(name, output_dir, detail_url)

    def _on_batch_extract(self):
        selected = self._get_selected_rows()
        if not selected:
            InfoBar.warning(
                title="提示", content="请先勾选要提取的漫剧",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self.window(),
            )
            return
        output_dir = self._ensure_output_dir()
        if not output_dir:
            return

        self._extract_queue = selected
        self._extract_idx = 0
        self._in_batch = True
        names = [r.get("_name", "?") for r in selected]
        self._log(f"批量提取 {len(self._extract_queue)} 部漫剧: {names}")
        self._process_next_batch()

    def _process_next_batch(self):
        if self._extract_idx >= len(self._extract_queue):
            self._in_batch = False
            self._extracting = False
            self._selected_keys.clear()
            self._update_stop_btn()
            self._refresh_btn.setEnabled(True)
            self._batch_extract_btn.setEnabled(True)
            self._progress_bar.setValue(100)
            self._status_label.setText("批量提取完成")
            self._log("批量提取全部完成", "success")
            self._render_current_page()
            InfoBar.success(
                title="批量提取完成",
                content=f"已处理 {self._extract_idx} 部漫剧",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=5000, parent=self.window(),
            )
            return

        row = self._extract_queue[self._extract_idx]
        name = row.get("_name", "")
        detail_url = row.get("_detail_url", "")
        self._log(f"[{self._extract_idx + 1}/{len(self._extract_queue)}] 提取: {name}")
        self._batch_extract_btn.setEnabled(False)
        self._start_extract(name, self._output_dir, detail_url)

    def _start_extract(self, name: str, output_dir: str, detail_url: str):
        self._extracting = True
        self._stop_btn.setEnabled(True)
        self._refresh_btn.setEnabled(False)
        if not self._in_batch:
            self._render_current_page()
        else:
            for ri in range(self._table.rowCount()):
                wrapper = self._table.cellWidget(ri, 1)
                if wrapper:
                    btn = wrapper.findChild(TransparentPushButton)
                    if btn:
                        btn.setEnabled(False)

        self._progress_bar.setValue(0)
        self._status_label.setText(f"正在提取: {name}")

        bt = self._ensure_browser_thread()
        bt.submit_detail_scrape(name, output_dir, detail_url)

    def _on_batch_item_finished(self, success: bool, message: str):
        if success:
            self._log(f"完成: {message}", "success")
        else:
            self._log(f"失败: {message}", "error")
        self._extract_idx += 1
        self._process_next_batch()

    # ── Log ──

    def _log(self, msg: str, level: str = "info"):
        self._log_signal.emit(msg, level)

    def _on_log(self, message: str, level: str = "info"):
        self._log_signal.emit(message, level)

    def _append_log(self, message: str, level: str):
        ts = datetime.now().strftime("%H:%M:%S")
        escaped = _html.escape(message)
        line = f'<b>[{ts}]</b> [{level.upper()}] {escaped}'
        cursor = self._log_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.insertHtml(line + "<br>")
        doc = self._log_edit.document()
        while doc.blockCount() > MAX_LOG_LINES:
            last_block = doc.lastBlock()
            cursor = QTextCursor(last_block)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            if doc.lastBlock().blockNumber() > 0:
                cursor.deletePreviousChar()

    def _clear_log(self):
        self._log_edit.clear()

    def _on_login_expired(self):
        if self._extracting and self._extract_queue:
            self._extract_queue.clear()
            self._in_batch = False
            self._log("检测到登录过期，已停止批量提取。请关闭静默模式后重试", "error")
            self._status_label.setText("需要登录 — 请关闭静默模式后重试")
            InfoBar.warning(
                title="需要登录",
                content="检测到登录过期，已停止批量提取。请关闭静默模式后重试",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=10000, parent=self.window(),
            )
            return

        self._silent_switch.setChecked(False)
        self._status_label.setText("需要登录 — 已自动关闭静默模式")
        self._log("检测到未登录，已自动关闭静默模式，请在弹出的浏览器中完成登录", "error")
        InfoBar.warning(
            title="需要登录",
            content="已自动关闭静默模式，请在浏览器中登录后重新操作",
            orient=Qt.Orientation.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=10000, parent=self.window(),
        )

    # ── Cleanup ──

    def _update_stop_btn(self):
        self._stop_btn.setEnabled(self._list_loading or self._extracting)

    def _on_stop(self):
        self._log("用户请求停止...", "warning")
        self._stop_btn.setEnabled(False)
        self._status_label.setText("正在停止...")
        if self._browser_thread:
            self._browser_thread.request_stop()
        self._list_loading = False
        self._extracting = False
        self._in_batch = False
        self._extract_queue.clear()
        self._selected_keys.clear()
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("刷新列表")
        self._render_current_page()

    def cleanup(self):
        """停止所有任务并关闭浏览器。由 MainWindow 关闭时调用。"""
        if self._browser_thread:
            self._browser_thread.shutdown()
            self._browser_thread.wait(5000)
            self._browser_thread = None
        self._list_loading = False
        self._extracting = False
        self._in_batch = False
        self._extract_queue.clear()
