from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from qfluentwidgets import (
    PushButton, PrimaryPushButton, ToolButton, SubtitleLabel,
    BodyLabel, FluentIcon, TextEdit, LineEdit
)

from template_manager import get_manager


class _EditDialog(QDialog):
    def __init__(self, parent=None, name: str = "", content: str = ""):
        super().__init__(parent)
        self.setWindowTitle("编辑模板" if name else "新建模板")
        self.setMinimumWidth(500)
        self.setMinimumHeight(340)
        self._build_ui(name, content)

    def _build_ui(self, name: str, content: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(BodyLabel("模板名称"))
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("输入模板名称...")
        self.name_edit.setText(name)
        layout.addWidget(self.name_edit)

        layout.addWidget(BodyLabel("提示词内容"))
        self.content_edit = TextEdit()
        self.content_edit.setPlaceholderText("输入系统提示词内容...")
        self.content_edit.setPlainText(content)
        self.content_edit.setMinimumHeight(160)
        layout.addWidget(self.content_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        confirm_btn = PrimaryPushButton("保存")
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)

    def _on_confirm(self):
        if self.name_edit.text().strip() and self.content_edit.toPlainText().strip():
            self.accept()

    def get_name(self) -> str:
        return self.name_edit.text().strip()

    def get_content(self) -> str:
        return self.content_edit.toPlainText().strip()


class TemplatePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = get_manager()
        self._build_ui()
        self._reload()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("系统提示词模板"))
        header.addStretch()
        layout.addLayout(header)

        layout.addWidget(BodyLabel('在这里管理系统提示词模板，首页"选择模板"按钮会从此处读取。'))

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["模板名称", "提示词内容", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 140)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        add_btn = PrimaryPushButton(FluentIcon.ADD, "新建模板")
        add_btn.clicked.connect(self._add)
        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _reload(self):
        self.table.setRowCount(0)
        for t in self._manager.all():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, self._cell(t.name))
            preview = t.content[:80] + ("..." if len(t.content) > 80 else "")
            self.table.setItem(row, 1, self._cell(preview))
            self._set_ops(row)
            self.table.setRowHeight(row, 38)

    def _set_ops(self, row: int):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(2)

        edit_btn = ToolButton(FluentIcon.EDIT)
        edit_btn.setFixedSize(QSize(28, 28))
        edit_btn.setToolTip("编辑")
        edit_btn.clicked.connect(lambda _, r=row: self._edit(r))

        del_btn = ToolButton(FluentIcon.DELETE)
        del_btn.setFixedSize(QSize(28, 28))
        del_btn.setToolTip("删除")
        del_btn.clicked.connect(lambda _, r=row: self._delete(r))

        up_btn = ToolButton(FluentIcon.UP)
        up_btn.setFixedSize(QSize(28, 28))
        up_btn.setToolTip("上移")
        up_btn.clicked.connect(lambda _, r=row: self._move_up(r))

        down_btn = ToolButton(FluentIcon.DOWN)
        down_btn.setFixedSize(QSize(28, 28))
        down_btn.setToolTip("下移")
        down_btn.clicked.connect(lambda _, r=row: self._move_down(r))

        for b in (edit_btn, del_btn, up_btn, down_btn):
            h.addWidget(b)
        self.table.setCellWidget(row, 2, w)

    def _add(self):
        dlg = _EditDialog(self)
        if dlg.exec():
            self._manager.add(dlg.get_name(), dlg.get_content())
            self._reload()

    def _edit(self, row: int):
        templates = self._manager.all()
        if row >= len(templates):
            return
        t = templates[row]
        dlg = _EditDialog(self, name=t.name, content=t.content)
        if dlg.exec():
            self._manager.update(row, dlg.get_name(), dlg.get_content())
            self._reload()

    def _delete(self, row: int):
        from qfluentwidgets import MessageBox
        templates = self._manager.all()
        if row >= len(templates):
            return
        box = MessageBox("确认删除", f"确定要删除模板「{templates[row].name}」吗？", self)
        if box.exec():
            self._manager.delete(row)
            self._reload()

    def _move_up(self, row: int):
        self._manager.move_up(row)
        self._reload()

    def _move_down(self, row: int):
        self._manager.move_down(row)
        self._reload()

    def _on_double_click(self, index):
        self._edit(index.row())

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item
