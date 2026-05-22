"""
乐乐文本对比工具 — PySide6 Fluent 风格复刻版
算法来源：乐乐文本对比工具.html (LCS 字符级 Diff)
"""
import sys
import unicodedata
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QSplitter, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette, QColor


# ============ Fluent 风格样式表 ============
STYLE = """
QMainWindow { background-color: #f5f5f7; }

#titleLabel {
    font-size: 32px; font-weight: 600; color: #1d1d1f; letter-spacing: -1px;
}
#subtitleLabel {
    font-size: 13px; color: #86868b; font-weight: 400; margin-top: 2px;
}

/* 主按钮 */
#btnCompare {
    background-color: #0071e3; color: #ffffff; border: none;
    border-radius: 20px; padding: 10px 28px; font-size: 15px; font-weight: 500;
}
#btnCompare:hover { background-color: #0077ed; }
#btnCompare:pressed { background-color: #005bb5; }

/* 次按钮 */
.toolBtn {
    background-color: #e8e8ed; color: #1d1d1f; border: none;
    border-radius: 20px; padding: 10px 20px; font-size: 14px; font-weight: 500;
}
.toolBtn:hover { background-color: #d2d2d7; }
.toolBtn:pressed { background-color: #c4c4c9; }

/* 对比统计 */
#diffStats {
    font-size: 13px; color: #1d1d1f;
    background-color: #ffffff; border-radius: 12px;
    border: 1px solid #e5e5e5; padding: 8px 16px;
}

/* 编辑器卡片 */
.editorCard {
    background-color: #ffffff; border-radius: 16px; border: 1px solid #e5e5e5;
}
.editorHeader {
    background-color: #fafafa; border-bottom: 1px solid #e5e5e5;
    border-top-left-radius: 16px; border-top-right-radius: 16px;
    padding: 12px 20px;
}
.editorTitle { font-size: 14px; font-weight: 600; color: #1d1d1f; }
.statLabel { font-size: 13px; color: #86868b; margin-left: 8px; }
.statHighlight { font-size: 13px; color: #ff3b30; font-weight: 600; margin-left: 6px; }

/* 格式化按钮 */
.formatBtn {
    background-color: #e8e8ed; color: #86868b; border: none;
    border-radius: 12px; padding: 3px 14px; font-size: 12px; font-weight: 500;
}
.formatBtn:hover { background-color: #d2d2d7; }
.formatBtn[active="true"] { background-color: #0071e3; color: #ffffff; }

/* 文本编辑器 */
QTextEdit {
    border: none; padding: 16px; font-size: 15px; line-height: 1.7;
    color: #1d1d1f; background-color: #ffffff;
    border-bottom-left-radius: 16px; border-bottom-right-radius: 16px;
    selection-background-color: #0071e3; selection-color: #ffffff;
}
QTextEdit:focus { background-color: #fafafa; }

QSplitter::handle { background-color: transparent; }
"""

# ============ LCS Diff 引擎 ============

