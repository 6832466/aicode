import asyncio
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QTextCursor, QFont
from PySide6.QtWidgets import (
    QFileDialog, QMenu, QWidget, QSplitter, QVBoxLayout, QHBoxLayout
)
from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, StrongBodyLabel,
    PushButton, ComboBox, LineEdit, TextEdit,
    InfoBar, InfoBarPosition, TabBar, MessageDialog,
    RoundMenu,
)

from app.config import chat_history_dir, FREE_MODELS, short_model_name
from app.models import ChatSession, ChatMessage, ChatRole, ModelConfig, load_models_config
from app.modelscope_client import get_client
from ui.widgets.log_widget import LogWidget

logger = logging.getLogger(__name__)

# Markdown CSS for rendering
MARKDOWN_CSS = """
<style>
body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.6; color: #333; }
pre { background-color: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }
code { background-color: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: Consolas, monospace; }
pre code { background-color: transparent; padding: 0; }
h1, h2, h3 { margin-top: 16px; margin-bottom: 8px; }
ul, ol { padding-left: 24px; }
blockquote { border-left: 3px solid #ddd; margin: 0; padding-left: 16px; color: #666; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
th { background-color: #f5f5f5; }
</style>
"""


def render_markdown(text: str) -> str:
    """Convert markdown to HTML with syntax highlighting."""
    try:
        import markdown
        html = markdown.markdown(
            text,
            extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists']
        )
        return MARKDOWN_CSS + f"<body>{html}</body>"
    except ImportError:
        # Fallback: basic formatting
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace("\n", "<br>")
        return f"<body><pre style='white-space: pre-wrap;'>{text}</pre></body>"


class ChatDisplayWidget(TextEdit):
    """Custom text edit with markdown rendering support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet(
            "QTextEdit { background-color: #FFFFFF; border: 1px solid #E0E0E0; "
            "border-radius: 4px; padding: 8px; }"
        )
        self.setFont(QFont("Microsoft YaHei", 10))
        self._last_assistant_pos = -1  # Cursor position before last assistant message

    def append_message(self, role: str, content: str, is_html: bool = False):
        """Append a message with proper formatting."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        role_colors = {
            "user": "#0078D4",
            "assistant": "#107C10",
            "system": "#6C7086"
        }
        role_names = {
            "user": "用户",
            "assistant": "助手",
            "system": "系统"
        }

        # Track position before assistant message for streaming updates
        if role == "assistant" and not is_html:
            self._last_assistant_pos = cursor.position()

        # Insert role label
        cursor.insertHtml(
            f"<span style='color: {role_colors.get(role, '#333')}; font-weight: bold;'>"
            f"[{role_names.get(role, role)}]</span><br>"
        )

        if is_html:
            cursor.insertHtml(content)
        else:
            if role == "assistant":
                html = render_markdown(content)
                cursor.insertHtml(html)
            else:
                escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                cursor.insertHtml(f"<div style='white-space: pre-wrap;'>{escaped}</div>")

        cursor.insertHtml("<br><br>")
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def update_last_message(self, content: str):
        """Update the last assistant message in-place (for streaming)."""
        if self._last_assistant_pos < 0:
            self.append_message("assistant", content)
            return

        cursor = self.textCursor()
        cursor.setPosition(self._last_assistant_pos)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()

        html = render_markdown(content)
        cursor.insertHtml(html)
        cursor.insertHtml("<br><br>")
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def reset_streaming_state(self):
        """Reset streaming position tracking."""
        self._last_assistant_pos = -1


