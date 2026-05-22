"""单个任务卡片"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar,
    QFrame, QPushButton, QCheckBox,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from app.core.task_manager import TaskInfo, TaskStatus
from app.utils.logger import get_logger

_log = get_logger('TaskItem')


def _truncate(text: str, max_chars: int = 25) -> str:
    """截断过长的标题"""
    if not text:
        return text
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + '...'


class TaskItem(QFrame):
    """自定义任务卡片"""

    start_clicked = Signal(str)
    pause_clicked = Signal(str)
    remove_clicked = Signal(str)
    checked_changed = Signal(str, bool)

    def __init__(self, task: TaskInfo, parent=None):
        super().__init__(parent)
        self._task = task
        self.setObjectName('TaskItem')
        self.setMinimumHeight(60)
        self._setup_ui()
        self.refresh(task=task)

    def _setup_ui(self):
        self.setStyleSheet("""
            #TaskItem {
                background: #FFFFFF;
                border: 1px solid #E8ECF0;
                border-radius: 8px;
                margin: 1px 0px;
            }
            #TaskItem:hover {
                border-color: #B0D0F0;
                background: #F8FAFD;
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)

        # 复选框
        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(18, 18)
        self.checkbox.setStyleSheet('QCheckBox { border: none; background: transparent; }')
        self.checkbox.stateChanged.connect(
            lambda state: self.checked_changed.emit(self._task.uid, state == Qt.Checked.value)
        )
        main_layout.addWidget(self.checkbox, alignment=Qt.AlignVCenter)

        # 状态图标
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(20, 20)
        self.status_icon.setAlignment(Qt.AlignCenter)
        self.status_icon.setStyleSheet('font-size: 13px; border: none; background: transparent;')
        main_layout.addWidget(self.status_icon, alignment=Qt.AlignVCenter)

        # 中间信息区
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        title_row.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel('解析中...')
        self.title_label.setFont(QFont('Microsoft YaHei', 11))
        self.title_label.setStyleSheet('color: #1a1a1a; border: none; background: transparent;')
        self.title_label.setMaximumWidth(340)
        self.title_label.setSizePolicy(
            self.title_label.sizePolicy().horizontalPolicy(),
            self.title_label.sizePolicy().verticalPolicy())
        self.title_label.setWordWrap(False)
        title_row.addWidget(self.title_label)

        self.platform_badge = QLabel()
        self.platform_badge.setStyleSheet(
            'color: white; border-radius: 3px; padding: 1px 6px; font-size: 10px; border: none;'
        )
        self.platform_badge.setFixedHeight(18)
        title_row.addWidget(self.platform_badge)
        title_row.addStretch()
        info_layout.addLayout(title_row)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(6)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #E8ECF0; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: #0078D4; border-radius: 2px; }
        """)
        progress_row.addWidget(self.progress_bar, stretch=1)

        self.percent_label = QLabel('0%')
        self.percent_label.setFixedWidth(30)
        self.percent_label.setStyleSheet('color: #666; font-size: 11px; border: none; background: transparent;')
        progress_row.addWidget(self.percent_label)

        self.speed_label = QLabel()
        self.speed_label.setStyleSheet('color: #0078D4; font-size: 11px; border: none; background: transparent;')
        progress_row.addWidget(self.speed_label)

        self.size_label = QLabel()
        self.size_label.setStyleSheet('color: #999; font-size: 11px; border: none; background: transparent;')
        progress_row.addWidget(self.size_label)
        info_layout.addLayout(progress_row)

        self.error_label = QLabel()
        self.error_label.setStyleSheet('color: #E02020; font-size: 11px; border: none; background: transparent;')
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        info_layout.addWidget(self.error_label)

        main_layout.addLayout(info_layout, stretch=1)

        # 右侧操作按钮
        btn_style = """
            QPushButton {
                background: #F0F2F5;
                border: 1px solid #D0D7DE;
                border-radius: 4px;
                font-size: 12px;
                color: #333;
                padding: 4px 10px;
                min-height: 26px;
                min-width: 44px;
            }
            QPushButton:hover {
                background: #D0E4F7;
                border-color: #0078D4;
                color: #0078D4;
            }
        """

        self.action_btn = QPushButton()
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.setStyleSheet(btn_style)
        self.action_btn.setFixedWidth(48)
        self.action_btn.clicked.connect(self._on_action)
        main_layout.addWidget(self.action_btn)

        self.delete_btn = QPushButton('删除')
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setFixedWidth(48)
        self.delete_btn.setStyleSheet(btn_style + """
            QPushButton:hover { background: #FDE0E0; border-color: #E02020; color: #E02020; }
        """)
        self.delete_btn.clicked.connect(lambda: self.remove_clicked.emit(self._task.uid))
        main_layout.addWidget(self.delete_btn)

    def refresh(self, task: TaskInfo = None):
        if task:
            self._task = task

        t = self._task
        status = t.status

        # 标题（截断过长的）
        if t.title:
            self.title_label.setText(_truncate(t.title))
            self.title_label.setToolTip(t.title)
            self.title_label.setStyleSheet('color: #1a1a1a; border: none; background: transparent;')
        elif status == TaskStatus.PARSING:
            self.title_label.setText('正在解析链接...')
            self.title_label.setToolTip('')
            self.title_label.setStyleSheet('color: #999; border: none; background: transparent;')
        elif not t.title:
            self.title_label.setText('等待解析...')
            self.title_label.setToolTip('')
            self.title_label.setStyleSheet('color: #999; border: none; background: transparent;')

        # 平台标签
        from app.utils.link_utils import source_to_display, source_to_color
        display = source_to_display(t.platform)
        if t.platform and display != t.platform:
            self.platform_badge.setText(display)
            self.platform_badge.setStyleSheet(
                f'color: white; background: {source_to_color(t.platform)}; border-radius: 3px;'
                'padding: 1px 6px; font-size: 10px; border: none;'
            )
            self.platform_badge.setVisible(True)
        else:
            self.platform_badge.setVisible(False)

        # 状态图标
        icons = {
            TaskStatus.WAITING: '○',
            TaskStatus.PARSING: '⟳',
            TaskStatus.DOWNLOADING: '↓',
            TaskStatus.PAUSED: '⏸',
            TaskStatus.COMPLETED: '✓',
            TaskStatus.FAILED: '✗',
        }
        icon_colors = {
            TaskStatus.WAITING: '#999',
            TaskStatus.PARSING: '#FF9800',
            TaskStatus.DOWNLOADING: '#0078D4',
            TaskStatus.PAUSED: '#FF9800',
            TaskStatus.COMPLETED: '#4CAF50',
            TaskStatus.FAILED: '#E02020',
        }
        self.status_icon.setText(icons.get(status, '?'))
        c = icon_colors.get(status, '#999')
        self.status_icon.setStyleSheet(f'font-size: 13px; border: none; background: transparent; color: {c};')

        # 进度
        self.progress_bar.setValue(t.progress)
        self.percent_label.setText(f'{t.progress}%')

        if status == TaskStatus.COMPLETED:
            self.progress_bar.setValue(100)
            self.percent_label.setText('100%')
            self.progress_bar.setStyleSheet("""
                QProgressBar { background: #E8ECF0; border: none; border-radius: 2px; }
                QProgressBar::chunk { background: #4CAF50; border-radius: 2px; }
            """)
        elif status == TaskStatus.FAILED:
            self.progress_bar.setStyleSheet("""
                QProgressBar { background: #E8ECF0; border: none; border-radius: 2px; }
                QProgressBar::chunk { background: #E02020; border-radius: 2px; }
            """)
        else:
            self.progress_bar.setStyleSheet("""
                QProgressBar { background: #E8ECF0; border: none; border-radius: 2px; }
                QProgressBar::chunk { background: #0078D4; border-radius: 2px; }
            """)

        # 速度/大小
        self.speed_label.setText(t.speed if t.speed else '')
        if t.total_bytes > 0:
            dl = self._fmt(t.downloaded_bytes)
            tot = self._fmt(t.total_bytes)
            self.size_label.setText(f'{dl}/{tot}')
        elif t.size_estimate > 0:
            self.size_label.setText(f'~{self._fmt(t.size_estimate)}')
        else:
            self.size_label.setText('')

        # 错误
        if status == TaskStatus.FAILED and t.error_msg:
            self.error_label.setText(t.error_msg)
            self.error_label.setVisible(True)
        else:
            self.error_label.setVisible(False)

        # 操作按钮
        if status == TaskStatus.DOWNLOADING:
            self.action_btn.setText('暂停')
            self.action_btn.setVisible(True)
        elif status in (TaskStatus.PAUSED, TaskStatus.WAITING):
            if status == TaskStatus.WAITING and not t._raw_info.get('download_url'):
                self.action_btn.setVisible(False)
            else:
                self.action_btn.setText('开始')
                self.action_btn.setVisible(True)
        elif status == TaskStatus.FAILED:
            if not t._raw_info.get('download_url') and not t.title:
                self.action_btn.setVisible(False)
            else:
                self.action_btn.setText('重试')
                self.action_btn.setVisible(True)
        else:
            self.action_btn.setVisible(False)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def set_checked(self, checked: bool):
        self.checkbox.setChecked(checked)

    def _on_action(self):
        try:
            status = self._task.status
            _log.debug(f'按钮点击: uid={self._task.uid} status={status.value}')
            if status == TaskStatus.DOWNLOADING:
                self.pause_clicked.emit(self._task.uid)
            elif status in (TaskStatus.PAUSED, TaskStatus.WAITING):
                self.start_clicked.emit(self._task.uid)
            elif status == TaskStatus.FAILED:
                self.start_clicked.emit(self._task.uid)
        except Exception as e:
            _log.exception(f'_on_action 异常: {e}')

    def _fmt(self, b: int) -> str:
        if b < 1024:
            return f'{b}B'
        elif b < 1024 * 1024:
            return f'{b/1024:.1f}K'
        elif b < 1024 * 1024 * 1024:
            return f'{b/(1024*1024):.1f}M'
        return f'{b/(1024*1024*1024):.2f}G'
