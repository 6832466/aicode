"""下载页 - 按剧分组的队列列表 + 进度条"""
import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea
from PySide6.QtCore import Qt
from qfluentwidgets import (
    CaptionLabel, StrongBodyLabel, TransparentPushButton,
    FluentIcon, InfoBar, InfoBarPosition,
)

from gui.workers.download_worker import DownloadQueueManager
from gui.widgets.series_download_card import SeriesDownloadCard

logger = logging.getLogger("hongguo")


class DownloadingPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue_manager: DownloadQueueManager | None = None
        self._series_cards: dict[int, SeriesDownloadCard] = {}
        self._task_to_card: dict[int, int] = {}  # task_id -> group_id
        self._task_to_ep: dict[int, int] = {}    # task_id -> episode_index
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)

        # 标题栏
        header = QHBoxLayout()
        title = StrongBodyLabel("下载队列")
        title.setStyleSheet("font-size: 16px;")
        header.addWidget(title)
        header.addStretch()

        self._stats_label = CaptionLabel("")
        self._stats_label.setStyleSheet("color: #888;")
        header.addWidget(self._stats_label)

        self._cancel_all_btn = TransparentPushButton(FluentIcon.DELETE, "取消全部")
        self._cancel_all_btn.clicked.connect(self._on_cancel_all)
        header.addWidget(self._cancel_all_btn)

        layout.addLayout(header)

        # 滚动列表
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(10)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._list_container)
        layout.addWidget(self._scroll, stretch=1)

    def set_queue_manager(self, manager: DownloadQueueManager):
        self._queue_manager = manager

        manager.series_group_added.connect(self._on_series_group_added)
        # task_started = 开始获取URL (立即触发, 显示行)
        manager.task_started.connect(self._on_task_started)
        # task_downloading = URL 获取完成, 开始下载
        manager.task_downloading.connect(self._on_task_downloading)
        manager.task_progress.connect(self._on_task_progress)
        manager.task_finished.connect(self._on_task_finished)
        manager.queue_updated.connect(self._update_stats)
        manager.series_group_done.connect(self._on_series_group_done)
        manager.all_done.connect(self._on_all_done)

    def _on_series_group_added(self, group_id: int, name: str, cover_url: str, total: int):
        try:
            logger.info(f"[DLPAGE] series_group_added: gid={group_id}, name={name}, total={total}")
            card = SeriesDownloadCard(group_id, name, cover_url, total)
            card.cancel_group_requested.connect(self._on_cancel_group)
            card.retry_episode_requested.connect(self._on_retry_episode)
            self._series_cards[group_id] = card
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

            if self._queue_manager:
                group_info = self._queue_manager.get_group_info(group_id)
                if group_info:
                    card.set_output_dir(str(group_info.output_dir))
                    logger.info(f"[DLPAGE] output_dir set: {group_info.output_dir}")

            if self._queue_manager:
                tasks = self._queue_manager.get_group_tasks(group_id)
                logger.info(f"[DLPAGE] registering {len(tasks)} tasks for gid={group_id}")
                for task in tasks:
                    self._task_to_card[task.task_id] = group_id
                    self._task_to_ep[task.task_id] = task.episode_index
            self._update_stats()
        except Exception:
            logger.exception(f"[DLPAGE] _on_series_group_added 异常: gid={group_id}")
            InfoBar.error(
                f"创建下载卡片失败: 《{name}》",
                "请查看日志了解详情",
                duration=8000,
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,
            )

    def _on_task_started(self, group_id: int, task_id: int):
        """任务开始获取URL, 确保行存在"""
        try:
            if task_id in self._task_to_card:
                return
            self._task_to_card[task_id] = group_id
            if group_id in self._series_cards:
                manager = self._queue_manager
                if manager:
                    task = manager.get_task_by_id(task_id)
                    if task:
                        self._task_to_ep[task_id] = task.episode_index
                        row = self._series_cards[group_id].add_episode_row(
                            task.episode_index, task.episode_name, task.task_id
                        )
                        row.set_status("获取链接...", "#f0ad4e")
            self._update_stats()
        except Exception:
            logger.exception(f"[DLPAGE] _on_task_started 异常: task_id={task_id}")

    def _on_task_downloading(self, group_id: int, task_id: int):
        """URL 获取完成 -> 惰性创建行, 开始下载"""
        try:
            if group_id in self._series_cards:
                ep = self._task_to_ep.get(task_id, 0)
                row = self._series_cards[group_id].get_episode_row(ep)
                if row is None:
                    card = self._series_cards[group_id]
                    manager = self._queue_manager
                    if manager:
                        task = manager.get_task_by_id(task_id)
                        if task:
                            row = card.add_episode_row(task.episode_index, task.episode_name, task.task_id)
                if row:
                    row.set_status("等待下载", "#0078d4")
            self._update_stats()
        except Exception:
            logger.exception(f"[DLPAGE] _on_task_downloading 异常: task_id={task_id}")

    def _on_task_progress(self, group_id: int, task_id: int, done: int, total: int, speed: str, eta: str):
        try:
            if group_id in self._series_cards:
                ep = self._task_to_ep.get(task_id, 0)
                self._series_cards[group_id].update_task_progress(done, total, speed, eta, ep)
            self._update_stats()
        except Exception:
            logger.exception(f"[DLPAGE] _on_task_progress 异常: task_id={task_id}")

    def _on_task_finished(self, group_id: int, task_id: int, success: bool, message: str, filepath: str):
        try:
            if group_id in self._series_cards:
                ep = self._task_to_ep.get(task_id, 0)
                card = self._series_cards[group_id]
                # URL 获取失败时 episode row 尚未创建, 在此懒创建
                if ep > 0 and card.get_episode_row(ep) is None:
                    manager = self._queue_manager
                    if manager:
                        task = manager.get_task_by_id(task_id)
                        if task:
                            row = card.add_episode_row(task.episode_index, task.episode_name, task.task_id)
                            row.set_status(message or "失败", "#f44336")
                card.mark_task_finished(success, ep, filepath, message)
            self._update_stats()
        except Exception:
            logger.exception(f"[DLPAGE] _on_task_finished 异常: task_id={task_id}")

    def _on_series_group_done(self, group_id: int, success: int, fail: int):
        if group_id in self._series_cards:
            card = self._series_cards[group_id]
            card._cancel_btn.hide()
            InfoBar.success(
                f"《{card._series_name}》下载完成",
                f"成功 {success} 集, 失败 {fail} 集",
                duration=3000,
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,
            )

    def _on_cancel_group(self, group_id: int):
        if self._queue_manager:
            self._queue_manager.cancel_group(group_id)
        if group_id in self._series_cards:
            self._series_cards[group_id].hide()
            self._series_cards[group_id].deleteLater()
            del self._series_cards[group_id]
        InfoBar.info("已取消", "该剧下载已取消", parent=self)
        self._update_stats()

    def _on_retry_episode(self, group_id: int, ep: int):
        if self._queue_manager:
            self._queue_manager.retry_task(group_id, ep)
        self._update_stats()

    def _on_cancel_all(self):
        if self._queue_manager:
            self._queue_manager.cancel_all()
            for card in self._series_cards.values():
                card.hide()
                card.deleteLater()
            self._series_cards.clear()
            self._task_to_card.clear()
            self._task_to_ep.clear()
            InfoBar.info("已清空队列", "", parent=self)
        self._update_stats()

    def _on_all_done(self, success_count: int, fail_count: int):
        InfoBar.success(
            "全部下载完成",
            f"成功 {success_count} 集, 失败 {fail_count} 集",
            duration=5000,
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT,
        )

    def _update_stats(self):
        if not self._queue_manager:
            return
        active = self._queue_manager.get_active_count()
        pending = self._queue_manager.get_pending_count()
        total_series = len(self._series_cards)
        self._stats_label.setText(
            f"{total_series} 部 · {active} 进行中 · {pending} 等待中"
        )
