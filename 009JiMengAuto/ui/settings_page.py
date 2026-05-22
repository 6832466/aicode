"""设置页面 - 即梦配置"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QFileDialog,
)
from qfluentwidgets import (
    CardWidget, BodyLabel, CaptionLabel, ComboBox, SwitchButton,
    LineEdit, PushButton, PrimaryPushButton, FluentIcon,
    ScrollArea, InfoBar, StrongBodyLabel,
)

from core.material_matcher import MaterialMatcher
from config.settings_manager import JMConfig
from utils.theme import THEME


class SettingsPage(QWidget):
    """设置页面"""

    def __init__(self, config: JMConfig, material_matcher: MaterialMatcher, parent=None):
        super().__init__(parent)
        self.config = config
        self.material_matcher = material_matcher

        self._init_ui()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 使用 ScrollArea 包裹设置内容
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)

        container = QWidget()
        container.setAttribute(Qt.WA_StyledBackground)
        scroll.setWidget(container)
        expand_layout = QVBoxLayout(container)
        expand_layout.setSpacing(12)
        expand_layout.setContentsMargins(0, 0, 0, 0)

        # ── 生成设置 ──
        gen_card = CardWidget(container)
        gen_layout = QVBoxLayout(gen_card)
        gen_layout.setContentsMargins(16, 16, 16, 16)
        gen_layout.setSpacing(12)

        gen_title = StrongBodyLabel("生成设置")
        gen_title.setStyleSheet(f"font-size: 14px;")
        gen_layout.addWidget(gen_title)

        # 任务间隔
        self._interval_edit = LineEdit()
        self._interval_edit.setText(str(self.config.interval_seconds.value))
        self._interval_edit.setFixedWidth(80)
        self._add_setting_row(gen_layout, "任务间隔（秒）", self._interval_edit)

        # 重试次数
        self._retry_edit = LineEdit()
        self._retry_edit.setText(str(self.config.retry_times.value))
        self._retry_edit.setFixedWidth(80)
        self._add_setting_row(gen_layout, "重试次数", self._retry_edit)

        expand_layout.addWidget(gen_card)

        # ── 下载设置 ──
        dl_card = CardWidget(container)
        dl_layout = QVBoxLayout(dl_card)
        dl_layout.setContentsMargins(16, 16, 16, 16)
        dl_layout.setSpacing(12)

        dl_title = StrongBodyLabel("下载设置")
        dl_title.setStyleSheet(f"font-size: 14px;")
        dl_layout.addWidget(dl_title)

        # 保存目录
        self._save_dir_edit = LineEdit()
        self._save_dir_edit.setText(self.config.save_dir.value)
        self._save_dir_edit.setFixedWidth(320)
        self._add_setting_row(dl_layout, "保存目录",
                              self._save_dir_edit,
                              self._create_browse_btn("folder"))

        # 最大并发数
        self._concurrent_combo = ComboBox()
        for i in range(1, 9):
            self._concurrent_combo.addItem(str(i))
        self._concurrent_combo.setCurrentText(str(self.config.max_concurrent.value))
        self._concurrent_combo.setFixedWidth(80)
        self._add_setting_row(dl_layout, "最大并发数", self._concurrent_combo)

        # 断点续传
        self._resume_switch = SwitchButton()
        self._resume_switch.setChecked(self.config.resume_enabled.value)
        self._add_setting_row(dl_layout, "断点续传", self._resume_switch)

        expand_layout.addWidget(dl_card)

        # ── 数据文件 ──
        data_card = CardWidget(container)
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(16, 16, 16, 16)
        data_layout.setSpacing(12)

        data_title = StrongBodyLabel("数据文件")
        data_title.setStyleSheet(f"font-size: 14px;")
        data_layout.addWidget(data_title)

        # 提示词表
        self._prompt_path_edit = LineEdit()
        self._prompt_path_edit.setText(self.config.prompt_excel_path.value)
        self._prompt_path_edit.setFixedWidth(320)
        self._add_setting_row(data_layout, "提示词表",
                              self._prompt_path_edit,
                              self._create_browse_btn("file"))

        # 人物对照表
        self._char_path_edit = LineEdit()
        self._char_path_edit.setText(self.config.character_excel_path.value)
        self._char_path_edit.setFixedWidth(320)
        self._add_setting_row(data_layout, "人物对照表",
                              self._char_path_edit,
                              self._create_browse_btn("char"))

        expand_layout.addWidget(data_card)

        # ── 保存按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_reset = PushButton(FluentIcon.HISTORY, "恢复默认")
        self._btn_reset.clicked.connect(self._on_reset_default)
        self._btn_save = PrimaryPushButton(FluentIcon.SAVE, "保存设置")
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_reset)
        btn_row.addWidget(self._btn_save)
        expand_layout.addLayout(btn_row)

        expand_layout.addStretch()

        layout.addWidget(scroll)

    def _add_setting_row(self, layout: QVBoxLayout, label: str, *widgets):
        """添加一行设置"""
        row = QHBoxLayout()
        row.addWidget(BodyLabel(label))
        row.addStretch()
        for w in widgets:
            row.addWidget(w)
        layout.addLayout(row)

    def _create_browse_btn(self, mode: str) -> PushButton:
        """创建浏览按钮"""
        btn = PushButton("浏览...")
        btn.clicked.connect(lambda: self._on_browse(mode))
        return btn

    def _on_browse(self, mode: str):
        """浏览文件或目录"""
        if mode == "folder":
            path = QFileDialog.getExistingDirectory(self, "选择保存目录")
            if path:
                self._save_dir_edit.setText(path)
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择文件", "", "Excel (*.xlsx *.xls)"
            )
            if path:
                if mode == "file":
                    self._prompt_path_edit.setText(path)
                else:
                    self._char_path_edit.setText(path)

    def _on_save(self):
        """保存设置"""
        try:
            self.config.interval_seconds.value = int(self._interval_edit.text())
            self.config.retry_times.value = int(self._retry_edit.text())
            self.config.save_dir.value = self._save_dir_edit.text()
            self.config.max_concurrent.value = int(self._concurrent_combo.currentText())
            self.config.resume_enabled.value = self._resume_switch.isChecked()
            self.config.prompt_excel_path.value = self._prompt_path_edit.text()
            self.config.character_excel_path.value = self._char_path_edit.text()
            self.config.save()
            InfoBar.success("已保存", "设置已保存成功", parent=self, duration=2000)
        except Exception as e:
            InfoBar.error("保存失败", str(e), parent=self, duration=3000)

    def _on_reset_default(self):
        """恢复默认设置"""
        from qfluentwidgets import qconfig
        qconfig.reset(self.config)
        # 刷新 UI
        self._interval_edit.setText(str(self.config.interval_seconds.value))
        self._retry_edit.setText(str(self.config.retry_times.value))
        self._save_dir_edit.setText(self.config.save_dir.value)
        self._concurrent_combo.setCurrentText(str(self.config.max_concurrent.value))
        self._resume_switch.setChecked(self.config.resume_enabled.value)
        self._prompt_path_edit.setText(self.config.prompt_excel_path.value)
        self._char_path_edit.setText(self.config.character_excel_path.value)
        InfoBar.info("已恢复", "已恢复默认设置", parent=self, duration=2000)
