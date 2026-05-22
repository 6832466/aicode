import re

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTextEdit, QLineEdit, QSpinBox, QComboBox,
    QDialogButtonBox, QLabel,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QIcon

from app.models import PromptItem
from app.config import MIN_DURATION, MAX_DURATION, app_icon_path

RATIOS = ["16:9", "9:16", "4:3", "3:4", "1:1", "21:9"]


class _CharHighlighter(QSyntaxHighlighter):
    """Highlight [角色名] patterns with red text on yellow background."""

    def __init__(self, char_names: list[str], parent=None):
        super().__init__(parent)
        self._names = char_names
        self._fmt = QTextCharFormat()
        self._fmt.setForeground(QColor(200, 0, 0))
        self._fmt.setBackground(QColor(255, 255, 0))
        self._fmt.setFontWeight(QFont.Bold)

    def highlightBlock(self, text: str):
        for name in self._names:
            # Highlight [name] bracket form
            pattern = f"[{name}]"
            idx = 0
            while True:
                idx = text.find(pattern, idx)
                if idx < 0:
                    break
                self.setFormat(idx, len(pattern), self._fmt)
                idx += len(pattern)
            # Also highlight plain text occurrences (skip if inside brackets already)
            idx = 0
            while True:
                idx = text.find(name, idx)
                if idx < 0:
                    break
                # Don't double-highlight if this is part of [name]
                if idx > 0 and text[idx - 1] == '[':
                    idx += len(name)
                    continue
                # Avoid matching inside existing highlighted text
                self.setFormat(idx, len(name), self._fmt)
                idx += len(name)


class EditDialog(QDialog):
    """Dialog for editing a single prompt item."""

    def __init__(self, item: PromptItem, char_map: dict[str, str], available_refs: list[str] | None = None, parent=None):
        super().__init__(parent)
        self._item = item
        self._char_map = char_map
        self._char_names = available_refs or list(char_map.values())
        self.setWindowTitle(f"编辑提示词 — 第 {item.index + 1} 条")
        self.resize(900, 600)
        self._set_icon()
        self._setup_ui()
        self._load_item()

    def _set_icon(self):
        try:
            p = app_icon_path()
            if p.exists():
                self.setWindowIcon(QIcon(str(p)))
        except Exception:
            pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        # Prompt
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setAcceptRichText(False)
        self._prompt_edit.setPlaceholderText("输入提示词…")
        self._prompt_edit.setMinimumHeight(280)
        font = self._prompt_edit.font()
        font.setPointSize(font.pointSize() + 2)
        self._prompt_edit.setFont(font)
        # Highlight [角色名] in red on yellow background
        prompt_names = list(self._char_map.keys())
        if prompt_names:
            self._highlighter = _CharHighlighter(prompt_names, self._prompt_edit.document())
        form.addRow("提示词:", self._prompt_edit)

        # References
        ref_row = QHBoxLayout()
        self._refs_edit = QLineEdit()
        self._refs_edit.setPlaceholderText("用逗号分隔，如: suwan, chenjingming")
        ref_row.addWidget(self._refs_edit, stretch=1)
        if self._char_names:
            hint = QLabel(f"可用: {', '.join(self._char_names)}")
            hint.setStyleSheet("color: #888;")
            ref_row.addWidget(hint)
        form.addRow("引用角色:", ref_row)

        # Duration
        self._dur_spin = QSpinBox()
        self._dur_spin.setRange(MIN_DURATION, MAX_DURATION)
        self._dur_spin.setSuffix(" 秒")
        self._dur_spin.setFixedWidth(100)
        form.addRow("时长:", self._dur_spin)

        # Ratio
        self._ratio_combo = QComboBox()
        self._ratio_combo.setEditable(True)
        self._ratio_combo.addItems(RATIOS)
        self._ratio_combo.setFixedWidth(120)
        form.addRow("比例:", self._ratio_combo)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_item(self):
        self._prompt_edit.setPlainText(self._item.display_prompt)
        self._refs_edit.setText(", ".join(self._item.references))
        self._dur_spin.setValue(self._item.duration)
        idx = self._ratio_combo.findText(self._item.ratio)
        if idx >= 0:
            self._ratio_combo.setCurrentIndex(idx)
        else:
            self._ratio_combo.setCurrentText(self._item.ratio)

    def _regenerate_api_prompt(self, raw_text: str) -> str:
        """Use full raw text as API prompt, append reference suffix at end."""
        result = raw_text.strip()

        # Build reference suffix from [角色名] brackets in raw text
        refs = self._detect_references(raw_text, result)
        if refs:
            ref_parts = []
            for ref in refs:
                char_name = next((cn for cn, rn in self._char_map.items() if rn == ref), None)
                if char_name:
                    ref_parts.append(f"{char_name}是 @{ref}")
            if ref_parts:
                result = result + "\n\n" + " ,".join(ref_parts)

        return result

    def _detect_references(self, raw_text: str, api_prompt: str) -> list[str]:
        found = []
        seen = set()

        # Scan raw text for [角色名] bracket patterns matching char_map
        bracket_names = re.findall(r"\[([^\]]+)\]", raw_text)
        for name in bracket_names:
            ref = None
            if name in self._char_map:
                ref = self._char_map[name]
            elif name in self._char_names:
                ref = name
            if ref and ref not in seen:
                found.append(ref)
                seen.add(ref)

        # Also scan for char_map keys appearing as plain text (no brackets needed)
        for cn_name, ref_name in self._char_map.items():
            if ref_name not in seen and cn_name in raw_text:
                found.append(ref_name)
                seen.add(ref_name)

        return found

    def _on_accept(self):
        self._item.raw_prompt = self._prompt_edit.toPlainText().strip()
        self._item.prompt_text = self._regenerate_api_prompt(self._item.raw_prompt)
        self._item.references = self._detect_references(self._item.raw_prompt, self._item.prompt_text)
        self._item.duration = self._dur_spin.value()
        self._item.ratio = self._ratio_combo.currentText().strip()
        self.accept()
