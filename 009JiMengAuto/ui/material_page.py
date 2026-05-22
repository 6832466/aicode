"""素材管理页面 - 即梦素材库"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QHeaderView,
    QAbstractItemView, QTableWidget, QTableWidgetItem, QFileDialog,
)
from qfluentwidgets import (
    TableWidget, CardWidget, PrimaryPushButton, PushButton,
    FluentIcon, InfoBar, BodyLabel, CaptionLabel, ComboBox,
    StrongBodyLabel, ScrollArea,
)

from core.material_matcher import MaterialMatcher
from data.models import MaterialType
from ui.widgets import StatCard
from utils.theme import THEME
from utils.helpers import format_file_size


class MaterialPage(QWidget):
    """素材管理页面"""

    def __init__(self, material_matcher: MaterialMatcher, parent=None):
        super().__init__(parent)
        self.material_matcher = material_matcher

        self._init_ui()
        self._refresh_table()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # ── 统计卡片行 ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        self._card_total = StatCard("总素材", 0, "📁", THEME["primary"])
        self._card_image = StatCard("图片", 0, "🖼️", THEME["success"])
        self._card_audio = StatCard("音频", 0, "🎵", THEME["warning"])
        self._card_video = StatCard("视频", 0, "🎬", THEME["danger"])
        for c in [self._card_total, self._card_image, self._card_audio, self._card_video]:
            stats_layout.addWidget(c)
        layout.addLayout(stats_layout)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._btn_import = PrimaryPushButton(FluentIcon.ADD, "导入素材表")
        self._btn_refresh = PushButton(FluentIcon.SYNC, "刷新")
        self._btn_clear = PushButton(FluentIcon.DELETE, "清空素材")

        # 筛选
        toolbar.addWidget(BodyLabel("筛选:"))
        self._filter_combo = ComboBox()
        self._filter_combo.addItems(["全部", "图片", "音频", "视频"])
        self._filter_combo.setCurrentIndex(0)
        self._filter_combo.setFixedWidth(100)
        toolbar.addWidget(self._filter_combo)

        toolbar.addWidget(self._btn_import)
        toolbar.addWidget(self._btn_refresh)
        toolbar.addStretch()
        toolbar.addWidget(self._btn_clear)
        layout.addLayout(toolbar)

        # ── 素材列表 ──
        self._table = TableWidget(self)
        self._table.setBorderRadius(8)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)

        columns = ["人物名", "素材类型", "文件路径", "文件大小", "状态", "操作"]
        self._table.setColumnCount(len(columns))
        self._table.setHorizontalHeaderLabels(columns)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 120)
        self._table.setColumnWidth(1, 80)
        self._table.setColumnWidth(3, 80)
        self._table.setColumnWidth(4, 80)
        self._table.setColumnWidth(5, 80)

        layout.addWidget(self._table)

        # 连接信号
        self._btn_import.clicked.connect(self._on_import)
        self._btn_refresh.clicked.connect(self._refresh_table)
        self._btn_clear.clicked.connect(self._on_clear)
        self._filter_combo.currentTextChanged.connect(self._on_filter)

    def _refresh_table(self):
        """刷新表格"""
        self._table.setRowCount(0)
        materials = self.material_matcher.get_all_materials()

        # 筛选
        filter_type = self._filter_combo.currentText()
        if filter_type != "全部":
            type_map = {"图片": "image", "音频": "audio", "视频": "video"}
            materials = [m for m in materials if m.material_type.value == type_map.get(filter_type, "")]

        for i, mat in enumerate(materials):
            self._table.insertRow(i)
            self._table.setItem(i, 0, self._cell(mat.character_name))
            self._table.setItem(i, 1, self._cell(mat.material_type.display()))

            # 文件路径截断显示
            path_text = mat.file_path
            if len(path_text) > 60:
                path_text = path_text[:60] + "..."
            self._table.setItem(i, 2, self._cell(path_text))

            size_text = format_file_size(mat.file_size) if mat.file_size > 0 else "--"
            self._table.setItem(i, 3, self._cell(size_text))

            # 状态
            status_text = "✓ 存在" if mat.exists else "✗ 缺失"
            status_color = THEME["success"] if mat.exists else THEME["danger"]
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(Qt.GlobalColor(status_color))
            self._table.setItem(i, 4, status_item)

            self._table.setItem(i, 5, self._cell("替换"))

        self._update_stats()

    def _cell(self, text: str):
        """创建表格单元格"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _update_stats(self):
        """更新统计"""
        materials = self.material_matcher.get_all_materials()
        self._card_total.set_value(len(materials))
        self._card_image.set_value(sum(1 for m in materials if m.material_type == MaterialType.IMAGE))
        self._card_audio.set_value(sum(1 for m in materials if m.material_type == MaterialType.AUDIO))
        self._card_video.set_value(sum(1 for m in materials if m.material_type == MaterialType.VIDEO))

    def _on_import(self):
        """导入素材表"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择素材表", "", "Excel (*.xlsx *.xls)"
        )
        if not path:
            return
        try:
            from data.excel_handler import read_character_excel
            data = read_character_excel(path)
            self.material_matcher.load_materials(data)
            self._refresh_table()
            InfoBar.success("导入成功", f"已导入 {len(data)} 条素材", parent=self, duration=3000)
        except Exception as e:
            InfoBar.error("导入失败", str(e), parent=self, duration=3000)

    def _on_clear(self):
        """清空素材"""
        self.material_matcher.load_materials([])
        self._refresh_table()
        InfoBar.success("已清空", "素材库已清空", parent=self, duration=2000)

    def _on_filter(self, text: str):
        """筛选变化"""
        self._refresh_table()
