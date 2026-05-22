"""
AI改文 — 智能文本改写与优化（核心功能）
"""

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QFrame, QMenu, QTextBrowser,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from qfluentwidgets import (
    LineEdit, PushButton, PrimaryPushButton, ComboBox,
    EditableComboBox, StrongBodyLabel, CaptionLabel, InfoBar,
    InfoBarPosition,
)

from app.constants import (
    INSTRUCTION_FIX_TYPOS, DEFAULT_SEGMENT_SIZE, rewrite_history_dir,
)
from app.config_manager import ConfigManager
from core.text_processor import (
    TextProcessor, get_instruction_prompt, compute_diff, count_characters,
)
from services.ai_service import AIService, AISegmentWorker
from ui.components.text_edit import TextEditWidget


class TextRewritePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("text_rewrite_page")
        self._parent = parent
        self.config = ConfigManager()
        self._stream_worker = None
        self._is_processing = False
        self._compare_mode = False
        self._init_ui()
        self._load_config()

    # ═══════════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════════

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 12)
        layout.setSpacing(6)

        # 标题 — 独立一行置顶
        title = StrongBodyLabel("AI改文")
        title.setStyleSheet("font-size: 22px; color: #1a1a1a;")
        layout.addWidget(title)

        # 参数行：指令 + 模型 + 分段
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        header_row.addWidget(CaptionLabel("指令:"))
        self.instruction_combo = ComboBox()
        self.instruction_combo.addItem(INSTRUCTION_FIX_TYPOS)
        self.instruction_combo.setCurrentText(INSTRUCTION_FIX_TYPOS)
        self.instruction_combo.setMinimumWidth(120)
        header_row.addWidget(self.instruction_combo)

        header_row.addWidget(CaptionLabel("模型:"))
        self.model_combo = EditableComboBox()
        self.model_combo.setMinimumWidth(140)
        header_row.addWidget(self.model_combo)

        header_row.addWidget(CaptionLabel("分段:"))
        self.segment_input = LineEdit()
        self.segment_input.setText(str(DEFAULT_SEGMENT_SIZE))
        self.segment_input.setFixedWidth(70)
        header_row.addWidget(self.segment_input)

        header_row.addStretch()
        layout.addLayout(header_row)

        # 编辑器区域 — 占 70% 高度
        layout.addWidget(self._build_editor_area(), 1)

        # 底部操作栏
        layout.addWidget(self._build_bottom_bar())

    def _build_editor_area(self) -> QSplitter:
        splitter = QSplitter(Qt.Horizontal)

        # 输入区
        left = QWidget()
        left_ly = QVBoxLayout(left)
        left_ly.setContentsMargins(0, 0, 0, 0)
        left_ly.setSpacing(4)

        left_label = StrongBodyLabel("原文本")
        left_ly.addWidget(left_label)

        self.input_editor = TextEditWidget("在此粘贴或输入文本...")
        self.input_editor.btn_copy.clicked.connect(self._copy_input)
        self.input_editor.btn_clear.clicked.connect(self.input_editor.clear)
        self.input_editor.btn_format.clicked.connect(
            lambda: self.input_editor.setText(TextProcessor.format_text(self.input_editor.text()))
        )
        self._setup_context_menu(self.input_editor)
        left_ly.addWidget(self.input_editor)
        splitter.addWidget(left)

        # 中间操作按钮（竖排，居中）
        middle = QWidget()
        middle.setMinimumWidth(80)
        middle_ly = QVBoxLayout(middle)
        middle_ly.setContentsMargins(8, 0, 8, 0)
        middle_ly.setSpacing(12)
        middle_ly.addStretch()

        self.btn_swap = PushButton("交换")
        self.btn_swap.setMinimumHeight(36)
        self.btn_swap.setMinimumWidth(64)
        self.btn_swap.clicked.connect(self._on_swap)
        middle_ly.addWidget(self.btn_swap, alignment=Qt.AlignCenter)

        self.btn_compare = PushButton("对比")
        self.btn_compare.setMinimumHeight(36)
        self.btn_compare.setMinimumWidth(64)
        self.btn_compare.clicked.connect(self._on_compare)
        middle_ly.addWidget(self.btn_compare, alignment=Qt.AlignCenter)

        middle_ly.addStretch()
        splitter.addWidget(middle)

        # 输出区
        right = QWidget()
        right_ly = QVBoxLayout(right)
        right_ly.setContentsMargins(0, 0, 0, 0)
        right_ly.setSpacing(4)

        right_label = StrongBodyLabel("结果")
        right_ly.addWidget(right_label)

        self.output_editor = TextEditWidget("处理结果将显示在此...")
        self.output_editor.btn_copy.clicked.connect(self._copy_output)
        self.output_editor.btn_clear.clicked.connect(self.output_editor.clear)
        self.output_editor.btn_format.clicked.connect(
            lambda: self.output_editor.setText(TextProcessor.format_text(self.output_editor.text()))
        )
        self._setup_context_menu(self.output_editor)
        right_ly.addWidget(self.output_editor)

        # 对比浏览器（富文本显示，默认隐藏）
        self.compare_browser = QTextBrowser()
        self.compare_browser.setOpenExternalLinks(False)
        self.compare_browser.setFont(QFont("Microsoft YaHei", 11))
        self.compare_browser.hide()
        right_ly.addWidget(self.compare_browser)

        splitter.addWidget(right)
        splitter.setSizes([450, 100, 450])
        return splitter

    def _build_bottom_bar(self) -> QFrame:
        bar = QFrame()
        ly = QHBoxLayout(bar)
        ly.setContentsMargins(0, 4, 0, 0)
        ly.setSpacing(8)

        ly.addStretch()

        self.btn_process = PrimaryPushButton("AI一键处理")
        self.btn_process.clicked.connect(self._on_ai_process)
        ly.addWidget(self.btn_process)

        return bar

    # ═══════════════════════════════════════════
    #  右键菜单
    # ═══════════════════════════════════════════

    def _setup_context_menu(self, editor_widget: TextEditWidget):
        editor_widget.editor.setContextMenuPolicy(Qt.CustomContextMenu)
        editor_widget.editor.customContextMenuRequested.connect(
            lambda pos, ew=editor_widget: self._show_context_menu(pos, ew)
        )

    def _show_context_menu(self, pos, editor_widget: TextEditWidget):
        menu = QMenu(self)
        add_action = menu.addAction("添加序号")
        del_action = menu.addAction("删除序号")
        menu.addSeparator()
        select_all_action = menu.addAction("全选")
        copy_action = menu.addAction("复制")
        paste_action = menu.addAction("粘贴")
        clear_action = menu.addAction("清除")
        action = menu.exec(editor_widget.editor.mapToGlobal(pos))
        if action is None:
            return
        editor = editor_widget.editor
        if action == add_action:
            text = editor_widget.text()
            if text:
                editor_widget.setText(TextProcessor.add_numbers(text))
        elif action == del_action:
            text = editor_widget.text()
            if text:
                editor_widget.setText(TextProcessor.remove_numbers(text))
        elif action == select_all_action:
            editor.selectAll()
        elif action == copy_action:
            editor.copy()
        elif action == paste_action:
            editor.paste()
        elif action == clear_action:
            editor.clear()

    # ═══════════════════════════════════════════
    #  配置加载
    # ═══════════════════════════════════════════

    def _load_config(self):
        ep = self.config.get_default_endpoint()
        self.model_combo.clear()
        self.model_combo.addItems(["deepseek-v4-pro", "deepseek-v4-flash"])
        self.model_combo.setCurrentText("deepseek-v4-flash")

    # ═══════════════════════════════════════════
    #  操作槽函数
    # ═══════════════════════════════════════════

    def _copy_input(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.input_editor.text())

    def _copy_output(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.output_editor.text())

    def _on_swap(self):
        input_text = self.input_editor.text()
        output_text = self.output_editor.text()
        self.input_editor.setText(output_text)
        self.output_editor.setText(input_text)

    def _on_compare(self):
        original = self.input_editor.text()
        modified = self.output_editor.text()
        if not original or not modified:
            self._show_error("请先输入原文并获得处理结果")
            return
        if self._compare_mode:
            self._exit_compare_mode()
            return
        html = compute_diff(original, modified)
        self.compare_browser.setHtml(html)
        self.output_editor.hide()
        self.compare_browser.show()
        self._compare_mode = True
        self.btn_compare.setText("关闭对比")

    def _exit_compare_mode(self):
        self.compare_browser.hide()
        self.output_editor.show()
        self._compare_mode = False
        self.btn_compare.setText("对比")

    # ═══════════════════════════════════════════
    #  AI 处理
    # ═══════════════════════════════════════════

    def _on_ai_process(self):
        if self._is_processing:
            self._show_error("正在处理中，请等待完成")
            return

        text = self.input_editor.text()
        if not text.strip():
            self._show_error("请先在左侧输入文本")
            return

        model = self.model_combo.currentText().strip()

        ep = self.config.get_default_endpoint()
        if not ep:
            self._show_error("未配置 API 端点，请先在全局设置中添加")
            return

        system_prompt = get_instruction_prompt(self.instruction_combo.currentText())
        if not system_prompt:
            self._show_error(f"未知指令: {self.instruction_combo.currentText()}")
            return

        self._set_processing_state(True)
        if self._compare_mode:
            self._exit_compare_mode()
        self.output_editor.clear()

        # 分段
        try:
            seg_size = int(self.segment_input.text().strip())
        except ValueError:
            seg_size = DEFAULT_SEGMENT_SIZE
        segments = TextProcessor.split_into_segments(text, seg_size)

        self._seg_worker = AISegmentWorker(
            ep.base_url, ep.api_key, model,
            segments, system_prompt, max(self.config.timeout, 180),
        )
        self._seg_worker.progress.connect(self._on_seg_progress)
        self._seg_worker.chunk_ready.connect(self._on_stream_chunk)
        self._seg_worker.finished.connect(self._on_seg_finished)
        self._seg_worker.start()

    def _on_stream_chunk(self, chunk: str):
        self.output_editor.appendText(chunk)

    def _on_process_finished(self, ok: bool, msg: str):
        self._set_processing_state(False)
        if ok:
            self._save_rewrite_record()
        elif msg:
            self._show_error(f"处理失败: {msg}")

    def _on_seg_progress(self, current: int, total: int):
        self.btn_process.setText(f"处理中... {current}/{total}")

    def _on_seg_finished(self, ok: bool, msg: str):
        self._set_processing_state(False)
        if ok:
            self._save_rewrite_record()
            if msg:
                self._show_info("提示", msg)
        elif msg:
            self._show_error(f"处理失败: {msg}")

    def _set_processing_state(self, processing: bool):
        self._is_processing = processing
        self.btn_process.setEnabled(not processing)
        self.btn_process.setText("处理中..." if processing else "AI一键处理")

    # ═══════════════════════════════════════════
    #  改文记录自动保存
    # ═══════════════════════════════════════════

    def _save_rewrite_record(self):
        """自动保存改文记录"""
        if not self.config.auto_save_records:
            return
        try:
            original = self.input_editor.text()
            modified = self.output_editor.text()
            record = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "instruction": self.instruction_combo.currentText(),
                "model": self.model_combo.currentText().strip(),
                "original_chars": count_characters(original),
                "modified_chars": count_characters(modified),
                "original": original[:500],
                "modified": modified[:500],
            }
            save_dir = rewrite_history_dir()
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            (save_dir / filename).write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ═══════════════════════════════════════════
    #  辅助
    # ═══════════════════════════════════════════

    def _show_error(self, msg: str):
        InfoBar.error(
            title="提示", content=msg,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000, parent=self,
        )

    def _show_info(self, title: str, msg: str):
        InfoBar.info(
            title=title, content=msg,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000, parent=self,
        )
