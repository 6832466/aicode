"""历史页 - 已完成下载记录表格"""
import json
import logging
import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QLineEdit,
    QMessageBox, QCheckBox, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont
from qfluentwidgets import (
    BodyLabel, CaptionLabel, StrongBodyLabel,
    FluentIcon, InfoBar, InfoBarPosition,
)

from gui.history_db import HistoryDatabase

logger = logging.getLogger("hongguo")


class HistoryPage(QWidget):
    re_download = Signal(str, list)  # series_id, episode_indices

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._db = HistoryDatabase()
        self._records: list[dict] = []
        self._row_checkboxes: list[QCheckBox] = []
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)

        # 标题栏
        header = QHBoxLayout()

        title = StrongBodyLabel("下载历史")
        title.setStyleSheet("font-size: 16px;")
        header.addWidget(title)

        self._select_all_cb = QCheckBox("全选")
        self._select_all_cb.setStyleSheet("""
            QCheckBox {
                font-size: 12px; color: #888; spacing: 4px;
            }
            QCheckBox:hover { color: #0078d4; }
        """)
        self._select_all_cb.toggled.connect(self._on_select_all)
        header.addSpacing(12)
        header.addWidget(self._select_all_cb)
        header.addStretch()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索历史记录...")
        self._search_edit.setFixedWidth(220)
        self._search_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ddd; border-radius: 6px;
                padding: 6px 10px; font-size: 13px;
            }
        """)
        self._search_edit.textChanged.connect(self._on_search)
        header.addWidget(self._search_edit)

        clear_btn = QPushButton("清空历史")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self._on_clear_all)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #fff0f0; border: 1px solid #f44336;
                border-radius: 6px; padding: 0 16px;
                color: #f44336; font-size: 12px; font-weight: 600;
            }
            QPushButton:hover { background: #ffebee; }
        """)
        header.addWidget(clear_btn)

        layout.addLayout(header)

        # 表格
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "", "短剧名称", "已下载", "总集数", "清晰度", "日期", "路径", "操作"
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnWidth(0, 24)
        self._table.setColumnWidth(2, 70)
        self._table.setColumnWidth(3, 60)
        self._table.setColumnWidth(4, 60)
        self._table.setColumnWidth(5, 100)
        self._table.setColumnWidth(6, 160)
        self._table.setColumnWidth(7, 240)
        self._table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e8e8e8;
                border-radius: 8px;
                gridline-color: #f0f0f0;
                background: white;
            }
            QHeaderView::section {
                background: #fafafa;
                border: none;
                border-bottom: 2px solid #e8e8e8;
                padding: 8px 6px;
                font-weight: 600;
                color: #555;
            }
        """)
        layout.addWidget(self._table, stretch=1)

    def refresh(self):
        try:
            self._records = self._db.get_all(limit=200)
            self._populate_table()
        except Exception:
            logger.exception("刷新历史记录失败")
            self._records = []

    def _populate_table(self):
        try:
            self._table.setRowCount(len(self._records))
            self._row_checkboxes.clear()
            self._select_all_cb.blockSignals(True)
            self._select_all_cb.setChecked(False)
            self._select_all_cb.blockSignals(False)
            for i, rec in enumerate(self._records):
                # Checkbox
                cb = QCheckBox()
                self._row_checkboxes.append(cb)
                self._table.setCellWidget(i, 0, cb)

                # 名称
                name_item = QTableWidgetItem(rec["series_name"])
                name_item.setData(Qt.UserRole, rec["id"])
                self._table.setItem(i, 1, name_item)

                # 已下载
                eps = json.loads(rec["episodes_downloaded"] or "[]")
                self._table.setItem(i, 2, QTableWidgetItem(f"{len(eps)}集" if eps else "-"))

                # 总集数
                total = rec["total_episodes"] or 0
                self._table.setItem(i, 3, QTableWidgetItem(f"{total}集" if total else "-"))

                # 清晰度
                self._table.setItem(i, 4, QTableWidgetItem(rec.get("quality", "-")))

                # 日期
                self._table.setItem(i, 5, QTableWidgetItem(rec.get("download_date", "-")))

                # 路径
                path = rec.get("local_path", "")
                short = (path[:50] + "...") if len(path) > 50 else path
                path_item = QTableWidgetItem(short)
                path_item.setToolTip(path)
                self._table.setItem(i, 6, path_item)

                # 操作按钮
                op_widget = QWidget()
                op_layout = QHBoxLayout(op_widget)
                op_layout.setContentsMargins(4, 2, 4, 2)
                op_layout.setSpacing(4)

                record_id = rec["id"]

                open_btn = QPushButton("打开")
                open_btn.setFixedSize(56, 28)
                open_btn.setStyleSheet(self._small_btn_style())
                open_btn.clicked.connect(lambda checked, rid=record_id: self._open_folder(rid))
                op_layout.addWidget(open_btn)

                re_dl_btn = QPushButton("重下")
                re_dl_btn.setFixedSize(56, 28)
                re_dl_btn.setStyleSheet(self._small_btn_style("#0078d4"))
                re_dl_btn.clicked.connect(lambda checked, rid=record_id: self._re_download(rid))
                op_layout.addWidget(re_dl_btn)

                del_btn = QPushButton("删除")
                del_btn.setFixedSize(56, 28)
                del_btn.setStyleSheet(self._small_btn_style("#f44336"))
                del_btn.clicked.connect(lambda checked, rid=record_id: self._delete_record(rid))
                op_layout.addWidget(del_btn)

                self._table.setCellWidget(i, 7, op_widget)
        except Exception:
            logger.exception("填充历史表格失败")

    @staticmethod
    def _small_btn_style(accent: str = "#555") -> str:
        return f"""
            QPushButton {{
                background: #fafafa;
                border: 1px solid {accent}40;
                border-radius: 4px;
                color: {accent};
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {accent}18;
                border-color: {accent};
            }}
        """

    def _on_select_all(self, checked: bool):
        for cb in self._row_checkboxes:
            cb.setChecked(checked)

    def _on_search(self, text: str):
        if text.strip():
            self._records = self._db.search(text.strip())
        else:
            self._records = self._db.get_all(limit=200)
        self._populate_table()

    def _open_folder(self, record_id: int):
        try:
            rec = next((r for r in self._records if r["id"] == record_id), None)
            if not rec:
                return
            path = rec.get("local_path", "")
            if not path:
                InfoBar.warning("路径为空", "该记录没有保存的本地路径", parent=self)
                return
            subprocess.Popen(['explorer', path])
        except Exception:
            logger.exception(f"打开文件夹失败: id={record_id}")

    def _re_download(self, record_id: int):
        rec = next((r for r in self._records if r["id"] == record_id), None)
        if not rec:
            return
        series_id = rec["series_id"]
        eps = json.loads(rec["episodes_downloaded"] or "[]")
        self.re_download.emit(series_id, eps)
        InfoBar.info("重新下载", f"已加入队列: {rec['series_name']}", parent=self)

    def _delete_record(self, record_id: int):
        try:
            rec = next((r for r in self._records if r["id"] == record_id), None)
            if not rec:
                return

            path = rec.get("local_path", "")
            has_files = bool(path and os.path.exists(path))

            msg = QMessageBox(self)
            msg.setWindowTitle("删除确认")
            msg.setText(f"确定要删除记录「{rec['series_name']}」吗?")
            if has_files:
                msg.setInformativeText(f"本地文件夹存在:\n{path}\n\n是否同时删除本地文件? (此操作不可撤销)")
            else:
                msg.setInformativeText("本地文件不存在或将只删除记录")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            msg.setDefaultButton(QMessageBox.Cancel)
            msg.button(QMessageBox.Yes).setText("同时删除文件")
            msg.button(QMessageBox.No).setText("仅删除记录")
            msg.button(QMessageBox.Cancel).setText("取消")

            result = msg.exec()
            if result == QMessageBox.Cancel:
                return

            if result == QMessageBox.Yes and path:
                self._async_delete_files(path)

            self._db.delete(record_id)
            InfoBar.success("已删除", "", parent=self)
            self.refresh()
        except Exception:
            logger.exception(f"删除历史记录失败: id={record_id}")

    def _async_delete_files(self, path: str):
        """在后台线程安全删除文件夹"""
        from pathlib import Path as _Path

        target = _Path(path).resolve()
        allowed = _Path(self.config.download_path).resolve()
        if not (str(target).startswith(str(allowed)) and target != allowed):
            logger.error(f"拒绝删除安全范围外的路径: {path}")
            return

        forbidden = {"C:\\", str(_Path.home()), str(_Path.home() / "Desktop"),
                     str(_Path.home() / "Documents"), str(_Path.home() / "Downloads")}
        if str(target).rstrip("\\") in forbidden:
            logger.error(f"拒绝删除危险路径: {path}")
            return

        class DeleteWorker(QThread):
            def run(self):
                try:
                    from send2trash import send2trash
                    send2trash(path)
                except Exception:
                    pass

        worker = DeleteWorker()
        if not hasattr(self, '_delete_workers'):
            self._delete_workers = []
        worker.finished.connect(lambda w=worker: self._delete_workers.remove(w) if w in self._delete_workers else None)
        self._delete_workers.append(worker)
        worker.start()
        logger.info(f"后台删除: {path}")

    def _on_clear_all(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("清空确认")
        msg.setText("确定要清空全部历史记录吗?")
        msg.setInformativeText("此操作仅删除记录, 不会删除已下载的视频文件")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        if msg.exec() == QMessageBox.Ok:
            self._db.clear_all()
            self.refresh()
            InfoBar.success("已清空", "全部历史记录已清空", parent=self)
