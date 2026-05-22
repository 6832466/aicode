# -*- coding: utf-8 -*-
"""视频卡片 — Fluent CardWidget"""
import os
import sys
import traceback
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
)
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor
from qfluentwidgets import (
    CardWidget, PushButton, PrimaryPushButton,
    StrongBodyLabel, CaptionLabel, FluentIcon,
)

from core.analyzer import extract_episode_number, find_script_path
from core.compressor import extract_thumbnail, get_video_duration, get_ffmpeg_path


class ThumbnailWidget(QWidget):
    """自定义缩略图组件，直接在 paintEvent 中绘制"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._text = "⏳ 加载中..."
        self.setFixedSize(250, 250)

    def setThumbnail(self, pixmap):
        self._pixmap = pixmap
        self._text = ""
        self.update()

    def setStatusText(self, text):
        self._pixmap = None
        self._text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f2f2f7"))
        painter.drawRoundedRect(QRectF(0, 0, w, h), 6, 6)
        painter.setPen(QColor("#e0e0e0"))
        painter.drawLine(0, h - 1, w, h - 1)

        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        elif self._text:
            painter.setPen(QColor("#888888"))
            painter.setFont(QFont("Microsoft YaHei", 13))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self._text)
        painter.end()


BTN_RETRY = """
PushButton {
    color: #d13438; border: 1px solid #d13438;
    border-radius: 5px; padding: 4px 10px; font-size: 11px;
}
PushButton:hover { background: #ffe5e5; }
"""

BTN_DANGER = """
TransparentPushButton { color: #999; }
TransparentPushButton:hover { color: #e81123; }
"""


class VideoCard(CardWidget):
    preview_clicked = Signal(str)
    open_script_clicked = Signal(str)
    analyze_clicked = Signal(str)
    delete_clicked = Signal(str)
    stop_clicked = Signal(str)
    error_occurred = Signal(str)

    def _log_error(self, context, exc):
        tb = traceback.format_exc()
        self.error_occurred.emit(f"{context}: {exc}\n{tb[:800]}")

    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self._stop_pending = False
        self.setFixedSize(250, 480)
        self.setBorderRadius(8)

        try:
            self._setup_ui()
            self._update_display()
        except Exception as e:
            self._log_error("初始化视频卡异常", e)

    def _setup_ui(self):
        try:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 6)
            layout.setSpacing(0)

            # Thumbnail
            self._thumb_label = ThumbnailWidget()
            layout.addWidget(self._thumb_label)

            # Card body
            body = QWidget()
            body.setStyleSheet("background: transparent;")
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(14, 10, 14, 4)
            body_layout.setSpacing(4)

            ep = extract_episode_number(os.path.basename(self.video_path))
            name = f"第{ep}集" if ep else os.path.basename(self.video_path)
            name_label = StrongBodyLabel(name)
            name_label.setFont(QFont("Microsoft YaHei", 12))
            body_layout.addWidget(name_label)

            self._info_label = CaptionLabel()
            body_layout.addWidget(self._info_label)

            self._status_label = CaptionLabel()
            body_layout.addWidget(self._status_label)

            body_layout.addSpacing(8)

            # Button row
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)

            self._preview_btn = PushButton(FluentIcon.PLAY, "预览")
            self._preview_btn.setFixedHeight(28)
            self._preview_btn.clicked.connect(lambda: self.preview_clicked.emit(self.video_path))
            btn_row.addWidget(self._preview_btn)

            self._script_btn = PushButton(FluentIcon.DOCUMENT, "剧本")
            self._script_btn.setFixedHeight(28)
            self._script_btn.clicked.connect(
                lambda: self.open_script_clicked.emit(find_script_path(self.video_path) or ""))
            btn_row.addWidget(self._script_btn)

            btn_row.addStretch()

            from qfluentwidgets import TransparentPushButton
            self._delete_btn = TransparentPushButton(FluentIcon.CLOSE, "")
            self._delete_btn.setStyleSheet(BTN_DANGER)
            self._delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.video_path))
            btn_row.addWidget(self._delete_btn)

            body_layout.addLayout(btn_row)
            body_layout.addSpacing(6)

            self._analyze_btn = PrimaryPushButton("开始分析")
            self._analyze_btn.clicked.connect(self._on_analyze_btn_clicked)
            body_layout.addWidget(self._analyze_btn)

            layout.addWidget(body)
        except Exception as e:
            self._log_error("初始化视频卡UI异常", e)
            raise

    def _update_display(self):
        try:
            size_mb = os.path.getsize(self.video_path) / (1024 * 1024)
            size_str = f"{size_mb:.1f} MB"
            dur_str = ""
            try:
                ffmpeg = get_ffmpeg_path()
                dur = get_video_duration(ffmpeg, self.video_path)
                if dur and dur > 0:
                    m, s = divmod(int(dur), 60)
                    h, m = divmod(m, 60)
                    dur_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            except Exception as e:
                self._log_error("获取视频时长异常", e)
            parts = [size_str]
            if dur_str:
                parts.append(dur_str)
            self._info_label.setText(" · ".join(parts))

            sp = find_script_path(self.video_path)
            if sp:
                self.set_status("done", "已完成", 100)
                self.set_script_exists(True)
            else:
                self.set_status("idle", "就绪", 0)
                self.set_script_exists(False)
        except Exception as e:
            self._log_error("更新显示异常", e)

    def load_thumbnail(self, thumb_path=None):
        try:
            if thumb_path is None:
                thumb_path = extract_thumbnail(self.video_path)
            if thumb_path and os.path.exists(thumb_path):
                src = QPixmap(thumb_path)
                if not src.isNull():
                    self._thumb_label.setThumbnail(src)
                else:
                    self._thumb_label.setStatusText("预览失败")
                try:
                    os.remove(thumb_path)
                except Exception:
                    pass
            else:
                self._thumb_label.setStatusText("暂无预览")
        except Exception as e:
            self._log_error("加载缩略图异常", e)
            self._thumb_label.setStatusText("加载失败")

    def set_script_exists(self, exists):
        try:
            self._script_btn.setEnabled(exists)
            if exists:
                self.set_status("done", "已完成", 100)
                if self._analyze_btn:
                    self._analyze_btn.setVisible(False)
        except Exception as e:
            self._log_error("设置剧本状态异常", e)

    def _on_analyze_btn_clicked(self):
        try:
            if self._stop_pending:
                return
            status = self._status_label.text()
            if ("◉" in status or "●" in status) and "分析" in status:
                self._stop_pending = True
                self._analyze_btn.setText("正在停止…")
                self._analyze_btn.setEnabled(False)
                self.stop_clicked.emit(self.video_path)
            else:
                self.analyze_clicked.emit(self.video_path)
        except Exception as e:
            self._log_error("分析按钮点击异常", e)

    def set_status(self, status, message="", percent=0):
        try:
            colors = {"idle": "#888", "compressing": "#0078d4", "analyzing": "#0078d4",
                      "done": "#107c10", "failed": "#d13438"}
            dots = {"idle": "●", "compressing": "◉", "analyzing": "◉",
                    "done": "✔", "failed": "✕"}
            color = colors.get(status, "#888")
            dot = dots.get(status, "●")

            text = f"{dot} {message}"
            self._status_label.setText(text)
            self._status_label.setStyleSheet(f"color: {color}; font-size: 11px;")

            # 失败状态：浅红色边框
            if status == "failed":
                self.setStyleSheet("VideoCard { border: 2px solid #f4a2a2; border-radius: 8px; }")
            else:
                self.setStyleSheet("")

            if self._analyze_btn:
                self._analyze_btn.setVisible(status != "done")
                if status in ("compressing", "analyzing"):
                    self._stop_pending = False
                    self._analyze_btn.setText("停止")
                    self._analyze_btn.setEnabled(True)
                    self._analyze_btn.setStyleSheet("""
                        QPushButton {
                            background: #d13438; color: white;
                            border: none; border-radius: 6px;
                            padding: 8px 16px; font-size: 14px; font-weight: 500;
                        }
                        QPushButton:hover { background: #e04346; }
                        QPushButton:pressed { background: #c02f33; }
                    """)
                else:
                    self._stop_pending = False
                    self._analyze_btn.setText("开始分析")
                    self._analyze_btn.setEnabled(True)
                    self._analyze_btn.setStyleSheet("""
                        QPushButton {
                            background: #0078d4; color: white;
                            border: none; border-radius: 6px;
                            padding: 8px 16px; font-size: 14px; font-weight: 500;
                        }
                        QPushButton:hover { background: #1a88e0; }
                        QPushButton:pressed { background: #006cbf; }
                    """)
        except Exception as e:
            self._log_error("设置状态异常", e)
