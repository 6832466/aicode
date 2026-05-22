import json
import logging
import uuid
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QHeaderView,
    QTreeView, QFileDialog, QMessageBox, QApplication
)
from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, StrongBodyLabel,
    PushButton, ComboBox, LineEdit, TextEdit, SpinBox,
    InfoBar, InfoBarPosition, TreeWidget,
    SubtitleLabel,
)
from PySide6.QtWidgets import QTreeWidgetItem

from app.config import templates_path, usage_stats_path, short_model_name
from app.models import PromptTemplate, UsageStats
from ui.widgets.log_widget import LogWidget

logger = logging.getLogger(__name__)


class TemplatesTreeModel(QAbstractItemModel):
    """Tree model for prompt templates organized by category."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict[str, list[PromptTemplate]] = {}
        self._categories: list[str] = []

    def rowCount(self, parent=QModelIndex()):
        if not parent.isValid():
            return len(self._categories)
        if parent.internalId() == 0:  # Category node
            cat = self._categories[parent.row()]
            return len(self._data.get(cat, []))
        return 0

    def columnCount(self, parent=QModelIndex()):
        return 1

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            if not index.parent().isValid():  # Category
                return self._categories[index.row()]
            else:  # Template
                cat = self._categories[index.parent().row()]
                templates = self._data.get(cat, [])
                if index.row() < len(templates):
                    return templates[index.row()].name
        return None

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, 0)
        return self.createIndex(row, column, parent.row() + 1)

    def parent(self, index):
        if not index.isValid() or index.internalId() == 0:
            return QModelIndex()
        cat_idx = int(index.internalId()) - 1
        return self.createIndex(cat_idx, 0, 0)

    def set_data(self, templates: list[PromptTemplate]):
        self.beginResetModel()
        self._data = {}
        self._categories = []
        for t in templates:
            if t.category not in self._data:
                self._data[t.category] = []
                self._categories.append(t.category)
            self._data[t.category].append(t)
        self.endResetModel()

    def get_template(self, index: QModelIndex) -> PromptTemplate | None:
        if not index.isValid():
            return None
        if not index.parent().isValid():
            return None
        cat = self._categories[index.parent().row()]
        templates = self._data.get(cat, [])
        if index.row() < len(templates):
            return templates[index.row()]
        return None

    def get_all(self) -> list[PromptTemplate]:
        result = []
        for cat in self._categories:
            result.extend(self._data.get(cat, []))
        return result


class ToolsPage(ScrollArea):
    """Auxiliary tools page with templates, token counter, and usage stats."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolsPage")
        self._init_ui()
        self._load_templates()
        self._load_usage_stats()

    def _init_ui(self):
        container = QWidget()
        self.setWidget(container)
        self.setWidgetResizable(True)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Left panel: Templates
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        left_header = QHBoxLayout()
        left_header.addWidget(StrongBodyLabel("Prompt 模板"))
        left_header.addStretch()

        self._btn_new_template = PushButton("新建")
        self._btn_new_template.setFixedWidth(60)
        self._btn_new_template.clicked.connect(self._new_template)
        left_header.addWidget(self._btn_new_template)

        self._btn_edit_template = PushButton("编辑")
        self._btn_edit_template.setFixedWidth(60)
        self._btn_edit_template.clicked.connect(self._edit_template)
        left_header.addWidget(self._btn_edit_template)

        self._btn_delete_template = PushButton("删除")
        self._btn_delete_template.setFixedWidth(60)
        self._btn_delete_template.clicked.connect(self._delete_template)
        left_header.addWidget(self._btn_delete_template)

        left_layout.addLayout(left_header)

        # Template tree
        template_card = CardWidget()
        template_layout = QVBoxLayout(template_card)
        template_layout.setContentsMargins(8, 8, 8, 8)

        self._template_tree = QTreeView()
        self._template_model = TemplatesTreeModel()
        self._template_tree.setModel(self._template_model)
        self._template_tree.setHeaderHidden(True)
        self._template_tree.setFixedWidth(250)
        self._template_tree.clicked.connect(self._on_template_selected)
        template_layout.addWidget(self._template_tree)

        left_layout.addWidget(template_card)

        # Template content display
        self._template_content = TextEdit()
        self._template_content.setReadOnly(True)
        self._template_content.setPlaceholderText("选择模板查看内容")
        self._template_content.setFixedHeight(150)
        left_layout.addWidget(self._template_content)

        # Copy button
        self._btn_copy = PushButton("复制到剪贴板")
        self._btn_copy.setFixedWidth(120)
        self._btn_copy.clicked.connect(self._copy_template)
        left_layout.addWidget(self._btn_copy)

        layout.addWidget(left_panel)

        # Right panel: Token counter and usage stats
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(16)

        # Token counter
        token_card = CardWidget()
        token_layout = QVBoxLayout(token_card)
        token_layout.setContentsMargins(16, 16, 16, 16)
        token_layout.setSpacing(12)

        token_header = QHBoxLayout()
        token_header.addWidget(StrongBodyLabel("Token 计数器"))
        token_header.addStretch()
        right_layout.addLayout(token_header)

        self._token_input = TextEdit()
        self._token_input.setPlaceholderText("输入文本，自动计算 token 数量")
        self._token_input.setMaximumHeight(120)
        self._token_input.textChanged.connect(self._update_token_count)
        token_layout.addWidget(self._token_input)

        token_result = QHBoxLayout()
        token_result.addWidget(BodyLabel("Token 数:"))
        self._token_count_label = StrongBodyLabel("0")
        token_result.addWidget(self._token_count_label)
        token_result.addWidget(BodyLabel("(估算，实际可能有差异)"))
        token_result.addStretch()
        token_layout.addLayout(token_result)

        right_layout.addWidget(token_card)

        # Usage stats
        stats_card = CardWidget()
        stats_layout = QVBoxLayout(stats_card)
        stats_layout.setContentsMargins(16, 16, 16, 16)
        stats_layout.setSpacing(12)

        stats_header = QHBoxLayout()
        stats_header.addWidget(StrongBodyLabel("使用统计"))
        stats_header.addStretch()

        self._btn_refresh_stats = PushButton("刷新")
        self._btn_refresh_stats.setFixedWidth(60)
        self._btn_refresh_stats.clicked.connect(self._load_usage_stats)
        stats_header.addWidget(self._btn_refresh_stats)

        self._btn_export_stats = PushButton("导出")
        self._btn_export_stats.setFixedWidth(60)
        self._btn_export_stats.clicked.connect(self._export_stats)
        stats_header.addWidget(self._btn_export_stats)

        stats_layout.addLayout(stats_header)

        # Stats display (simple list for now)
        self._stats_display = QWidget()
        self._stats_grid = QGridLayout(self._stats_display)
        self._stats_grid.setSpacing(8)
        stats_layout.addWidget(self._stats_display)

        right_layout.addWidget(stats_card)

        # API Debug Tool
        api_card = CardWidget()
        api_layout = QVBoxLayout(api_card)
        api_layout.setContentsMargins(16, 16, 16, 16)
        api_layout.setSpacing(12)

        api_header = QHBoxLayout()
        api_header.addWidget(StrongBodyLabel("API 调试工具"))
        api_header.addStretch()

        self._btn_send_api = PushButton("发送请求")
        self._btn_send_api.setFixedWidth(80)
        self._btn_send_api.clicked.connect(self._send_api_request)
        api_header.addWidget(self._btn_send_api)

        api_layout.addLayout(api_header)

        # Endpoint
        endpoint_layout = QHBoxLayout()
        endpoint_layout.addWidget(BodyLabel("接口:"))
        self._api_endpoint = ComboBox()
        self._api_endpoint.addItems([
            "https://api-inference.modelscope.cn/v1/chat/completions",
            "https://api-inference.modelscope.cn/v1/embeddings",
            "https://api-inference.modelscope.cn/v1/images/generations",
        ])
        self._api_endpoint.setFixedWidth(400)
        endpoint_layout.addWidget(self._api_endpoint)
        endpoint_layout.addStretch()
        api_layout.addLayout(endpoint_layout)

        # Request body
        api_layout.addWidget(BodyLabel("请求体 (JSON):"))
        self._api_body = TextEdit()
        self._api_body.setPlaceholderText('{\n  "model": "Qwen/Qwen2.5-7B-Instruct",\n  "messages": [{"role": "user", "content": "Hello"}]\n}')
        self._api_body.setMaximumHeight(120)
        api_layout.addWidget(self._api_body)

        # Response
        api_layout.addWidget(BodyLabel("响应结果:"))
        self._api_response = TextEdit()
        self._api_response.setReadOnly(True)
        self._api_response.setMaximumHeight(100)
        self._api_response.setStyleSheet(
            "QTextEdit { background-color: #1E1E2E; color: #CDD6F4; font-family: Consolas, monospace; }"
        )
        api_layout.addWidget(self._api_response)

        # Timing
        self._api_timing_label = BodyLabel("耗时: --")
        api_layout.addWidget(self._api_timing_label)

        right_layout.addWidget(api_card)
        right_layout.addStretch()

        layout.addWidget(right_panel)

        # Log at bottom
        self._log_widget = LogWidget()
        layout.addWidget(self._log_widget)

    def _load_templates(self):
        path = templates_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                templates = [PromptTemplate.from_dict(t) for t in data]
                self._template_model.set_data(templates)
                self._log_widget.info(f"已加载 {len(templates)} 个模板")
            except Exception as e:
                logger.warning(f"Failed to load templates: {e}")
                self._template_model.set_data([])

    def _save_templates(self):
        path = templates_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        templates = self._template_model.get_all()
        data = [t.to_dict() for t in templates]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _on_template_selected(self, index):
        template = self._template_model.get_template(index)
        if template:
            self._template_content.setPlainText(template.content)

    def _new_template(self):
        from qfluentwidgets import MessageBoxBase

        class NewTemplateDialog(MessageBoxBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                self._init_ui()

            def _init_ui(self):
                layout_v = QVBoxLayout(self.widget)
                layout_v.setSpacing(12)

                layout_v.addWidget(SubtitleLabel("新建模板", self))

                form = QGridLayout()
                form.setSpacing(8)

                form.addWidget(BodyLabel("名称:"), 0, 0)
                self._name_edit = LineEdit()
                form.addWidget(self._name_edit, 0, 1)

                form.addWidget(BodyLabel("分类:"), 1, 0)
                self._category_edit = LineEdit()
                self._category_edit.setText("默认")
                form.addWidget(self._category_edit, 1, 1)

                form.addWidget(BodyLabel("内容:"), 2, 0)
                self._content_edit = TextEdit()
                self._content_edit.setFixedHeight(150)
                form.addWidget(self._content_edit, 2, 1)

                layout_v.addLayout(form)

            def get_template(self) -> PromptTemplate | None:
                name = self._name_edit.text().strip()
                content = self._content_edit.toPlainText().strip()
                if not name or not content:
                    return None
                return PromptTemplate(
                    id=str(uuid.uuid4())[:8],
                    name=name,
                    category=self._category_edit.text().strip() or "默认",
                    content=content,
                )

        dlg = NewTemplateDialog(self)
        if dlg.exec():
            template = dlg.get_template()
            if template:
                templates = self._template_model.get_all()
                templates.append(template)
                self._template_model.set_data(templates)
                self._save_templates()
                InfoBar.success("创建成功", f"模板 '{template.name}' 已保存", parent=self)
                self._log_widget.info(f"新建模板: {template.name}")

    def _edit_template(self):
        index = self._template_tree.currentIndex()
        template = self._template_model.get_template(index)
        if not template:
            InfoBar.warning("请先选择模板", parent=self)
            return

        from qfluentwidgets import MessageBoxBase

        class EditTemplateDialog(MessageBoxBase):
            def __init__(self, parent=None, tmpl=None):
                self._tmpl = tmpl
                super().__init__(parent)
                self._init_ui()
                if tmpl:
                    self._name_edit.setText(tmpl.name)
                    self._category_edit.setText(tmpl.category)
                    self._content_edit.setPlainText(tmpl.content)

            def _init_ui(self):
                layout_v = QVBoxLayout(self.widget)
                layout_v.setSpacing(12)

                layout_v.addWidget(SubtitleLabel("编辑模板", self))

                form = QGridLayout()
                form.setSpacing(8)

                form.addWidget(BodyLabel("名称:"), 0, 0)
                self._name_edit = LineEdit()
                form.addWidget(self._name_edit, 0, 1)

                form.addWidget(BodyLabel("分类:"), 1, 0)
                self._category_edit = LineEdit()
                form.addWidget(self._category_edit, 1, 1)

                form.addWidget(BodyLabel("内容:"), 2, 0)
                self._content_edit = TextEdit()
                self._content_edit.setFixedHeight(150)
                form.addWidget(self._content_edit, 2, 1)

                layout_v.addLayout(form)

            def get_template(self) -> PromptTemplate | None:
                name = self._name_edit.text().strip()
                content = self._content_edit.toPlainText().strip()
                if not name or not content:
                    return None
                self._tmpl.name = name
                self._tmpl.category = self._category_edit.text().strip() or "默认"
                self._tmpl.content = content
                return self._tmpl

        dlg = EditTemplateDialog(self, tmpl=template)
        if dlg.exec():
            dlg.get_template()
            self._template_model.set_data(self._template_model.get_all())
            self._save_templates()
            InfoBar.success("保存成功", parent=self)

    def _delete_template(self):
        index = self._template_tree.currentIndex()
        template = self._template_model.get_template(index)
        if not template:
            InfoBar.warning("请先选择模板", parent=self)
            return

        btn = QMessageBox.question(
            self, "确认删除",
            f"确定要删除模板 '{template.name}' 吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if btn == QMessageBox.Yes:
            templates = self._template_model.get_all()
            templates = [t for t in templates if t.id != template.id]
            self._template_model.set_data(templates)
            self._save_templates()
            self._log_widget.info(f"已删除模板: {template.name}")

    def _copy_template(self):
        index = self._template_tree.currentIndex()
        template = self._template_model.get_template(index)
        if template:
            clipboard = QApplication.clipboard()
            clipboard.setText(template.content)
            InfoBar.success("已复制", f"模板 '{template.name}' 已复制到剪贴板", parent=self)

    def _update_token_count(self):
        text = self._token_input.toPlainText()
        if not text:
            self._token_count_label.setText("0")
            return

        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            count = len(enc.encode(text))
            self._token_count_label.setText(str(count))
        except ImportError:
            # Fallback: rough estimate (1 token ≈ 4 chars for Chinese, 0.75 words for English)
            char_count = len(text)
            word_count = len(text.split())
            # Rough estimate
            estimate = max(char_count // 3, word_count // 0.75)
            self._token_count_label.setText(f"~{int(estimate)}")

    def _load_usage_stats(self):
        path = usage_stats_path()
        if not path.exists():
            self._log_widget.info("暂无使用统计数据")
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stats = [UsageStats.from_dict(s) for s in data]

            # Clear existing
            while self._stats_grid.count():
                item = self._stats_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            # Aggregate by model
            model_totals: dict[str, UsageStats] = {}
            for s in stats:
                if s.model_id not in model_totals:
                    model_totals[s.model_id] = UsageStats(
                        date="合计",
                        model_id=s.model_id,
                    )
                model_totals[s.model_id].request_count += s.request_count
                model_totals[s.model_id].input_tokens += s.input_tokens
                model_totals[s.model_id].output_tokens += s.output_tokens

            # Display top models
            row = 0
            self._stats_grid.addWidget(BodyLabel("模型"), row, 0)
            self._stats_grid.addWidget(BodyLabel("请求数"), row, 1)
            self._stats_grid.addWidget(BodyLabel("输入Token"), row, 2)
            self._stats_grid.addWidget(BodyLabel("输出Token"), row, 3)

            for model_id, s in sorted(model_totals.items(), key=lambda x: -x[1].request_count)[:10]:
                row += 1
                self._stats_grid.addWidget(BodyLabel(short_model_name(model_id)[:20]), row, 0)
                self._stats_grid.addWidget(BodyLabel(str(s.request_count)), row, 1)
                self._stats_grid.addWidget(BodyLabel(str(s.input_tokens)), row, 2)
                self._stats_grid.addWidget(BodyLabel(str(s.output_tokens)), row, 3)

            self._log_widget.info(f"已加载 {len(stats)} 条使用记录")

        except Exception as e:
            logger.exception("Failed to load usage stats")
            self._log_widget.error(f"加载统计数据失败: {e}")

    def _send_api_request(self):
        """Send custom API request and display response."""
        import asyncio
        import time
        import aiohttp

        endpoint = self._api_endpoint.currentText()
        body_text = self._api_body.toPlainText().strip()

        if not body_text:
            InfoBar.warning("请输入请求体", parent=self)
            return

        try:
            body = json.loads(body_text)
        except json.JSONDecodeError as e:
            InfoBar.error("JSON 格式错误", str(e), parent=self)
            return

        # Get API key from settings
        from ui.pages.settings_page import SettingsPage
        from app.modelscope_client import get_client

        client = get_client()
        api_key = client._api_key
        if not api_key:
            InfoBar.warning("请先配置 API Key", parent=self)
            return

        self._btn_send_api.setEnabled(False)
        self._btn_send_api.setText("发送中...")
        self._api_response.clear()
        start_time = time.time()

        async def _send():
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                timeout = aiohttp.ClientTimeout(total=60)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(endpoint, json=body, headers=headers) as resp:
                        elapsed = time.time() - start_time
                        self._api_timing_label.setText(f"耗时: {elapsed:.2f}s | 状态: {resp.status}")

                        # Get response
                        if resp.status == 200:
                            result = await resp.json()
                        else:
                            result = {"error": await resp.text(), "status": resp.status}

                        # Display formatted JSON
                        formatted = json.dumps(result, ensure_ascii=False, indent=2)
                        self._api_response.setPlainText(formatted[:5000])  # Limit display
                        self._log_widget.info(f"API 调用成功: {endpoint}")

            except Exception as e:
                elapsed = time.time() - start_time
                self._api_timing_label.setText(f"耗时: {elapsed:.2f}s | 失败")
                self._api_response.setPlainText(str(e))
                self._log_widget.error(f"API 调用失败: {e}")

            finally:
                self._btn_send_api.setEnabled(True)
                self._btn_send_api.setText("发送请求")

        asyncio.ensure_future(_send())

    def _export_stats(self):
        path = usage_stats_path()
        if not path.exists():
            InfoBar.warning("暂无数据可导出", parent=self)
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出使用统计", "usage_stats.json",
            "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if not save_path:
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if save_path.endswith(".csv"):
                import csv
                with open(save_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=["date", "model_id", "request_count", "input_tokens", "output_tokens"])
                    writer.writeheader()
                    writer.writerows(data)
            else:
                Path(save_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            InfoBar.success("导出成功", f"已导出到 {save_path}", parent=self)
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self)
