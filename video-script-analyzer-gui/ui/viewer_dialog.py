# -*- coding: utf-8 -*-
"""视频 + 剧本并排查看器 — 全 Fluent 控件"""
import os
import sys
import subprocess
import traceback

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QFont, QIcon
from qfluentwidgets import (
    PushButton, PrimaryPushButton, StrongBodyLabel,
    TextEdit, Slider, FluentIcon,
)

from core.analyzer import find_script_path, extract_episode_number


class ViewerDialog(QDialog):
    """视频播放 + 剧本查看"""
    error_occurred = Signal(str)

    def __init__(self, video_path=None, script_path=None, video_paths=None, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.script_path = script_path
        self.video_paths = video_paths or []
        self.current_idx = 0
        self._muted = False

        if video_path and video_path in self.video_paths:
            self.current_idx = self.video_paths.index(video_path)

        self.setWindowTitle("视频剧本查看器")
        self.resize(1440, 860)
        self.setMinimumSize(900, 540)

        icon_path = os.path.join(sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "1.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        try:
            self.setup_ui()
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"查看器初始化异常: {e}\n{tb[:800]}")

        if video_path:
            self.load_video(video_path)

    def setup_ui(self):
        try:
            self._setup_ui_impl()
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"查看器UI初始化异常: {e}\n{tb[:800]}")
            raise

    def _setup_ui_impl(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Nav bar
        nav_bar = QWidget()
        nav_bar.setFixedHeight(38)
        nav_bar.setStyleSheet("background: #fafafa; border-bottom: 1px solid #e0e0e0;")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(10, 0, 10, 0)
        nav_layout.setSpacing(8)

        self.title_label = StrongBodyLabel("视频剧本查看器")
        nav_layout.addWidget(self.title_label)
        nav_layout.addStretch()

        self.prev_btn = PushButton(FluentIcon.LEFT_ARROW, "上一集")
        self.prev_btn.setFixedHeight(36)
        self.prev_btn.clicked.connect(self._prev_video)
        nav_layout.addWidget(self.prev_btn)

        self.next_btn = PushButton(FluentIcon.RIGHT_ARROW, "下一集")
        self.next_btn.setFixedHeight(36)
        self.next_btn.clicked.connect(self._next_video)
        nav_layout.addWidget(self.next_btn)

        main_layout.addWidget(nav_bar)

        # Split view
        self.splitter = QSplitter(Qt.Horizontal)

        # ── Left: Video ──
        video_panel = QWidget()
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(8, 2, 4, 4)
        video_layout.setSpacing(4)

        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #000; border-radius: 8px;")
        video_layout.addWidget(self.video_widget)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.play_btn = PrimaryPushButton(FluentIcon.PLAY, "播放")
        self.play_btn.setFixedHeight(32)
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.time_label = StrongBodyLabel("00:00 / 00:00")
        controls.addWidget(self.time_label)

        self.seek_slider = Slider(Qt.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.sliderMoved.connect(self._seek)
        controls.addWidget(self.seek_slider)

        self.volume_btn = PushButton(FluentIcon.VOLUME, "")
        self.volume_btn.clicked.connect(self._toggle_mute)
        controls.addWidget(self.volume_btn)

        video_layout.addLayout(controls)

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_state_changed)

        self.splitter.addWidget(video_panel)

        # ── Right: Script ──
        script_panel = QWidget()
        script_layout = QVBoxLayout(script_panel)
        script_layout.setContentsMargins(4, 0, 8, 4)

        script_title = StrongBodyLabel("分镜剧本")
        script_title.setFont(QFont("Microsoft YaHei", 14))
        script_layout.addWidget(script_title)

        self.script_editor = TextEdit()
        self.script_editor.setReadOnly(True)
        self.script_editor.setStyleSheet("""
            TextEdit {
                background-color: #fafafa; color: #1d1d1f;
                border: 1px solid #ddd; border-radius: 6px;
                padding: 12px;
                font-family: 'Microsoft YaHei', 'Consolas', monospace;
                font-size: 14px;
            }
        """)
        script_layout.addWidget(self.script_editor)

        self.splitter.addWidget(script_panel)
        self.splitter.setSizes([720, 720])

        main_layout.addWidget(self.splitter)

        self._update_nav_buttons()

    def load_video(self, video_path):
        try:
            self.video_path = video_path
            ep = extract_episode_number(os.path.basename(video_path))
            ep_text = f"第{ep}集" if ep else os.path.basename(video_path)
            self.setWindowTitle(f"视频剧本查看器 - {ep_text}")
            self.title_label.setText(f"  {ep_text}")

            self.media_player.setSource(QUrl.fromLocalFile(video_path))
            self.media_player.pause()

            sp = find_script_path(video_path)
            if sp:
                self.script_path = sp
                with open(sp, "r", encoding="utf-8") as f:
                    self.script_editor.setPlainText(f.read())
            else:
                self.script_path = None
                self.script_editor.setPlainText("该视频尚未分析，请先点击「分析」生成剧本。")

            self._update_nav_buttons()
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"加载视频异常: {e}\n{tb[:800]}")

    def _toggle_play(self):
        try:
            if self.media_player.playbackState() == QMediaPlayer.PlayingState:
                self.media_player.pause()
            else:
                self.media_player.play()
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"播放/暂停切换异常: {e}\n{tb[:800]}")

    def _seek(self, value):
        try:
            if self.media_player.duration() > 0:
                pos = int(value / 1000.0 * self.media_player.duration())
                self.media_player.setPosition(pos)
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"进度拖动异常: {e}\n{tb[:800]}")

    def _toggle_mute(self):
        try:
            self._muted = not self._muted
            self.audio_output.setMuted(self._muted)
            self.volume_btn.setIcon(FluentIcon.MUTE if self._muted else FluentIcon.VOLUME)
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"静音切换异常: {e}\n{tb[:800]}")

    def _on_position_changed(self, pos):
        try:
            dur = self.media_player.duration()
            if dur > 0 and not self.seek_slider.isSliderDown():
                self.seek_slider.setValue(int(pos / dur * 1000))
            self.time_label.setText(f"{self._fmt(pos)} / {self._fmt(dur)}")
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"位置更新异常: {e}\n{tb[:800]}")

    def _on_duration_changed(self, dur):
        try:
            self.time_label.setText(f"00:00 / {self._fmt(dur)}")
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"时长更新异常: {e}\n{tb[:800]}")

    def _on_state_changed(self, state):
        try:
            if state == QMediaPlayer.PlayingState:
                self.play_btn.setText("暂停")
                self.play_btn.setIcon(FluentIcon.PAUSE)
            else:
                self.play_btn.setText("播放")
                self.play_btn.setIcon(FluentIcon.PLAY)
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"播放状态更新异常: {e}\n{tb[:800]}")

    def _fmt(self, ms):
        try:
            s = ms // 1000
            m, s = divmod(s, 60)
            h, m = divmod(m, 60)
            if h:
                return f"{h}:{m:02d}:{s:02d}"
            return f"{m:02d}:{s:02d}"
        except Exception:
            return "--:--"

    def _prev_video(self):
        try:
            if not self.video_paths:
                return
            self.current_idx = (self.current_idx - 1) % len(self.video_paths)
            self.load_video(self.video_paths[self.current_idx])
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"上一集切换异常: {e}\n{tb[:800]}")

    def _next_video(self):
        try:
            if not self.video_paths:
                return
            self.current_idx = (self.current_idx + 1) % len(self.video_paths)
            self.load_video(self.video_paths[self.current_idx])
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"下一集切换异常: {e}\n{tb[:800]}")

    def _update_nav_buttons(self):
        try:
            total = len(self.video_paths)
            self.prev_btn.setEnabled(total > 1 and self.current_idx > 0)
            self.next_btn.setEnabled(total > 1 and self.current_idx < total - 1)
        except Exception as e:
            tb = traceback.format_exc()
            self.error_occurred.emit(f"导航按钮更新异常: {e}\n{tb[:800]}")

    def closeEvent(self, event):
        try:
            self.media_player.stop()
        except Exception:
            pass
        super().closeEvent(event)
