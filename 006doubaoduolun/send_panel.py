from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont
from qfluentwidgets import (
    PushButton, PrimaryPushButton, ToolButton, SubtitleLabel,
    BodyLabel, FluentIcon, InfoBadge, isDarkTheme
)

from models import SendMessage, SendStatus, ChatMode
from dialogs import AddMessageDialog, ImportDialog, DetailDialog, BatchEditDialog


STATUS_COLORS = {
    SendStatus.PENDING: ("#9E9E9E", "#757575"),
    SendStatus.SENDING: ("#2196F3", "#1565C0"),
    SendStatus.SENT: ("#4CAF50", "#2E7D32"),
    SendStatus.FAILED: ("#F44336", "#C62828"),
}

COL_ID = 0
COL_CONTENT = 1
COL_STATUS = 2
COL_MODE = 3
COL_TIME = 4
COL_REPLY = 5
COL_OPS = 6


class SendPanel(QWidget):
    messages_changed = Signal()
    start_from_index = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages: list[SendMessage] = []
        self._next_id = 1
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("发送消息队列"))
        header.addStretch()
        layout.addLayout(header)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["序号", "消息内容", "状态", "模式", "发送时间", "回复", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(COL_CONTENT, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_OPS, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_ID, 50)
        self.table.setColumnWidth(COL_STATUS, 80)
        self.table.setColumnWidth(COL_MODE, 90)
        self.table.setColumnWidth(COL_TIME, 90)
        self.table.setColumnWidth(COL_REPLY, 50)
        self.table.setColumnWidth(COL_OPS, 130)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        add_btn = PrimaryPushButton(FluentIcon.ADD, "添加消息")
        add_btn.clicked.connect(self._add_message)
        import_btn = PushButton(FluentIcon.DOWNLOAD, "导入文件")
        import_btn.clicked.connect(self._import_messages)
        clear_btn = PushButton(FluentIcon.DELETE, "清空全部")
        clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(import_btn)
        btn_row.addWidget(clear_btn)
        batch_btn = PushButton(FluentIcon.EDIT, "批量编辑")
        batch_btn.clicked.connect(self._batch_edit)
        btn_row.addWidget(batch_btn)
        btn_row.addStretch()

        self.resume_label = BodyLabel("从序号继续：")
        from qfluentwidgets import LineEdit as _LineEdit
        self.resume_spin = _LineEdit()
        self.resume_spin.setText("1")
        self.resume_spin.setFixedWidth(60)
        self.resume_spin.setPlaceholderText("序号")
        resume_btn = PushButton("继续执行")
        resume_btn.clicked.connect(self._resume_from)
        btn_row.addWidget(self.resume_label)
        btn_row.addWidget(self.resume_spin)
        btn_row.addWidget(resume_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def get_messages(self) -> list[SendMessage]:
        return list(self._messages)

    def get_pending_messages(self) -> list[SendMessage]:
        return [m for m in self._messages if m.status == SendStatus.PENDING]

    def update_status(self, msg_id: int, status: SendStatus):
        for i, msg in enumerate(self._messages):
            if msg.id == msg_id:
                msg.status = status
                self._refresh_row(i)
                self.table.scrollTo(self.table.model().index(i, 0))
                break

    def update_reply_link(self, msg_id: int, reply_id: int):
        for i, msg in enumerate(self._messages):
            if msg.id == msg_id:
                msg.reply_id = reply_id
                self._refresh_row(i)
                break

    def update_send_time(self, msg_id: int):
        from datetime import datetime
        for i, msg in enumerate(self._messages):
            if msg.id == msg_id:
                msg.send_time = datetime.now()
                self._refresh_row(i)
                break

    # ------------------------------------------------------------------ #
    #  Slots                                                               #
    # ------------------------------------------------------------------ #

    def _add_message(self):
        dlg = AddMessageDialog(self)
        if dlg.exec():
            msg = SendMessage(
                id=self._next_id,
                content=dlg.get_content(),
                forced_mode=dlg.get_mode(),
            )
            self._next_id += 1
            self._messages.append(msg)
            self._append_row(msg)
            self.messages_changed.emit()

    def _import_messages(self):
        dlg = ImportDialog(self)
        if dlg.exec():
            for text in dlg.get_messages():
                msg = SendMessage(id=self._next_id, content=text)
                self._next_id += 1
                self._messages.append(msg)
                self._append_row(msg)
            self.messages_changed.emit()

    def _clear_all(self):
        from qfluentwidgets import MessageBox
        box = MessageBox("确认清空", "确定要清空全部消息吗？此操作不可撤销。", self)
        if box.exec():
            self._messages.clear()
            self.table.setRowCount(0)
            self._next_id = 1
            self.messages_changed.emit()

    def _resume_from(self):
        try:
            idx = int(self.resume_spin.text()) - 1
        except ValueError:
            idx = 0
        self.start_from_index.emit(max(0, idx))

    def _batch_edit(self):
        total = len(self._messages)
        if total == 0:
            return
        dlg = BatchEditDialog(total, self)
        if dlg.exec():
            start, end = dlg.get_range()
            mode = dlg.get_mode()
            # row numbers are 1-based display index
            for i in range(start - 1, end):
                if i >= total:
                    break
                msg = self._messages[i]
                msg.forced_mode = mode if mode != ChatMode.AUTO else None
                self._refresh_row(i)
            self.messages_changed.emit()

    def _on_double_click(self, index):
        row = index.row()
        if row < len(self._messages):
            msg = self._messages[row]
            DetailDialog(f"消息 #{msg.id} 详情", msg.content, self).exec()

    def _edit_message(self, row: int):
        if row >= len(self._messages):
            return
        msg = self._messages[row]
        if msg.status != SendStatus.PENDING:
            return
        dlg = AddMessageDialog(self, edit_content=msg.content, edit_mode=msg.forced_mode or ChatMode.AUTO)
        dlg.setWindowTitle("编辑消息")
        if dlg.exec():
            msg.content = dlg.get_content()
            msg.forced_mode = dlg.get_mode()
            self._refresh_row(row)

    def _delete_message(self, row: int):
        if row >= len(self._messages):
            return
        self._messages.pop(row)
        self.table.removeRow(row)
        self.messages_changed.emit()

    def _move_up(self, row: int):
        if row <= 0 or row >= len(self._messages):
            return
        self._messages[row], self._messages[row - 1] = self._messages[row - 1], self._messages[row]
        self._rebuild_table()

    def _move_down(self, row: int):
        if row < 0 or row >= len(self._messages) - 1:
            return
        self._messages[row], self._messages[row + 1] = self._messages[row + 1], self._messages[row]
        self._rebuild_table()

    # ------------------------------------------------------------------ #
    #  Table helpers                                                       #
    # ------------------------------------------------------------------ #

    def _append_row(self, msg: SendMessage):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._fill_row(row, msg)

    def _refresh_row(self, row: int):
        if row < len(self._messages):
            self._fill_row(row, self._messages[row])

    def _rebuild_table(self):
        self.table.setRowCount(0)
        for msg in self._messages:
            self._append_row(msg)

    def _fill_row(self, row: int, msg: SendMessage):
        self.table.setItem(row, COL_ID, self._cell(str(msg.id), center=True))
        preview = msg.content[:40] + ("..." if len(msg.content) > 40 else "")
        self.table.setItem(row, COL_CONTENT, self._cell(preview))

        status_item = self._cell(msg.status.value, center=True)
        light, dark = STATUS_COLORS.get(msg.status, ("#9E9E9E", "#757575"))
        color = dark if isDarkTheme() else light
        status_item.setForeground(QColor(color))
        font = QFont()
        font.setBold(True)
        status_item.setFont(font)
        self.table.setItem(row, COL_STATUS, status_item)

        mode_text = msg.mode.value if msg.mode != ChatMode.AUTO else (
            msg.forced_mode.value if msg.forced_mode and msg.forced_mode != ChatMode.AUTO else "—"
        )
        self.table.setItem(row, COL_MODE, self._cell(mode_text, center=True))

        time_text = msg.send_time.strftime("%H:%M:%S") if msg.send_time else "—"
        self.table.setItem(row, COL_TIME, self._cell(time_text, center=True))

        reply_text = f"#{msg.reply_id}" if msg.reply_id else "—"
        self.table.setItem(row, COL_REPLY, self._cell(reply_text, center=True))

        # ops widget
        ops_widget = QWidget()
        ops_layout = QHBoxLayout(ops_widget)
        ops_layout.setContentsMargins(2, 2, 2, 2)
        ops_layout.setSpacing(2)

        edit_btn = ToolButton(FluentIcon.EDIT)
        edit_btn.setFixedSize(QSize(28, 28))
        edit_btn.setToolTip("编辑")
        edit_btn.setEnabled(msg.status == SendStatus.PENDING)
        edit_btn.clicked.connect(lambda _, r=row: self._edit_message(r))

        del_btn = ToolButton(FluentIcon.DELETE)
        del_btn.setFixedSize(QSize(28, 28))
        del_btn.setToolTip("删除")
        del_btn.clicked.connect(lambda _, r=row: self._delete_message(r))

        up_btn = ToolButton(FluentIcon.UP)
        up_btn.setFixedSize(QSize(28, 28))
        up_btn.setToolTip("上移")
        up_btn.clicked.connect(lambda _, r=row: self._move_up(r))

        down_btn = ToolButton(FluentIcon.DOWN)
        down_btn.setFixedSize(QSize(28, 28))
        down_btn.setToolTip("下移")
        down_btn.clicked.connect(lambda _, r=row: self._move_down(r))

        for b in (edit_btn, del_btn, up_btn, down_btn):
            ops_layout.addWidget(b)
        self.table.setCellWidget(row, COL_OPS, ops_widget)
        self.table.setRowHeight(row, 36)

    @staticmethod
    def _cell(text: str, center: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item
