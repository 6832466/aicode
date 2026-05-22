"""通过内嵌 WebView 自动提取 Session Cookie 与 User ID。"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView

from qfluentwidgets import PrimaryPushButton, PushButton, BodyLabel

from api_config import get_session_cookie

BJ_URL = "https://bj.nfai.lol/"


class CookieLoginDialog(QDialog):
    """内嵌 WebView，用户登录后自动提取 session cookie 与 user ID。"""

    cookie_obtained = Signal(str, str)  # session_cookie, user_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cookieLoginDialog")
        self.setWindowTitle("乐乐动漫助手 - 登录获取 Cookie")
        self.resize(800, 600)
        self.setModal(True)

        self._session_cookie = ""
        self._user_id = "13679"

        self._build_ui()
        self._setup_webview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hint_bar = QVBoxLayout()
        hint_bar.setContentsMargins(16, 12, 16, 12)
        hint = BodyLabel("请在下方页面中登录，登录成功后点击「应用」自动填充。")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_bar.addWidget(hint)
        layout.addLayout(hint_bar)

        self._webview = QWebEngineView()
        layout.addWidget(self._webview, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 12, 16, 12)
        btn_row.addStretch()

        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        apply_btn = PrimaryPushButton("应用")
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        layout.addLayout(btn_row)

    def _setup_webview(self) -> None:
        profile = self._webview.page().profile()
        cookie_store = profile.cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)

        saved_cookie = get_session_cookie()
        if saved_cookie:
            from PySide6.QtWebEngineCore import QWebEngineHttpRequest
            req = QWebEngineHttpRequest()
            req.setUrl(QUrl(BJ_URL))
            req.setHeader(b"Cookie", f"session={saved_cookie}".encode())
            self._webview.load(req)
        else:
            self._webview.load(QUrl(BJ_URL))

    def _on_cookie_added(self, cookie) -> None:
        name = bytes(cookie.name().data()).decode("utf-8")
        if name == "session":
            self._session_cookie = bytes(cookie.value().data()).decode("utf-8")

    def reject(self) -> None:
        cookie_store = self._webview.page().profile().cookieStore()
        cookie_store.cookieAdded.disconnect(self._on_cookie_added)
        super().reject()

    def _on_apply(self) -> None:
        self._webview.page().runJavaScript(
            "localStorage.getItem('user')",
            self._on_user_id_ready,
        )

    def _on_user_id_ready(self, value) -> None:
        if value and value != "null":
            if isinstance(value, dict):
                self._user_id = str(value.get("id", 13679))
            else:
                self._user_id = str(value)
        self.cookie_obtained.emit(self._session_cookie, self._user_id)
        self.accept()
