from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout

from qfluentwidgets import (
    Dialog,
    LineEdit,
    SpinBox,
    StrongBodyLabel,
)


class GroupEditDialog(Dialog):
    """新建/编辑分组对话框"""

    def __init__(self, parent=None, name: str = "", sort: int = 0):
        super().__init__("新建分组" if not name else "编辑分组", "", parent)
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")

        layout = QVBoxLayout()
        layout.setSpacing(8)

        layout.addWidget(StrongBodyLabel("分组名称"))
        self.name_input = LineEdit()
        self.name_input.setText(name)
        self.name_input.setPlaceholderText("请输入分组名称")
        layout.addWidget(self.name_input)

        layout.addWidget(StrongBodyLabel("排序"))
        self.sort_spin = SpinBox()
        self.sort_spin.setRange(0, 9999)
        self.sort_spin.setValue(sort)
        layout.addWidget(self.sort_spin)

        # 插入到按钮上方
        self.vBoxLayout.insertLayout(1, layout)
        self.setMinimumWidth(360)

    def get_values(self):
        return self.name_input.text().strip(), self.sort_spin.value()
