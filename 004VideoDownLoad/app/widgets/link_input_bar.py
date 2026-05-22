"""链接输入栏 + 下载选项组件"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton,
    QComboBox, QLabel, QTextEdit, QDialog, QDialogButtonBox,
)
from PySide6.QtCore import Signal, Qt
from qfluentwidgets import (
    LineEdit, PushButton, ComboBox, PrimaryPushButton,
    InfoBar, InfoBarPosition, Dialog,
)


class BatchAddDialog(Dialog):
    """批量添加链接对话框"""

    def __init__(self, parent=None):
        super().__init__('批量添加链接', '', parent)
        self._links: list[str] = []

        layout = QVBoxLayout(self)
        hint = QLabel('每行粘贴一个视频链接（最多50个）：')
        layout.addWidget(hint)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText('https://v.douyin.com/xxx\nhttps://v.kuaishou.com/xxx\n...')
        self.text_edit.setMinimumSize(500, 300)
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = PushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        ok_btn = PrimaryPushButton('添加')
        ok_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _on_accept(self):
        from app.utils.link_utils import extract_links
        text = self.text_edit.toPlainText()
        self._links = extract_links(text)
        if not self._links:
            InfoBar.warning(
                title='提示',
                content='未识别到有效链接，请检查链接格式',
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        self.accept()

    def get_links(self) -> list[str]:
        return self._links


class LinkInputBar(QWidget):
    """顶部链接输入栏"""

    add_links = Signal(list)  # 添加链接信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 第一行：链接输入
        input_row = QHBoxLayout()

        self.link_input = LineEdit()
        self.link_input.setPlaceholderText('粘贴抖音/快手等等视频链接，按回车添加')
        self.link_input.setMinimumHeight(38)
        self.link_input.returnPressed.connect(self._on_add_single)
        input_row.addWidget(self.link_input, stretch=1)

        add_btn = PrimaryPushButton('添加')
        add_btn.setMinimumHeight(38)
        add_btn.clicked.connect(self._on_add_single)
        input_row.addWidget(add_btn)

        layout.addLayout(input_row)

        # 第二行：下载选项
        option_row = QHBoxLayout()

        option_row.addWidget(QLabel('画质:'))
        self.quality_combo = ComboBox()
        self.quality_combo.addItems(['1080P', '720P', '4K', '480P', '360P'])
        self.quality_combo.setCurrentText('1080P')
        option_row.addWidget(self.quality_combo)

        option_row.addSpacing(16)
        option_row.addWidget(QLabel('格式:'))
        self.format_combo = ComboBox()
        self.format_combo.addItems(['MP4', 'MKV', 'WebM'])
        self.format_combo.setCurrentText('MP4')
        option_row.addWidget(self.format_combo)

        option_row.addSpacing(16)
        option_row.addWidget(QLabel('去水印:'))
        self.watermark_combo = ComboBox()
        self.watermark_combo.addItems(['开启', '关闭'])
        self.watermark_combo.setCurrentText('开启')
        option_row.addWidget(self.watermark_combo)

        option_row.addStretch()
        layout.addLayout(option_row)

    def _on_add_single(self):
        text = self.link_input.text().strip()
        if not text:
            return
        from app.utils.link_utils import extract_links
        links = extract_links(text)
        if links:
            self.add_links.emit(links)
            self.link_input.clear()
        else:
            InfoBar.warning(
                title='提示',
                content='链接格式不正确，请检查',
                position=InfoBarPosition.TOP,
                parent=self.window(),
            )

    def get_options(self) -> dict:
        return {
            'quality': self.quality_combo.currentText(),
            'format': self.format_combo.currentText().lower(),
            'no_watermark': self.watermark_combo.currentText() == '开启',
        }
