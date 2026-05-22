"""任务管理页面 - 即梦视频生成"""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QHeaderView,
    QAbstractItemView, QTableWidget, QTableWidgetItem, QSplitter,
)
from qfluentwidgets import (
    TableWidget, CardWidget, PrimaryPushButton, PushButton,
    FluentIcon, InfoBar, ComboBox, LineEdit, TextEdit,
    BodyLabel, CaptionLabel, StrongBodyLabel, ScrollArea,
)

from data.models import Task, TaskStatus
from core.task_manager import TaskManager
from core.material_matcher import MaterialMatcher
from core.dreamina_cli import DreaminaCLI, GenerationWorker
from ui.import_dialog import ImportDialog
from ui.character_dialog import CharacterDialog
from ui.widgets import StatCard, StatusBadge, DetailPanel
from utils.theme import THEME, STATUS_COLORS


class TaskPage(QWidget):
    """任务管理页面"""

    def __init__(self, task_manager: TaskManager,
                 material_matcher: MaterialMatcher,
                 dreamina_cli: DreaminaCLI, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.material_matcher = material_matcher
        self.dreamina_cli = dreamina_cli
        self._worker: QThread = None
        self._gen_worker: GenerationWorker = None
        self._selected_task: Task = None

        self._init_ui()
        self._connect_signals()
        self._refresh_stats()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # ── 统计卡片行 ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        self._card_pending = StatCard("待生成", 0, "⏳", THEME["text_secondary"])
        self._card_generating = StatCard("生成中", 0, "🎬", THEME["primary"])
        self._card_completed = StatCard("已完成", 0, "✓", THEME["success"])
        self._card_failed = StatCard("失败", 0, "✗", THEME["danger"])
        for c in [self._card_pending, self._card_generating,
                  self._card_completed, self._card_failed]:
            stats_layout.addWidget(c)
        layout.addLayout(stats_layout)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._btn_import = PrimaryPushButton(FluentIcon.ADD, "导入任务")
        self._btn_generate = PrimaryPushButton(FluentIcon.PLAY, "开始生成")
        self._btn_generate.setEnabled(False)
        self._btn_pause = PushButton(FluentIcon.PAUSE, "暂停")
        self._btn_pause.setEnabled(False)
        self._btn_retry = PushButton(FluentIcon.SYNC, "重试失败")
        self._btn_character = PushButton(FluentIcon.PEOPLE, "人物对照表")

        toolbar.addWidget(self._btn_import)
        toolbar.addWidget(self._btn_generate)
        toolbar.addWidget(self._btn_pause)
        toolbar.addWidget(self._btn_retry)
        toolbar.addStretch()
        toolbar.addWidget(self._btn_character)
        layout.addLayout(toolbar)

        # ── 主区域：左右分栏 ──
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：任务列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._table = TableWidget(self)
        self._table.setBorderRadius(8)
        self._table.setAlternatingRowColors(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        left_layout.addWidget(self._table)
        splitter.addWidget(left_widget)

        # 右侧：详情面板
        self._detail_panel = DetailPanel("任务详情", self)
        self._setup_detail_panel()
        splitter.addWidget(self._detail_panel)

        splitter.setSizes([750, 350])
        layout.addWidget(splitter)

        # ── 设置表格 ──
        self._setup_table()

        # 连接信号
        self._btn_import.clicked.connect(self._on_import)
        self._btn_generate.clicked.connect(self._on_generate)
        self._btn_pause.clicked.connect(self._on_pause)
        self._btn_retry.clicked.connect(self._on_retry_failed)
        self._btn_character.clicked.connect(self._on_character)
        self._btn_save.clicked.connect(self._on_save_detail)
        self._detail_duration.currentTextChanged.connect(self._on_detail_changed)
        self._detail_ratio.currentTextChanged.connect(self._on_detail_changed)
        self._table.clicked.connect(self._on_task_selected)

    def _setup_table(self):
        """配置表格列"""
        columns = ["场次", "描述词", "时长", "比例", "状态", "操作"]
        self._table.setColumnCount(len(columns))
        self._table.setHorizontalHeaderLabels(columns)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 80)
        self._table.setColumnWidth(2, 60)
        self._table.setColumnWidth(3, 60)
        self._table.setColumnWidth(4, 80)
        self._table.setColumnWidth(5, 80)

    def _setup_detail_panel(self):
        """设置详情面板内容"""
        content = self._detail_panel._content_layout

        # 场次显示
        self._detail_scene = BodyLabel("选择左侧任务查看详情")
        self._detail_scene.setStyleSheet(f"font-size: 13px; color: {THEME['text_secondary']};")
        content.addWidget(self._detail_scene)

        # 时长
        duration_row = QHBoxLayout()
        duration_row.addWidget(BodyLabel("时长:"))
        self._detail_duration = ComboBox()
        self._detail_duration.addItems([f"{s}秒" for s in range(3, 16)])
        self._detail_duration.setCurrentIndex(9)  # 12秒
        self._detail_duration.setEnabled(False)
        duration_row.addWidget(self._detail_duration)
        duration_row.addStretch()
        content.addLayout(duration_row)

        # 比例
        ratio_row = QHBoxLayout()
        ratio_row.addWidget(BodyLabel("比例:"))
        self._detail_ratio = ComboBox()
        for r in ["16:9", "9:16", "21:9", "4:3", "1:1", "3:4"]:
            self._detail_ratio.addItem(r)
        self._detail_ratio.setEnabled(False)
        ratio_row.addWidget(self._detail_ratio)
        ratio_row.addStretch()
        content.addLayout(ratio_row)

        # 提示词
        content.addWidget(BodyLabel("提示词:"))
        self._detail_prompt = TextEdit()
        self._detail_prompt.setReadOnly(True)
        self._detail_prompt.setMaximumHeight(120)
        self._detail_prompt.setStyleSheet(f"""
            TextEdit {{
                background-color: {THEME['bg_card']};
                border: 1px solid {THEME['border']};
                border-radius: 6px;
                padding: 8px;
                color: {THEME['text_primary']};
            }}
        """)
        content.addWidget(self._detail_prompt)

        # 保存按钮
        self._btn_save = PushButton(FluentIcon.SAVE, "保存修改")
        self._btn_save.setEnabled(False)
        content.addWidget(self._btn_save)

    def _connect_signals(self):
        """连接 TaskManager 信号"""
        self.task_manager.task_added.connect(lambda _: self._refresh_table())
        self.task_manager.task_removed.connect(lambda _: self._refresh_table())
        self.task_manager.task_updated.connect(lambda _: self._refresh_table())
        self.task_manager.tasks_imported.connect(lambda _: self._refresh_table())

    def _refresh_table(self):
        """刷新表格"""
        self._table.setRowCount(0)
        tasks = self.task_manager.get_all_tasks()
        tasks.sort(key=lambda t: t.seq)

        for i, task in enumerate(tasks):
            self._table.insertRow(i)
            self._table.setItem(i, 0, self._cell(task.scene))
            prompt_text = task.prompt[:50] + ("..." if len(task.prompt) > 50 else "")
            self._table.setItem(i, 1, self._cell(prompt_text))
            self._table.setItem(i, 2, self._cell(f"{task.duration}秒"))
            self._table.setItem(i, 3, self._cell(task.ratio))

            # 状态徽章
            status_widget = StatusBadge(task.status.value)
            self._table.setCellWidget(i, 4, status_widget)

            # 操作按钮
            action_text = "重新生成" if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) else "生成"
            self._table.setItem(i, 5, self._cell(action_text))

        self._refresh_stats()

    def _cell(self, text: str):
        """创建表格单元格"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _refresh_stats(self):
        """刷新统计卡片"""
        stats = self.task_manager.get_stats()
        self._card_pending.set_value(stats.get("pending", 0))
        self._card_generating.set_value(stats.get("generating", 0))
        self._card_completed.set_value(stats.get("completed", 0))
        self._card_failed.set_value(stats.get("failed", 0))

        has_pending = stats.get("pending", 0) > 0
        self._btn_generate.setEnabled(has_pending)

    def _on_task_selected(self, index):
        """选择任务时更新详情"""
        tasks = sorted(self.task_manager.get_all_tasks(), key=lambda t: t.seq)
        row = index.row()
        if row < 0 or row >= len(tasks):
            return
        self._selected_task = tasks[row]
        task = self._selected_task

        self._detail_panel.set_title(f"任务详情 - {task.scene}")
        self._detail_scene.setText(f"场次：{task.scene}")
        self._detail_duration.setCurrentText(f"{task.duration}秒")
        self._detail_duration.setEnabled(True)
        self._detail_ratio.setCurrentText(task.ratio)
        self._detail_ratio.setEnabled(True)
        self._detail_prompt.setText(task.prompt)
        self._btn_save.setEnabled(True)

    def _on_save_detail(self):
        """保存详情修改"""
        if not self._selected_task:
            return
        task = self._selected_task
        dur_text = self._detail_duration.currentText()
        dur = int(dur_text.replace("秒", ""))
        ratio = self._detail_ratio.currentText()

        self.task_manager.update_task(task.id, duration=dur, ratio=ratio)
        InfoBar.success("已保存", f"{task.scene} 的修改已保存", parent=self, duration=2000)

    def _on_detail_changed(self, _):
        """详情字段变更时实时同步"""
        if not self._selected_task:
            return
        task = self._selected_task
        dur_text = self._detail_duration.currentText()
        dur = int(dur_text.replace("秒", ""))
        ratio = self._detail_ratio.currentText()
        self.task_manager.update_task(task.id, duration=dur, ratio=ratio)

    def _on_import(self):
        """导入任务"""
        dialog = ImportDialog(self.task_manager, self.material_matcher, self)
        dialog.exec()

    def _on_character(self):
        """打开人物对照表"""
        dialog = CharacterDialog(self.material_matcher, self)
        dialog.exec()

    def _on_retry_failed(self):
        """重试失败的任务"""
        failed = self.task_manager.get_tasks_by_status(TaskStatus.FAILED)
        if not failed:
            InfoBar.info("提示", "没有失败的任务", parent=self, duration=2000)
            return
        # 重置为待生成
        for task in failed:
            self.task_manager.update_task_status(task.id, TaskStatus.PENDING)
        InfoBar.success("已重置", f"已重置 {len(failed)} 个失败任务", parent=self, duration=2000)

    def _on_generate(self):
        """开始生成"""
        pending = self.task_manager.get_pending_tasks()
        if not pending:
            InfoBar.warning("提示", "没有待生成的任务", parent=self, duration=2000)
            return

        # 检查 CLI 登录
        if not self.dreamina_cli.check_login():
            InfoBar.warning("CLI 未登录",
                            "请先运行 dreamina login 完成登录",
                            parent=self, duration=5000)
            return

        self._btn_generate.setEnabled(False)
        self._btn_pause.setEnabled(True)
        self._btn_import.setEnabled(False)

        # 创建生成线程
        from config.settings_manager import get_config
        cfg = get_config()
        self._gen_worker = GenerationWorker(
            tasks=pending,
            cli=self.dreamina_cli,
            interval=cfg.interval_seconds.value,
            retry=cfg.retry_times.value,
        )
        self._thread = QThread(self)
        self._gen_worker.moveToThread(self._thread)
        self._thread.started.connect(self._gen_worker.run)
        self._gen_worker.task_status_changed.connect(self._on_gen_status)
        self._gen_worker.progress_updated.connect(self._on_gen_progress)
        self._gen_worker.generation_finished.connect(self._on_gen_finished)
        self._thread.start()

    def _on_gen_status(self, task_id: str, status: str):
        """生成状态更新"""
        self.task_manager.update_task_status(task_id, TaskStatus(status))

    def _on_gen_progress(self, current: int, total: int):
        """生成进度更新"""
        self._btn_generate.setText(f"生成中 {current}/{total}")

    def _on_gen_finished(self):
        """生成完成"""
        self._btn_generate.setEnabled(True)
        self._btn_pause.setEnabled(False)
        self._btn_import.setEnabled(True)
        self._btn_generate.setText("开始生成")
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        InfoBar.success("生成完成", "所有任务已处理完毕", parent=self, duration=3000)

    def _on_pause(self):
        """暂停生成"""
        if self._gen_worker:
            self._gen_worker.stop()
        self._btn_pause.setEnabled(False)
        self._btn_generate.setEnabled(True)
        self._btn_generate.setText("开始生成")
        InfoBar.info("已暂停", "生成已暂停", parent=self, duration=2000)
