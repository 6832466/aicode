import json
import logging
import csv
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import QHeaderView, QFileDialog, QTableView, QMessageBox
from PySide6.QtGui import QColor
from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, StrongBodyLabel,
    PushButton, ComboBox, TableWidget, LineEdit,
    InfoBar, InfoBarPosition, MessageBoxBase, SubtitleLabel,
    CheckBox, LineEdit,
)

from app.config import FREE_MODELS, MODEL_TYPE_NAMES, models_config_path, PRESET_COMBOS, load_groups, save_groups, short_model_name, get_model_type
from app.models import ModelConfig, ModelType, load_models_config, save_models_config, get_default_models
from ui.widgets.log_widget import LogWidget

logger = logging.getLogger(__name__)


class ModelsTableModel(QAbstractTableModel):
    HEADERS = ["启用", "模型名称", "模型ID", "类型", "优先级", "分组", "备注"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[ModelConfig] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None

        model = self._data[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return None  # Checkbox handled separately
            elif col == 1:
                return model.name
            elif col == 2:
                return model.model_id
            elif col == 3:
                return model.model_type.display_name
            elif col == 4:
                return "★" * model.priority
            elif col == 5:
                return ", ".join(model.groups) if model.groups else "-"
            elif col == 6:
                return model.notes

        if role == Qt.CheckStateRole and col == 0:
            return Qt.Checked if model.enabled else Qt.Unchecked

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or index.row() >= len(self._data):
            return False

        model = self._data[index.row()]
        col = index.column()

        if role == Qt.CheckStateRole and col == 0:
            model.enabled = value == Qt.Checked
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True

        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0:
            flags |= Qt.ItemIsUserCheckable
        return flags

    def set_data(self, data: list[ModelConfig]):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def get_model(self, row: int) -> ModelConfig | None:
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def update_model(self, row: int, model: ModelConfig):
        if 0 <= row < len(self._data):
            self._data[row] = model
            self.dataChanged.emit(self.index(row, 0), self.index(row, 6))

    def add_model(self, model: ModelConfig):
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append(model)
        self.endInsertRows()

    def remove_model(self, row: int):
        if 0 <= row < len(self._data):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._data.pop(row)
            self.endRemoveRows()

    def get_all(self) -> list[ModelConfig]:
        return self._data.copy()


class ModelEditDialog(MessageBoxBase):
    """Dialog for adding or editing a model"""

    def __init__(self, parent=None, model: ModelConfig = None, groups: list[str] = None):
        self._edit_model = model
        self._groups = groups or []
        super().__init__(parent)
        self._init_ui()
        if model:
            self._load_model(model)

    def _init_ui(self):
        from PySide6.QtWidgets import QVBoxLayout, QGridLayout, QCheckBox

        layout = QVBoxLayout(self.widget)
        layout.setSpacing(12)

        title = "编辑模型" if self._edit_model else "添加模型"
        layout.addWidget(SubtitleLabel(title, self))

        form = QGridLayout()
        form.setSpacing(8)

        form.addWidget(BodyLabel("模型ID:"), 0, 0)
        self._model_id_edit = LineEdit()
        self._model_id_edit.setPlaceholderText("如: Qwen/Qwen2.5-7B-Instruct")
        form.addWidget(self._model_id_edit, 0, 1)

        form.addWidget(BodyLabel("显示名称:"), 1, 0)
        self._name_edit = LineEdit()
        self._name_edit.setPlaceholderText("自定义显示名称")
        form.addWidget(self._name_edit, 1, 1)

        form.addWidget(BodyLabel("模型类型:"), 2, 0)
        self._type_combo = ComboBox()
        self._type_combo.addItems(["大语言模型", "多模态模型", "图像模型"])
        form.addWidget(self._type_combo, 2, 1)

        form.addWidget(BodyLabel("优先级:"), 3, 0)
        self._priority_combo = ComboBox()
        self._priority_combo.addItems(["1 (最低)", "2", "3 (默认)", "4", "5 (最高)"])
        self._priority_combo.setCurrentIndex(2)
        form.addWidget(self._priority_combo, 3, 1)

        form.addWidget(BodyLabel("分组:"), 4, 0)
        self._groups_edit = LineEdit()
        self._groups_edit.setPlaceholderText("多个分组用逗号分隔，如: 日常,代码")
        form.addWidget(self._groups_edit, 4, 1)

        form.addWidget(BodyLabel("备注:"), 5, 0)
        self._notes_edit = LineEdit()
        self._notes_edit.setPlaceholderText("可选")
        form.addWidget(self._notes_edit, 5, 1)

        layout.addLayout(form)

    def _load_model(self, model: ModelConfig):
        self._model_id_edit.setText(model.model_id)
        self._name_edit.setText(model.name)
        self._type_combo.setCurrentIndex(
            {"llm": 0, "multimodal": 1, "image": 2}.get(model.model_type.value, 0)
        )
        self._priority_combo.setCurrentIndex(model.priority - 1)
        self._groups_edit.setText(", ".join(model.groups))
        self._notes_edit.setText(model.notes)

    def get_model(self) -> ModelConfig | None:
        model_id = self._model_id_edit.text().strip()
        if not model_id:
            return None

        name = self._name_edit.text().strip() or short_model_name(model_id)
        type_map = {
            0: ModelType.LLM,
            1: ModelType.MULTIMODAL,
            2: ModelType.IMAGE,
        }
        groups_str = self._groups_edit.text().strip()
        groups = [g.strip() for g in groups_str.split(",") if g.strip()] if groups_str else []

        return ModelConfig(
            model_id=model_id,
            name=name,
            model_type=type_map[self._type_combo.currentIndex()],
            priority=self._priority_combo.currentIndex() + 1,
            groups=groups,
            notes=self._notes_edit.text().strip(),
        )


class ModelsPage(ScrollArea):
    models_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modelsPage")
        self._groups: list[str] = []
        self._all_models: list[ModelConfig] = []
        self._init_ui()
        self._load_models()
        self._load_groups()

    def _init_ui(self):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout

        container = QWidget()
        self.setWidget(container)
        self.setWidgetResizable(True)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("模型管理"))
        header.addStretch()

        # Preset combo
        self._preset_combo = ComboBox()
        self._preset_combo.addItem("预设组合")
        for name in PRESET_COMBOS.keys():
            self._preset_combo.addItem(name)
        self._preset_combo.setFixedWidth(120)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        header.addWidget(self._preset_combo)

        self._btn_add = PushButton("添加模型")
        self._btn_add.setFixedWidth(90)
        self._btn_add.clicked.connect(self._add_model)
        header.addWidget(self._btn_add)

        self._btn_import = PushButton("导入")
        self._btn_import.setFixedWidth(60)
        self._btn_import.clicked.connect(self._import_models)
        header.addWidget(self._btn_import)

        self._btn_export = PushButton("导出")
        self._btn_export.setFixedWidth(60)
        self._btn_export.clicked.connect(self._export_models)
        header.addWidget(self._btn_export)

        layout.addLayout(header)

        # Group management
        group_layout = QHBoxLayout()
        group_layout.addWidget(BodyLabel("分组筛选:"))
        self._group_filter = ComboBox()
        self._group_filter.addItem("全部分组")
        self._group_filter.setFixedWidth(150)
        self._group_filter.currentIndexChanged.connect(self._on_group_filter_changed)
        group_layout.addWidget(self._group_filter)

        self._btn_new_group = PushButton("新建分组")
        self._btn_new_group.setFixedWidth(80)
        self._btn_new_group.clicked.connect(self._new_group)
        group_layout.addWidget(self._btn_new_group)

        self._btn_delete_group = PushButton("删除分组")
        self._btn_delete_group.setFixedWidth(80)
        self._btn_delete_group.clicked.connect(self._delete_group)
        group_layout.addWidget(self._btn_delete_group)

        group_layout.addStretch()
        layout.addLayout(group_layout)

        # Batch operations
        batch_layout = QHBoxLayout()
        self._btn_enable_all = PushButton("全部启用")
        self._btn_enable_all.setFixedWidth(80)
        self._btn_enable_all.clicked.connect(self._enable_all)
        batch_layout.addWidget(self._btn_enable_all)

        self._btn_disable_all = PushButton("全部禁用")
        self._btn_disable_all.setFixedWidth(80)
        self._btn_disable_all.clicked.connect(self._disable_all)
        batch_layout.addWidget(self._btn_disable_all)

        self._btn_edit = PushButton("编辑选中")
        self._btn_edit.setFixedWidth(80)
        self._btn_edit.clicked.connect(self._edit_selected)
        batch_layout.addWidget(self._btn_edit)

        self._btn_delete = PushButton("删除选中")
        self._btn_delete.setFixedWidth(80)
        self._btn_delete.clicked.connect(self._delete_selected)
        batch_layout.addWidget(self._btn_delete)

        self._btn_load_default = PushButton("加载默认")
        self._btn_load_default.setFixedWidth(80)
        self._btn_load_default.clicked.connect(self._load_default)
        batch_layout.addWidget(self._btn_load_default)

        batch_layout.addStretch()

        # Clipboard import and batch priority
        self._btn_clipboard = PushButton("从剪贴板导入")
        self._btn_clipboard.setFixedWidth(100)
        self._btn_clipboard.clicked.connect(self._import_from_clipboard)
        batch_layout.addWidget(self._btn_clipboard)

        self._btn_set_priority = PushButton("批量设置优先级")
        self._btn_set_priority.setFixedWidth(100)
        self._btn_set_priority.clicked.connect(self._batch_set_priority)
        batch_layout.addWidget(self._btn_set_priority)

        layout.addLayout(batch_layout)

        # Table
        table_card = CardWidget()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(8, 8, 8, 8)

        self._table = QTableView()
        self._model = ModelsTableModel()
        self._table.setModel(self._model)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._on_table_double_clicked)
        self._table.setStyleSheet(
            "QTableView { background-color: #FAFAFA; gridline-color: #E0E0E0; }"
        )
        table_layout.addWidget(self._table)

        layout.addWidget(table_card)

        # Log
        self._log_widget = LogWidget()
        layout.addWidget(self._log_widget)

    def _load_groups(self):
        self._groups = load_groups()
        self._update_group_filter()

    def _update_group_filter(self):
        self._group_filter.clear()
        self._group_filter.addItem("全部分组")
        for group in self._groups:
            self._group_filter.addItem(group)

    def _new_group(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "新建分组", "分组名称:")
        if ok and name.strip():
            name = name.strip()
            if name not in self._groups:
                self._groups.append(name)
                save_groups(self._groups)
                self._update_group_filter()
                self._log_widget.info(f"已创建分组: {name}")

    def _delete_group(self):
        if self._group_filter.currentIndex() == 0:
            InfoBar.warning("请选择要删除的分组", parent=self)
            return
        group = self._group_filter.currentText()
        btn = QMessageBox.question(
            self, "确认删除",
            f"确定要删除分组 '{group}' 吗？模型不会被删除，只是从该分组移除。",
            QMessageBox.Yes | QMessageBox.No
        )
        if btn == QMessageBox.Yes:
            self._groups.remove(group)
            save_groups(self._groups)
            for m in self._all_models:
                if group in m.groups:
                    m.groups.remove(group)
            self._save_models()
            self._update_group_filter()
            self._log_widget.info(f"已删除分组: {group}")

    def _on_group_filter_changed(self, index: int):
        self._apply_filter()

    def _load_models(self):
        models = load_models_config()
        if models:
            self._all_models = models
            self._apply_filter()
            self._log_widget.info(f"已加载 {len(models)} 个模型配置")
        else:
            self._log_widget.info("暂无模型配置，点击'加载默认'添加")

    def _apply_filter(self):
        """Filter models by selected group and update table."""
        group = self._group_filter.currentText()
        if self._group_filter.currentIndex() <= 0 or group == "全部分组":
            self._model.set_data(self._all_models)
        else:
            filtered = [m for m in self._all_models if group in m.groups]
            self._model.set_data(filtered)

    def _save_models(self):
        save_models_config(self._all_models)
        self._log_widget.info(f"已保存 {len(self._all_models)} 个模型配置")
        self.models_changed.emit()
        self._apply_filter()

    def _add_model(self):
        dlg = ModelEditDialog(self, groups=self._groups)
        if dlg.exec():
            model = dlg.get_model()
            if model:
                self._all_models.append(model)
                self._save_models()

    def _edit_selected(self):
        rows = self._table.selectedIndexes()
        if not rows:
            InfoBar.warning("请先选择模型", parent=self)
            return
        row = rows[0].row()
        self._edit_model(row)

    def _on_table_double_clicked(self, index):
        self._edit_model(index.row())

    def _edit_model(self, row: int):
        model = self._model.get_model(row)
        if model:
            dlg = ModelEditDialog(self, model=model, groups=self._groups)
            if dlg.exec():
                new_model = dlg.get_model()
                if new_model:
                    new_model.enabled = model.enabled
                    # Update in _all_models by matching model_id
                    for i, m in enumerate(self._all_models):
                        if m.model_id == model.model_id:
                            self._all_models[i] = new_model
                            break
                    self._save_models()

    def _import_models(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入模型配置", "", "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            if path.endswith(".csv"):
                models = []
                with open(path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        model_id = row.get("model_id", "").strip()
                        if not model_id:
                            continue
                        groups_str = row.get("groups", "")
                        groups = [g.strip() for g in groups_str.split(",") if g.strip()] if groups_str else []
                        model_type = row.get("type", "llm").lower()
                        models.append(ModelConfig(
                            model_id=model_id,
                            name=row.get("name", short_model_name(model_id)),
                            model_type=ModelType(model_type) if model_type in ("llm", "multimodal", "image") else ModelType.LLM,
                            enabled=row.get("enabled", "true").lower() == "true",
                            priority=int(row.get("priority", 3)),
                            groups=groups,
                            notes=row.get("notes", ""),
                        ))
            else:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                models = [ModelConfig.from_dict(m) for m in data]
            self._all_models = models
            self._save_models()
            InfoBar.success("导入成功", f"已导入 {len(models)} 个模型", parent=self)
        except Exception as e:
            InfoBar.error("导入失败", str(e), parent=self)
            logger.exception("导入模型配置失败")

    def _export_models(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出模型配置", "models.json", "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            models = self._all_models
            if path.endswith(".csv"):
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(["model_id", "name", "type", "enabled", "priority", "groups", "notes"])
                    for m in models:
                        writer.writerow([
                            m.model_id, m.name, m.model_type.value,
                            "true" if m.enabled else "false",
                            m.priority, ",".join(m.groups), m.notes
                        ])
            else:
                data = [m.to_dict() for m in models]
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            InfoBar.success("导出成功", f"已导出到 {path}", parent=self)
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self)

    def _enable_all(self):
        for model in self._all_models:
            model.enabled = True
        self._save_models()

    def _disable_all(self):
        for model in self._all_models:
            model.enabled = False
        self._save_models()

    def _delete_selected(self):
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()), reverse=True)
        if not rows:
            InfoBar.warning("请先选择模型", parent=self)
            return
        btn = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(rows)} 个模型吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if btn == QMessageBox.Yes:
            ids_to_delete = set()
            for row in rows:
                model = self._model.get_model(row)
                if model:
                    ids_to_delete.add(model.model_id)
            self._all_models = [m for m in self._all_models if m.model_id not in ids_to_delete]
            self._save_models()

    def _load_default(self):
        self._all_models = get_default_models()
        self._save_models()
        InfoBar.success("加载成功", f"已加载 {len(self._all_models)} 个默认模型", parent=self)

    def _on_preset_selected(self, index: int):
        if index == 0:  # "预设组合" placeholder
            return
        preset_name = self._preset_combo.currentText()
        if preset_name in PRESET_COMBOS:
            model_ids = PRESET_COMBOS[preset_name]
            models = []
            for model_id in model_ids:
                models.append(ModelConfig(
                    model_id=model_id,
                    name=short_model_name(model_id),
                    model_type=ModelType(get_model_type(model_id)),
                ))
            self._all_models = models
            self._save_models()
            InfoBar.success("加载成功", f"已加载 '{preset_name}' 组合", parent=self)
            self._preset_combo.setCurrentIndex(0)

    def get_enabled_models(self) -> list[ModelConfig]:
        """Return all enabled model configurations."""
        return [m for m in self._all_models if m.enabled]

    def get_groups(self) -> list[str]:
        """Return all available groups."""
        return self._groups.copy()

    def _import_from_clipboard(self):
        """Import models from clipboard (one model ID per line)."""
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if not text:
            InfoBar.warning("剪贴板为空", parent=self)
            return

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            InfoBar.warning("剪贴板中没有有效的模型ID", parent=self)
            return

        models = []
        for model_id in lines:
            models.append(ModelConfig(
                model_id=model_id,
                name=short_model_name(model_id),
                model_type=ModelType(get_model_type(model_id)),
            ))

        # Add to existing models
        existing_ids = {m.model_id for m in self._all_models}
        added = 0
        for m in models:
            if m.model_id not in existing_ids:
                self._all_models.append(m)
                existing_ids.add(m.model_id)
                added += 1

        self._save_models()
        InfoBar.success("导入成功", f"从剪贴板导入 {added} 个新模型", parent=self)
        self._log_widget.info(f"从剪贴板导入 {added} 个模型")

    def _batch_set_priority(self):
        """Batch set priority for selected models."""
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not rows:
            InfoBar.warning("请先选择模型", parent=self)
            return

        from PySide6.QtWidgets import QInputDialog
        priority, ok = QInputDialog.getInt(
            self, "批量设置优先级",
            "请输入优先级 (1-5):",
            value=3, min=1, max=5
        )
        if ok:
            selected_ids = set()
            for row in rows:
                model = self._model.get_model(row)
                if model:
                    selected_ids.add(model.model_id)
            for m in self._all_models:
                if m.model_id in selected_ids:
                    m.priority = priority
            self._save_models()
            InfoBar.success("设置成功", f"已设置 {len(rows)} 个模型优先级为 {priority}", parent=self)
            self._log_widget.info(f"批量设置优先级: {len(rows)} 个模型 → {priority}")
