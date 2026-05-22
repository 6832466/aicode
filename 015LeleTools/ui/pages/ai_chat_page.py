"""
AI多轮对话 — ChatGPT风格对话界面 + 会话管理
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (
    CardWidget, LineEdit, PushButton, PrimaryPushButton,
    ComboBox, EditableComboBox, TextEdit, StrongBodyLabel,
    CaptionLabel, BodyLabel, ListWidget, InfoBar, InfoBarPosition,
    FluentIcon,
)

from app.config_manager import ConfigManager
from core.chat_session import SessionManager
from models.chat_message import ChatSession
from services.ai_service import AIService
from ui.components.chat_widget import ChatWidget


class AIChatPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ai_chat_page")
        self._parent = parent
        self.config = ConfigManager()
        self.session_mgr = SessionManager()
        self._current_session: ChatSession | None = None
        self._stream_worker = None
        self._is_processing = False
        self._init_ui()
        self._load_config()
        self._load_sessions()

    # ═══════════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════════

    def _init_ui(self):
        splitter = QSplitter(Qt.Horizontal)

        # ── 左侧：会话列表 ──
        left = QWidget()
        left.setFixedWidth(220)
        left_ly = QVBoxLayout(left)
        left_ly.setContentsMargins(8, 16, 8, 16)
        left_ly.setSpacing(8)

        left_header = StrongBodyLabel("会话列表")
        left_header.setStyleSheet("font-size: 16px;")
        left_ly.addWidget(left_header)

        self.session_list = ListWidget()
        self.session_list.itemClicked.connect(self._on_session_clicked)
        left_ly.addWidget(self.session_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_new = PushButton("新建")
        self.btn_new.clicked.connect(self._on_new_session)
        btn_row.addWidget(self.btn_new)

        self.btn_rename = PushButton("重命名")
        self.btn_rename.clicked.connect(self._on_rename_session)
        btn_row.addWidget(self.btn_rename)

        self.btn_del = PushButton("删除")
        self.btn_del.clicked.connect(self._on_delete_session)
        btn_row.addWidget(self.btn_del)

        left_ly.addLayout(btn_row)
        splitter.addWidget(left)

        # ── 右侧：对话区 ──
        right = QWidget()
        right_ly = QVBoxLayout(right)
        right_ly.setContentsMargins(0, 10, 16, 16)
        right_ly.setSpacing(8)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        toolbar.addWidget(CaptionLabel("模型:"))
        self.model_combo = EditableComboBox()
        self.model_combo.setMinimumWidth(160)
        toolbar.addWidget(self.model_combo)

        toolbar.addStretch()

        toolbar.addWidget(CaptionLabel("系统提示词:"))
        self.system_prompt_input = LineEdit()
        self.system_prompt_input.setPlaceholderText("设置系统提示词...")
        self.system_prompt_input.setMinimumWidth(200)
        toolbar.addWidget(self.system_prompt_input, 1)

        self.btn_apply_prompt = PushButton("应用")
        self.btn_apply_prompt.clicked.connect(self._on_apply_prompt)
        toolbar.addWidget(self.btn_apply_prompt)

        right_ly.addLayout(toolbar)

        # 对话组件
        self.chat_widget = ChatWidget()
        self.chat_widget.message_sent.connect(self._on_message_sent)
        self.chat_widget.btn_send.clicked.connect(self._chat_widget_send)
        self.chat_widget.btn_clear.clicked.connect(self._on_clear_chat)
        right_ly.addWidget(self.chat_widget, 1)

        splitter.addWidget(right)
        splitter.setSizes([220, 800])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

    # ═══════════════════════════════════════════
    #  会话管理
    # ═══════════════════════════════════════════

    def _load_sessions(self):
        self.session_list.clear()
        for s in self.session_mgr.sessions:
            self.session_list.addItem(s.name)

    def _switch_session(self, session: ChatSession):
        self._cancel_stream()
        self._current_session = session
        self.chat_widget.clear_messages()
        for msg in session.messages:
            self.chat_widget.add_message(msg.role, msg.content, msg.timestamp)
        self.system_prompt_input.setText(session.system_prompt)
        if session.model:
            self.model_combo.setCurrentText(session.model)

    def _on_session_clicked(self, item):
        idx = self.session_list.currentRow()
        if 0 <= idx < len(self.session_mgr.sessions):
            session = self.session_mgr.sessions[idx]
            self._switch_session(session)

    def _load_config(self):
        ep = self.config.get_default_endpoint()
        self.model_combo.clear()
        self.model_combo.addItems(["deepseek-v4-pro", "deepseek-v4-flash"])
        if ep:
            self.model_combo.setCurrentText(ep.model)

    def _on_new_session(self):
        self._cancel_stream()
        ep = self.config.get_default_endpoint()
        model = ep.model if ep else ""
        session = self.session_mgr.create(model=model)
        self._load_sessions()
        self._switch_session(session)

    def _on_rename_session(self):
        if not self._current_session:
            return
        name, ok = QInputDialog.getText(
            self, "重命名会话", "新名称:",
            text=self._current_session.name,
        )
        if ok and name.strip():
            self.session_mgr.rename(self._current_session.id, name.strip())
            self._load_sessions()
            self._current_session.name = name.strip()

    def _on_delete_session(self):
        if not self._current_session:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除会话「{self._current_session.name}」吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.session_mgr.delete(self._current_session.id)
            self._current_session = None
            self.chat_widget.clear_messages()
            self._load_sessions()

    # ═══════════════════════════════════════════
    #  对话处理
    # ═══════════════════════════════════════════

    def _on_apply_prompt(self):
        if self._current_session:
            self._current_session.system_prompt = self.system_prompt_input.text().strip()
            self.session_mgr.save_session(self._current_session)

    def _chat_widget_send(self):
        text = self.chat_widget.chat_input.toPlainText().strip()
        if text:
            self.chat_widget._send()

    def _on_message_sent(self, text: str):
        """用户发送消息后触发 AI 回复"""
        if self._is_processing:
            return

        # 确保有当前会话
        if not self._current_session:
            self._on_new_session()
            # 手动添加消息到新会话
            self._current_session.add_message("user", text)
        else:
            self._current_session.add_message("user", text)

        ep = self.config.get_default_endpoint()
        if not ep:
            self._show_error("未配置 API 端点，请先在全局设置中添加")
            return

        model = self.model_combo.currentText().strip() or ep.model
        if self._current_session:
            self._current_session.model = model
            self._current_session.system_prompt = self.system_prompt_input.text().strip()

        api_messages = self._current_session.get_api_messages() if self._current_session else [
            {"role": "system", "content": self._current_session.system_prompt if self._current_session else ""},
            {"role": "user", "content": text},
        ]

        self._is_processing = True
        self.chat_widget.btn_send.setEnabled(False)
        self.chat_widget.start_stream_message()

        self._stream_worker = AIService.process(
            system_prompt="",
            user_content="",
            model=model,
            stream=True,
            timeout=self.config.timeout,
            messages=api_messages,
        )
        self._stream_worker.chunk_ready.connect(self._on_stream_chunk)
        self._stream_worker.finished.connect(self._on_stream_finished)
        self._stream_worker.start()

    def _on_stream_chunk(self, chunk: str):
        self.chat_widget.append_stream_chunk(chunk)

    def _on_stream_finished(self, ok: bool, msg: str):
        self._is_processing = False
        self.chat_widget.btn_send.setEnabled(True)

        if ok:
            content = self.chat_widget.stream_content
            self.chat_widget.finish_stream()
            if self._current_session:
                self._current_session.add_message("assistant", content)
                self.session_mgr.save_session(self._current_session)
        else:
            self.chat_widget.finish_stream()
            if msg:
                self.chat_widget.add_message("assistant", f"[错误] {msg}")

    def _on_clear_chat(self):
        if self._current_session:
            self._current_session.messages = []
            self.session_mgr.save_session(self._current_session)

    def _cancel_stream(self):
        if self._stream_worker and self._stream_worker.isRunning():
            self._stream_worker.cancel()
            self._stream_worker.quit()
            self._stream_worker.wait(3000)
        self._stream_worker = None
        self._is_processing = False
        self.chat_widget.btn_send.setEnabled(True)

    # ═══════════════════════════════════════════
    #  辅助
    # ═══════════════════════════════════════════

    def _show_error(self, msg: str):
        InfoBar.error(
            title="提示", content=msg,
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000, parent=self,
        )
