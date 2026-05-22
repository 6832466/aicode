from __future__ import annotations

import logging

from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QVBoxLayout, QWidget

from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    TableView,
    TitleLabel,
)

from app.api_client import BitBrowserAPI
from app.models import GroupItem
from app.utils import extract_rows
from ui.widgets.api_worker import ApiCaller
from ui.widgets.group_edit_dialog import GroupEditDialog

logger = logging.getLogger(__name__)


class GroupPage(QWidget):
    COL_ID = 0
    COL_NAME = 1
    COL_SORT = 2

    def __init__(self, api: BitBrowserAPI, parent=None):
        super().__init__(parent)
        self.api = api
        self._groups: list[GroupItem] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        title = TitleLabel("分组管理")
        layout.addWidget(title)

        # 工具栏
        toolbar = QHBoxLayout()
        self.add_btn = PrimaryPushButton(FluentIcon.ADD, "新建分组")
        self.add_btn.clicked.connect(self._add_group)
        self.edit_btn = PushButton(FluentIcon.EDIT, "编辑")
        self.edit_btn.clicked.connect(self._edit_group)
        self.del_btn = PushButton(FluentIcon.DELETE, "删除")
        self.del_btn.clicked.connect(self._delete_group)
        self.refresh_btn = PushButton(FluentIcon.SYNC, "刷新")
        self.refresh_btn.clicked.connect(self.refresh_data)

        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.del_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)

        # 表格
        self.table = TableView(self)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(TableView.SelectionMode.SingleSelection)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setSectionResizeMode(self.COL_ID, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        # Model
        self._model = QStandardItemModel(0, 3, self)
        self._model.setHorizontalHeaderLabels(["ID", "分组名称", "排序"])
        self.table.setModel(self._model)

    def refresh_data(self):
        if not self.api.base_url:
            InfoBar.warning("提示", "请先在设置页配置 API 地址", parent=self)
            return
        c = ApiCaller()
        c.finished.connect(self._on_list_result)
        c.error.connect(lambda e: InfoBar.error("获取分组失败", e, parent=self))
        c.run(self.api.group_list, 0, 200)

    def showEvent(self, event):
        super().showEvent(event)
        if self.api.base_url:
            self.refresh_data()

    def _on_list_result(self, data: dict):
        rows = extract_rows(data)
        self._groups = [
            GroupItem(
                id=g.get("id", ""),
                name=g.get("groupName", ""),
                sort=g.get("sortNum", 0),
            )
            for g in rows
        ]
        self._model.removeRows(0, self._model.rowCount())
        for g in self._groups:
            row = [
                QStandardItem(g.id),
                QStandardItem(g.name),
                QStandardItem(str(g.sort)),
            ]
            row[self.COL_ID].setEditable(False)
            row[self.COL_NAME].setEditable(False)
            row[self.COL_SORT].setEditable(False)
            self._model.appendRow(row)

    def _selected_group(self) -> GroupItem | None:
        idx = self.table.currentIndex()
        if idx.isValid() and 0 <= idx.row() < len(self._groups):
            return self._groups[idx.row()]
        return None

    def _add_group(self):
        dlg = GroupEditDialog(self)
        if dlg.exec():
            name, sort = dlg.get_values()
            if not name:
                InfoBar.warning("提示", "分组名称不能为空", parent=self)
                return
            c = ApiCaller()
            c.finished.connect(lambda _: self.refresh_data())
            c.error.connect(lambda e: InfoBar.error("创建失败", e, parent=self))
            c.run(self.api.group_add, name, sort)

    def _edit_group(self):
        g = self._selected_group()
        if not g:
            InfoBar.warning("提示", "请先选择一个分组", parent=self)
            return
        dlg = GroupEditDialog(self, g.name, g.sort)
        if dlg.exec():
            name, sort = dlg.get_values()
            if not name:
                InfoBar.warning("提示", "分组名称不能为空", parent=self)
                return
            c = ApiCaller()
            c.finished.connect(lambda _: self.refresh_data())
            c.error.connect(lambda e: InfoBar.error("编辑失败", e, parent=self))
            c.run(self.api.group_edit, g.id, name, sort)

    def _delete_group(self):
        g = self._selected_group()
        if not g:
            InfoBar.warning("提示", "请先选择一个分组", parent=self)
            return
        msg = MessageBox("确认删除", f"确定要删除分组「{g.name}」吗？\n此操作不可恢复。", self)
        if msg.exec():
            c = ApiCaller()
            c.finished.connect(lambda _: self.refresh_data())
            c.error.connect(lambda e: InfoBar.error("删除失败", e, parent=self))
            c.run(self.api.group_delete, g.id)
