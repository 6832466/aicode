"""下载队列页面 - 重新设计的布局"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from qfluentwidgets import (
    PrimaryPushButton,
    InfoBar, InfoBarPosition, CardWidget, FluentIcon as FIF,
)

from app.widgets.task_list_widget import TaskListWidget
from app.utils.logger import get_logger

_log = get_logger('DownloadQueue')


class DownloadQueuePage(QWidget):
    """下载队列 - 重新设计的布局"""

    def __init__(self, task_manager=None, settings_manager=None, parent=None):
        super().__init__(parent)
        self._task_manager = task_manager
        self._settings = settings_manager

        self._signals_connected = False
        self.setStyleSheet('background: #FFFFFF;')
        self._setup_ui()

        if task_manager:
            self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ═══ 顶部：链接输入卡片 ═══
        input_card = CardWidget()
        input_card.setStyleSheet('CardWidget { background: #FAFBFC; border-radius: 10px; }')
        card_layout = QVBoxLayout(input_card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(12)

        # 标题行
        header_layout = QHBoxLayout()
        title = QLabel('添加下载链接')
        title.setFont(QFont('Microsoft YaHei', 11, QFont.Bold))
        title.setStyleSheet('color: #1a1a1a; border: none;')
        header_layout.addWidget(title)
        header_layout.addStretch()
        card_layout.addLayout(header_layout)

        # 输入行
        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.link_input = QTextEdit()
        self.link_input.setPlaceholderText('粘贴抖音/快手等等视频链接（支持多链接，每行一个或用空格分隔）')
        self.link_input.setMinimumHeight(56)
        self.link_input.setMaximumHeight(72)
        self.link_input.setStyleSheet("""
            QTextEdit {
                border: 1px solid #D0D7DE;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 14px;
                background: #FFFFFF;
            }
            QTextEdit:focus {
                border-color: #0078D4;
                border-width: 2px;
            }
        """)
        self.link_input.installEventFilter(self)
        input_row.addWidget(self.link_input, stretch=1)

        add_btn = PrimaryPushButton('添加')
        add_btn.setMinimumSize(80, 40)
        add_btn.clicked.connect(self._on_add_single)
        input_row.addWidget(add_btn)

        card_layout.addLayout(input_row)

        layout.addWidget(input_card)

        # ═══ 任务列表 ═══
        list_header = QHBoxLayout()
        list_title = QLabel('下载任务')
        list_title.setFont(QFont('Microsoft YaHei', 12, QFont.Bold))
        list_title.setStyleSheet('color: #1a1a1a;')
        list_header.addWidget(list_title)
        list_header.addStretch()
        layout.addLayout(list_header)

        # 列表容器 - 白色圆角卡片包裹
        list_card = CardWidget()
        list_card.setStyleSheet('CardWidget { background: #FAFBFC; border-radius: 10px; }')
        list_inner = QVBoxLayout(list_card)
        list_inner.setContentsMargins(4, 4, 4, 4)

        self.task_list = TaskListWidget(self)
        list_inner.addWidget(self.task_list, stretch=1)

        layout.addWidget(list_card, stretch=1)

    def eventFilter(self, obj, event):
        """拦截链接输入框的 Ctrl+Enter 作为提交快捷键"""
        from PySide6.QtCore import QEvent
        if obj == self.link_input and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
                self._on_add_single()
                return True
        return super().eventFilter(obj, event)

    def set_task_manager(self, tm):
        self._task_manager = tm
        self.task_list.set_task_manager(tm)
        if not self._signals_connected:
            self._connect_signals()

    def _connect_signals(self):
        if self._signals_connected:
            return
        tm = self._task_manager
        if tm:
            tm.task_added.connect(self._on_task_added)
            tm.task_removed.connect(self._on_task_removed)
            tm.task_updated.connect(self._on_task_updated)
            tm.task_progress.connect(self._on_task_progress)
            tm.task_status_changed.connect(self._on_status_changed)
            tm.parse_finished.connect(self._on_parse_finished)
            self._signals_connected = True

    def _on_add_single(self):
        if not self._task_manager:
            return
        from app.utils.link_utils import extract_links
        text = self.link_input.toPlainText().strip()
        if not text:
            return
        links = extract_links(text)
        if links:
            self._task_manager.add_batch(links)
            self.link_input.clear()
            InfoBar.info(title=f'已添加 {len(links)} 个任务', content='正在解析，解析完成后请手动开始下载',
                         position=InfoBarPosition.TOP, parent=self.window(), duration=2000)
        else:
            InfoBar.warning(title='链接格式不正确', content='请检查链接是否正确',
                            position=InfoBarPosition.TOP, parent=self.window())

    def _on_task_added(self, uid):
        try:
            if self._task_manager and uid in self._task_manager._tasks:
                self.task_list.add_task_item(self._task_manager._tasks[uid])
        except Exception as e:
            _log.exception(f'_on_task_added 异常: {e}')

    def _on_task_removed(self, uid):
        try:
            self.task_list.remove_task_item(uid)
        except Exception as e:
            _log.exception(f'_on_task_removed 异常: {e}')

    def _on_task_updated(self, uid):
        try:
            if self._task_manager and uid in self._task_manager._tasks:
                self.task_list.update_task_item(uid, self._task_manager._tasks[uid])
        except Exception as e:
            _log.exception(f'_on_task_updated 异常: {e}')

    def _on_task_progress(self, uid, percent, downloaded, total, speed):
        try:
            if self._task_manager and uid in self._task_manager._tasks:
                self.task_list.update_task_item(uid, self._task_manager._tasks[uid])
        except Exception as e:
            _log.exception(f'_on_task_progress 异常: {e}')

    def _on_status_changed(self, uid, status):
        try:
            if self._task_manager and uid in self._task_manager._tasks:
                task = self._task_manager._tasks[uid]
                self.task_list.update_task_item(uid, task)
                if status.value == 'completed' and self._settings:
                    if self._settings.get('download.notify_complete', True):
                        InfoBar.success(title='下载完成', content=f'「{task.title}」',
                                        position=InfoBarPosition.BOTTOM_RIGHT,
                                        parent=self.window(), duration=5000)
                elif status.value == 'failed':
                    InfoBar.error(title='下载失败',
                                  content=f'「{task.title}」{task.error_msg}',
                                  position=InfoBarPosition.BOTTOM_RIGHT,
                                  parent=self.window(), duration=8000)
        except Exception as e:
            _log.exception(f'_on_status_changed 异常: {e}')

    def _on_parse_finished(self, uid, success):
        try:
            if not success:
                InfoBar.warning(title='解析失败', content='视频不存在或已被删除',
                                position=InfoBarPosition.TOP, parent=self.window(), duration=3000)
        except Exception as e:
            _log.exception(f'_on_parse_finished 异常: {e}')