class ChatTab(QWidget):
    """Single chat session tab."""

    message_sent = Signal(str, str)

    def __init__(self, parent=None, session: ChatSession = None):
        super().__init__(parent)
        self._session = session or ChatSession(session_id=str(uuid.uuid4())[:8])
        self._streaming = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Model selection (multi-select)
        model_layout = QHBoxLayout()
        model_layout.addWidget(BodyLabel("模型:"))
        self._model_combo = ComboBox()
        self._model_combo.setFixedWidth(300)
        self._load_models()
        model_layout.addWidget(self._model_combo)

        model_layout.addWidget(BodyLabel("(多选对比)"))
        self._compare_btn = PushButton("对比模式")
        self._compare_btn.setFixedWidth(80)
        self._compare_btn.setCheckable(True)
        model_layout.addWidget(self._compare_btn)

        model_layout.addStretch()

        self._system_prompt_edit = LineEdit()
        self._system_prompt_edit.setPlaceholderText("系统提示词（可选）")
        self._system_prompt_edit.setFixedWidth(300)
        model_layout.addWidget(BodyLabel("系统提示:"))
        model_layout.addWidget(self._system_prompt_edit)

        layout.addLayout(model_layout)

        # Chat display (splitter for compare mode)
        self._splitter = QSplitter(Qt.Horizontal)
        self._chat_display = ChatDisplayWidget()
        self._splitter.addWidget(self._chat_display)

        # Secondary display for compare mode
        self._chat_display_2 = ChatDisplayWidget()
        self._chat_display_2.setVisible(False)
        self._splitter.addWidget(self._chat_display_2)

        layout.addWidget(self._splitter, 1)

        # Input area
        input_layout = QHBoxLayout()
        self._input_edit = TextEdit()
        self._input_edit.setPlaceholderText("输入消息...")
        self._input_edit.setMaximumHeight(100)
        input_layout.addWidget(self._input_edit, 1)

        self._send_btn = PushButton("发送")
        self._send_btn.setFixedWidth(80)
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        layout.addLayout(input_layout)

    def _load_models(self):
        models = load_models_config()
        if models:
            for m in models:
                if m.enabled:
                    self._model_combo.addItem(f"{m.name}", m.model_id)
        else:
            for model_type, model_ids in FREE_MODELS.items():
                if model_type in ("llm", "multimodal"):
                    for model_id in model_ids[:3]:
                        name = short_model_name(model_id)
                        self._model_combo.addItem(f"{name}", model_id)

    def _send_message(self):
        text = self._input_edit.toPlainText().strip()
        if not text or self._streaming:
            return

        model_id = self._model_combo.currentData()
        if not model_id:
            model_id = "Qwen/Qwen2.5-7B-Instruct"

        session = self._session
        session.add_message(ChatRole.USER, text, model_id)
        self._input_edit.clear()

        # Display user message
        self._chat_display.append_message("user", text)

        # Add placeholder for assistant
        session.add_message(ChatRole.ASSISTANT, "", model_id)

        # Compare mode: send to second model too
        models_to_use = [model_id]
        if self._compare_btn.isChecked() and self._model_combo.count() > 1:
            second_idx = (self._model_combo.currentIndex() + 1) % self._model_combo.count()
            models_to_use.append(self._model_combo.itemData(second_idx))
            self._chat_display_2.setVisible(True)
            self._chat_display_2.clear()
            self._chat_display_2.append_message("user", text)

        system_prompt = self._system_prompt_edit.text().strip()

        async def _stream():
            self._streaming = True
            self._send_btn.setEnabled(False)

            client = get_client()

            tasks = []
            for i, mid in enumerate(models_to_use):
                tasks.append(self._stream_response(client, mid, session, system_prompt, i))

            await asyncio.gather(*tasks, return_exceptions=True)

            self._streaming = False
            self._send_btn.setEnabled(True)

        asyncio.ensure_future(_stream())

    async def _stream_response(self, client, model_id, session, system_prompt, display_index):
        target_display = self._chat_display if display_index == 0 else self._chat_display_2
        content = ""
        last_update_len = 0

        try:
            messages = [m.to_openai_format() for m in session.messages[:-1]]

            async for event_type, data in client.stream_chat(
                model_id=model_id,
                messages=messages,
                system_prompt=system_prompt,
            ):
                if event_type == "content":
                    content += data
                    # Throttle UI updates: only update when content grew by >10 chars or has natural breaks
                    if len(content) - last_update_len > 10 or data.endswith(("\n", ".", "。", "!", "！", "?", "？")):
                        target_display.update_last_message(content)
                        last_update_len = len(content)
                elif event_type == "done":
                    break

            # Final render with full markdown
            target_display.update_last_message(content)
            target_display.reset_streaming_state()

            if display_index == 0:
                session.messages[-1].content = content
            else:
                session.add_message(ChatRole.ASSISTANT, content, model_id)

        except Exception as e:
            logger.exception("Stream chat failed")
            target_display.reset_streaming_state()
            target_display.append_message("assistant", f"[错误: {e}]")

    def get_session(self) -> ChatSession:
        return self._session

    def save_session(self):
        history_dir = chat_history_dir()
        filename = f"{self._session.title.replace('/', '_')[:30]}_{self._session.session_id}.json"
        path = history_dir / filename
        data = self._session.to_dict()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


