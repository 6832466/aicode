"""
任务卡片组件 — 每个音视频文件一张卡片
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QCheckBox
from qfluentwidgets import (
    CardWidget, ProgressBar, TransparentPushButton,
    FluentIcon, BodyLabel, CaptionLabel, StrongBodyLabel, InfoBadge,
)

from app.models import TaskItem
from app.config import MODE_ASR


class TaskCard(CardWidget):
    """单个任务的卡片"""

    card_clicked = Signal(str)  # task_id
    remove_clicked = Signal(str)
    reprocess_clicked = Signal(str)
    open_srt_clicked = Signal(str)
    selection_changed = Signal(str, bool)  # task_id, selected

    def __init__(self, task: TaskItem, parent=None):
        super().__init__(parent)
        self._task = task
        self._is_selected = False
        self._init_ui()
        self.refresh(task)

    def _init_ui(self):
        self.setFixedHeight(140)
        self.setMinimumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(8)

        # ── 第一行：复选框 + 文件名 + 模式标签 ──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(18, 18)
        self.checkbox.stateChanged.connect(self._on_checkbox_changed)
        header_row.addWidget(self.checkbox)

        self.name_label = StrongBodyLabel()
        self.name_label.setWordWrap(True)
        header_row.addWidget(self.name_label, 1)

        self.mode_badge = InfoBadge.custom("ASR", "#0078D4", "#DEEBF7")
        header_row.addWidget(self.mode_badge)

        layout.addLayout(header_row)

        # ── 第二行：进度条 ──
        self.progress_bar = ProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # ── 第三行：状态文字 ──
        self.status_label = CaptionLabel()
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        # ── 第四行：操作按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.reprocess_btn = TransparentPushButton("重新处理")
        self.reprocess_btn.setIcon(FluentIcon.SYNC)
        self.reprocess_btn.clicked.connect(lambda: self.reprocess_clicked.emit(self._task.id))
        btn_row.addWidget(self.reprocess_btn)

        self.open_btn = TransparentPushButton("打开字幕")
        self.open_btn.setIcon(FluentIcon.DOCUMENT)
        self.open_btn.clicked.connect(lambda: self.open_srt_clicked.emit(self._task.id))
        self.open_btn.setVisible(False)
        btn_row.addWidget(self.open_btn)

        btn_row.addStretch()

        self.remove_btn = TransparentPushButton("移除")
        self.remove_btn.setIcon(FluentIcon.DELETE)
        self.remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self._task.id))
        btn_row.addWidget(self.remove_btn)

        layout.addLayout(btn_row)

    def refresh(self, task: TaskItem):
        """根据最新的 task 数据更新卡片显示"""
        self._task = task

        # 文件名截断
        name = task.file_name
        if len(name) > 40:
            name = name[:37] + "..."
        self.name_label.setText(name)

        # 模式标签
        if task.is_asr_mode:
            self.mode_badge.setText("ASR")
            self.mode_badge.setCustomBackgroundColor("#0078D4", "#DEEBF7")
        else:
            self.mode_badge.setText("对齐")
            self.mode_badge.setCustomBackgroundColor("#107C10", "#DFF6DD")

        # 进度条
        if task.state in ("pending", "done", "failed", "stopped"):
            self.progress_bar.setVisible(False)
        else:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(int(task.progress * 100))

        # 状态文字
        if task.state == "done":
            self.status_label.setText(f"已完成 — {task.srt_path or '字幕已生成'}")
            self.status_label.setStyleSheet("color: #107C10;")
        elif task.state == "failed":
            self.status_label.setText(f"失败 — {task.error or '未知错误'}")
            self.status_label.setStyleSheet("color: #C42B1C;")
        elif task.state == "pending":
            self.status_label.setText("等待处理")
            self.status_label.setStyleSheet("color: #888888;")
        else:
            extra = ""
            if task.segments_count > 0:
                extra = f" 第 {task.current_segment}/{task.segments_count} 段"
            self.status_label.setText(f"{task.state_label}…{extra}")
            self.status_label.setStyleSheet("color: #0078D4;")

        # 按钮可见性
        self.open_btn.setVisible(task.state == "done" and task.srt_path is not None)

    def _on_checkbox_changed(self, state):
        self._is_selected = (state == Qt.Checked)
        self.selection_changed.emit(self._task.id, self._is_selected)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(selected)
        self.checkbox.blockSignals(False)

    def is_selected(self) -> bool:
        return self._is_selected

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.card_clicked.emit(self._task.id)
        super().mousePressEvent(event)

    @property
    def task_id(self) -> str:
        return self._task.id

    @property
    def task(self) -> TaskItem:
        return self._task