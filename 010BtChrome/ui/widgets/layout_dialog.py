from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from qfluentwidgets import ComboBox, StrongBodyLabel


class LayoutDialog(QDialog):
    """窗口排列设置对话框"""

    def __init__(self, parent=None, selected_ids: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("排列窗口")
        self.setMinimumWidth(380)

        self._selected_ids = selected_ids or []
        count = len(self._selected_ids) if self._selected_ids else "全部"

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = StrongBodyLabel(f"排列窗口 — 已选 {count} 个")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.combo_type = ComboBox()
        self.combo_type.addItems(["box (网格)", "diagonal (对角线)"])
        self.combo_type.setCurrentIndex(0)
        self.combo_type.currentIndexChanged.connect(self._on_type_change)
        form.addRow("排列方式", self.combo_type)

        self.combo_order = ComboBox()
        self.combo_order.addItem("正序 (asc)", "asc")
        self.combo_order.addItem("倒序 (desc)", "desc")
        form.addRow("排序", self.combo_order)

        self.spin_col = QSpinBox()
        self.spin_col.setRange(1, 10)
        self.spin_col.setValue(4)
        form.addRow("列数", self.spin_col)

        self.spin_width = QSpinBox()
        self.spin_width.setRange(500, 3840)
        self.spin_width.setValue(500)
        self.spin_width.setSingleStep(50)
        form.addRow("窗口宽度", self.spin_width)

        self.spin_height = QSpinBox()
        self.spin_height.setRange(200, 2160)
        self.spin_height.setValue(300)
        self.spin_height.setSingleStep(50)
        form.addRow("窗口高度", self.spin_height)

        self.spin_start_x = QSpinBox()
        self.spin_start_x.setRange(0, 3840)
        form.addRow("起始 X", self.spin_start_x)

        self.spin_start_y = QSpinBox()
        self.spin_start_y.setRange(0, 2160)
        form.addRow("起始 Y", self.spin_start_y)

        self.spin_space_x = QSpinBox()
        self.spin_space_x.setRange(0, 500)
        form.addRow("水平间距", self.spin_space_x)

        self.spin_space_y = QSpinBox()
        self.spin_space_y.setRange(0, 500)
        form.addRow("垂直间距", self.spin_space_y)

        # 对角线偏移（仅 diagonal 时使用）
        self.spin_offset_x = QSpinBox()
        self.spin_offset_x.setRange(-500, 500)
        self.spin_offset_x.setValue(50)
        form.addRow("偏移 X", self.spin_offset_x)

        self.spin_offset_y = QSpinBox()
        self.spin_offset_y.setRange(-500, 500)
        self.spin_offset_y.setValue(50)
        form.addRow("偏移 Y", self.spin_offset_y)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.ok_btn = QPushButton("应用")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self._on_type_change(0)

    def _on_type_change(self, idx: int):
        is_diagonal = idx == 1
        self.spin_offset_x.setEnabled(is_diagonal)
        self.spin_offset_y.setEnabled(is_diagonal)
        self.spin_col.setEnabled(not is_diagonal)

    def get_data(self) -> dict:
        d: dict[str, Any] = {
            "type": "box" if self.combo_type.currentIndex() == 0 else "diagonal",
            "startX": self.spin_start_x.value(),
            "startY": self.spin_start_y.value(),
            "width": self.spin_width.value(),
            "height": self.spin_height.value(),
            "col": self.spin_col.value(),
            "spaceX": self.spin_space_x.value(),
            "spaceY": self.spin_space_y.value(),
            "offsetX": self.spin_offset_x.value(),
            "offsetY": self.spin_offset_y.value(),
            "orderBy": self.combo_order.currentData(),
        }
        if self._selected_ids:
            d["ids"] = self._selected_ids
        return d
