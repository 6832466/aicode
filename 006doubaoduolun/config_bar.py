from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from PySide6.QtCore import Signal
from qfluentwidgets import (
    PushButton, PrimaryPushButton, LineEdit, ComboBox,
    BodyLabel, FluentIcon
)

from models import AppConfig, ChatMode


class ConfigBar(QWidget):
    start_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()
    new_chat_requested = Signal()
    connect_browser_requested = Signal()

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._running = False
        self._paused = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(12)

        self._modes = [ChatMode.EXPERT, ChatMode.THINK, ChatMode.FAST]

        row1.addWidget(BodyLabel("前"))
        self.expert_spin = LineEdit()
        self.expert_spin.setText(str(self.config.expert_rounds))
        self.expert_spin.setFixedWidth(60)
        self.expert_spin.setPlaceholderText("轮数")
        self.expert_spin.textChanged.connect(self._on_expert_changed)
        row1.addWidget(self.expert_spin)
        row1.addWidget(BodyLabel("轮使用："))

        self.first_mode_combo = ComboBox()
        for m in self._modes:
            self.first_mode_combo.addItem(m.value)
        self.first_mode_combo.setCurrentIndex(self._modes.index(self.config.first_mode))
        self.first_mode_combo.currentIndexChanged.connect(
            lambda i: setattr(self.config, "first_mode", self._modes[i])
        )
        row1.addWidget(self.first_mode_combo)

        row1.addWidget(BodyLabel("之后切换为："))
        self.second_mode_combo = ComboBox()
        for m in self._modes:
            self.second_mode_combo.addItem(m.value)
        self.second_mode_combo.setCurrentIndex(self._modes.index(self.config.second_mode))
        self.second_mode_combo.currentIndexChanged.connect(
            lambda i: setattr(self.config, "second_mode", self._modes[i])
        )
        row1.addWidget(self.second_mode_combo)

        row1.addWidget(BodyLabel("发送间隔（秒）："))
        self.interval_spin = LineEdit()
        self.interval_spin.setText(str(self.config.send_interval))
        self.interval_spin.setFixedWidth(60)
        self.interval_spin.setPlaceholderText("秒")
        self.interval_spin.textChanged.connect(self._on_interval_changed)
        row1.addWidget(self.interval_spin)

        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(BodyLabel("系统提示词："))
        self.prompt_edit = LineEdit()
        self.prompt_edit.setPlaceholderText("可选，新建对话时发送一次...")
        self.prompt_edit.textChanged.connect(lambda t: setattr(self.config, "system_prompt", t))
        row2.addWidget(self.prompt_edit, 1)

        self.template_btn = PushButton(FluentIcon.CHEVRON_DOWN_MED, "选择模板")
        self.template_btn.clicked.connect(self._show_templates)
        row2.addWidget(self.template_btn)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)

        self.connect_btn = PushButton(FluentIcon.LINK, "连接浏览器")
        self.connect_btn.clicked.connect(self.connect_browser_requested)

        self.new_chat_btn = PushButton(FluentIcon.ADD_TO, "新建对话")
        self.new_chat_btn.clicked.connect(self.new_chat_requested)

        self.start_btn = PrimaryPushButton(FluentIcon.PLAY, "开始执行")
        self.start_btn.clicked.connect(self._on_start)

        self.pause_btn = PushButton(FluentIcon.PAUSE, "暂停")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause)

        self.stop_btn = PushButton(FluentIcon.CLOSE, "停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)

        for btn in (self.connect_btn, self.new_chat_btn, self.start_btn, self.pause_btn, self.stop_btn):
            row3.addWidget(btn)
        row3.addStretch()
        layout.addLayout(row3)

    def _on_expert_changed(self, text: str):
        try:
            v = int(text)
            if 0 <= v <= 999:
                self.config.expert_rounds = v
        except ValueError:
            pass

    def _on_interval_changed(self, text: str):
        try:
            v = int(text)
            if 1 <= v <= 300:
                self.config.send_interval = v
        except ValueError:
            pass

    def _on_start(self):
        self._running = True
        self._paused = False
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.start_requested.emit()

    def _on_pause(self):
        if not self._paused:
            self._paused = True
            self.pause_btn.setText("继续")
            self.pause_btn.setIcon(FluentIcon.PLAY.icon())
            self.pause_requested.emit()
        else:
            self._paused = False
            self.pause_btn.setText("暂停")
            self.pause_btn.setIcon(FluentIcon.PAUSE.icon())
            self.resume_requested.emit()

    def _on_stop(self):
        self._running = False
        self._paused = False
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("暂停")
        self.stop_btn.setEnabled(False)
        self.stop_requested.emit()

    def set_finished(self):
        self._running = False
        self._paused = False
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("暂停")
        self.stop_btn.setEnabled(False)

    def _show_templates(self):
        from qfluentwidgets import RoundMenu, Action
        from template_manager import get_manager
        menu = RoundMenu(parent=self)
        templates = get_manager().all()
        if not templates:
            action = Action("（暂无模板，请在模板管理中添加）")
            action.setEnabled(False)
            menu.addAction(action)
        else:
            for t in templates:
                action = Action(t.name)
                action.triggered.connect(lambda checked, p=t.content: self.prompt_edit.setText(p))
                menu.addAction(action)
        menu.exec(self.template_btn.mapToGlobal(self.template_btn.rect().bottomLeft()))


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(24)

        self.state_label = BodyLabel("当前状态：就绪")
        self.round_label = BodyLabel("当前轮次：0/0")
        self.mode_label = BodyLabel("当前模式：—")
        self.success_label = BodyLabel("成功：0")
        self.fail_label = BodyLabel("失败：0")
        self.pending_label = BodyLabel("待发送：0")
        self.start_time_label = BodyLabel("开始时间：—")

        for lbl in (self.state_label, self.round_label, self.mode_label,
                    self.success_label, self.fail_label, self.pending_label,
                    self.start_time_label):
            layout.addWidget(lbl)
        layout.addStretch()

    def update(self, state: str = None, current_round: int = None, total: int = None,
               mode: str = None, success: int = None, fail: int = None,
               pending: int = None, start_time: str = None):
        if state is not None:
            self.state_label.setText(f"当前状态：{state}")
        if current_round is not None and total is not None:
            self.round_label.setText(f"当前轮次：{current_round}/{total}")
        if mode is not None:
            self.mode_label.setText(f"当前模式：{mode}")
        if success is not None:
            self.success_label.setText(f"成功：{success}")
        if fail is not None:
            self.fail_label.setText(f"失败：{fail}")
        if pending is not None:
            self.pending_label.setText(f"待发送：{pending}")
        if start_time is not None:
            self.start_time_label.setText(f"开始时间：{start_time}")