def compute_lcs(str1: str, str2: str) -> str:
    """最长公共子序列 DP O(m*n)"""
    m, n = len(str1), len(str2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if str1[i - 1] == str2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    i, j = m, n
    chars = []
    while i > 0 and j > 0:
        if str1[i - 1] == str2[j - 1]:
            chars.append(str1[i - 1])
            i -= 1; j -= 1
        elif dp[i - 1][j] > dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return ''.join(reversed(chars))


def diff_texts(original: str, new_text: str) -> dict:
    """
    字符级 Diff。
    返回: {"items": [{char, isDiff}], "added": int, "removed": int}
    """
    items = []
    lcs = compute_lcs(original, new_text)
    orig_idx = new_idx = lcs_idx = 0
    added_count = 0
    removed_count = 0

    while orig_idx < len(original) or new_idx < len(new_text):
        if (lcs_idx < len(lcs) and orig_idx < len(original) and new_idx < len(new_text)
                and original[orig_idx] == lcs[lcs_idx] and new_text[new_idx] == lcs[lcs_idx]):
            items.append({"char": new_text[new_idx], "isDiff": False})
            orig_idx += 1; new_idx += 1; lcs_idx += 1
        else:
            orig_in_lcs = (lcs_idx < len(lcs) and orig_idx < len(original)
                           and original[orig_idx] == lcs[lcs_idx])
            new_in_lcs = (lcs_idx < len(lcs) and new_idx < len(new_text)
                          and new_text[new_idx] == lcs[lcs_idx])

            if new_idx < len(new_text) and not new_in_lcs:
                items.append({"char": new_text[new_idx], "isDiff": True})
                new_idx += 1
                added_count += 1
            elif orig_idx < len(original) and not orig_in_lcs:
                orig_idx += 1
                removed_count += 1
            else:
                if new_idx < len(new_text):
                    items.append({"char": new_text[new_idx], "isDiff": True})
                    new_idx += 1
                    added_count += 1
                if orig_idx < len(original):
                    orig_idx += 1
                    removed_count += 1

    return {"items": items, "added": added_count, "removed": removed_count}


# ============ 字数统计 (WPS 对齐) ============

def get_word_count(text: str) -> int:
    """
    WPS 字数统计 — 精确对齐验证：
    计入：汉字 (CJK)、中文全角标点、数字（逐位计 1）
    剔除：英文字母、空格、ASCII 半角标点符号
    """
    count = 0
    for ch in text:
        cat = unicodedata.category(ch)
        cp = ord(ch)
        # 数字 (Nd) → 计入
        if cat == 'Nd':
            count += 1
        # CJK 汉字 (Lo, 0x4E00-0x9FFF 及扩展)
        elif cat == 'Lo' and (0x3400 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF
                              or 0x20000 <= cp <= 0x2FFFF):
            count += 1
        # 中文全角标点 / 韩文 / 日文标点 (Po, Ps, Pe, Pi, Pf 且 codepoint > 0x7F)
        elif cat in ('Po', 'Ps', 'Pe', 'Pi', 'Pf', 'So', 'Sm', 'Sk', 'Sc') and cp > 0x7F:
            count += 1
        # CJK 兼容符号 (Lm, Sk 等)
        elif cat in ('Lm', 'Lt') and cp > 0x7F:
            count += 1
        elif cat == 'Zs' and cp == 0x3000:  # 全角空格 IDEOGRAPHIC SPACE
            count += 1
        # ASCII 字母、空格、标点 → 不计数
    return count


def format_text(text: str) -> str:
    """去掉标点符号，仅保留汉字/字母/数字，非连续匹配项间换行"""
    import re
    regex = re.compile(r'[一-鿿a-zA-Z0-9]')
    parts = []
    last_end = 0
    for m in regex.finditer(text):
        if m.start() > last_end:
            parts.append('\n')
        parts.append(m.group())
        last_end = m.end()
    return re.sub(r'\n+', '\n', ''.join(parts))


# ============ HTML 工具函数 ============

def _escape(ch: str) -> str:
    if ch == '&': return '&amp;'
    if ch == '<': return '&lt;'
    if ch == '>': return '&gt;'
    if ch == '"': return '&quot;'
    if ch == '\n': return '<br>'
    return ch


def _diff_html(ch: str, is_diff: bool) -> str:
    safe = _escape(ch)
    if is_diff:
        return (f'<span style="color:#ff3b30; font-style:italic; '
                f'text-decoration:line-through; text-decoration-color:#ff3b30; '
                f'text-decoration-thickness:1.5px;">{safe}</span>')
    return safe


# ============ 编辑器面板 ============

class EditorPanel(QFrame):
    """编辑器面板：标题栏 + 字数统计 + 格式化 + 文本编辑器"""

    def __init__(self, title: str):
        super().__init__()
        self.setProperty("class", "editorCard")
        self._format_active = False
        self._title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- 标题栏 ---
        header = QFrame()
        header.setProperty("class", "editorHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 12, 16, 12)

        title_lbl = QLabel(title)
        title_lbl.setProperty("class", "editorTitle")
        h.addWidget(title_lbl)
        h.addStretch()

        self.word_label = QLabel("字数 0")
        self.word_label.setProperty("class", "statLabel")
        h.addWidget(self.word_label)

        self.diff_label = QLabel("")
        self.diff_label.setProperty("class", "statHighlight")
        self.diff_label.hide()
        h.addWidget(self.diff_label)

        self.fmt_btn = QPushButton("格式化")
        self.fmt_btn.setProperty("class", "formatBtn")
        self.fmt_btn.setFixedHeight(26)
        self.fmt_btn.setCursor(Qt.PointingHandCursor)
        self.fmt_btn.clicked.connect(self._toggle_format)
        h.addWidget(self.fmt_btn)

        layout.addWidget(header)

        # --- 编辑器 ---
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(True)
        self.editor.setPlaceholderText("请输入文本内容...")
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor)

    # ---- public ----
    def text(self) -> str:
        return self.editor.toPlainText()

    def set_plain(self, t: str):
        self.editor.setPlainText(t)
        self._format_active = False
        self._sync_fmt_btn()

    def set_html(self, html: str):
        self.editor.setHtml(html)

    def is_in_diff_view(self) -> bool:
        return self.editor.toPlainText() != self.editor.toHtml() and bool(self.editor.toHtml())

    def clear(self):
        self.editor.clear()
        self._format_active = False
        self._sync_fmt_btn()
        self.diff_label.hide()
        self.update_word_count()

    def update_word_count(self):
        self.word_label.setText(f"字数 {get_word_count(self.text())}")

    def show_diff_stat(self, changes: int):
        if changes > 0:
            self.diff_label.setText(f"+{changes} 处变更")
            self.diff_label.show()
        else:
            self.diff_label.hide()

    # ---- internal ----
    def _toggle_format(self):
        self._format_active = not self._format_active
        self._sync_fmt_btn()
        if self._format_active:
            self.editor.setPlainText(format_text(self.text()))
        self.update_word_count()

    def _sync_fmt_btn(self):
        self.fmt_btn.setProperty("active", "true" if self._format_active else "false")
        self.fmt_btn.style().unpolish(self.fmt_btn)
        self.fmt_btn.style().polish(self.fmt_btn)

    def _on_text_changed(self):
        self.update_word_count()
        # 一旦用户编辑，隐藏 diff 统计
        self.diff_label.hide()


# ============ 主窗口 ============

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("乐乐文本对比工具")
        self.resize(1260, 760)
        self.setMinimumSize(800, 500)
        QApplication.setFont(QFont("Microsoft YaHei", 9))

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        container = QWidget()
        c = QVBoxLayout(container)
        c.setContentsMargins(40, 32, 40, 36)
        c.setSpacing(20)

        # --- 标题 ---
        tt = QLabel("乐乐文本对比工具")
        tt.setObjectName("titleLabel"); tt.setAlignment(Qt.AlignCenter)
        st = QLabel("基于 LCS 最长公共子序列 · 字符级精准对比")
        st.setObjectName("subtitleLabel"); st.setAlignment(Qt.AlignCenter)

        c.addWidget(tt)
        c.addWidget(st)

        # --- 工具栏 ---
        bar = QHBoxLayout()
        bar.setAlignment(Qt.AlignCenter)
        bar.setSpacing(14)

        self.btn_cmp = QPushButton("开始对比")
        self.btn_cmp.setObjectName("btnCompare")
        self.btn_cmp.setCursor(Qt.PointingHandCursor)
        self.btn_cmp.clicked.connect(self._compare)
        bar.addWidget(self.btn_cmp)

        self.btn_clr = QPushButton("清空全部")
        self.btn_clr.setProperty("class", "toolBtn")
        self.btn_clr.setCursor(Qt.PointingHandCursor)
        self.btn_clr.clicked.connect(self._clear)
        bar.addWidget(self.btn_clr)

        self.btn_swap = QPushButton("交换文本")
        self.btn_swap.setProperty("class", "toolBtn")
        self.btn_swap.setCursor(Qt.PointingHandCursor)
        self.btn_swap.clicked.connect(self._swap)
        bar.addWidget(self.btn_swap)

        self.btn_reset = QPushButton("重置视图")
        self.btn_reset.setProperty("class", "toolBtn")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset_view)
        bar.addWidget(self.btn_reset)

        c.addLayout(bar)

        # --- 对比统计条 ---
        self.stats_bar = QLabel("")
        self.stats_bar.setObjectName("diffStats")
        self.stats_bar.setAlignment(Qt.AlignCenter)
        self.stats_bar.hide()
        c.addWidget(self.stats_bar)

        # --- 双栏编辑器 ---
        self.ed_orig = EditorPanel("原文本")
        self.ed_new = EditorPanel("新文本")

        sp = QSplitter(Qt.Horizontal)
        sp.addWidget(self.ed_orig)
        sp.addWidget(self.ed_new)
        sp.setSizes([600, 600])
        c.addWidget(sp, stretch=1)
        root.addWidget(container)

    # ======== Actions ========

    def _compare(self):
        orig = self.ed_orig.text()
        new = self.ed_new.text()
        if not orig.strip() and not new.strip():
            return

        diff = diff_texts(orig, new)
        items = diff["items"]

        # 构建 HTML 显示在新文本编辑器
        html = ''.join(_diff_html(it["char"], it["isDiff"]) for it in items)
        self.ed_new.set_html(html)

        # 更新统计
        self.ed_orig.update_word_count()
        added = diff["added"]
        removed = diff["removed"]
        if added > 0 or removed > 0:
            self.stats_bar.setText(
                f'对比结果：新增 {added} 字符（红色删除线） / 删除 {removed} 字符'
            )
            self.stats_bar.show()
        else:
            self.stats_bar.setText("两段文本完全一致，无差异")
            self.stats_bar.show()

        self.ed_new.show_diff_stat(added)

    def _clear(self):
        self.ed_orig.clear()
        self.ed_new.clear()
        self.stats_bar.hide()

    def _swap(self):
        t1 = self.ed_orig.text()
        t2 = self.ed_new.text()
        self.ed_orig.set_plain(t2)
        self.ed_new.set_plain(t1)
        self.stats_bar.hide()

    def _reset_view(self):
        """把新文本编辑器从 diff HTML 还原为纯文本"""
        plain = self.ed_new.text()
        self.ed_new.set_plain(plain)
        self.stats_bar.hide()
        self.ed_new.diff_label.hide()


# ============ 入口 ============

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    palette = app.palette()
    palette.setColor(QPalette.Window, QColor("#f5f5f7"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.Text, QColor("#1d1d1f"))
    palette.setColor(QPalette.PlaceholderText, QColor("#c0c0c4"))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
