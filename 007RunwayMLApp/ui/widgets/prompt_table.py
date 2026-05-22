from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtWidgets import QTableView, QHeaderView, QMenu
from PySide6.QtGui import QAction, QColor

from app.models import PromptItem, TaskStatus

_COLUMNS = ["序号", "状态", "提示词", "引用角色", "时长", "比例", "失败原因"]
_COL_INDEX = 0
_COL_STATUS = 1
_COL_PROMPT = 2
_COL_REFS = 3
_COL_DUR = 4
_COL_RATIO = 5
_COL_ERROR = 6


class PromptTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[PromptItem] = []

    def set_items(self, items: list[PromptItem]):
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def update_item(self, index: int):
        """Emit dataChanged for a single row to refresh status cell."""
        if 0 <= index < len(self._items):
            top_left = self.createIndex(index, 0)
            bottom_right = self.createIndex(index, len(_COLUMNS) - 1)
            self.dataChanged.emit(top_left, bottom_right)

    @staticmethod
    def _status_display(item: PromptItem) -> str:
        if item.status == TaskStatus.QUEUED:
            if item.missing_refs:
                return "缺少素材"
            return "待提交"
        if item.status == TaskStatus.SUBMITTING:
            return "提交中…"
        if item.status == TaskStatus.RUNNING:
            pct = int(item.progress_ratio * 100)
            return f"{pct}%" if pct > 0 else "已提交"
        if item.status == TaskStatus.THROTTLED:
            return "排队中"
        if item.status == TaskStatus.DONE:
            return "已完成"
        if item.status == TaskStatus.DOWNLOADING:
            return "下载中…"
        if item.status == TaskStatus.DOWNLOADED:
            return "已下载"
        if item.status == TaskStatus.FAILED:
            return "失败"
        return item.status.value

    def item_at(self, row: int) -> PromptItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLUMNS)

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return _COLUMNS[section]
        return None

    def data(self, index, role):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        col = index.column()

        if col == _COL_INDEX:
            if role == Qt.DisplayRole:
                return str(item.index + 1)
            if role == Qt.TextAlignmentRole:
                return Qt.AlignCenter

        if col == _COL_STATUS:
            if role == Qt.UserRole:
                return item.status.value
            if role == Qt.DisplayRole:
                return self._status_display(item)

        if col == _COL_PROMPT:
            if role == Qt.DisplayRole:
                text = item.display_prompt
                return text[:120] + ("…" if len(text) > 120 else "")
            if role == Qt.ToolTipRole:
                return item.display_prompt

        if col == _COL_REFS:
            if role == Qt.DisplayRole:
                return ", ".join(item.references) if item.references else "—"

        if col == _COL_DUR:
            if role == Qt.DisplayRole:
                return f"{item.duration}s"
            if role == Qt.TextAlignmentRole:
                return Qt.AlignCenter

        if col == _COL_RATIO:
            if role == Qt.DisplayRole:
                return item.ratio
            if role == Qt.TextAlignmentRole:
                return Qt.AlignCenter

        if col == _COL_ERROR:
            if role == Qt.DisplayRole:
                return item.error_message or ""
            if role == Qt.ToolTipRole:
                return item.error_message or ""

        if role == Qt.BackgroundRole:
            if item.status == TaskStatus.RUNNING:
                return QColor(173, 216, 230)  # light blue

        return None


class PromptTableView(QTableView):
    edit_requested = Signal(int)            # row index
    submit_requested = Signal(int)          # row index
    retry_download_requested = Signal(int)  # row index
    delete_item_requested = Signal(int)     # row index
    clear_list_requested = Signal()         # clear entire list
    reload_requested = Signal()             # re-import from last Excel files

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QTableView.SelectRows)
        self.setSelectionMode(QTableView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        # Signals
        self.doubleClicked.connect(self._on_double_click)
        self.customContextMenuRequested.connect(self._on_context_menu)

        hh = self.horizontalHeader()
        hh.setSectionResizeMode(_COL_INDEX, QHeaderView.Fixed)
        hh.setSectionResizeMode(_COL_STATUS, QHeaderView.Fixed)
        hh.setSectionResizeMode(_COL_REFS, QHeaderView.Fixed)
        hh.setSectionResizeMode(_COL_DUR, QHeaderView.Fixed)
        hh.setSectionResizeMode(_COL_RATIO, QHeaderView.Fixed)
        hh.setSectionResizeMode(_COL_ERROR, QHeaderView.Fixed)
        hh.setSectionResizeMode(_COL_PROMPT, QHeaderView.Stretch)

        self.setColumnWidth(_COL_INDEX, 50)
        self.setColumnWidth(_COL_STATUS, 80)
        self.setColumnWidth(_COL_REFS, 140)
        self.setColumnWidth(_COL_DUR, 50)
        self.setColumnWidth(_COL_RATIO, 50)
        self.setColumnWidth(_COL_ERROR, 120)

    def _on_double_click(self, index: QModelIndex):
        self.edit_requested.emit(index.row())

    def _on_context_menu(self, pos):
        try:
            idx = self.indexAt(pos)
            if not idx.isValid():
                return
            row = idx.row()
            model = self.model()
            if not isinstance(model, PromptTableModel):
                return
            item = model.item_at(row)
            if item is None:
                return

            self._build_menu(row, item, pos)
        except Exception:
            import traceback
            traceback.print_exc()

    def _build_menu(self, row: int, item: PromptItem, pos):
        menu = QMenu(self)

        # 1. Item actions first
        edit_action = QAction("编辑此条", self)
        edit_action.triggered.connect(lambda: self.edit_requested.emit(row))
        menu.addAction(edit_action)

        submit_action = QAction("提交此任务", self)
        submit_action.triggered.connect(lambda: self.submit_requested.emit(row))
        can_submit = item.status not in (
            TaskStatus.SUBMITTING, TaskStatus.RUNNING, TaskStatus.THROTTLED, TaskStatus.DOWNLOADING,
        )
        submit_action.setEnabled(can_submit)
        menu.addAction(submit_action)

        # Retry download for items with video URL
        if item.result_video_url:
            retry_dl = QAction("重试下载", self)
            retry_dl.triggered.connect(lambda: self.retry_download_requested.emit(row))
            menu.addAction(retry_dl)

        menu.addSeparator()

        # Reload
        reload_action = QAction("重新加载", self)
        reload_action.triggered.connect(lambda: self.reload_requested.emit())
        menu.addAction(reload_action)

        # Delete item
        del_action = QAction("删除此项", self)
        del_action.triggered.connect(lambda: self._confirm_delete_item(row))
        menu.addAction(del_action)

        # Clear all
        clear_all = QAction("清空列表", self)
        clear_all.triggered.connect(lambda: self._confirm_clear())
        menu.addAction(clear_all)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _confirm_delete_item(self, row: int):
        try:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "确认删除", f"确定要删除第 {row + 1} 条提示词吗？\n此项将被永久移除（序号不变）。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.delete_item_requested.emit(row)
        except Exception:
            import traceback
            traceback.print_exc()

    def _confirm_clear(self):
        try:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "确认清空", "确定要清空提示词列表吗？\n此操作不可撤销。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.clear_list_requested.emit()
        except Exception:
            import traceback
            traceback.print_exc()
