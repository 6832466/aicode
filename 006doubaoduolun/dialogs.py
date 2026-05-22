from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QComboBox, QFileDialog, QListWidget, QListWidgetItem,
    QSizePolicy, QWidget, QFrame
)
from PySide6.QtCore import Qt
from qfluentwidgets import (
    PushButton, LineEdit, ComboBox, TextEdit, BodyLabel,
    SubtitleLabel, RadioButton, PrimaryPushButton, MessageBox
)
import csv
import os

from models import ChatMode


class AddMessageDialog(QDialog):
    def __init__(self, parent=None, edit_content: str = "", edit_mode: ChatMode = ChatMode.AUTO):
        super().__init__(parent)
        self.setWindowTitle("添加发送消息")
        self.setMinimumWidth(480)
        self.setMinimumHeight(320)
        self._build_ui(edit_content, edit_mode)

    def _build_ui(self, content: str, mode: ChatMode):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(SubtitleLabel("消息内容"))
        self.text_edit = TextEdit()
        self.text_edit.setPlaceholderText("在此输入要发送给豆包的消息...")
        self.text_edit.setMinimumHeight(160)
        self.text_edit.setPlainText(content)
        layout.addWidget(self.text_edit)

        mode_row = QHBoxLayout()
        mode_row.addWidget(BodyLabel("强制使用模式："))
        self._chat_modes = list(ChatMode)
        self.mode_combo = ComboBox()
        for m in self._chat_modes:
            self.mode_combo.addItem(m.value)
        self.mode_combo.setCurrentIndex(self._chat_modes.index(mode))
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        confirm_btn = PrimaryPushButton("添加到队列")
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)

    def _on_confirm(self):
        if not self.text_edit.toPlainText().strip():
            return
        self.accept()

    def get_content(self) -> str:
        return self.text_edit.toPlainText().strip()

    def get_mode(self) -> ChatMode:
        return self._chat_modes[self.mode_combo.currentIndex()]


class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量导入消息")
        self.setMinimumWidth(520)
        self.setMinimumHeight(440)
        self._messages: list[str] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(SubtitleLabel("导入方式"))

        self.rb_txt = RadioButton("从文本文件导入（每行一条消息）")
        self.rb_excel = RadioButton("从 Excel 文件导入")
        self.rb_csv = RadioButton("从 CSV 文件导入")
        self.rb_paste = RadioButton("手动粘贴（每行一条消息）")
        self.rb_txt.setChecked(True)
        for rb in (self.rb_txt, self.rb_excel, self.rb_csv, self.rb_paste):
            layout.addWidget(rb)
            rb.toggled.connect(self._on_mode_changed)

        self.file_btn = PushButton("选择文件")
        self.file_btn.clicked.connect(self._pick_file)
        layout.addWidget(self.file_btn)

        self.paste_area = TextEdit()
        self.paste_area.setPlaceholderText("每行一条消息，粘贴到此处...")
        self.paste_area.setMinimumHeight(80)
        self.paste_area.setVisible(False)
        self.paste_area.textChanged.connect(self._on_paste_changed)
        layout.addWidget(self.paste_area)

        self.preview_label = BodyLabel("预览（共识别到 0 条消息）：")
        layout.addWidget(self.preview_label)

        self.preview_list = QListWidget()
        self.preview_list.setMinimumHeight(100)
        layout.addWidget(self.preview_list)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        self.confirm_btn = PrimaryPushButton("确认导入")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)

    def _on_mode_changed(self):
        is_paste = self.rb_paste.isChecked()
        self.file_btn.setVisible(not is_paste)
        self.paste_area.setVisible(is_paste)
        self._messages = []
        self._refresh_preview()

    def _pick_file(self):
        if self.rb_txt.isChecked():
            path, _ = QFileDialog.getOpenFileName(self, "选择文本文件", "", "文本文件 (*.txt)")
            if path:
                self._load_txt(path)
        elif self.rb_excel.isChecked():
            path, _ = QFileDialog.getOpenFileName(self, "选择 Excel 文件", "", "Excel 文件 (*.xlsx *.xls)")
            if path:
                self._load_excel(path)
        elif self.rb_csv.isChecked():
            path, _ = QFileDialog.getOpenFileName(self, "选择 CSV 文件", "", "CSV 文件 (*.csv)")
            if path:
                self._load_csv(path)

    def _load_txt(self, path: str):
        with open(path, encoding="utf-8") as f:
            self._messages = [line.strip() for line in f if line.strip()]
        self._refresh_preview()

    def _load_excel(self, path: str):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path)
            ws = wb.active
            self._messages = []
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell and str(cell).strip():
                        self._messages.append(str(cell).strip())
                        break
        except ImportError:
            MessageBox("提示", "请先安装 openpyxl：pip install openpyxl", self).exec()
        self._refresh_preview()

    def _load_csv(self, path: str):
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            self._messages = [row[0].strip() for row in reader if row and row[0].strip()]
        self._refresh_preview()

    def _on_paste_changed(self):
        text = self.paste_area.toPlainText()
        self._messages = [line.strip() for line in text.splitlines() if line.strip()]
        self._refresh_preview()

    def _refresh_preview(self):
        self.preview_list.clear()
        for i, msg in enumerate(self._messages, 1):
            self.preview_list.addItem(f"{i}. {msg[:80]}{'...' if len(msg) > 80 else ''}")
        self.preview_label.setText(f"预览（共识别到 {len(self._messages)} 条消息）：")
        self.confirm_btn.setEnabled(bool(self._messages))

    def get_messages(self) -> list[str]:
        return self._messages


