"""百度搜索采集工具 — PySide6 + QFluentWidgets 卡片式风格"""
import json
import re
import sys

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QFrame, QLabel,
)
from PySide6.QtGui import QFont, QIcon

from qfluentwidgets import (
    FluentIcon, LineEdit, PrimaryPushButton, CardWidget,
    InfoBar, InfoBarPosition, BodyLabel,
    StrongBodyLabel, CaptionLabel, setTheme, Theme,
    ElevatedCardWidget,
)

from mcp_client import McpClient


def _unwrap(content: dict) -> dict:
    """从 MCP tools/call 响应中提取工具实际返回值"""
    result = content.get("result", {})
    contents = result.get("content", [])
    if contents and isinstance(contents, list):
        text = contents[0].get("text", "")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"raw": text}
    if isinstance(result, dict):
        return result
    return {}


# ─── 搜索工作线程 ───────────────────────────────────────────

class SearchWorker(QThread):
    status_changed = Signal(str)
    result_ready = Signal(list)
    finished = Signal(bool, str)

    def __init__(self, keyword: str, parent=None):
        super().__init__(parent)
        self.keyword = keyword.strip()

    def run(self):
        if not self.keyword:
            self.finished.emit(False, "请输入搜索关键词")
            return

        self.status_changed.emit("正在连接 MCP 服务器...")
        client = McpClient()
        try:
            init_resp = client.initialize()
            if "error" in init_resp:
                self.finished.emit(False, f"连接失败: {init_resp['error']}")
                return

            self.status_changed.emit("正在打开百度...")
            nav_resp = client.call_tool("chrome_navigate", {"url": "https://www.baidu.com"})
            nav = _unwrap(nav_resp)
            if nav.get("error"):
                self.finished.emit(False, f"导航失败: {nav['error']}")
                return

            # 等待页面加载
            QThread.msleep(2000)
            self.status_changed.emit("定位搜索框...")

            # 用 chrome_read_page 获取交互元素
            page_resp = client.call_tool("chrome_read_page", {"filter": "interactive"})
            page_data = _unwrap(page_resp)
            page_text = page_data.get("pageContent", "")

            # 找搜索框和按钮的 ref
            search_ref = None
            submit_ref = None
            for line in page_text.split("\n"):
                if "textbox" in line.lower() and search_ref is None:
                    m = re.search(r'\[ref=(\S+)\]', line)
                    if m:
                        search_ref = m.group(1)
                if ('button' in line.lower() and '百度' in line and submit_ref is None):
                    m = re.search(r'\[ref=(\S+)\]', line)
                    if m:
                        submit_ref = m.group(1)

            if not search_ref:
                self.finished.emit(False, "未找到百度搜索框，请检查页面是否正常加载")
                return
            if not submit_ref:
                self.finished.emit(False, "未找到搜索按钮")
                return

            self.status_changed.emit("填入搜索关键词...")
            fill_resp = client.call_tool("chrome_fill_or_select", {
                "ref": search_ref,
                "value": self.keyword,
            })
            fill_data = _unwrap(fill_resp)
            if fill_data.get("error"):
                self.finished.emit(False, f"填入关键词失败: {fill_data['error']}")
                return

            QThread.msleep(300)
            self.status_changed.emit("点击搜索...")
            click_resp = client.call_tool("chrome_click_element", {"ref": submit_ref})
            click_data = _unwrap(click_resp)
            if click_data.get("error"):
                self.finished.emit(False, f"点击搜索失败: {click_data['error']}")
                return

            self.status_changed.emit("等待搜索结果加载...")
            QThread.msleep(3500)

            self.status_changed.emit("正在采集搜索结果...")

            # 用 CSS 选择器提取 h3 标题
            html_resp = client.call_tool("chrome_get_web_content", {
                "format": "html",
                "selector": "h3",
            })
            html_data = _unwrap(html_resp)
            if html_data.get("error"):
                self.finished.emit(False, f"提取页面失败: {html_data['error']}")
                return

            html_content = html_data.get("textContent", html_data.get("html", ""))
            if not html_content:
                self.finished.emit(False, "页面内容为空")
                return

            # 解析 HTML 提取标题和链接
            try:
                from html.parser import HTMLParser

                class TitleParser(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.items = []
                        self._current = {}
                        self._in_a = False
                        self._text = ""

                    def handle_starttag(self, tag, attrs):
                        if tag == "a":
                            self._in_a = True
                            self._current = {"title": "", "link": "", "desc": ""}
                            for k, v in attrs:
                                if k == "href":
                                    self._current["link"] = v
                        if tag == "h3":
                            self._text = ""

                    def handle_data(self, data):
                        if self._in_a:
                            t = data.strip()
                            if t:
                                self._current["title"] += t

                    def handle_endtag(self, tag):
                        if tag == "a" and self._current.get("title"):
                            title = self._current["title"].strip()
                            if len(title) > 2:
                                self.items.append(dict(self._current))
                            self._current = {}
                            self._in_a = False

                parser = TitleParser()
                parser.feed(html_content)
                parser.close()
                items = parser.items

                # 去重
                seen = set()
                unique = []
                for item in items:
                    if item["title"] not in seen:
                        seen.add(item["title"])
                        unique.append(item)
                items = unique[:15]

            except Exception:
                items = [{"title": f"解析异常，原始内容: {html_content[:200]}", "desc": "", "link": ""}]

            if not items:
                self.finished.emit(False, "未找到搜索结果，请检查页面是否正常加载")
                return

            self.result_ready.emit(items)
            self.status_changed.emit(f"采集完成，共 {len(items)} 条结果")
            self.finished.emit(True, f"成功采集 {len(items)} 条结果")

        except Exception as e:
            self.finished.emit(False, f"异常: {e}")
        finally:
            client.close()


# ─── 结果卡片 ───────────────────────────────────────────────

class ResultCard(ElevatedCardWidget):
    def __init__(self, title: str, desc: str, link: str, index: int, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(12)
        idx_label = QLabel(str(index))
        idx_label.setFixedSize(26, 26)
        idx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_label.setStyleSheet("""
            QLabel {
                background-color: #0078d4; color: white;
                border-radius: 13px; font-weight: bold; font-size: 12px;
            }
        """)
        header.addWidget(idx_label)

        title_label = StrongBodyLabel(title)
        title_label.setWordWrap(True)
        header.addWidget(title_label, 1)
        layout.addLayout(header)

        if link:
            link_label = CaptionLabel(link)
            link_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            link_label.setStyleSheet("color: #0078d4; font-size: 11px;")
            layout.addWidget(link_label)

        if desc:
            desc_label = BodyLabel(desc)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #555; font-size: 12px; line-height: 1.5;")
            layout.addWidget(desc_label)


# ─── 主窗口 ─────────────────────────────────────────────────

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._worker: SearchWorker | None = None
        self._cards = []
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("百度搜索采集")
        self.setMinimumSize(800, 600)
        self.resize(1000, 720)

        icon_path = "1.ico"
        import os
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        elif os.path.exists(os.path.join("..", "1.ico")):
            self.setWindowIcon(QIcon(os.path.join("..", "1.ico")))

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(16)

        # ── 搜索卡片 ──
        search_card = CardWidget(self)
        sc_layout = QVBoxLayout(search_card)
        sc_layout.setContentsMargins(28, 22, 28, 22)
        sc_layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(FluentIcon.SEARCH.icon().pixmap(28, 28))
        heading = QLabel("百度搜索采集工具")
        heading.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))

        title_row = QHBoxLayout()
        title_row.addWidget(icon_label)
        title_row.addWidget(heading)
        title_row.addStretch()
        sc_layout.addLayout(title_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(12)
        self._input = LineEdit()
        self._input.setPlaceholderText("输入搜索关键词，例如：人工智能、PySide6教程...")
        self._input.setFixedHeight(42)
        self._input.returnPressed.connect(self._on_search)
        input_row.addWidget(self._input, 1)

        self._btn = PrimaryPushButton("搜索")
        self._btn.setFixedSize(100, 42)
        self._btn.clicked.connect(self._on_search)
        input_row.addWidget(self._btn)
        sc_layout.addLayout(input_row)
        root.addWidget(search_card)

        # ── 状态 ──
        self._status = BodyLabel("就绪 — 输入关键词后点击搜索")
        self._status.setStyleSheet("color: #888; font-size: 13px;")
        root.addWidget(self._status)

        # ── 结果区域 ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._result_container = QWidget()
        self._result_container.setStyleSheet("background: transparent;")
        self._result_layout = QVBoxLayout(self._result_container)
        self._result_layout.setContentsMargins(0, 0, 0, 0)
        self._result_layout.setSpacing(12)
        self._result_layout.addStretch()

        self._scroll.setWidget(self._result_container)

        self._empty_hint = QLabel("输入关键词，点击搜索，结果会以卡片形式显示在这里")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setStyleSheet("color: #aaa; font-size: 14px; padding: 80px 0;")
        self._result_layout.insertWidget(0, self._empty_hint)

        root.addWidget(self._scroll, 1)

    def _on_search(self):
        keyword = self._input.text().strip()
        if not keyword:
            InfoBar.warning("提示", "请输入搜索关键词", duration=2000,
                           parent=self, position=InfoBarPosition.TOP)
            return

        self._clear_results()
        self._btn.setEnabled(False)
        self._input.setEnabled(False)
        self._status.setText(f"正在搜索「{keyword}」...")
        self._status.setStyleSheet("color: #0078d4; font-size: 13px;")

        self._worker = SearchWorker(keyword)
        self._worker.status_changed.connect(self._status.setText)
        self._worker.result_ready.connect(self._on_results)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _clear_results(self):
        self._empty_hint.hide()
        for card in self._cards:
            self._result_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        # 移除 stretch
        item = self._result_layout.takeAt(self._result_layout.count() - 1)
        if item and item.spacerItem():
            del item

    def _on_results(self, items: list):
        # 移除 stretch
        if self._result_layout.count() > 0:
            last = self._result_layout.takeAt(self._result_layout.count() - 1)
            if last and last.spacerItem():
                del last

        for i, item in enumerate(items, 1):
            card = ResultCard(
                title=item.get("title", ""),
                desc=item.get("desc", ""),
                link=item.get("link", ""),
                index=i,
            )
            self._result_layout.addWidget(card)
            self._cards.append(card)

        self._result_layout.addStretch()

    def _on_finished(self, success: bool, message: str):
        self._btn.setEnabled(True)
        self._input.setEnabled(True)
        if success:
            self._status.setStyleSheet("color: #107c10; font-size: 13px;")
            InfoBar.success("完成", message, duration=3000,
                           parent=self, position=InfoBarPosition.TOP)
        else:
            self._status.setStyleSheet("color: #d13438; font-size: 13px;")
            InfoBar.error("失败", message, duration=5000,
                         parent=self, position=InfoBarPosition.TOP)
        self._worker = None

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        event.accept()


if __name__ == "__main__":
    # 在 QApplication 之前提取 --search 参数，避免被 Qt 吃掉
    argv = sys.argv[:]
    search_keyword = ""
    if "--search" in argv:
        idx = argv.index("--search")
        if idx + 1 < len(argv):
            search_keyword = argv[idx + 1]
            del argv[idx:idx + 2]
        else:
            del argv[idx]

    app = QApplication(argv)
    setTheme(Theme.AUTO)

    window = MainWindow()
    window.show()

    if search_keyword:
        from PySide6.QtCore import QTimer
        window._input.setText(search_keyword)
        QTimer.singleShot(800, window._on_search)

    sys.exit(app.exec())
