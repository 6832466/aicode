"""任务列表组件"""
import os
import subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QCheckBox,
    QLabel, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from qfluentwidgets import (
    PushButton, PrimaryPushButton, FluentIcon as FIF,
    InfoBar, InfoBarPosition, Dialog,
)

from app.core.task_manager import TaskInfo, TaskStatus
from app.widgets.task_item import TaskItem
from app.utils.logger import get_logger

_log = get_logger('TaskList')


class TaskListWidget(QWidget):
    """任务列表"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: dict[str, TaskItem] = {}
        self._task_manager = None
        self._select_all_updating = False  # 防止递归信号
        self._setup_ui()

    def set_task_manager(self, tm):
        self._task_manager = tm

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(12, 8, 12, 8)

        self.select_all_cb = QCheckBox('全选')
        self.select_all_cb.setStyleSheet('font-size: 12px; color: #666;')
        self.select_all_cb.stateChanged.connect(self._on_select_all)
        toolbar.addWidget(self.select_all_cb)
        toolbar.addStretch()

        batch_del = PushButton('批量删除')
        batch_del.setIcon(FIF.DELETE)
        batch_del.clicked.connect(self._on_batch_delete)
        toolbar.addWidget(batch_del)

        retry = PushButton('重试失败')
        retry.setIcon(FIF.SYNC)
        retry.clicked.connect(self._on_retry_failed)
        toolbar.addWidget(retry)

        layout.addLayout(toolbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet('border: none; background: #E8E8E8; max-height: 1px;')
        layout.addWidget(sep)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet('QScrollArea { border: none; background: transparent; }')

        self.container = QWidget()
        self.container.setStyleSheet('background: transparent;')
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(8, 8, 8, 8)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()
        scroll.setWidget(self.container)
        layout.addWidget(scroll, stretch=1)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet('border: none; background: #E8E8E8; max-height: 1px;')
        layout.addWidget(sep2)

        # 底部状态栏
        bottom = QHBoxLayout()
        bottom.setContentsMargins(12, 8, 12, 8)

        self.stats_label = QLabel('暂无任务')
        self.stats_label.setStyleSheet('color: #888; font-size: 12px;')
        bottom.addWidget(self.stats_label)
        bottom.addStretch()

        self.pause_all_btn = PushButton('全部暂停')
        self.pause_all_btn.setIcon(FIF.PAUSE)
        self.pause_all_btn.clicked.connect(self._on_pause_all)
        bottom.addWidget(self.pause_all_btn)

        self.start_all_btn = PrimaryPushButton('开始全部')
        self.start_all_btn.setIcon(FIF.PLAY)
        self.start_all_btn.clicked.connect(self._on_start_all)
        bottom.addWidget(self.start_all_btn)

        layout.addLayout(bottom)

    def add_task_item(self, task: TaskInfo):
        item = TaskItem(task, self.container)
        item.start_clicked.connect(self._on_start)
        item.pause_clicked.connect(self._on_pause)
        item.remove_clicked.connect(self._on_remove)
        item.checked_changed.connect(self._on_item_checked)
        count = self.list_layout.count()
        self.list_layout.insertWidget(count - 1, item)
        self._items[task.uid] = item
        self._update_stats()

    def remove_task_item(self, uid: str):
        if uid in self._items:
            item = self._items[uid]
            self.list_layout.removeWidget(item)
            item.deleteLater()
            del self._items[uid]
            self._update_select_all_state()
            self._update_stats()

    def update_task_item(self, uid: str, task: TaskInfo = None):
        if uid in self._items:
            if task:
                self._items[uid].refresh(task=task)
            else:
                self._items[uid].refresh()

    # ── 复选框逻辑 ──

    def _on_item_checked(self, uid: str, checked: bool):
        self._update_select_all_state()

    def _on_select_all(self, state):
        if self._select_all_updating:
            return
        checked = state == Qt.Checked.value
        self._select_all_updating = True
        for item in self._items.values():
            item.set_checked(checked)
        self._select_all_updating = False

    def _update_select_all_state(self):
        if not self._items:
            self._select_all_updating = True
            self.select_all_cb.setChecked(False)
            self._select_all_updating = False
            return
        all_checked = all(item.is_checked() for item in self._items.values())
        none_checked = not any(item.is_checked() for item in self._items.values())
        self._select_all_updating = True
        if all_checked:
            self.select_all_cb.setCheckState(Qt.Checked)
        elif none_checked:
            self.select_all_cb.setCheckState(Qt.Unchecked)
        else:
            self.select_all_cb.setCheckState(Qt.PartiallyChecked)
        self._select_all_updating = False

    # ── 操作 ──

    def _on_start(self, uid):
        _log.debug(f'_on_start: {uid}')
        try:
            if self._task_manager:
                self._task_manager.start_task(uid)
        except Exception as e:
            _log.exception(f'_on_start 异常: {e}')

    def _on_pause(self, uid):
        _log.debug(f'_on_pause: {uid}')
        try:
            if self._task_manager:
                self._task_manager.pause_task(uid)
        except Exception as e:
            _log.exception(f'_on_pause 异常: {e}')

    def _on_remove(self, uid):
        _log.debug(f'_on_remove: {uid}')
        try:
            if uid not in self._items:
                return
            item = self._items[uid]
            if item._task.status == TaskStatus.DOWNLOADING:
                d = Dialog('确认删除', '该任务正在下载中，删除将取消下载。确定删除吗？', self.window())
                if d.exec():
                    self._do_remove(uid)
            else:
                title = item._task.title or uid
                d = Dialog('确认删除', f'确定删除任务「{title}」吗？', self.window())
                if d.exec():
                    self._do_remove(uid)
        except Exception as e:
            _log.exception(f'_on_remove 异常: {e}')

    def _do_remove(self, uid):
        if self._task_manager:
            self._task_manager.remove_task(uid)

    def _on_batch_delete(self):
        """批量删除：只删除勾选的任务"""
        checked = [uid for uid, item in self._items.items() if item.is_checked()]
        if not checked:
            InfoBar.warning(
                title='未选择任务',
                content='请先勾选要删除的任务，再点击批量删除',
                position=InfoBarPosition.TOP,
                parent=self.window(),
            )
            return
        d = Dialog('批量删除', f'确定删除已勾选的 {len(checked)} 个任务吗？', self.window())
        if d.exec():
            for uid in checked:
                if self._task_manager:
                    self._task_manager.remove_task(uid)

    def _on_retry_failed(self):
        if not self._task_manager:
            return
        count = 0
        for uid, item in self._items.items():
            if item._task.status == TaskStatus.FAILED:
                self._task_manager.start_task(uid)
                count += 1
        if count == 0:
            InfoBar.info(title='提示', content='没有失败的任务',
                         position=InfoBarPosition.TOP, parent=self.window())

    def _on_pause_all(self):
        if self._task_manager:
            self._task_manager.pause_all()

    def _on_start_all(self):
        if self._task_manager:
            self._task_manager.start_all()

    def _update_stats(self):
        total = len(self._items)
        active = sum(1 for i in self._items.values() if i._task.status == TaskStatus.DOWNLOADING)
        waiting = sum(1 for i in self._items.values() if i._task.status == TaskStatus.WAITING)
        completed = sum(1 for i in self._items.values() if i._task.status == TaskStatus.COMPLETED)
        failed = sum(1 for i in self._items.values() if i._task.status == TaskStatus.FAILED)
        parts = []
        if total:
            parts.append(f'共 {total} 个')
        if active:
            parts.append(f'下载中 {active}')
        if waiting:
            parts.append(f'等待中 {waiting}')
        if completed:
            parts.append(f'已完成 {completed}')
        if failed:
            parts.append(f'失败 {failed}')
        self.stats_label.setText(' | '.join(parts) if parts else '暂无任务')
