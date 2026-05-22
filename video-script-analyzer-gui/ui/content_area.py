# -*- coding: utf-8 -*-
"""内容区域 — 全 Fluent 控件：卡片网格 + 底部运行日志"""
import os
import sys
import datetime
import traceback

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QGridLayout,
)
from qfluentwidgets import (
    SmoothScrollArea, StrongBodyLabel, CaptionLabel,
    PushButton, LineEdit, ComboBox, TextEdit, FluentIcon,
)

from .video_card import VideoCard
from core.analyzer import extract_episode_number, find_script_path
from core.compressor import extract_thumbnail


class LogWidget(QWidget):
    """底部运行日志"""

    def __init__(self, parent=None):
        try:
            super().__init__(parent)
            self.setObjectName("LogPanel")
            self.setFixedHeight(120)
            self.setStyleSheet("""
                QWidget#LogPanel {
                    background: #ffffff;
                    border-top: 1px solid #e0e0e0;
                }
            """)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 8, 16, 8)
            layout.setSpacing(0)

            header_row = QHBoxLayout()
            header_row.addWidget(StrongBodyLabel("运行日志"))
            header_row.addStretch()

            clear_btn = PushButton(FluentIcon.DELETE, "清空")
            clear_btn.setFixedHeight(26)
            clear_btn.clicked.connect(self.clear)
            header_row.addWidget(clear_btn)
            layout.addLayout(header_row)

            self.log_view = TextEdit()
            self.log_view.setReadOnly(True)
            self.log_view.setStyleSheet("""
                TextEdit {
                    border: none; background: transparent;
                    font-family: 'Consolas', 'Microsoft YaHei', monospace;
                    font-size: 13px; padding: 4px 8px; color: #1d1d1f;
                }
            """)
            layout.addWidget(self.log_view)
        except Exception as e:
            import sys
            tb = traceback.format_exc()
            print(f"[ERROR] 日志组件初始化失败: {e}\n{tb}", file=sys.stderr)
            raise

    def append(self, message, level="info"):
        try:
            colors = {"info": "#1d1d1f", "success": "#107c10", "error": "#d13438", "warning": "#e08800"}
            color = colors.get(level, "#1d1d1f")
            prefix = {"info": "ℹ", "success": "✔", "error": "✘", "warning": "⚠"}.get(level, "·")
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            html = f'<div style="color:{color}; margin:1px 0;">[{ts}] {prefix} {message}</div>'
            current = self.log_view.toHtml()
            self.log_view.setHtml(html + current)
        except Exception as e:
            import sys
            print(f"[ERROR] 日志追加失败: {e}", file=sys.stderr)

    def clear(self):
        try:
            self.log_view.clear()
        except Exception as e:
            import sys
            print(f"[ERROR] 日志清空失败: {e}", file=sys.stderr)


