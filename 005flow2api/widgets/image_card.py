"""Character / image result card widget."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QDialog,
    QDialogButtonBox, QTextEdit, QSizePolicy,
)
from qfluentwidgets import CardWidget, PushButton, ToolButton, FluentIcon


class CharacterCard(CardWidget):
    """Card displaying a character with thumbnail, name, and action buttons."""

    delete_clicked = Signal(int)
    retry_clicked = Signal(int)
    download_clicked = Signal(int)
    view_clicked = Signal(int)
    copy_clicked = Signal(int)
    description_edited = Signal(int, str)

    def __init__(self, index: int, name: str, description: str = "", aliases: str = "", parent=None):
        super().__init__(parent)
        self.index = index
        self.name = name
        self.description = description
        self.aliases = aliases
        self.image_data: bytes | None = None
        self.reference_image: bytes | None = None  # 垫图数据
        self._state = "idle"
        self._description_edited = False

        self._setup_ui()
        self.set_state("idle")

    def _setup_ui(self):
        self.setMinimumSize(230, 420)
        self.setFixedSize(240, 430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Row 0: Checkbox + Name
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.checkbox = QCheckBox()
        self.checkbox.setToolTip("选择此角色")
        top_row.addWidget(self.checkbox)

        self.name_label = QLabel(self.name)
        self.name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumHeight(38)
        top_row.addWidget(self.name_label, 1)
        layout.addLayout(top_row)

        # Row 1: Image area 200x200
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(180, 180)
        self.image_label.setStyleSheet(
            "QLabel { background-color: #f5f5f5; border-radius: 8px; border: 1px solid #ddd; }"
        )
        self.image_label.setScaledContents(False)
        self.image_label.setCursor(Qt.PointingHandCursor)
        self.image_label.mousePressEvent = self._on_image_click
        layout.addWidget(self.image_label, alignment=Qt.AlignCenter)

        # Row 2: State label
        self.state_label = QLabel()
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.state_label)

        # Row 3: Description preview
        self.desc_label = QLabel(self._truncate_text(self.description, 100))
        self.desc_label.setWordWrap(True)
        self.desc_label.setMinimumHeight(36)
        self.desc_label.setStyleSheet("color: #333; font-size: 12px; padding: 2px;")
        self.desc_label.setToolTip(self.description)
        layout.addWidget(self.desc_label)

        # Row 4: Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self.view_btn = ToolButton(FluentIcon.ZOOM)
        self.view_btn.setToolTip("查看大图")
        self.view_btn.setFixedSize(28, 28)
        self.view_btn.clicked.connect(lambda: self.view_clicked.emit(self.index))

        self.edit_btn = ToolButton(FluentIcon.EDIT)
        self.edit_btn.setToolTip("编辑描述词")
        self.edit_btn.setFixedSize(28, 28)
        self.edit_btn.clicked.connect(self._on_edit_description)

        self.download_btn = ToolButton(FluentIcon.DOWN)
        self.download_btn.setToolTip("下载图片")
        self.download_btn.setFixedSize(28, 28)
        self.download_btn.clicked.connect(lambda: self.download_clicked.emit(self.index))

        self.copy_btn = ToolButton(FluentIcon.COPY)
        self.copy_btn.setToolTip("复制完整提示词")
        self.copy_btn.setFixedSize(28, 28)
        self.copy_btn.clicked.connect(lambda: self.copy_clicked.emit(self.index))

        self.retry_btn = ToolButton(FluentIcon.SYNC)
        self.retry_btn.setToolTip("重新生成")
        self.retry_btn.setFixedSize(28, 28)
        self.retry_btn.clicked.connect(lambda: self.retry_clicked.emit(self.index))

        self.delete_btn = ToolButton(FluentIcon.DELETE)
        self.delete_btn.setToolTip("删除此卡")
        self.delete_btn.setFixedSize(28, 28)
        self.delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.index))

        btn_row.addStretch()
        btn_row.addWidget(self.view_btn)
        btn_row.addWidget(self.edit_btn)
        btn_row.addWidget(self.download_btn)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.retry_btn)
        btn_row.addWidget(self.delete_btn)
        layout.addLayout(btn_row)

    def _truncate_text(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."

    def _on_image_click(self, event):
        if self.image_data:
            self.view_clicked.emit(self.index)

    def _on_edit_description(self):
        dialog = QDialog(self.window())
        dialog.setWindowTitle(f"编辑描述词 — {self.name}")
        dialog.resize(500, 350)
        dlg_layout = QVBoxLayout(dialog)

        label = QLabel(f"角色: {self.name}")
        label.setStyleSheet("font-weight: bold; font-size: 13px;")
        dlg_layout.addWidget(label)

        editor = QTextEdit()
        editor.setPlainText(self.description)
        editor.setPlaceholderText("输入角色描述词…")
        dlg_layout.addWidget(editor)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            new_desc = editor.toPlainText().strip()
            if new_desc and new_desc != self.description:
                self.description = new_desc
                self.desc_label.setText(self._truncate_text(new_desc, 50))
                self._description_edited = True
                self.retry_btn.setVisible(True)
                self.description_edited.emit(self.index, new_desc)

    def set_state(self, state: str, message: str = ""):
        """Update card state: idle, queued, generating, done, error."""
        self._state = state
        states = {
            "idle": ("待生成", "#aaa"),
            "queued": ("排队中", "#f0ad4e"),
            "generating": ("生成中…", "#5bc0de"),
            "done": ("已完成", "#5cb85c"),
            "error": ("失败", "#d9534f"),
        }
        label, color = states.get(state, (state, "#999"))
        self.state_label.setText(label)
        self.state_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
        if message:
            self.state_label.setToolTip(message)

        self.download_btn.setVisible(state == "done")
        self.retry_btn.setVisible(state == "error" or self._description_edited)

        # Red border for failed cards
        if state == "error":
            self.setStyleSheet(
                "CharacterCard { border: 2px solid #d9534f; border-radius: 8px; background: #fff; }"
            )
        else:
            self.setStyleSheet("")

    def set_thumbnail(self, image_data: bytes):
        """Display image thumbnail from raw bytes, scaled to 200x200."""
        self.image_data = image_data
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
            self.image_label.setStyleSheet(
                "QLabel { background-color: transparent; border: none; }"
            )

    def reset_description_edited(self):
        """Reset the edited flag — called when generation starts."""
        self._description_edited = False

    @property
    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    @property
    def state(self) -> str:
        return self._state
