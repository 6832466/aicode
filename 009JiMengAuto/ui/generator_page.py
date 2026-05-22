"""视频生成页面"""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QAbstractItemView, QTableWidget
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QHeaderView, QLabel,
    QSplitter, QPushButton, QComboBox, QGroupBox,
)
from qfluentwidgets import (
    TableWidget, CardWidget, PrimaryPushButton, PushButton,
    FluentIcon, InfoBar, InfoBarPosition, ToolTipFilter,
    ComboBox, LineEdit, TextEdit, BodyLabel, CaptionLabel,
)

from data.models import Task, TaskStatus, MaterialType
from core.task_manager import TaskManager
from core.material_matcher import MaterialMatcher
from core.dreamina_cli import DreaminaCLI, GenerationWorker
from ui.import_dialog import ImportDialog
from ui.character_dialog import CharacterDialog


class StatCard(CardWidget):
    """统计卡片"""

    def __init__(self, title: str, value: int = 0, parent=None):
        super().__init__(parent)
        self._value_label = BodyLabel(str(value), self)
        self._title_label = CaptionLabel(title, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(0)
        self._value_label.setStyleSheet("font-size: 14px; font-weight: 700;")
        self._value_label.setText(str(value))
        layout.addWidget(self._value_label)
        layout.addWidget(self._title_label)

    def set_value(self, v: int):
        self._value_label.setText(str(v))


class GeneratorPage(QWidget):
    """视频生成页面"""

    def __init__(self, task_manager: TaskManager,
                 material_matcher: MaterialMatcher,
                 dreamina_cli: DreaminaCLI, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.material_matcher = material_matcher
        self.dreamina_cli = dreamina_cli
        self._worker: QThread = None
        self._gen_worker: GenerationWorker = None

        self._init_ui()
        self._connect_signals()
        self._refresh_stats()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # ── 统计卡片行 ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(6)
        self._card_pending = StatCard("待生成")
        self._card_generating = StatCard("生成中")
        self._card_completed = StatCard("已完成")
        self._card_failed = StatCard("失败")
        for c in [self._card_pending, self._card_generating,
                  self._card_completed, self._card_failed]:
            stats_layout.addWidget(c)
        layout.addLayout(stats_layout)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        self._btn_import = PrimaryPushButton(FluentIcon.ADD, "导入")
        self._btn_generate = PrimaryPushButton(FluentIcon.PLAY, "开始生成")
        self._btn_generate.setEnabled(False)
        self._btn_pause = PushButton(FluentIcon.PAUSE, "暂停")
        self._btn_pause.setEnabled(False)
        self._btn_character = PushButton(FluentIcon.PEOPLE, "人物对照表")

        toolbar.addWidget(self._btn_import)
        toolbar.addWidget(self._btn_generate)
        toolbar.addWidget(self._btn_pause)
        toolbar.addStretch()
        toolbar.addWidget(self._btn_character)
        layout.addLayout(toolbar)

        # ── 主区域：左右分栏 ──
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：任务列表
        left_widget = QWidget()
        left_widget.setAttribute(Qt.WA_StyledBackground)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._table = TableWidget(self)
        self._table.setBorderRadius(8)
        self._table.setAlternatingRowColors(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        left_layout.addWidget(self._table)
        splitter.addWidget(left_widget)

        # 右侧：详情面板
        right_widget = QWidget()
        right_widget.setAttribute(Qt.WA_StyledBackground)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        detail_card = CardWidget(self)
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.setSpacing(8)

        self._detail_title = BodyLabel("任务详情")

        # 场次
        self._detail_scene = BodyLabel("选择左侧任务查看详情")

        # 时长
        duration_row = QHBoxLayout()
        duration_row.addWidget(BodyLabel("时长:"))
        self._detail_duration = ComboBox()
        self._detail_duration.addItems([f"{s}秒" for s in range(3, 16)])
        self._detail_duration.setCurrentIndex(9)  # 12秒
        self._detail_duration.setEnabled(False)
        duration_row.addWidget(self._detail_duration)
        duration_row.addStretch()
        detail_layout.addLayout(duration_row)

        # 比例
        ratio_row = QHBoxLayout()
        ratio_row.addWidget(BodyLabel("比例:"))
        self._detail_ratio = ComboBox()
        for r in ["16:9", "9:16", "21:9", "4:3", "1:1", "3:4"]:
            self._detail_ratio.addItem(r)
        self._detail_ratio.setEnabled(False)
        ratio_row.addWidget(self._detail_ratio)
        ratio_row.addStretch()
        detail_layout.addLayout(ratio_row)

        # 提示词
        detail_layout.addWidget(BodyLabel("提示词:"))
        self._detail_prompt = TextEdit()
        self._detail_prompt.setReadOnly(True)
        self._detail_prompt.setMaximumHeight(120)
        detail_layout.addWidget(self._detail_prompt)

        # 保存修改按钮
        self._btn_save = PushButton(FluentIcon.SAVE, "保存修改")
        self._btn_save.setEnabled(False)
        detail_layout.addWidget(self._btn_save)

        right_layout.addWidget(detail_card)
        splitter.addWidget(right_widget)

        splitter.setSizes([700, 360])
        layout.addWidget(splitter)

        # ── 设置表格列 ──
        self._setup_table()

        # 连接信号
        self._btn_import.clicked.connect(self._on_import)
        self._btn_generate.clicked.connect(self._on_generate)
        self._btn_pause.clicked.connect(self._on_pause)
        self._btn_character.clicked.connect(self._on_character)
        self._btn_save.clicked.connect(self._on_save_detail)
        self._detail_duration.currentTextChanged.connect(self._on_detail_changed)
        self._detail_ratio.currentTextChanged.connect(self._on_detail_changed)
        self._table.clicked.connect(self._on_task_selected)

    def _setup_table(self):
        """配置表格列"""
        columns = ["", "场次", "描述词", "时长", "比例", "状态", "操作"]
        self._table.setColumnCount(len(columns))
        self._table.setHorizontalHeaderLabels(columns)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(1, 80)
        self._table.setColumnWidth(3, 60)
        self._table.setColumnWidth(4, 60)
        self._table.setColumnWidth(5, 80)
        self._table.setColumnWidth(6, 80)

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
        tasks.sort(key=lambda t: t.sequence)

        for i, task in enumerate(tasks):
            self._table.insertRow(i)
            # checkbox # 场次 描述词 时长 比例 状态 操作
            self._table.setItem(i, 0, self._cell(""))
            self._table.setItem(i, 1, self._cell(task.scene))
            self._table.setItem(i, 2, self._cell(task.prompt[:60] + ("..." if len(task.prompt) > 60 else "")))
            self._table.setItem(i, 3, self._cell(f"{task.duration}秒"))
            self._table.setItem(i, 4, self._cell(task.ratio))

            status_text = task.status.display()
            self._table.setItem(i, 5, self._cell(status_text))

            # 操作按钮
            action = "重新" if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) else "生成"
            self._table.setItem(i, 6, self._cell(action))

        self._refresh_stats()

    def _cell(self, text: str):
        """创建表格单元格"""
        from PySide6.QtWidgets import QTableWidgetItem
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
        tasks = sorted(self.task_manager.get_all_tasks(), key=lambda t: t.sequence)
        row = index.row()
        if row < 0 or row >= len(tasks):
            return
        self._selected_task = tasks[row]
        task = self._selected_task

        self._detail_title.setText(f"任务详情 - {task.scene}")
        self._detail_scene.setText(f"场次：{task.scene}")
        self._detail_duration.setCurrentText(f"{task.duration}秒")
        self._detail_duration.setEnabled(True)
        self._detail_ratio.setCurrentText(task.ratio)
        self._detail_ratio.setEnabled(True)
        self._detail_prompt.setText(task.prompt)
        self._btn_save.setEnabled(True)

    def _on_save_detail(self):
        """保存详情修改"""
        if not hasattr(self, '_selected_task') or not self._selected_task:
            return
        task = self._selected_task
        dur_text = self._detail_duration.currentText()
        dur = int(dur_text.replace("秒", ""))
        ratio = self._detail_ratio.currentText()

        self.task_manager.update_task(
            task.id, duration=dur, ratio=ratio,
        )
        InfoBar.success("已保存", f"{task.scene} 的修改已保存",
                        parent=self, duration=2000)

    def _on_detail_changed(self, _):
        """详情字段变更时标记（实时同步）"""
        if not hasattr(self, '_selected_task') or not self._selected_task:
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
        self._gen_worker.log_message.connect(self._on_gen_log)
        self._thread.start()

    def _on_gen_status(self, task_id: str, status: str):
        """生成状态更新"""
        from data.models import TaskStatus
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
        InfoBar.success("生成完成", "所有任务已处理完毕",
                        parent=self, duration=3000)

    def _on_pause(self):
        """暂停生成"""
        if self._gen_worker:
            self._gen_worker.stop()
        self._btn_pause.setEnabled(False)
        self._btn_generate.setEnabled(True)
        self._btn_generate.setText("开始生成")
        InfoBar.info("已暂停", "生成已暂停", parent=self, duration=2000)

    def _on_gen_log(self, msg: str):
        """生成日志"""
        pass  # 可接入日志控件
