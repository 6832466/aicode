"""下载队列单项 - 名称, 进度条, 速度, ETA"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QProgressBar
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import BodyLabel, CaptionLabel, TransparentPushButton, FluentIcon


class DownloadItemWidget(QWidget):
    """下载队列中的单项控件"""

    cancel_requested = Signal(int)  # task_id

    def __init__(self, task_id: int, name: str, parent=None):
        super().__init__(parent)
        self._task_id = task_id
        self._name = name
        self._status = "pending"  # pending, downloading, completed, failed, cancelled
        self._setup_ui()

    @property
    def task_id(self) -> int:
        return self._task_id

    @property
    def status(self) -> str:
        return self._status

    def _setup_ui(self):
        self.setFixedHeight(80)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(4)

        # 第一行: 名称 + 状态
        row1 = QHBoxLayout()
        self._name_label = BodyLabel(self._name)
        self._name_label.setWordWrap(False)
        row1.addWidget(self._name_label, stretch=1)

        self._status_label = CaptionLabel("等待中")
        self._status_label.setStyleSheet("color: #888;")
        row1.addWidget(self._status_label)

        self._cancel_btn = TransparentPushButton(FluentIcon.CANCEL, "")
        self._cancel_btn.setFixedSize(28, 28)
        self._cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self._task_id))
        self._cancel_btn.hide()
        row1.addWidget(self._cancel_btn)

        main_layout.addLayout(row1)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFixedHeight(18)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background: #f5f5f5;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self._progress_bar)

        # 第二行: 详情 (大小 / 速度 / ETA)
        row2 = QHBoxLayout()
        self._detail_label = CaptionLabel("")
        self._detail_label.setStyleSheet("color: #888;")
        row2.addWidget(self._detail_label)
        row2.addStretch()
        main_layout.addLayout(row2)

    def update_progress(self, bytes_done: int, bytes_total: int, speed: str, eta: str):
        """更新进度"""
        self._status = "downloading"
        self._status_label.setText("下载中")
        self._status_label.setStyleSheet("color: #0078d4;")
        self._cancel_btn.show()

        if bytes_total > 0:
            pct = min(int(bytes_done / bytes_total * 100), 100)
            self._progress_bar.setValue(pct)
            done_str = self._format_size(bytes_done)
            total_str = self._format_size(bytes_total)
            self._progress_bar.setFormat(f"{done_str} / {total_str}  ({pct}%)")
        else:
            self._progress_bar.setValue(0)
            self._progress_bar.setFormat(f"{self._format_size(bytes_done)}")

        parts = []
        if speed:
            parts.append(speed)
        if eta:
            parts.append(f"剩余 {eta}")
        self._detail_label.setText("  ".join(parts))

    def mark_completed(self, success: bool, message: str = ""):
        """标记完成"""
        self._cancel_btn.hide()

        if success:
            self._status = "completed"
            self._status_label.setText("完成")
            self._status_label.setStyleSheet("color: #2e7d32;")
            self._progress_bar.setValue(100)
            self._progress_bar.setStyleSheet(self._progress_bar.styleSheet().replace(
                "background-color: #0078d4;", "background-color: #4caf50;"
            ))
            self._detail_label.setText(message)
        else:
            self._status = "failed"
            self._status_label.setText("失败")
            self._status_label.setStyleSheet("color: #f14c4c;")
            self._detail_label.setText(message)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes >= 1024 * 1024 * 1024:
            return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"
        elif size_bytes >= 1024 * 1024:
            return f"{size_bytes / 1024 / 1024:.1f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.0f} KB"
        return f"{size_bytes} B"
