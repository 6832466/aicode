"""下载管理页面 - 即梦下载器"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QHeaderView,
    QTableWidget, QAbstractItemView, QTableWidgetItem,
)
from qfluentwidgets import (
    TableWidget, PrimaryPushButton, PushButton,
    FluentIcon, InfoBar, BodyLabel, CaptionLabel, ProgressBar,
)

from core.download_manager import DownloadManager
from data.models import DownloadStatus
from ui.widgets import StatCard, StatusBadge
from utils.theme import THEME
from utils.helpers import format_file_size


class DownloadPage(QWidget):
    """下载管理页面"""

    def __init__(self, download_manager: DownloadManager, parent=None):
        super().__init__(parent)
        self.download_manager = download_manager

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # ── 统计卡片行 ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        self._card_pending = StatCard("待下载", 0, "📥", THEME["text_secondary"])
        self._card_downloading = StatCard("下载中", 0, "⬇️", THEME["primary"])
        self._card_completed = StatCard("已完成", 0, "✓", THEME["success"])
        self._card_failed = StatCard("失败", 0, "✗", THEME["danger"])
        for c in [self._card_pending, self._card_downloading,
                  self._card_completed, self._card_failed]:
            stats_layout.addWidget(c)
        layout.addLayout(stats_layout)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._btn_download = PrimaryPushButton(FluentIcon.DOWNLOAD, "下载选中")
        self._btn_refresh = PushButton(FluentIcon.SYNC, "刷新")
        self._btn_pause = PushButton(FluentIcon.PAUSE, "暂停选中")
        self._btn_retry = PushButton(FluentIcon.SYNC, "重试失败")
        self._btn_clear = PushButton(FluentIcon.DELETE, "清空已完成")

        toolbar.addWidget(self._btn_download)
        toolbar.addWidget(self._btn_refresh)
        toolbar.addWidget(self._btn_pause)
        toolbar.addWidget(self._btn_retry)
        toolbar.addStretch()
        toolbar.addWidget(self._btn_clear)
        layout.addLayout(toolbar)

        # ── 下载列表 ──
        self._table = TableWidget(self)
        self._table.setBorderRadius(8)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)

        columns = ["文件名", "场次", "大小", "进度", "状态"]
        self._table.setColumnCount(len(columns))
        self._table.setHorizontalHeaderLabels(columns)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.setColumnWidth(1, 100)
        self._table.setColumnWidth(2, 80)
        self._table.setColumnWidth(3, 150)
        self._table.setColumnWidth(4, 80)

        layout.addWidget(self._table)

        # ── 连接按钮 ──
        self._btn_download.clicked.connect(self._on_download_selected)
        self._btn_refresh.clicked.connect(self._refresh_table)
        self._btn_pause.clicked.connect(self._on_pause_selected)
        self._btn_retry.clicked.connect(self._on_retry_failed)
        self._btn_clear.clicked.connect(self._on_clear_completed)

        # 初始刷新
        self._refresh_table()

    def _connect_signals(self):
        """连接 DownloadManager 信号"""
        self.download_manager.download_added.connect(lambda _: self._refresh_table())
        self.download_manager.download_updated.connect(lambda _: self._refresh_table())
        self.download_manager.download_completed.connect(lambda _: self._refresh_table())
        self.download_manager.download_failed.connect(lambda _: self._refresh_table())

    def _refresh_table(self):
        """刷新下载列表"""
        self._table.setRowCount(0)
        downloads = self.download_manager.get_all_downloads()

        for i, d in enumerate(downloads):
            self._table.insertRow(i)
            self._table.setItem(i, 0, self._cell(d.filename))
            self._table.setItem(i, 1, self._cell(d.scene))

            size_text = format_file_size(d.file_size) if d.file_size > 0 else "--"
            self._table.setItem(i, 2, self._cell(size_text))

            # 进度条
            progress_widget = QWidget()
            progress_layout = QHBoxLayout(progress_widget)
            progress_layout.setContentsMargins(4, 2, 4, 2)
            pb = ProgressBar()
            pb.setRange(0, 100)
            pb.setValue(int(d.progress * 100))
            pb.setFixedHeight(16)
            progress_layout.addWidget(pb)
            self._table.setCellWidget(i, 3, progress_widget)

            # 状态徽章
            status_widget = StatusBadge(d.status.value)
            self._table.setCellWidget(i, 4, status_widget)

        self._update_stats(downloads)

    def _cell(self, text: str):
        """创建表格单元格"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _update_stats(self, downloads: list):
        """更新统计数字"""
        counts = {s.value: 0 for s in DownloadStatus}
        for d in downloads:
            counts[d.status.value] = counts.get(d.status.value, 0) + 1

        self._card_pending.set_value(counts.get("pending", 0))
        self._card_downloading.set_value(counts.get("downloading", 0))
        self._card_completed.set_value(counts.get("completed", 0))
        self._card_failed.set_value(counts.get("failed", 0))

    def _get_selected_ids(self) -> list[str]:
        """获取选中的任务ID"""
        downloads = self.download_manager.get_all_downloads()
        ids = []
        for idx in self._table.selectedIndexes():
            row = idx.row()
            if 0 <= row < len(downloads):
                did = downloads[row].id
                if did not in ids:
                    ids.append(did)
        return ids

    def _on_download_selected(self):
        """下载选中"""
        ids = self._get_selected_ids()
        if not ids:
            InfoBar.warning("提示", "请先选择要下载的任务", parent=self, duration=2000)
            return
        self.download_manager.start_downloads(ids)
        InfoBar.info("开始下载", f"已启动 {len(ids)} 个下载任务", parent=self, duration=2000)

    def _on_pause_selected(self):
        """暂停选中"""
        ids = self._get_selected_ids()
        for did in ids:
            self.download_manager.pause(did)
        InfoBar.info("已暂停", f"已暂停 {len(ids)} 个下载", parent=self, duration=2000)

    def _on_retry_failed(self):
        """重试失败的任务"""
        failed = self.download_manager.get_downloads_by_status(DownloadStatus.FAILED)
        ids = [d.id for d in failed]
        if not ids:
            InfoBar.info("提示", "没有失败的任务", parent=self, duration=2000)
            return
        self.download_manager.start_downloads(ids)
        InfoBar.info("重试中", f"正在重试 {len(ids)} 个任务", parent=self, duration=2000)

    def _on_clear_completed(self):
        """清空已完成"""
        self.download_manager.clear_completed()
        self._refresh_table()
        InfoBar.success("已清空", "已清空所有已完成任务", parent=self, duration=2000)
