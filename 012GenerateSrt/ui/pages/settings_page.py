"""
设置页 — 模型路径、处理参数、输出配置
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
from qfluentwidgets import (
    ScrollArea, CardWidget, SettingCardGroup,
    LineEdit, PushButton, ComboBox, SpinBox,
    BodyLabel, CaptionLabel, StrongBodyLabel,
    FluentIcon, InfoBar, InfoBarPosition, SwitchButton,
)

from app.config import (
    models_dir, data_dir,
    MAX_SEGMENT_SECONDS, SEGMENT_OVERLAP_SECONDS,
    MAX_LINE_CHARS, MIN_SPEECH_SECONDS,
)


class SettingsPage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._init_ui()

    def _init_ui(self):
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # ── 页面标题 ──
        title = StrongBodyLabel("设置")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)

        # ── 模型配置 ──
        model_group = SettingCardGroup("模型配置", parent=container)

        model_path_card = CardWidget()
        model_path_layout = QHBoxLayout(model_path_card)
        model_path_layout.setContentsMargins(16, 10, 16, 10)
        model_label = BodyLabel("模型目录")
        self.model_path_edit = LineEdit()
        self.model_path_edit.setText(str(models_dir()))
        self.model_path_edit.setReadOnly(True)
        model_path_layout.addWidget(model_label)
        model_path_layout.addWidget(self.model_path_edit, 1)
        model_browse_btn = PushButton("浏览")
        model_browse_btn.clicked.connect(self._browse_model_dir)
        model_path_layout.addWidget(model_browse_btn)
        model_group.addSettingCard(model_path_card)

        model_hint = CaptionLabel(
            "SenseVoiceSmall 模型将存放在此目录。首次使用需下载 (~300MB)，"
            "也可手动下载离线包后解压到此目录。"
        )
        model_hint.setWordWrap(True)
        model_hint.setStyleSheet("color: #888888; padding: 4px 16px;")
        model_group.addSettingCard(model_hint)

        layout.addWidget(model_group)

        # ── 处理参数 ──
        proc_group = SettingCardGroup("处理参数", parent=container)

        seg_card = CardWidget()
        seg_layout = QHBoxLayout(seg_card)
        seg_layout.setContentsMargins(16, 10, 16, 10)
        seg_layout.addWidget(BodyLabel("单段最大时长 (秒)"))
        self.seg_spin = SpinBox()
        self.seg_spin.setRange(10, 60)
        self.seg_spin.setValue(MAX_SEGMENT_SECONDS)
        seg_layout.addWidget(self.seg_spin)
        seg_layout.addStretch()
        proc_group.addSettingCard(seg_card)

        overlap_card = CardWidget()
        overlap_layout = QHBoxLayout(overlap_card)
        overlap_layout.setContentsMargins(16, 10, 16, 10)
        overlap_layout.addWidget(BodyLabel("段间重叠 (秒)"))
        self.overlap_spin = SpinBox()
        self.overlap_spin.setRange(0, 5)
        self.overlap_spin.setValue(int(SEGMENT_OVERLAP_SECONDS))
        overlap_layout.addWidget(self.overlap_spin)
        overlap_layout.addStretch()
        proc_group.addSettingCard(overlap_card)

        min_speech_card = CardWidget()
        min_speech_layout = QHBoxLayout(min_speech_card)
        min_speech_layout.setContentsMargins(16, 10, 16, 10)
        min_speech_layout.addWidget(BodyLabel("最小语音段 (秒)"))
        self.min_speech_spin = SpinBox()
        self.min_speech_spin.setRange(0, 3)
        self.min_speech_spin.setValue(int(MIN_SPEECH_SECONDS))
        min_speech_layout.addWidget(self.min_speech_spin)
        min_speech_layout.addStretch()
        proc_group.addSettingCard(min_speech_card)

        layout.addWidget(proc_group)

        # ── 字幕输出 ──
        output_group = SettingCardGroup("字幕输出", parent=container)

        line_card = CardWidget()
        line_layout = QHBoxLayout(line_card)
        line_layout.setContentsMargins(16, 10, 16, 10)
        line_layout.addWidget(BodyLabel("每行最大字数"))
        self.line_spin = SpinBox()
        self.line_spin.setRange(10, 50)
        self.line_spin.setValue(MAX_LINE_CHARS)
        line_layout.addWidget(self.line_spin)
        line_layout.addStretch()
        output_group.addSettingCard(line_card)

        format_card = CardWidget()
        format_layout = QHBoxLayout(format_card)
        format_layout.setContentsMargins(16, 10, 16, 10)
        format_layout.addWidget(BodyLabel("输出格式"))
        self.format_combo = ComboBox()
        self.format_combo.addItems(["SRT (标准字幕)", "TXT (纯文本)", "VTT (Web 标准)"])
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        output_group.addSettingCard(format_card)

        event_card = CardWidget()
        event_layout = QHBoxLayout(event_card)
        event_layout.setContentsMargins(16, 10, 16, 10)
        event_layout.addWidget(BodyLabel("标注音频事件 (掌声/笑声)"))
        self.event_switch = SwitchButton()
        self.event_switch.setChecked(True)
        event_layout.addWidget(self.event_switch)
        event_layout.addStretch()
        output_group.addSettingCard(event_card)

        layout.addWidget(output_group)

        # FFmpeg 路径
        ffmpeg_group = SettingCardGroup("FFmpeg", parent=container)
        ffmpeg_card = CardWidget()
        ffmpeg_layout = QHBoxLayout(ffmpeg_card)
        ffmpeg_layout.setContentsMargins(16, 10, 16, 10)
        ffmpeg_layout.addWidget(BodyLabel("FFmpeg 路径"))
        self.ffmpeg_edit = LineEdit()
        self.ffmpeg_edit.setPlaceholderText("自动检测 (系统 PATH 或内置)")
        ffmpeg_layout.addWidget(self.ffmpeg_edit, 1)
        ffmpeg_browse = PushButton("浏览")
        ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        ffmpeg_layout.addWidget(ffmpeg_browse)
        ffmpeg_group.addSettingCard(ffmpeg_card)
        layout.addWidget(ffmpeg_group)

        layout.addStretch()

    def _browse_model_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择模型存放目录")
        if folder:
            self.model_path_edit.setText(folder)

    def _browse_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 ffmpeg.exe", "", "ffmpeg.exe (ffmpeg.exe)",
        )
        if path:
            self.ffmpeg_edit.setText(path)

    def get_settings(self) -> dict:
        """获取所有设置值"""
        return {
            "model_dir": self.model_path_edit.text(),
            "max_segment": self.seg_spin.value(),
            "segment_overlap": self.overlap_spin.value(),
            "min_speech": self.min_speech_spin.value(),
            "max_line_chars": self.line_spin.value(),
            "output_format": self.format_combo.currentIndex(),
            "mark_events": self.event_switch.isChecked(),
            "ffmpeg_path": self.ffmpeg_edit.text(),
        }