class ChatPage(ScrollArea):
    """Enhanced chat page with multi-tab and multi-model compare."""

    message_sent = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chatPage")
        self._tabs: dict[str, ChatTab] = {}
        self._init_ui()
        self._new_tab()

    def _init_ui(self):
        container = QWidget()
        self.setWidget(container)
        self.setWidgetResizable(True)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("对话中心"))
        header.addStretch()

        self._btn_new_tab = PushButton("+ 新标签")
        self._btn_new_tab.setFixedWidth(80)
        self._btn_new_tab.clicked.connect(self._new_tab)
        header.addWidget(self._btn_new_tab)

        self._btn_save = PushButton("保存")
        self._btn_save.setFixedWidth(60)
        self._btn_save.clicked.connect(self._save_current)
        header.addWidget(self._btn_save)

        self._btn_load = PushButton("加载")
        self._btn_load.setFixedWidth(60)
        self._btn_load.clicked.connect(self._load_session)
        header.addWidget(self._btn_load)

        layout.addLayout(header)

        # Tab bar
        self._tab_bar = TabBar()
        self._tab_bar.setFixedHeight(36)
        self._tab_bar.tabCloseRequested.connect(self._close_tab)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.setTabsClosable(True)

        # Context menu for tabs
        self._tab_bar.customContextMenuRequested.connect(self._show_tab_menu)
        self._tab_bar.setContextMenuPolicy(Qt.CustomContextMenu)

        layout.addWidget(self._tab_bar)

        # Tab content area
        self._tab_stack = QWidget()
        self._stack_layout = QVBoxLayout(self._tab_stack)
        self._stack_layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._tab_stack, 1)

        # Log
        self._log_widget = LogWidget()
        layout.addWidget(self._log_widget)

    def _new_tab(self):
        session = ChatSession(session_id=str(uuid.uuid4())[:8])
        tab = ChatTab(self, session=session)
        tab_id = session.session_id

        self._tabs[tab_id] = tab
        self._tab_bar.addTab(tab_id, session.title)
        self._tab_bar.setCurrentIndex(self._tab_bar.count() - 1)

        self._stack_layout.addWidget(tab)
        tab.show()
        self._log_widget.info(f"新建对话标签: {tab_id}")

    def _close_tab(self, index: int):
        if self._tab_bar.count() <= 1:
            return  # Keep at least one tab

        tab_id = self._tab_bar.tabText(index)
        if tab_id in self._tabs:
            tab = self._tabs.pop(tab_id)
            self._stack_layout.removeWidget(tab)
            tab.deleteLater()

        self._tab_bar.removeTab(index)
        self._log_widget.info(f"关闭标签: {tab_id}")

    def _on_tab_changed(self, index: int):
        if index < 0:
            return

        tab_id = self._tab_bar.tabText(index) if index < self._tab_bar.count() else ""
        for tid, tab in self._tabs.items():
            tab.setVisible(tid == tab_id)

    def _show_tab_menu(self, pos):
        index = self._tab_bar.tabAt(pos)
        if index < 0:
            return

        menu = RoundMenu(parent=self)
        rename_action = RoundMenu.addAction = lambda: self._rename_tab(index)  # Simplified
        # Note: RoundMenu usage simplified - just use context menu directly

        # Use Qt context menu instead
        from PySide6.QtWidgets import QMenu
        qmenu = QMenu(self)
        qmenu.addAction("重命名", lambda: self._rename_tab(index))
        qmenu.addAction("关闭", lambda: self._close_tab(index))
        qmenu.exec(self._tab_bar.mapToGlobal(pos))

    def _rename_tab(self, index: int):
        from PySide6.QtWidgets import QInputDialog
        tab_id = self._tab_bar.tabText(index)
        if tab_id in self._tabs:
            session = self._tabs[tab_id].get_session()
            name, ok = QInputDialog.getText(self, "重命名", "标签名称:", text=session.title)
            if ok and name.strip():
                session.title = name.strip()
                self._tab_bar.setTabText(index, name.strip())

    def _save_current(self):
        index = self._tab_bar.currentIndex()
        if index < 0:
            return

        tab_id = self._tab_bar.tabText(index)
        if tab_id in self._tabs:
            path = self._tabs[tab_id].save_session()
            InfoBar.success("保存成功", f"已保存到 {path.name}", parent=self)
            self._log_widget.info(f"对话已保存: {path}")

    def _load_session(self):
        history_dir = chat_history_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "加载对话", str(history_dir), "JSON Files (*.json)"
        )
        if path:
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                session = ChatSession.from_dict(data)

                # Create new tab with loaded session
                tab = ChatTab(self, session=session)
                self._tabs[session.session_id] = tab
                self._tab_bar.addTab(session.session_id, session.title)
                self._tab_bar.setCurrentIndex(self._tab_bar.count() - 1)

                self._stack_layout.addWidget(tab)
                tab.show()

                # Populate display
                for msg in session.messages:
                    tab._chat_display.append_message(
                        msg.role.value,
                        msg.content,
                        is_html=(msg.role == ChatRole.ASSISTANT)
                    )

                InfoBar.success("加载成功", f"已加载 {session.title}", parent=self)
                self._log_widget.info(f"对话已加载: {path}")
            except Exception as e:
                InfoBar.error("加载失败", str(e), parent=self)
                self._log_widget.error(f"加载对话失败: {e}")
