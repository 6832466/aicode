"""
主页 — 卡片式任务工作区
"""

import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QFileDialog, QSplitter, QSizePolicy, QTextEdit, QGridLayout,
)

_debug_log = Path(__file__).parent.parent.parent / "debug.log"
def _dbg(msg: str):
    ts = time.strftime("%H:%M:%S")
    with open(_debug_log, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] HP: {msg}\n")
from qfluentwidgets import (
    CardWidget, PrimaryPushButton, PushButton, TransparentPushButton,
    SegmentedWidget, FluentIcon, BodyLabel, CaptionLabel,
    StrongBodyLabel, TextEdit, IndeterminateProgressBar,
    InfoBar, InfoBarPosition, LineEdit, ComboBox,
    ScrollArea, FlowLayout, TitleLabel, SubtitleLabel,
    SwitchButton, Slider, SpinBox, MessageBoxBase, MessageBox
)

from app.config import (
    MODE_ASR, MODE_ALIGNMENT, MAX_SEGMENT_SECONDS,
    SEGMENT_OVERLAP_SECONDS, MAX_LINE_CHARS, MIN_SPEECH_SECONDS,
)
from app.models import TaskItem
from ui.widgets.task_card import TaskCard


# 支持的音视频扩展名
SUPPORTED_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v",
    ".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg", ".wma", ".opus",
}


class DroppableTextEdit(TextEdit):
    """支持拖拽文本文件的编辑框"""
    text_file_dropped = Signal(str)  # 文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p and Path(p).suffix.lower() in (".txt", ".text", ".srt", ".md"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.exists(p):
                try:
                    content = Path(p).read_text(encoding="utf-8")
                    self.setPlainText(content)
                    self.text_file_dropped.emit(p)
                    event.acceptProposedAction()
                    return
                except UnicodeDecodeError:
                    try:
                        content = Path(p).read_text(encoding="gbk")
                        self.setPlainText(content)
                        self.text_file_dropped.emit(p)
                        event.acceptProposedAction()
                        return
                    except Exception:
                        pass
        event.ignore()


