"""Login dialog using embedded browser to extract session cookie from bj.nfai.lol."""
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView


class CookieLoginDialog(QDialog):
    """Embedded browser dialog that lets user log in and extracts session cookie."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录获取 Cookie — bj.nfai.lol")
        self.resize(950, 700)
        self.setMinimumSize(750, 550)
        self.setModal(True)

        self._session_cookie = ""
        self._user_id = "13679"
        self._all_cookies = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create web view first, then access its profile
        self._web = QWebEngineView()
        layout.addWidget(self._web, 1)

        # Bottom bar
        bar = QHBoxLayout()
        bar.setContentsMargins(16, 10, 16, 10)
        bar.setSpacing(12)

        self._status = QLabel("请在窗口中登录 bj.nfai.lol，登录后点击下方按钮获取 Cookie")
        self._status.setStyleSheet("color: #555; font-size: 13px;")
        bar.addWidget(self._status, 1)

        self._capture_btn = QPushButton("获取并应用")
        self._capture_btn.setMinimumSize(120, 38)
        self._capture_btn.setStyleSheet(
            "QPushButton { background: #1a73e8; color: white; border-radius: 4px; "
            "font-size: 14px; font-weight: bold; } "
            "QPushButton:hover { background: #1557b0; } "
        )
        self._capture_btn.clicked.connect(self._on_capture)
        bar.addWidget(self._capture_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumSize(80, 38)
        cancel_btn.clicked.connect(self.reject)
        bar.addWidget(cancel_btn)

        layout.addLayout(bar)

        # Hook cookie store from the web view's profile
        cookie_store = self._web.page().profile().cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)

        self._web.load(QUrl("https://bj.nfai.lol/"))

    def _on_cookie_added(self, cookie):
        name = cookie.name().data().decode("utf-8", errors="replace")
        value = cookie.value().data().decode("utf-8", errors="replace")
        self._all_cookies[name] = value
        if name == "session":
            self._session_cookie = value

    def _on_capture(self):
        self._status.setText("正在提取 Cookie...")
        self._status.setStyleSheet("color: #f0ad4e; font-size: 13px;")
        self._capture_btn.setEnabled(False)

        # Load all cookies from store (triggers cookieAdded for each)
        self._web.page().profile().cookieStore().loadAllCookies()

        QTimer.singleShot(800, self._finish_capture)

    def _finish_capture(self):
        if self._session_cookie:
            self._status.setText(f"已获取 Cookie，长度: {len(self._session_cookie)}")
            self._status.setStyleSheet("color: #5cb85c; font-size: 13px; font-weight: bold;")
            self._web.page().runJavaScript(
                """
                (function() {
                    try {
                        var userStr = localStorage.getItem('user');
                        if (userStr) {
                            var u = JSON.parse(userStr);
                            return String(u.id || '');
                        }
                    } catch(e) {}
                    return '';
                })()
                """,
                self._on_js_result
            )
        else:
            names = list(self._all_cookies.keys())
            self._status.setText(
                f"未检测到 session cookie，请确认已登录！\n"
                f"已有 cookies: {', '.join(names) if names else '(无)'}"
            )
            self._status.setStyleSheet("color: #d9534f; font-size: 12px;")
            self._capture_btn.setEnabled(True)

    def _on_js_result(self, result):
        if result and result.strip():
            self._user_id = result.strip()
        self.accept()

    @property
    def session_cookie(self) -> str:
        return self._session_cookie

    @property
    def user_id(self) -> str:
        return self._user_id
