"""Left sidebar panel for prompt input and generation settings."""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QWidget, QTextEdit,
    QScrollArea, QFileDialog, QMessageBox,
)
from qfluentwidgets import (
    TextEdit, ComboBox, PrimaryPushButton, PushButton,
    CardWidget, InfoBar, InfoBarPosition, ToolButton, FluentIcon,
    FlowLayout,
)

from utils import parse_prompts, parse_characters_json, ASPECT_RATIO_MAP, RESOLUTION_MAP, Character
from config import cfg

DEFAULT_PREFIX = "根据下面的描述生成一张比例1:1的人物图片，亚洲面孔，3D国漫风格，"
DEFAULT_SUFFIX = "不要加分割线，纯白色背景，左边腰部以上正面特写，右边正面全身照，站立姿势，不要文字，不要手中拿的物品，双手自然放下，8头身比，极致的身材比例（8k分辨率，极致细节，大师杰作，高品质。）"


class PromptPanel(CardWidget):
    """Left sidebar: JSON prompt input + prefix/suffix + aspect ratio/resolution selectors + action buttons."""

    start_generation = Signal(list, str, str, str, str)  # characters, prefix, suffix, aspect_ratio_value, resolution_value
    parse_requested = Signal(list, str, str, str, str)  # characters, prefix, suffix, aspect_ratio_value, resolution_value
    reference_cards_requested = Signal(list)  # list of (name, image_bytes) tuples

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(380)
        self.setMinimumHeight(680)
        self._reference_paths: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Title
        title = QLabel("提示词输入")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(title)

        # Hint
        hint = QLabel("粘贴 JSON 角色数据，或每行一个提示词")
        hint.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(hint)

        # Prompt text area
        self.prompt_edit = TextEdit()
        self.prompt_edit.setPlaceholderText(
            "在此粘贴 JSON 角色数组，或每行一个提示词…\n\n"
            'JSON 格式示例：\n'
            '[{"name":"角色名","aliases":"别名","description":"描述词"}]\n\n'
            "也可以每行一个提示词，支持批量生成"
        )
        self.prompt_edit.setMinimumHeight(140)
        layout.addWidget(self.prompt_edit)

        # Prefix input
        prefix_label = QLabel("前缀词")
        prefix_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(prefix_label)

        self.prefix_edit = QTextEdit()
        self.prefix_edit.setPlainText(DEFAULT_PREFIX)
        self.prefix_edit.setPlaceholderText("前缀词，添加到描述词之前…")
        self.prefix_edit.setMaximumHeight(60)
        self.prefix_edit.setMinimumHeight(40)
        layout.addWidget(self.prefix_edit)

        # Suffix input
        suffix_label = QLabel("后缀词")
        suffix_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(suffix_label)

        self.suffix_edit = QTextEdit()
        self.suffix_edit.setPlainText(DEFAULT_SUFFIX)
        self.suffix_edit.setPlaceholderText("后缀词，添加到描述词之后…")
        self.suffix_edit.setMaximumHeight(80)
        self.suffix_edit.setMinimumHeight(50)
        layout.addWidget(self.suffix_edit)

        # Aspect ratio selector
        ratio_label = QLabel("图片比例")
        ratio_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(ratio_label)

        self.ratio_combo = ComboBox()
        self.ratio_combo.addItems(list(ASPECT_RATIO_MAP.keys()))
        self.ratio_combo.setCurrentText(cfg.aspect_ratio.value)
        layout.addWidget(self.ratio_combo)

        # Resolution selector
        res_label = QLabel("分辨率")
        res_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(res_label)

        self.resolution_combo = ComboBox()
        self.resolution_combo.addItems(list(RESOLUTION_MAP.keys()))
        self.resolution_combo.setCurrentText(cfg.resolution.value)
        layout.addWidget(self.resolution_combo)

        # Reference image area
        ref_label = QLabel("参考图片 (垫图)")
        ref_label.setStyleSheet("font-weight: bold; color: #555;")
        layout.addWidget(ref_label)

        ref_btn_row = QHBoxLayout()
        ref_btn_row.setSpacing(8)
        self.add_ref_btn = PushButton("添加参考图")
        self.add_ref_btn.setFixedHeight(28)
        self.add_ref_btn.clicked.connect(self._on_add_reference)
        ref_btn_row.addWidget(self.add_ref_btn)
        self.clear_ref_btn = PushButton("清空")
        self.clear_ref_btn.setFixedHeight(28)
        self.clear_ref_btn.clicked.connect(self._on_clear_references)
        ref_btn_row.addWidget(self.clear_ref_btn)

        self.create_ref_cards_btn = PushButton("从参考图创建卡片")
        self.create_ref_cards_btn.setFixedHeight(28)
        self.create_ref_cards_btn.clicked.connect(self._on_create_ref_cards)
        ref_btn_row.addWidget(self.create_ref_cards_btn)
        ref_btn_row.addStretch()
        layout.addLayout(ref_btn_row)

        # Thumbnail scroll area
        self.ref_scroll = QScrollArea()
        self.ref_scroll.setMinimumHeight(120)
        self.ref_scroll.setMaximumHeight(220)
        self.ref_scroll.setWidgetResizable(True)
        self.ref_scroll.setStyleSheet("QScrollArea { border: 1px solid #ddd; border-radius: 4px; background: #fafafa; }")
        self.ref_container = QWidget()
        self.ref_layout = FlowLayout(self.ref_container, needAni=False)
        self.ref_layout.setContentsMargins(4, 4, 4, 4)
        self.ref_layout.setSpacing(4)
        self.ref_scroll.setWidget(self.ref_container)
        layout.addWidget(self.ref_scroll)

        layout.addStretch(1)

        # Action buttons
        self.parse_btn = PushButton("解析角色")
        self.parse_btn.setMinimumHeight(36)
        self.parse_btn.clicked.connect(self._on_parse)
        layout.addWidget(self.parse_btn)

        self.generate_btn = PrimaryPushButton("开始生图")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate)
        layout.addWidget(self.generate_btn)

        self.clear_btn = PushButton("清空")
        self.clear_btn.clicked.connect(self._on_clear)
        layout.addWidget(self.clear_btn)

    def _on_parse(self):
        text = self.prompt_edit.toPlainText().strip()
        prefix = self.prefix_edit.toPlainText().strip()
        suffix = self.suffix_edit.toPlainText().strip()

        characters = parse_characters_json(text)

        if not characters:
            prompts = parse_prompts(text)
            if not prompts:
                InfoBar.warning(
                    title="提示",
                    content="请先输入 JSON 角色数据或至少一行提示词",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self.window(),
                )
                return
            characters = [
                Character(name=f"角色{i+1}", description=p, index=i)
                for i, p in enumerate(prompts)
            ]

        ratio_text = self.ratio_combo.currentText()
        res_text = self.resolution_combo.currentText()
        cfg.set(cfg.aspect_ratio, ratio_text, save=False)
        cfg.set(cfg.resolution, res_text, save=False)
        ratio_value = ASPECT_RATIO_MAP[ratio_text]
        res_value = RESOLUTION_MAP[res_text]
        self.parse_requested.emit(characters, prefix, suffix, ratio_value, res_value)

    def _on_generate(self):
        prefix = self.prefix_edit.toPlainText().strip()
        suffix = self.suffix_edit.toPlainText().strip()
        ratio_text = self.ratio_combo.currentText()
        res_text = self.resolution_combo.currentText()
        cfg.set(cfg.aspect_ratio, ratio_text, save=False)
        cfg.set(cfg.resolution, res_text, save=False)
        ratio_value = ASPECT_RATIO_MAP[ratio_text]
        res_value = RESOLUTION_MAP[res_text]
        self.start_generation.emit([], prefix, suffix, ratio_value, res_value)

    def _on_clear(self):
        reply = QMessageBox.question(
            self.window(), "确认清空",
            "确定要清空提示词输入框吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.prompt_edit.clear()

    def enable_generate(self, enable: bool):
        self.generate_btn.setEnabled(enable)

    def _on_add_reference(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self.window(), "选择参考图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        for path in paths:
            if path not in self._reference_paths:
                self._reference_paths.append(path)
                self._add_ref_thumbnail(path)

    def _on_clear_references(self):
        if not self._reference_paths:
            return
        reply = QMessageBox.question(
            self.window(), "确认清空",
            f"确定要清空 {len(self._reference_paths)} 张参考图片吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._reference_paths.clear()
        old_container = self.ref_container
        self.ref_container = QWidget()
        self.ref_layout = FlowLayout(self.ref_container, needAni=False)
        self.ref_layout.setContentsMargins(4, 4, 4, 4)
        self.ref_layout.setSpacing(4)
        self.ref_scroll.setWidget(self.ref_container)
        old_container.deleteLater()

    def _on_create_ref_cards(self):
        if not self._reference_paths:
            InfoBar.info(
                title="提示", content="请先添加参考图片",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self.window(),
            )
            return
        items = []
        for path in self._reference_paths:
            try:
                with open(path, "rb") as f:
                    data = f.read()
                name = os.path.splitext(os.path.basename(path))[0]
                items.append((name, data))
            except Exception:
                pass
        if items:
            self.reference_cards_requested.emit(items)

    def _add_ref_thumbnail(self, path: str):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        thumb = pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label = QLabel()
        label.setFixedSize(64, 64)
        label.setPixmap(thumb)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("border: 1px solid #ddd; border-radius: 4px;")
        label.setToolTip(os.path.basename(path))
        self.ref_layout.addWidget(label)

    @property
    def reference_paths(self) -> list[str]:
        return list(self._reference_paths)

    @property
    def prompt_count(self) -> int:
        text = self.prompt_edit.toPlainText()
        chars = parse_characters_json(text)
        if chars:
            return len(chars)
        return len(parse_prompts(text))
