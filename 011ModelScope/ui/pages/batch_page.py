import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFileDialog, QHeaderView, QTableView, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter, QMessageBox
)
from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, StrongBodyLabel,
    PushButton, ComboBox, LineEdit, TextEdit, SpinBox,
    InfoBar, InfoBarPosition, ProgressRing, TogglePushButton,
    SubtitleLabel, CheckBox,
)

from app.models import ModelConfig
from app.config import FREE_MODELS, short_model_name
from app.batch_processor import get_batch_processor, TaskStatus
from ui.widgets.log_widget import LogWidget

logger = logging.getLogger(__name__)


class BatchPage(ScrollArea):
    task_started = Signal()
    task_completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("batchPage")
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(500)
        self._update_timer.timeout.connect(self._update_progress_ui)
        self._init_ui()
        self._load_last_task()

    def _init_ui(self):
        container = QWidget()
        self.setWidget(container)
        self.setWidgetResizable(True)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("批量任务"))
        header.addStretch()

        self._btn_new_task = PushButton("新建任务")
        self._btn_new_task.setFixedWidth(80)
        self._btn_new_task.clicked.connect(self._new_task)
        header.addWidget(self._btn_new_task)

        layout.addLayout(header)

        # Task configuration
        config_card = CardWidget()
        config_layout = QGridLayout(config_card)
        config_layout.setContentsMargins(16, 16, 16, 16)
        config_layout.setVerticalSpacing(12)

        config_layout.addWidget(StrongBodyLabel("任务配置"), 0, 0, 1, 4)

        # Model selection
        config_layout.addWidget(BodyLabel("选择模型:"), 1, 0)
        self._model_inputs = QVBoxLayout()
        self._model_checkboxes: list[CheckBox] = []
        self._init_model_selection()
        config_layout.addLayout(self._model_inputs, 1, 1, 3, 1)

        # Prompt input
        config_layout.addWidget(BodyLabel("Prompts:"), 1, 2)
        self._prompt_edit = TextEdit()
        self._prompt_edit.setPlaceholderText("每行一个 prompt，或从 CSV 导入")
        self._prompt_edit.setFixedHeight(150)
        config_layout.addWidget(self._prompt_edit, 1, 3, 3, 1)

        # Import button
        self._btn_import_csv = PushButton("导入CSV")
        self._btn_import_csv.setFixedWidth(80)
        self._btn_import_csv.clicked.connect(self._import_csv)
        config_layout.addWidget(self._btn_import_csv, 5, 2)

        # Concurrent setting
        config_layout.addWidget(BodyLabel("并发数:"), 5, 0)
        self._concurrent_spin = SpinBox()
        self._concurrent_spin.setRange(1, 10)
        self._concurrent_spin.setValue(3)
        self._concurrent_spin.setFixedWidth(80)
        config_layout.addWidget(self._concurrent_spin, 5, 1)

        layout.addWidget(config_card)

        # Control buttons
        control_layout = QHBoxLayout()

        self._btn_start = PushButton("开始")
        self._btn_start.setFixedWidth(80)
        self._btn_start.clicked.connect(self._start_task)
        control_layout.addWidget(self._btn_start)

        self._btn_pause = PushButton("暂停")
        self._btn_pause.setFixedWidth(80)
        self._btn_pause.setEnabled(False)
        self._btn_pause.clicked.connect(self._pause_task)
        control_layout.addWidget(self._btn_pause)

        self._btn_resume = PushButton("继续")
        self._btn_resume.setFixedWidth(80)
        self._btn_resume.setEnabled(False)
        self._btn_resume.clicked.connect(self._resume_task)
        control_layout.addWidget(self._btn_resume)

        self._btn_stop = PushButton("停止")
        self._btn_stop.setFixedWidth(80)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_task)
        control_layout.addWidget(self._btn_stop)

        control_layout.addStretch()

        self._btn_export = PushButton("导出结果")
        self._btn_export.setFixedWidth(80)
        self._btn_export.clicked.connect(self._export_results)
        control_layout.addWidget(self._btn_export)

        layout.addLayout(control_layout)

        # Progress display
        progress_card = CardWidget()
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(16, 16, 16, 16)

        progress_header = QHBoxLayout()
        progress_header.addWidget(StrongBodyLabel("任务进度"))
        self._status_label = BodyLabel("就绪")
        progress_header.addWidget(self._status_label)
        progress_header.addStretch()
        progress_layout.addLayout(progress_header)

        # Progress per model
        self._progress_grid = QGridLayout()
        self._progress_widgets: dict[str, ProgressRing] = {}
        progress_layout.addLayout(self._progress_grid)

        layout.addWidget(progress_card)

        # Results table
        results_card = CardWidget()
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(8, 8, 8, 8)

        results_header = QHBoxLayout()
        results_header.addWidget(StrongBodyLabel("结果对比"))
        results_header.addStretch()
        results_layout.addLayout(results_header)

        self._results_table = QTableView()
        self._results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._results_table.setAlternatingRowColors(True)
        self._results_table.setStyleSheet(
            "QTableView { background-color: #FAFAFA; gridline-color: #E0E0E0; }"
        )
        results_layout.addWidget(self._results_table)

        layout.addWidget(results_card)

        # Log
        self._log_widget = LogWidget()
        layout.addWidget(self._log_widget)

    def _init_model_selection(self):
        """Initialize model selection checkboxes"""
        from ui.pages.models_page import ModelsPage

        # Try to get from models page
        main_window = self.parent().parent() if self.parent() else None
        enabled_models = []
        if main_window and hasattr(main_window, "models_page"):
            enabled_models = main_window.models_page.get_enabled_models()

        if not enabled_models:
            # Use defaults
            for model_type, model_ids in FREE_MODELS.items():
                if model_type in ("llm", "multimodal"):
                    for model_id in model_ids[:2]:
                        enabled_models.append(ModelConfig(
                            model_id=model_id,
                            name=short_model_name(model_id),
                        ))

        for i, model in enumerate(enabled_models[:6]):
            cb = CheckBox(f"{model.name}")
            cb.setChecked(True)
            cb.model_id = model.model_id
            self._model_checkboxes.append(cb)
            self._model_inputs.addWidget(cb)

    def _new_task(self):
        """Create a new batch task"""
        from app.batch_processor import get_batch_processor

        model_ids = [
            cb.model_id for cb in self._model_checkboxes
            if cb.isChecked()
        ]
        if not model_ids:
            InfoBar.warning("请至少选择一个模型", parent=self)
            return

        prompts_text = self._prompt_edit.toPlainText().strip()
        if not prompts_text:
            InfoBar.warning("请输入 prompts", parent=self)
            return

        prompts = [p.strip() for p in prompts_text.split("\n") if p.strip()]
        if not prompts:
            InfoBar.warning("没有有效的 prompt", parent=self)
            return

        processor = get_batch_processor()
        processor.create_task(
            name=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            model_ids=model_ids,
            prompts=prompts,
        )
        processor._max_concurrent = self._concurrent_spin.value()

        self._init_progress_display(model_ids)
        self._log_widget.info(f"已创建任务: {len(model_ids)} 个模型, {len(prompts)} 个 prompts")

    def _init_progress_display(self, model_ids: list[str]):
        """Initialize progress display for selected models"""
        # Clear existing
        while self._progress_grid.count():
            item = self._progress_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._progress_widgets.clear()

        cols = 4
        for i, model_id in enumerate(model_ids):
            row = i // cols
            col = i % cols

            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(4)

            ring = ProgressRing()
            ring.setFixedSize(60, 60)
            ring.setRange(0, 100)
            ring.setValue(0)

            label = BodyLabel(short_model_name(model_id)[:15])
            label.setAlignment(Qt.AlignCenter)

            layout.addWidget(ring, alignment=Qt.AlignCenter)
            layout.addWidget(label, alignment=Qt.AlignCenter)

            self._progress_widgets[model_id] = ring
            self._progress_grid.addWidget(widget, row, col)

    def _start_task(self):
        """Start the batch task"""
        from app.batch_processor import get_batch_processor

        processor = get_batch_processor()
        if not processor.task:
            self._new_task()
            if not processor.task:
                return

        self._btn_start.setEnabled(False)
        self._btn_pause.setEnabled(True)
        self._btn_stop.setEnabled(True)
        self._btn_new_task.setEnabled(False)
        self._update_timer.start()

        async def _run():
            try:
                await processor.start()
                self.task_started.emit()
            except Exception as e:
                logger.exception("Batch task failed")
                self._log_widget.error(f"任务失败: {e}")
            finally:
                self._on_task_finished()

        asyncio.ensure_future(_run())

    def _pause_task(self):
        """Pause the running task"""
        from app.batch_processor import get_batch_processor
        get_batch_processor().pause()
        self._btn_pause.setEnabled(False)
        self._btn_resume.setEnabled(True)
        self._status_label.setText("已暂停")
        self._log_widget.info("任务已暂停")

    def _resume_task(self):
        """Resume the paused task"""
        from app.batch_processor import get_batch_processor
        get_batch_processor().resume()
        self._btn_pause.setEnabled(True)
        self._btn_resume.setEnabled(False)
        self._status_label.setText("运行中")
        self._log_widget.info("任务已继续")

    def _stop_task(self):
        """Stop the task"""
        from app.batch_processor import get_batch_processor
        get_batch_processor().stop()
        self._status_label.setText("已停止")
        self._log_widget.info("任务已停止")

    def _on_task_finished(self):
        """Called when task finishes"""
        self._update_timer.stop()
        self._btn_start.setEnabled(True)
        self._btn_pause.setEnabled(False)
        self._btn_resume.setEnabled(False)
        self._btn_stop.setEnabled(False)
        self._btn_new_task.setEnabled(True)

        from app.batch_processor import get_batch_processor, TaskStatus
        processor = get_batch_processor()

        if processor.status == TaskStatus.COMPLETED:
            self._status_label.setText("已完成")
            self._log_widget.info("任务完成")
            self.task_completed.emit()
        elif processor.status == TaskStatus.FAILED:
            self._status_label.setText("失败")
        else:
            self._status_label.setText("已停止")

        self._update_results_table()

    def _update_progress_ui(self):
        """Update progress rings from processor state"""
        from app.batch_processor import get_batch_processor

        processor = get_batch_processor()
        for model_id, progress in processor.progress.items():
            if model_id in self._progress_widgets:
                ring = self._progress_widgets[model_id]
                ring.setValue(int(progress.progress_percent))

    def _update_results_table(self):
        """Update results table"""
        from app.batch_processor import get_batch_processor
        from PySide6.QtCore import QAbstractTableModel

        processor = get_batch_processor()
        if not processor.task:
            return

        results = processor.results
        model_ids = processor.task.model_ids

        # Simple table model
        class ResultsTableModel(QAbstractTableModel):
            def __init__(self, results, model_ids):
                super().__init__()
                self._results = results
                self._model_ids = model_ids
                self._headers = ["Prompt"] + [short_model_name(m)[:15] for m in model_ids]

            def rowCount(self, parent=None):
                return len(self._results)

            def columnCount(self, parent=None):
                return len(self._headers)

            def data(self, index, role=Qt.DisplayRole):
                if not index.isValid():
                    return None
                if role == Qt.DisplayRole:
                    row = index.row()
                    col = index.column()
                    if col == 0:
                        return self._results[row].get("prompt", "")[:50]
                    else:
                        model_id = self._model_ids[col - 1]
                        if self._results[row].get("model_id") == model_id:
                            return self._results[row].get("response", "")[:100]
                        return ""
                return None

            def headerData(self, section, orientation, role=Qt.DisplayRole):
                if orientation == Qt.Horizontal and role == Qt.DisplayRole:
                    return self._headers[section]
                return None

        model = ResultsTableModel(results, model_ids)
        self._results_table.setModel(model)

    def _import_csv(self):
        """Import prompts from CSV"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 Prompts", "", "CSV Files (*.csv);;Text Files (*.txt)"
        )
        if not path:
            return

        try:
            if path.endswith(".csv"):
                import csv
                prompts = []
                with open(path, "r", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row:
                            prompts.append(row[0])
            else:
                prompts = Path(path).read_text(encoding="utf-8").strip().split("\n")

            self._prompt_edit.setPlainText("\n".join(prompts))
            InfoBar.success("导入成功", f"已导入 {len(prompts)} 条", parent=self)
        except Exception as e:
            InfoBar.error("导入失败", str(e), parent=self)

    def _export_results(self):
        """Export results to file"""
        from app.batch_processor import get_batch_processor

        processor = get_batch_processor()
        if not processor.results:
            InfoBar.warning("没有可导出的结果", parent=self)
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "导出结果", "batch_results.json",
            "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            if path.endswith(".csv"):
                import csv
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=["model_id", "prompt", "response", "success"])
                    writer.writeheader()
                    writer.writerows(processor.results)
            else:
                Path(path).write_text(
                    json.dumps(processor.results, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            InfoBar.success("导出成功", f"已导出到 {path}", parent=self)
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self)

    def _load_last_task(self):
        """Load last task and offer resume if interrupted."""
        from app.batch_processor import get_batch_processor, TaskStatus

        processor = get_batch_processor()
        task = processor.load_task()
        if not task:
            return

        self._init_progress_display(task.model_ids)
        self._log_widget.info(f"已加载上次任务: {task.name}")

        # Defer resume prompt to after UI is shown
        if task.status in ("running", "paused") and processor.progress:
            completed = sum(p.completed for p in processor.progress.values())
            total = sum(p.total for p in processor.progress.values())
            if completed > 0 and completed < total:
                def _prompt_resume():
                    btn = QMessageBox.question(
                        self, "恢复任务",
                        f"检测到未完成的任务 '{task.name}'（已完成 {completed}/{total}），是否从中断处继续？",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if btn == QMessageBox.Yes:
                        processor._status = TaskStatus.PENDING
                        self._log_widget.info(f"已恢复任务: {task.name}")
                        self._btn_start.setEnabled(True)

                from PySide6.QtCore import QTimer
                QTimer.singleShot(500, _prompt_resume)

        # Show existing results
        if processor.results:
            self._update_results_table()
