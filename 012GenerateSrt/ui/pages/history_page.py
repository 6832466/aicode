"""
历史记录页 — 查看过往处理记录
"""

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog,
)
from qfluentwidgets import (
    ScrollArea, CardWidget, PushButton, PrimaryPushButton,
    FluentIcon, BodyLabel, StrongBodyLabel, CaptionLabel,
    InfoBar, InfoBarPosition,
)

from app.config import data_dir
from app.models import BatchLogEntry


class HistoryPage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("historyPage")
        self._init_ui()
        self._load_history()

    def _init_ui(self):
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # ── 标题行 ──
        header = QHBoxLayout()
        title = StrongBodyLabel("历史记录")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch()

        export_btn = PushButton("导出 CSV")
        export_btn.setIcon(FluentIcon.SAVE)
        export_btn.clicked.connect(self._export_csv)
        header.addWidget(export_btn)

        clear_btn = PushButton("清空记录")
        clear_btn.setIcon(FluentIcon.DELETE)
        clear_btn.clicked.connect(self._clear_history)
        header.addWidget(clear_btn)

        layout.addLayout(header)

        # ── 统计卡片 ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        self.stats_total = self._make_stat_card("处理总数", "0")
        self.stats_success = self._make_stat_card("成功", "0")
        self.stats_failed = self._make_stat_card("失败", "0")
        stats_layout.addWidget(self.stats_total)
        stats_layout.addWidget(self.stats_success)
        stats_layout.addWidget(self.stats_failed)
        stats_layout.addStretch()

        layout.addLayout(stats_layout)

        # ── 表格 ──
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "文件名", "模式", "状态", "字幕路径", "用时", "处理时间",
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                background: white;
                gridline-color: #F0F0F0;
            }
            QTableWidget::item {
                padding: 8px 12px;
            }
            QTableWidget::item:selected {
                background: #E8F0FE;
                color: #333333;
            }
            QHeaderView::section {
                background: #FAFAFA;
                border: none;
                border-bottom: 1px solid #E0E0E0;
                padding: 8px 12px;
                font-weight: 600;
            }
        """)
        layout.addWidget(self.table)

    def _make_stat_card(self, label: str, value: str) -> CardWidget:
        """创建统计卡片"""
        card = CardWidget()
        card.setFixedSize(160, 80)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(4)

        val_label = StrongBodyLabel(value)
        val_label.setStyleSheet("font-size: 24px; font-weight: 700;")
        card_layout.addWidget(val_label)

        desc_label = CaptionLabel(label)
        desc_label.setStyleSheet("color: #888888;")
        card_layout.addWidget(desc_label)

        card.setObjectName(f"stat_{label}")
        return card

    def _load_history(self):
        """加载历史记录"""
        log_path = data_dir() / "batch_history.json"
        if not log_path.exists():
            self._update_stats([])
            return

        try:
            entries = json.loads(log_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = []

        self.table.setRowCount(len(entries))
        for i, entry in enumerate(entries[::-1]):  # 最新在前
            self.table.setItem(i, 0, QTableWidgetItem(entry.get("file_name", "")))
            self.table.setItem(i, 1, QTableWidgetItem(entry.get("mode", "")))
            self.table.setItem(i, 2, QTableWidgetItem(entry.get("state", "")))
            self.table.setItem(i, 3, QTableWidgetItem(entry.get("srt_path", "")))
            duration = entry.get("duration_seconds", 0)
            dur_str = f"{duration:.1f}s" if duration else ""
            self.table.setItem(i, 4, QTableWidgetItem(dur_str))
            self.table.setItem(i, 5, QTableWidgetItem(entry.get("processed_at", "")))

        self._update_stats(entries)

    def _update_stats(self, entries: list):
        """更新统计卡片"""
        total = len(entries)
        success = sum(1 for e in entries if e.get("state") == "done")
        failed = sum(1 for e in entries if e.get("state") == "failed")

        # 更新卡片内标签
        for card, val in [
            (self.stats_total, total),
            (self.stats_success, success),
            (self.stats_failed, failed),
        ]:
            label = card.findChild(StrongBodyLabel)
            if label:
                label.setText(str(val))

    def _export_csv(self):
        """导出为 CSV"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "history.csv", "CSV 文件 (*.csv)",
        )
        if not path:
            return

        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["文件名", "模式", "状态", "字幕路径", "用时(秒)", "处理时间"])
            for row in range(self.table.rowCount()):
                writer.writerow([
                    self.table.item(row, c).text() if self.table.item(row, c) else ""
                    for c in range(6)
                ])

        InfoBar.success(
            title="导出成功", content=f"已保存到: {path}",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000, parent=self,
        )

    def _clear_history(self):
        """清空历史"""
        self.table.setRowCount(0)
        log_path = data_dir() / "batch_history.json"
        log_path.write_text("[]", encoding="utf-8")
        self._update_stats([])

    def refresh(self):
        """外部刷新"""
        self._load_history()