class BatchEditDialog(QDialog):
    """Batch modify forced_mode for a range of messages."""
    def __init__(self, total: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量编辑模式")
        self.setMinimumWidth(420)
        self.setMinimumHeight(200)
        self._build_ui(total)

    def _build_ui(self, total: int):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        layout.addWidget(SubtitleLabel(f"批量修改模式（共 {total} 条消息）"))

        tips = BodyLabel("请输入行号范围（对应左侧表格的「序号」列，1 ~ " + str(total) + "）")
        tips.setWordWrap(True)
        layout.addWidget(tips)

        range_row = QHBoxLayout()
        range_row.setSpacing(8)
        range_row.addWidget(BodyLabel("从第"))
        self.start_edit = LineEdit()
        self.start_edit.setPlaceholderText("起始行")
        self.start_edit.setFixedWidth(70)
        range_row.addWidget(self.start_edit)
        range_row.addWidget(BodyLabel("行到第"))
        self.end_edit = LineEdit()
        self.end_edit.setPlaceholderText("结束行")
        self.end_edit.setFixedWidth(70)
        range_row.addWidget(self.end_edit)
        range_row.addWidget(BodyLabel("行"))
        range_row.addStretch()
        layout.addLayout(range_row)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(BodyLabel("设为模式："))
        self._modes = [ChatMode.EXPERT, ChatMode.THINK, ChatMode.FAST, ChatMode.AUTO]
        self.mode_combo = ComboBox()
        for m in self._modes:
            self.mode_combo.addItem(m.value)
        self.mode_combo.setCurrentIndex(0)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        confirm_btn = PrimaryPushButton("确认修改")
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)

    def _on_confirm(self):
        try:
            s = int(self.start_edit.text())
            e = int(self.end_edit.text())
        except ValueError:
            return
        if 1 <= s <= e:
            self.accept()

    def get_range(self) -> tuple[int, int]:
        return int(self.start_edit.text()), int(self.end_edit.text())

    def get_mode(self) -> ChatMode:
        return self._modes[self.mode_combo.currentIndex()]


class DetailDialog(QDialog):
    """Show full content of a message or reply."""
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.setMinimumHeight(400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        text = TextEdit()
        text.setPlainText(content)
        text.setReadOnly(True)
        layout.addWidget(text)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = PushButton("复制全文")
        copy_btn.clicked.connect(lambda: self._copy(content))
        close_btn = PrimaryPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _copy(self, text: str):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
    """Show full content of a message or reply."""
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.setMinimumHeight(400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        text = TextEdit()
        text.setPlainText(content)
        text.setReadOnly(True)
        layout.addWidget(text)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = PushButton("复制全文")
        copy_btn.clicked.connect(lambda: self._copy(content))
        close_btn = PrimaryPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _copy(self, text: str):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
