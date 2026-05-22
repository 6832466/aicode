"""导入任务弹窗"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton, LineEdit,
    BodyLabel, CaptionLabel, InfoBar, CardWidget,
    ComboBox, StrongBodyLabel,
)

from core.task_manager import TaskManager
from core.material_matcher import MaterialMatcher
from data.excel_handler import read_prompt_excel, read_character_excel
from utils.theme import THEME


class ImportDialog(QDialog):
    """导入任务弹窗"""

    def __init__(self, task_manager: TaskManager,
                 material_matcher: MaterialMatcher, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.material_matcher = material_matcher
        self._prompt_data: list[dict] = []
        self._char_data: list[dict] = []

        self.setWindowTitle("导入任务")
        self.resize(640, 560)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {THEME['bg_dark']};
            }}
        """)

        self._init_ui()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题
        title = StrongBodyLabel("导入任务")
        title.setStyleSheet(f"font-size: 16px;")
        layout.addWidget(title)

        # 提示词表路径
        prompt_row = QHBoxLayout()
        prompt_row.addWidget(BodyLabel("提示词表:"))
        self._prompt_path = LineEdit()
        self._prompt_path.setPlaceholderText("选择提示词Excel文件...")
        self._prompt_path.setFixedWidth(320)
        prompt_row.addWidget(self._prompt_path)
        self._btn_browse_prompt = PushButton("浏览")
        self._btn_browse_prompt.clicked.connect(lambda: self._browse_file("prompt"))
        prompt_row.addWidget(self._btn_browse_prompt)
        layout.addLayout(prompt_row)

        # 人物对照表路径
        char_row = QHBoxLayout()
        char_row.addWidget(BodyLabel("人物对照表:"))
        self._char_path = LineEdit()
        self._char_path.setPlaceholderText("选择人物对照表Excel文件...")
        self._char_path.setFixedWidth(320)
        char_row.addWidget(self._char_path)
        self._btn_browse_char = PushButton("浏览")
        self._btn_browse_char.clicked.connect(lambda: self._browse_file("character"))
        char_row.addWidget(self._btn_browse_char)
        layout.addLayout(char_row)

        # 预览区域
        preview_card = CardWidget(self)
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)

        preview_title = BodyLabel("导入预览")
        preview_title.setStyleSheet(f"font-size: 13px; font-weight: 500;")
        preview_layout.addWidget(preview_title)

        self._preview_label = CaptionLabel("请先选择文件")
        self._preview_label.setStyleSheet(f"color: {THEME['text_secondary']};")
        preview_layout.addWidget(self._preview_label)

        layout.addWidget(preview_card)

        # 名称映射
        mapping_title = BodyLabel("名称映射（提示词人名 → 素材人名）:")
        mapping_title.setStyleSheet(f"font-size: 13px;")
        layout.addWidget(mapping_title)

        self._mapping_table = QTableWidget()
        self._mapping_table.setColumnCount(2)
        self._mapping_table.setHorizontalHeaderLabels(["提示词中的人名", "映射到素材名"])
        self._mapping_table.horizontalHeader().setStretchLastSection(True)
        self._mapping_table.setMinimumHeight(120)
        self._mapping_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {THEME['bg_card']};
                border: 1px solid {THEME['border']};
                border-radius: 8px;
            }}
            QHeaderView::section {{
                background-color: {THEME['bg_dark']};
                color: {THEME['text_secondary']};
                border: none;
                padding: 6px 8px;
            }}
        """)
        layout.addWidget(self._mapping_table)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_cancel = PushButton("取消")
        self._btn_cancel.clicked.connect(self.close)
        self._btn_import = PrimaryPushButton("确认导入")
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._on_import)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_import)
        layout.addLayout(btn_row)

    def _browse_file(self, field: str):
        """浏览文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "", "Excel (*.xlsx *.xls)"
        )
        if not path:
            return
        if field == "prompt":
            self._prompt_path.setText(path)
        else:
            self._char_path.setText(path)
        self._update_preview()

    def _update_preview(self):
        """更新导入预览"""
        prompt_path = self._prompt_path.text()
        char_path = self._char_path.text()

        if not prompt_path:
            self._preview_label.setText("请先选择提示词表")
            self._btn_import.setEnabled(False)
            return

        try:
            prompt_data = read_prompt_excel(prompt_path)
            self._prompt_data = prompt_data

            total_duration = sum(r["duration"] for r in prompt_data)
            preview = f"• 检测到 {len(prompt_data)} 个任务\n"

            if char_path:
                try:
                    char_data = read_character_excel(char_path)
                    self._char_data = char_data
                    self.material_matcher.load_materials(char_data)
                    preview += f"• 检测到 {len(char_data)} 个素材关联\n"

                    # 扫描未匹配的人名
                    unmatched = set()
                    for r in prompt_data:
                        names = self.material_matcher.find_unmatched_names(r["prompt"])
                        unmatched.update(names)

                    # 显示名称映射
                    self._show_mappings(unmatched)
                    if unmatched:
                        preview += f"• 有 {len(unmatched)} 个名称需要映射"

                except Exception as e:
                    preview += f"⚠ 人物表读取失败: {e}"

            preview += f"• 总时长：{total_duration} 秒"
            self._preview_label.setText(preview)
            self._btn_import.setEnabled(True)

        except Exception as e:
            self._preview_label.setText(f"读取失败: {e}")
            self._btn_import.setEnabled(False)

    def _show_mappings(self, unmatched: set[str]):
        """显示名称映射编辑区域"""
        existing = self.material_matcher.get_name_mappings()
        all_material_names = [m.character_name for m in self.material_matcher.get_all_materials()]

        names_to_map = list(unmatched)

        self._mapping_table.setRowCount(len(names_to_map))
        for i, name in enumerate(names_to_map):
            # 源名
            src_item = QTableWidgetItem(name)
            src_item.setFlags(Qt.ItemIsEnabled)
            src_item.setTextAlignment(Qt.AlignCenter)
            self._mapping_table.setItem(i, 0, src_item)

            # 目标名（下拉选择）
            combo = ComboBox()
            combo.addItem("（不映射）")
            for mn in all_material_names:
                combo.addItem(mn)
            # 如果已有映射，选中它
            mapped = existing.get(name, "")
            if mapped:
                idx = combo.findText(mapped)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self._mapping_table.setCellWidget(i, 1, combo)

    def _on_import(self):
        """执行导入"""
        prompt_path = self._prompt_path.text()
        char_path = self._char_path.text()

        # 保存名称映射
        mappings = {}
        for i in range(self._mapping_table.rowCount()):
            src_item = self._mapping_table.item(i, 0)
            if not src_item:
                continue
            combo = self._mapping_table.cellWidget(i, 1)
            if combo and combo.currentText() and combo.currentText() != "（不映射）":
                mappings[src_item.text()] = combo.currentText()

        if mappings:
            self.material_matcher.save_name_mappings(mappings)

        # 导入任务
        self.task_manager.import_from_excel(
            prompt_path, char_path,
            matcher=self.material_matcher if char_path else None,
        )

        InfoBar.success("导入成功", "已导入任务到队列", parent=self, duration=3000)
        self.close()