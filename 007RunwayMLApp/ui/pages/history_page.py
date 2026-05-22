import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QFileDialog,
)
from qfluentwidgets import PushButton, BodyLabel, InfoBar, InfoBarPosition

logger = logging.getLogger(__name__)


_HISTORY_COLS = ["时间", "提示词", "引用", "状态", "视频路径"]


class HistoryTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def load(self, log_path: str):
        self.beginResetModel()
        self._rows.clear()
        if os.path.exists(log_path):
            try:
                data = json.loads(Path(log_path).read_text(encoding="utf-8"))
                for entry in data.get("completed", []):
                    entry["_status"] = "已完成"
                    self._rows.append(entry)
                for entry in data.get("failed", []):
                    entry["_status"] = "失败"
                    self._rows.append(entry)
            except Exception:
                logger.exception("加载历史记录文件失败: %s", log_path)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(_HISTORY_COLS)

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _HISTORY_COLS[section]
        return None

    def data(self, index, role):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return row.get("time", "")[:19]
            if col == 1:
                p = row.get("prompt", "")
                return p[:100] + ("…" if len(p) > 100 else "")
            if col == 2:
                refs = row.get("references", [])
                return ", ".join(refs) if refs else "—"
            if col == 3:
                return row.get("_status", row.get("status", "—"))
            if col == 4:
                return row.get("videoPath", row.get("video_path", "—"))

        if role == Qt.ToolTipRole:
            if col == 1:
                return row.get("prompt", "")

        return None


class HistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("historyPage")
        self._main_window = parent
        self._log_path: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(12)

        # Controls
        ctrl_row = QHBoxLayout()
        self._btn_reload = PushButton("重新加载")
        self._btn_reload.clicked.connect(self._on_reload)
        self._btn_export = PushButton("导出 CSV")
        self._btn_export.clicked.connect(self._on_export_csv)
        ctrl_row.addWidget(self._btn_reload)
        ctrl_row.addWidget(self._btn_export)
        ctrl_row.addStretch()
        self._info_label = BodyLabel("")
        layout.addLayout(ctrl_row)
        layout.addWidget(self._info_label)

        # Table
        self._table = QTableView()
        self._model = HistoryTableModel()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 160)
        self._table.setColumnWidth(2, 140)
        self._table.setColumnWidth(3, 80)
        layout.addWidget(self._table, stretch=1)

    def _on_reload(self):
        try:
            mw = self._main_window
            if mw and hasattr(mw, '_batch_log_file'):
                path = mw._batch_log_file()
                self._log_path = path
                self._model.load(path)
                self._info_label.setText(
                    f"已加载 {self._model.rowCount()} 条记录 ({Path(path).name})"
                )
            else:
                InfoBar.warning("无法加载", "日志路径未配置", position=InfoBarPosition.TOP, parent=self)
        except Exception:
            logger.exception("重新加载日志失败")

    def _on_export_csv(self):
        try:
            if self._model.rowCount() == 0:
                InfoBar.warning("无数据", "请先加载日志文件",
                               position=InfoBarPosition.TOP, parent=self)
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "导出 CSV", "history.csv", "CSV Files (*.csv)"
            )
            if path:
                import csv
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(_HISTORY_COLS)
                    for i in range(self._model.rowCount()):
                        row = []
                        for j in range(len(_HISTORY_COLS)):
                            row.append(self._model.data(
                                self._model.createIndex(i, j), Qt.DisplayRole
                            ))
                        writer.writerow(row)
                InfoBar.success("导出成功", f"已保存到 {path}",
                               position=InfoBarPosition.TOP, parent=self)
        except Exception:
            logger.exception("导出 CSV 失败")