class HomePage(QWidget):
    """主页工作区"""

    # 通知主窗口的信号
    task_added = Signal(object)      # TaskItem
    task_removed = Signal(str)       # task_id
    start_all = Signal()             # 开始全部
    pause_all = Signal()             # 暂停
    stop_all = Signal()              # 停止
    reprocess_task = Signal(str)     # 重新处理单任务
    open_srt = Signal(str)           # 打开字幕文件

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: dict[str, TaskItem] = {}
        self._cards: dict[str, TaskCard] = {}
        self._current_mode = MODE_ASR
        self._is_processing = False
        self._init_ui()
        self.setObjectName("homePage")

    # ═══════════════════════════════════════════
    #  UI 初始化
    # ═══════════════════════════════════════════

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 12)
        main_layout.setSpacing(12)

        # 启用拖拽
        self.setAcceptDrops(True)

        # ── 顶部工具栏 ──
        main_layout.addLayout(self._create_toolbar())

        # ── 中间内容区 (卡片列表 + 详情面板) ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # 左侧：带添加按钮的卡片区
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(0)

        # 卡片滚动区
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
        """)

        self.card_container = QWidget()
        self.card_container.setStyleSheet("background: transparent;")
        self.card_layout = FlowLayout(self.card_container, needAni=True)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(12)
        self.scroll_area.setWidget(self.card_container)
        left_layout.addWidget(self.scroll_area)

        splitter.addWidget(left_widget)

        # 右侧：详情面板
        self.detail_panel = self._create_detail_panel()
        splitter.addWidget(self.detail_panel)

        splitter.setSizes([700, 340])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        main_layout.addWidget(splitter, 1)

        # ── 底部日志区 ──
        main_layout.addWidget(self._create_log_area())

        # 初始添加按钮卡片
        self._add_placeholder_card()

    def _create_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        # 模式切换
        self.mode_segment = SegmentedWidget()
        self.mode_segment.addItem("mode_asr", "ASR 转写", None)
        self.mode_segment.addItem("mode_align", "强制对齐", None)
        self.mode_segment.setCurrentItem("mode_asr")
        self.mode_segment.currentItemChanged.connect(self._on_mode_changed)
        toolbar.addWidget(self.mode_segment)

        toolbar.addSpacing(16)

        # 添加文件按钮
        add_btn = PrimaryPushButton("添加文件")
        add_btn.setIcon(FluentIcon.ADD)
        add_btn.clicked.connect(self._add_files)
        toolbar.addWidget(add_btn)

        add_folder_btn = PushButton("添加文件夹")
        add_folder_btn.setIcon(FluentIcon.FOLDER)
        add_folder_btn.clicked.connect(self._add_folder)
        toolbar.addWidget(add_folder_btn)

        toolbar.addStretch()

        # 全选 / 删除选中
        self.select_all_btn = PushButton("全选")
        self.select_all_btn.setIcon(FluentIcon.ACCEPT)
        self.select_all_btn.clicked.connect(self._on_select_all)
        toolbar.addWidget(self.select_all_btn)

        self.delete_selected_btn = PushButton("删除选中")
        self.delete_selected_btn.setIcon(FluentIcon.DELETE)
        self.delete_selected_btn.clicked.connect(self._on_delete_selected)
        toolbar.addWidget(self.delete_selected_btn)

        toolbar.addSpacing(8)

        # 控制按钮
        self.start_btn = PrimaryPushButton("开始全部")
        self.start_btn.setIcon(FluentIcon.PLAY)
        self.start_btn.clicked.connect(self._on_start_all)
        toolbar.addWidget(self.start_btn)

        self.pause_btn = PushButton("暂停")
        self.pause_btn.setIcon(FluentIcon.PAUSE)
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause)
        toolbar.addWidget(self.pause_btn)

        self.stop_btn = PushButton("停止")
        self.stop_btn.setIcon(FluentIcon.CLOSE)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        toolbar.addWidget(self.stop_btn)

        return toolbar

    def _create_detail_panel(self) -> QWidget:
        """右侧详情面板"""
        panel = QWidget()
        panel.setFixedWidth(320)
        panel.setStyleSheet("""
            QWidget#detailPanel {
                background: #FAFAFA;
                border-radius: 8px;
                border: 1px solid #E0E0E0;
            }
        """)
        panel.setObjectName("detailPanel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 标题
        self.detail_title = TitleLabel("任务详情")
        layout.addWidget(self.detail_title)

        # 文件名
        self.detail_filename = SubtitleLabel("请选择左侧任务卡片")
        self.detail_filename.setWordWrap(True)
        layout.addWidget(self.detail_filename)

        # 模式标签
        self.detail_mode = CaptionLabel()
        layout.addWidget(self.detail_mode)

        layout.addSpacing(4)

        # 进度条
        self.detail_progress = IndeterminateProgressBar()
        self.detail_progress.setVisible(False)
        layout.addWidget(self.detail_progress)

        self.detail_progress_text = CaptionLabel()
        layout.addWidget(self.detail_progress_text)

        layout.addSpacing(4)

        # 文稿编辑区 (强制对齐模式)
        self.script_label = BodyLabel("文稿内容 (强制对齐模式)")
        self.script_label.setVisible(False)
        layout.addWidget(self.script_label)

        self.script_edit = DroppableTextEdit()
        self.script_edit.setPlaceholderText("在此粘贴或拖拽文本文件...")
        self.script_edit.setFixedHeight(120)
        self.script_edit.setVisible(False)
        self.script_edit.textChanged.connect(self._on_script_changed)
        layout.addWidget(self.script_edit)

        layout.addSpacing(8)

        # 操作按钮
        self.detail_reprocess_btn = PushButton("重新处理")
        self.detail_reprocess_btn.setIcon(FluentIcon.SYNC)
        self.detail_reprocess_btn.setVisible(False)
        layout.addWidget(self.detail_reprocess_btn)

        self.detail_open_btn = PushButton("打开字幕文件")
        self.detail_open_btn.setIcon(FluentIcon.DOCUMENT)
        self.detail_open_btn.setVisible(False)
        layout.addWidget(self.detail_open_btn)

        self.detail_remove_btn = PushButton("从列表移除")
        self.detail_remove_btn.setIcon(FluentIcon.DELETE)
        self.detail_remove_btn.setVisible(False)
        layout.addWidget(self.detail_remove_btn)

        layout.addStretch()
        return panel

    def _create_log_area(self) -> QWidget:
        """底部日志区"""
        log_widget = QWidget()
        log_widget.setFixedHeight(160)
        log_widget.setStyleSheet("""
            QWidget#logArea {
                background: #F5F5F5;
                border-radius: 6px;
                border: 1px solid #E0E0E0;
            }
        """)
        log_widget.setObjectName("logArea")

        layout = QVBoxLayout(log_widget)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        title = BodyLabel("处理日志")
        header.addWidget(title)
        header.addStretch()
        clear_btn = TransparentPushButton("清空")
        clear_btn.clicked.connect(self._clear_log)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                border: none;
                background: transparent;
                font-size: 13px;
                color: #444444;
            }
        """)
        layout.addWidget(self.log_text)

        return log_widget

    # ═══════════════════════════════════════════
    #  公开方法
    # ═══════════════════════════════════════════

    def add_task(self, task: TaskItem):
        """添加一个任务到列表"""
        if task.id in self._tasks:
            return
        self._tasks[task.id] = task

        # 移除占位卡片（如果有）
        self._remove_placeholder_card()

        card = TaskCard(task)
        card.card_clicked.connect(self._on_card_clicked)
        card.selection_changed.connect(self._on_card_selection_changed)
        card.remove_clicked.connect(self._remove_task)
        card.reprocess_clicked.connect(self.reprocess_task.emit)
        card.open_srt_clicked.connect(self._on_open_srt)
        self._cards[task.id] = card
        self.card_layout.addWidget(card)

        self._log(f"已添加: {task.file_name} ({task.mode_label})")

    def update_task(self, task: TaskItem):
        """更新任务状态"""
        if task.id in self._cards:
            self._tasks[task.id] = task
            self._cards[task.id].refresh(task)
            # 如果详情面板正在显示此任务，同步更新
            if hasattr(self, "_selected_task_id") and self._selected_task_id == task.id:
                self._show_detail(task)

    def remove_task(self, task_id: str):
        self._remove_task(task_id)

    def set_processing_state(self, is_processing: bool):
        """更新控制按钮状态"""
        self._is_processing = is_processing
        self.start_btn.setEnabled(not is_processing)
        self.pause_btn.setEnabled(is_processing)
        self.stop_btn.setEnabled(is_processing)

    def log(self, message: str):
        """外部追加日志"""
        self._log(message)

    def get_tasks(self) -> list:
        """获取当前所有任务"""
        return list(self._tasks.values())

    # ═══════════════════════════════════════════
    #  内部方法
    # ═══════════════════════════════════════════

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._show_drop_indicator(True)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._show_drop_indicator(False)

    def dropEvent(self, event: QDropEvent):
        self._show_drop_indicator(False)
        urls = event.mimeData().urls()
        paths = []
        for url in urls:
            p = url.toLocalFile()
            if p:
                paths.append(p)
        if paths:
            self._add_dropped_paths(paths)

    def _show_drop_indicator(self, show: bool):
        if show:
            self.scroll_area.setStyleSheet("""
                QScrollArea {
                    border: 2px dashed #0078D4;
                    border-radius: 8px;
                    background: #F0F6FF;
                }
            """)
        else:
            self.scroll_area.setStyleSheet("""
                QScrollArea { border: none; background: transparent; }
            """)

    def _add_dropped_paths(self, paths: list[str]):
        """处理拖拽/侧加载的文件路径（支持文件和文件夹混合）"""
        collected = []
        for p in paths:
            p = os.path.normpath(p)
            if not os.path.exists(p):
                continue
            if os.path.isfile(p):
                ext = Path(p).suffix.lower()
                if ext in SUPPORTED_EXTS:
                    collected.append(p)
            elif os.path.isdir(p):
                for root, _, filenames in os.walk(p):
                    for f in filenames:
                        fp = os.path.join(root, f)
                        if Path(f).suffix.lower() in SUPPORTED_EXTS:
                            collected.append(fp)
        if collected:
            self._add_file_paths(collected)
        else:
            self._log("拖拽的文件中未找到支持的音视频文件")

    def _add_files(self):
        """添加文件"""
        filter_str = "音视频文件 ("
        filter_str += " ".join(f"*{ext}" for ext in SUPPORTED_EXTS)
        filter_str += ");;所有文件 (*.*)"

        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音视频文件", "", filter_str,
        )
        if files:
            self._add_file_paths(files)

    def _add_folder(self):
        """添加文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not folder:
            return

        all_files = []
        for root, _, filenames in os.walk(folder):
            for f in filenames:
                ext = Path(f).suffix.lower()
                if ext in SUPPORTED_EXTS:
                    all_files.append(os.path.join(root, f))

        if all_files:
            self._add_file_paths(all_files)
        else:
            self._log("所选文件夹中未找到支持的音视频文件")

    def _add_file_paths(self, paths: list[str]):
        """添加文件路径列表"""
        _dbg(f"_add_file_paths: {len(paths)} path(s)")
        for p in paths:
            file_path = str(Path(p).resolve())
            file_name = Path(p).name
            task = TaskItem(
                file_path=file_path,
                file_name=file_name,
                mode=self._current_mode,
            )
            self.add_task(task)
            self.task_added.emit(task)

    def _on_mode_changed(self, mode_key: str):
        """模式切换"""
        self._current_mode = MODE_ALIGNMENT if mode_key == "mode_align" else MODE_ASR
        mode_name = "强制对齐" if self._current_mode == MODE_ALIGNMENT else "ASR 转写"
        self._log(f"切换到: {mode_name} 模式")
        # 更新详情面板文稿编辑区可见性
        self.script_label.setVisible(self._current_mode == MODE_ALIGNMENT)
        self.script_edit.setVisible(self._current_mode == MODE_ALIGNMENT)
        # 清空选中任务
        self._clear_detail()

    def _on_start_all(self):
        """开始处理全部"""
        pending = [t for t in self._tasks.values() if t.state == "pending"]
        _dbg(f"_on_start_all: pending={len(pending)}, tasks={len(self._tasks)}")
        if not pending:
            self._log("没有待处理的任务")
            return

        # 强制对齐模式检查文稿
        if self._current_mode == MODE_ALIGNMENT:
            no_script = [t for t in pending if not t.script_text.strip()]
            if no_script:
                names = ", ".join(t.file_name for t in no_script[:3])
                self._log(f"以下文件缺少文稿: {names}")
                return

        self.set_processing_state(True)
        self._log(f"开始批量处理 {len(pending)} 个文件")
        _dbg("_on_start_all: emitting start_all signal")
        self.start_all.emit()

    def _on_pause(self):
        self._log("暂停处理")
        self.pause_all.emit()

    def _on_stop(self):
        self._log("停止处理")
        self.stop_all.emit()
        self.set_processing_state(False)

    def _on_select_all(self):
        """全选 / 取消全选"""
        all_selected = all(
            card.is_selected() for card in self._cards.values()
        )
        new_state = not all_selected
        for card in self._cards.values():
            card.set_selected(new_state)
        self.select_all_btn.setText("取消全选" if new_state else "全选")

        # 全选时自动展示第一个任务的详情
        if new_state and self._cards:
            first_card = next(iter(self._cards.values()))
            self._on_card_clicked(first_card.task_id)
        elif not new_state:
            self._clear_detail()

    def _on_delete_selected(self):
        """删除选中的任务"""
        selected_ids = [
            tid for tid, card in self._cards.items()
            if card.is_selected()
        ]
        if not selected_ids:
            self._log("没有选中的任务")
            return
        for tid in selected_ids:
            self._remove_task(tid)
        self._log(f"已删除 {len(selected_ids)} 个任务")

    def _remove_task(self, task_id: str):
        """移除任务"""
        if task_id in self._cards:
            card = self._cards.pop(task_id)
            self.card_layout.removeWidget(card)
            card.deleteLater()

        self._tasks.pop(task_id, None)
        self.task_removed.emit(task_id)

        # 如果移除的是当前选中，清空详情
        if hasattr(self, "_selected_task_id") and self._selected_task_id == task_id:
            self._clear_detail()

        # 任务清空后重新显示占位卡片
        if not self._tasks:
            self._add_placeholder_card()

        self._log(f"已移除任务")

    def _on_card_clicked(self, task_id: str):
        """卡片被点击"""
        self._selected_task_id = task_id
        if task_id in self._tasks:
            self._show_detail(self._tasks[task_id])

    def _on_card_selection_changed(self, task_id: str, selected: bool):
        """复选框状态变化时同步更新详情面板"""
        if selected:
            self._selected_task_id = task_id
            if task_id in self._tasks:
                self._show_detail(self._tasks[task_id])
        elif hasattr(self, "_selected_task_id") and self._selected_task_id == task_id:
            self._clear_detail()

    def _show_detail(self, task: TaskItem):
        """更新右侧详情面板"""
        self.detail_title.setText("任务详情")
        self.detail_filename.setText(task.file_name)

        if task.is_asr_mode:
            self.detail_mode.setText("模式: ASR 转写")
        else:
            self.detail_mode.setText("模式: 强制对齐 (文稿驱动)")

        # 进度
        if task.state in ("pending", "done", "failed", "stopped"):
            self.detail_progress.setVisible(False)
        else:
            self.detail_progress.setVisible(True)

        self.detail_progress_text.setText(
            task.state_label if task.progress_text else task.state_label
        )

        # 文稿区（强制对齐模式）
        is_alignment = task.is_alignment_mode
        self.script_label.setVisible(is_alignment)
        self.script_edit.setVisible(is_alignment)

        if is_alignment:
            # 断开信号避免 textChanged 触发无限循环
            self.script_edit.blockSignals(True)
            self.script_edit.setPlainText(task.script_text)
            self.script_edit.blockSignals(False)

        # 按钮
        self.detail_reprocess_btn.setVisible(task.state in ("done", "failed", "stopped"))
        self.detail_open_btn.setVisible(task.state == "done" and task.srt_path is not None)
        self.detail_remove_btn.setVisible(True)

        if task.state == "done" and task.srt_path:
            self.detail_open_btn.clicked.connect(lambda: self._on_open_srt(task.id))
        self.detail_remove_btn.clicked.connect(lambda: self._remove_task(task.id))
        self.detail_reprocess_btn.clicked.connect(lambda: self.reprocess_task.emit(task.id))

    def _on_script_changed(self):
        """文稿编辑区内容变化"""
        if not hasattr(self, "_selected_task_id"):
            return
        tid = self._selected_task_id
        if tid in self._tasks:
            self._tasks[tid].script_text = self.script_edit.toPlainText()

    def _on_open_srt(self, task_id: str):
        """打开字幕文件"""
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if task.srt_path and os.path.exists(task.srt_path):
                os.startfile(task.srt_path)
            else:
                self._log(f"字幕文件不存在: {task.srt_path}")

    def _clear_detail(self):
        """清空详情面板"""
        if hasattr(self, "_selected_task_id"):
            del self._selected_task_id
        self.detail_title.setText("任务详情")
        self.detail_filename.setText("请选择左侧任务卡片")
        self.detail_mode.setText("")
        self.detail_progress.setVisible(False)
        self.detail_progress_text.setText("")
        self.script_label.setVisible(False)
        self.script_edit.setVisible(False)
        self.detail_reprocess_btn.setVisible(False)
        self.detail_open_btn.setVisible(False)
        self.detail_remove_btn.setVisible(False)

    def _add_placeholder_card(self):
        """无任务时的添加引导卡片"""
        card = CardWidget()
        card.setFixedSize(180, 140)
        card.setStyleSheet("""
            CardWidget {
                border: 2px dashed #C0C0C0;
                border-radius: 12px;
                background: #F9F9F9;
            }
            CardWidget:hover {
                border-color: #0078D4;
                background: #F0F6FF;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        from qfluentwidgets import FluentIcon
        icon_label = QLabel()
        icon_label.setPixmap(FluentIcon.ADD.icon().pixmap(32, 32))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        hint = CaptionLabel("点击添加音视频文件")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        card.mousePressEvent = lambda e: self._add_files()
        card.setObjectName("placeholderCard")
        self.card_layout.addWidget(card)
        self._placeholder_card = card

    def _remove_placeholder_card(self):
        """移除占位卡片"""
        if hasattr(self, "_placeholder_card") and self._placeholder_card:
            self.card_layout.removeWidget(self._placeholder_card)
            self._placeholder_card.deleteLater()
            self._placeholder_card = None

    def _log(self, message: str):
        """追加日志"""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {message}")
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_log(self):
        """清空日志"""
        self.log_text.clear()