class ContentArea(SmoothScrollArea):
    """视频卡片网格"""

    preview_requested = Signal(str)
    script_requested = Signal(str)
    analyze_requested = Signal(str)
    delete_requested = Signal(str)
    stop_requested = Signal(str)
    retry_all_requested = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        try:
            super().__init__(parent)
            self.cards = {}
            self.video_paths = []
            self.card_statuses = {}

            self.setWidgetResizable(True)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setStyleSheet("SmoothScrollArea { border: none; background: transparent; }")

            container = QWidget()
            self.setWidget(container)
            self.main_layout = QVBoxLayout(container)
            self.main_layout.setContentsMargins(24, 20, 24, 20)
            self.main_layout.setSpacing(16)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[ERROR] ContentArea初始化失败: {e}\n{tb}", file=sys.stderr)
            raise

        # Header
        header = QHBoxLayout()
        self.title_label = StrongBodyLabel("视频列表")
        self.title_label.setStyleSheet("font-size: 18px;")
        header.addWidget(self.title_label)
        header.addStretch()

        self.filter_combo = ComboBox()
        self.filter_combo.addItems(["全部", "已分析", "未分析"])
        self.filter_combo.setFixedWidth(100)
        self.filter_combo.currentTextChanged.connect(self._apply_filter)
        header.addWidget(self.filter_combo)

        self.search_input = LineEdit()
        self.search_input.setPlaceholderText("搜索集数...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self._apply_filter)
        header.addWidget(self.search_input)

        self.retry_btn = PushButton(FluentIcon.UPDATE, "一键重试")
        self.retry_btn.setEnabled(False)
        self.retry_btn.clicked.connect(self._on_retry_all)
        header.addWidget(self.retry_btn)

        clear_btn = PushButton(FluentIcon.DELETE, "清空")
        clear_btn.clicked.connect(self._clear_all)
        header.addWidget(clear_btn)
        self.main_layout.addLayout(header)

        # Summary
        self.summary_label = CaptionLabel("未加载视频")
        self.main_layout.addWidget(self.summary_label)

        # Card grid
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setVerticalSpacing(14)
        self.grid_layout.setHorizontalSpacing(14)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.grid_widget)

        # Empty state
        self.empty_label = CaptionLabel("请从侧边栏选择视频文件夹或文件")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #888; padding: 60px;")
        self.main_layout.addWidget(self.empty_label)

        self.main_layout.addStretch()

    def _log_error(self, context, exc):
        tb = traceback.format_exc()
        self.error_occurred.emit(f"{context}: {exc}\n{tb[:800]}")

    def load_videos(self, paths, replace=True):
        try:
            videos = []
            for p in paths:
                if os.path.isfile(p) and p.lower().endswith('.mp4'):
                    videos.append(p)
                elif os.path.isdir(p):
                    for f in sorted(os.listdir(p)):
                        if f.lower().endswith('.mp4'):
                            videos.append(os.path.join(p, f))

            if replace:
                self.video_paths = sorted(videos, key=lambda x: extract_episode_number(os.path.basename(x)))
            else:
                existing = set(self.video_paths)
                for v in videos:
                    if v not in existing:
                        self.video_paths.append(v)
                        existing.add(v)
                self.video_paths = sorted(self.video_paths, key=lambda x: extract_episode_number(os.path.basename(x)))

            self._rebuild_grid()
            self._update_summary()
        except Exception as e:
            self._log_error("加载视频异常", e)

    def _rebuild_grid(self):
        try:
            for card in self.cards.values():
                card.hide()
                card.setParent(None)
                card.deleteLater()
            self.cards.clear()

            # 清空网格布局
            while self.grid_layout.count():
                item = self.grid_layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().setParent(None)
                    item.widget().deleteLater()
            QApplication.processEvents()

            if not self.video_paths:
                self.empty_label.setVisible(True)
                self.grid_widget.setVisible(False)
                return

            self.empty_label.setVisible(False)
            self.grid_widget.setVisible(True)

            # 根据可用宽度计算每行卡片数
            viewport_width = self.viewport().width() if self.viewport() else 1200
            available = viewport_width - 48  # 左右 margin 各 24
            cards_per_row = max(1, available // (250 + 14))

            for i, vpath in enumerate(self.video_paths):
                card = VideoCard(vpath)
                card.preview_clicked.connect(self.preview_requested.emit)
                card.open_script_clicked.connect(self.script_requested.emit)
                card.analyze_clicked.connect(self.analyze_requested.emit)
                card.stop_clicked.connect(self.stop_requested.emit)
                card.error_occurred.connect(self.error_occurred.emit)
                card.delete_clicked.connect(self._remove_video)

                if find_script_path(vpath):
                    card.set_script_exists(True)
                    self.card_statuses[vpath] = "done"
                else:
                    self.card_statuses[vpath] = "idle"

                QTimer.singleShot(200 + i * 80, lambda p=vpath, c=card: self._lazy_thumb(p, c))

                row = i // cards_per_row
                col = i % cards_per_row
                self.cards[vpath] = card
                self.grid_layout.addWidget(card, row, col)

            self.grid_widget.updateGeometry()
            self._update_retry_btn()
        except Exception as e:
            self._log_error("重建网格异常", e)

    def _lazy_thumb(self, path, card):
        try:
            thumb = extract_thumbnail(path)
            if thumb:
                card.load_thumbnail(thumb_path=thumb)
            else:
                card.load_thumbnail(thumb_path=None)
        except Exception as e:
            self._log_error(f"缩略图加载异常: {os.path.basename(path)}", e)

    def _apply_filter(self):
        try:
            filter_mode = self.filter_combo.currentText()
            text = self.search_input.text().strip()

            # 先全部隐藏
            for card in self.cards.values():
                card.hide()

            # 计算可见路径列表
            visible_paths = []
            for vpath in self.video_paths:
                show = True
                if filter_mode == "已分析":
                    show = find_script_path(vpath) is not None
                elif filter_mode == "未分析":
                    show = find_script_path(vpath) is None
                if show and text:
                    ep = extract_episode_number(os.path.basename(vpath))
                    if str(ep) != text and text.lower() not in os.path.basename(vpath).lower():
                        show = False
                if show:
                    visible_paths.append(vpath)

            # 清除网格，按可见路径重新放置卡片
            for card in self.cards.values():
                self.grid_layout.removeWidget(card)

            if not visible_paths:
                self.grid_widget.updateGeometry()
                return

            viewport_width = self.viewport().width() if self.viewport() else 1200
            available = viewport_width - 48
            cards_per_row = max(1, available // (250 + 14))

            for i, vpath in enumerate(visible_paths):
                card = self.cards.get(vpath)
                if card:
                    row = i // cards_per_row
                    col = i % cards_per_row
                    self.grid_layout.addWidget(card, row, col)
                    card.show()

            self.grid_widget.updateGeometry()
        except Exception as e:
            self._log_error("筛选异常", e)

    def _update_summary(self):
        try:
            total = len(self.video_paths)
            done = sum(1 for vp in self.video_paths if find_script_path(vp))
            self.summary_label.setText(f"共 {total} 个视频 · 已分析 {done} 个 · 待处理 {total - done} 个")
            self.title_label.setText(f"视频列表（{total}）")
        except Exception as e:
            self._log_error("更新摘要异常", e)

    def update_card_status(self, video_path, status, message="", percent=0):
        try:
            card = self.cards.get(video_path)
            if card:
                card.set_status(status, message, percent)
                if status == "done":
                    card.set_script_exists(True)
            self.card_statuses[video_path] = status
            self._update_retry_btn()
            self._update_summary()
        except Exception as e:
            self._log_error("更新卡片状态异常", e)

    def _remove_video(self, video_path):
        try:
            if video_path in self.cards:
                card = self.cards.pop(video_path)
                card.setParent(None)
                card.deleteLater()
            if video_path in self.video_paths:
                self.video_paths.remove(video_path)
            self.card_statuses.pop(video_path, None)
            self.delete_requested.emit(video_path)
            self._update_retry_btn()
            self._update_summary()
        except Exception as e:
            self._log_error("移除视频异常", e)

    def _on_retry_all(self):
        try:
            paths = [vp for vp, status in self.card_statuses.items() if status == "failed"]
            if paths:
                self.retry_all_requested.emit(paths)
        except Exception as e:
            self._log_error("一键重试异常", e)

    def _update_retry_btn(self):
        try:
            has_failed = any(s == "failed" for s in self.card_statuses.values())
            self.retry_btn.setEnabled(has_failed)
        except Exception as e:
            self._log_error("更新重试按钮异常", e)

    def _clear_all(self):
        try:
            for card in list(self.cards.values()):
                card.hide()
                card.setParent(None)
                card.deleteLater()
            for vpath in list(self.video_paths):
                self.delete_requested.emit(vpath)
            self.cards.clear()
            self.video_paths.clear()
            self.card_statuses.clear()

            while self.grid_layout.count():
                item = self.grid_layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().setParent(None)
                    item.widget().deleteLater()

            self.empty_label.setVisible(True)
            self.grid_widget.setVisible(False)
            self._update_retry_btn()
            self._update_summary()
        except Exception as e:
            self._log_error("清空视频异常", e)

    def get_selected_paths(self):
        try:
            return list(self.video_paths)
        except Exception as e:
            self._log_error("获取视频路径列表异常", e)
            return []
