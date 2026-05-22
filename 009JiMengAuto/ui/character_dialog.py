"""人物对照表弹窗"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog,
)
from qfluentwidgets import (
    PrimaryPushButton, PushButton,
    BodyLabel, CaptionLabel, InfoBar, CardWidget,
)

from core.material_matcher import MaterialMatcher
from data.models import MaterialType
from utils.helpers import infer_material_type


class CharacterDialog(QDialog):
    """人物对照表弹窗"""

    def __init__(self, material_matcher: MaterialMatcher, parent=None):
        super().__init__(parent)
        self.material_matcher = material_matcher

        self.setWindowTitle("人物对照表")
        self.resize(600, 400)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        central = CardWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题
        title_row = QHBoxLayout()
        title = BodyLabel("人物对照表")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        title_row.addWidget(title)
        title_row.addStretch()

        count_label = CaptionLabel(f"共 {len(self.material_matcher.get_all_materials())} 条素材")
        title_row.addWidget(count_label)

        self._btn_add = PrimaryPushButton("添加")
        self._btn_add.clicked.connect(self._on_add)
        title_row.addWidget(self._btn_add)
        layout.addLayout(title_row)

        # 表格
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["人物", "路径", "类型", "操作"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 100)
        self._table.setColumnWidth(2, 60)
        self._table.setColumnWidth(3, 120)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._table)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_close = PushButton("关闭")
        self._btn_close.clicked.connect(self.close)
        self._btn_save = PrimaryPushButton("保存")
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_close)
        btn_row.addWidget(self._btn_save)
        layout.addLayout(btn_row)

        outer.addWidget(central)
        self._refresh_table()

    def _refresh_table(self):
        """刷新表格"""
        materials = self.material_matcher.get_all_materials()
        self._table.setRowCount(len(materials))

        for i, m in enumerate(materials):
            self._table.setItem(i, 0, QTableWidgetItem(m.character_name))
            self._table.setItem(i, 1, QTableWidgetItem(m.file_path))
            self._table.setItem(i, 2, QTableWidgetItem(m.material_type.display()))

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)

            btn_edit = PushButton("编辑")
            btn_edit.clicked.connect(lambda checked, row=i: self._on_edit(row))
            btn_del = PushButton("删除")
            btn_del.clicked.connect(lambda checked, row=i: self._on_delete(row))

            btn_layout.addWidget(btn_edit)
            btn_layout.addWidget(btn_del)
            self._table.setCellWidget(i, 3, btn_widget)

    def _on_add(self):
        """添加素材"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择素材文件",
            "",
            "素材 (*.jpg *.jpeg *.png *.webp *.wav *.mp3 *.mp4 *.mov);;所有文件 (*.*)"
        )
        if not path:
            return

        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "输入人物名", "人物名字:")
        if not ok or not name.strip():
            return

        from data.models import CharacterMaterial
        mtype = infer_material_type(path)
        mat = CharacterMaterial(
            character_name=name.strip(),
            file_path=path,
            material_type=MaterialType(mtype),
        )
        # 添加到匹配器
        current = self.material_matcher.get_all_materials()
        current.append(mat)
        # 通过重新加载来更新（简易方式）
        self.material_matcher.load_materials(
            [{"人物名字": m.character_name, "引用名": m.file_path}
             for m in current]
        )
        self._refresh_table()

    def _on_edit(self, row: int):
        """编辑素材"""
        materials = self.material_matcher.get_all_materials()
        if row < 0 or row >= len(materials):
            return
        mat = materials[row]

        path, _ = QFileDialog.getOpenFileName(
            self, "选择新文件", str(mat.file_path),
            "素材 (*.jpg *.jpeg *.png *.webp *.wav *.mp3 *.mp4 *.mov);;所有文件 (*.*)"
        )
        if path:
            # 更新路径
            current = self.material_matcher.get_all_materials()
            current[row] = type(mat)(
                character_name=mat.character_name,
                file_path=path,
                material_type=MaterialType(infer_material_type(path)),
            )
            self.material_matcher.load_materials(
                [{"人物名字": m.character_name, "引用名": m.file_path}
                 for m in current]
            )
            self._refresh_table()

    def _on_delete(self, row: int):
        """删除素材"""
        materials = self.material_matcher.get_all_materials()
        if row < 0 or row >= len(materials):
            return
        current = list(materials)
        deleted = current.pop(row)
        self.material_matcher.load_materials(
            [{"人物名字": m.character_name, "引用名": m.file_path}
             for m in current]
        )
        self._refresh_table()
        InfoBar.info("已删除", f"已删除: {deleted.character_name}",
                     parent=self, duration=2000)

    def _on_save(self):
        """保存"""
        InfoBar.success("已保存", "人物对照表已更新",
                        parent=self, duration=2000)
        self.close()
