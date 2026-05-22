"""探索页右侧面板 — 紧凑系列信息 + 选集网格 + 捕获/下载按钮"""
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QPushButton, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QUrl, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from qfluentwidgets import (
    BodyLabel, CaptionLabel, StrongBodyLabel,
    FlowLayout, CardWidget, PrimaryPushButton,
    FluentIcon,
)

from gui.widgets.episode_button import EpisodeButton

logger = logging.getLogger("hongguo")

CACHE_DIR = __import__('pathlib').Path(__file__).parent.parent / ".cover_cache"
CACHE_DIR.mkdir(exist_ok=True)


class ExploreRightPanel(QWidget):
    capture_requested = Signal()        # 用户点击 "捕获当前剧集"
    download_requested = Signal(list)   # selected_episodes (list[int], 1-based)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series_info: dict = {}
        self._vid_list: list = []
        self._episode_buttons: list[EpisodeButton] = []
        self._captured = False
        self._current_cover_url = ""
        self._nam = QNetworkAccessManager()
        self._nam.finished.connect(self._on_cover_loaded)

        self.setMinimumWidth(300)
        self.setMaximumWidth(480)
        self._setup_ui()
        self._show_placeholder()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 状态栏
        self._status_label = CaptionLabel("浏览剧集页面自动检测")
        self._status_label.setStyleSheet("color: #888; font-size: 12px;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # 信息卡片
        self._info_card = CardWidget()
        info_layout = QVBoxLayout(self._info_card)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(6)

        # 封面 + 标题 行
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self._cover_label = QLabel()
        self._cover_label.setFixedSize(90, 120)
        self._cover_label.setAlignment(Qt.AlignCenter)
        self._cover_label.setScaledContents(True)
        self._cover_label.setStyleSheet(
            "QLabel { background: #f5f5f5; border-radius: 6px; border: 1px solid #e8e8e8; }"
        )
        top_row.addWidget(self._cover_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        self._title_label = StrongBodyLabel("")
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet("font-size: 15px;")
        text_col.addWidget(self._title_label)

        self._tags_flow = FlowLayout(needAni=False)
        text_col.addLayout(self._tags_flow)

        self._stats_label = CaptionLabel("")
        self._stats_label.setStyleSheet("color: #888;")
        text_col.addWidget(self._stats_label)

        text_col.addStretch()
        top_row.addLayout(text_col, stretch=1)
        info_layout.addLayout(top_row)

        self._info_card.setVisible(False)
        layout.addWidget(self._info_card)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._capture_btn = PrimaryPushButton(FluentIcon.CAMERA, "捕获当前剧集")
        self._capture_btn.setMinimumHeight(40)
        self._capture_btn.clicked.connect(lambda: self.capture_requested.emit())
        self._capture_btn.setEnabled(False)
        btn_row.addWidget(self._capture_btn, stretch=1)

        self._download_btn = QPushButton("开始下载")
        self._download_btn.setMinimumHeight(40)
        self._download_btn.setCursor(Qt.PointingHandCursor)
        self._download_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4; color: #fff; border: none;
                border-radius: 8px; font-size: 15px; font-weight: 700;
                padding: 8px 0px;
            }
            QPushButton:hover { background: #1084d8; }
            QPushButton:disabled { background: #c0c0c0; color: #fff; }
        """)
        self._download_btn.clicked.connect(self._on_download_clicked)
        self._download_btn.setEnabled(False)
        btn_row.addWidget(self._download_btn, stretch=1)

        layout.addLayout(btn_row)

        # 选集区域
        sel_header = QHBoxLayout()
        sel_header.setSpacing(8)
        self._select_count_label = CaptionLabel("")
        self._select_count_label.setStyleSheet("color: #888;")
        sel_header.addWidget(self._select_count_label)
        sel_header.addStretch()

        for text, slot in [("全选", self._select_all), ("取消", self._deselect_all), ("反选", self._invert)]:
            btn = QPushButton(text)
            btn.setFixedSize(56, 28)
            btn.clicked.connect(slot)
            btn.setStyleSheet("""
                QPushButton {
                    background: #f5f5f5; border: 1px solid #d0d0d0;
                    border-radius: 4px; color: #555; font-size: 12px;
                }
                QPushButton:hover { background: #e3f2fd; border-color: #0078d4; color: #0078d4; }
            """)
            sel_header.addWidget(btn)

        layout.addLayout(sel_header)

        # 选集滚动网格
        self._episode_scroll = QScrollArea()
        self._episode_scroll.setWidgetResizable(True)
        self._episode_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._episode_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._episode_container = QWidget()
        self._episode_container.setStyleSheet("background: transparent;")
        self._episode_layout = FlowLayout(self._episode_container, needAni=False)
        self._episode_scroll.setWidget(self._episode_container)
        layout.addWidget(self._episode_scroll, stretch=1)

    # ==================== 数据方法 ====================

    def set_series_info(self, series_info: dict, vid_list: list):
        self._series_info = series_info
        self._vid_list = vid_list
        self._captured = False
        total = len(vid_list)

        cover_url = series_info.get("series_cover", "")
        if cover_url:
            self._load_cover(cover_url)

        self._title_label.setText(series_info.get("series_name", ""))

        self._clear_tags()
        tags = series_info.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split() if t.strip()]
        for tag in tags[:6]:
            tag_label = QLabel(tag)
            tag_label.setStyleSheet(
                "QLabel { background: #e3f2fd; color: #0078d4; "
                "border-radius: 3px; padding: 1px 6px; font-size: 10px; }"
            )
            self._tags_flow.addWidget(tag_label)

        popularity = series_info.get("popularity", 0)
        pop_str = f"{popularity / 10000:.1f}万热度" if popularity > 0 else ""
        self._stats_label.setText(f"{pop_str}  ·  共 {total} 集")

        self._populate_episode_grid(total)

        self._status_label.setText(f"已检测到: {series_info.get('series_name', '')} — 共 {total} 集")
        self._status_label.setStyleSheet("color: #0078d4; font-size: 12px;")

        self._info_card.setVisible(True)
        self._capture_btn.setEnabled(True)
        self._download_btn.setEnabled(False)

    def mark_captured(self):
        self._captured = True
        name = self._series_info.get("series_name", "")
        self._status_label.setText(f"已捕获: {name} — 可以选择集数开始下载")
        self._status_label.setStyleSheet("color: #4caf50; font-size: 12px;")
        self._capture_btn.setEnabled(False)
        self._capture_btn.setText("已捕获")
        self._download_btn.setEnabled(True)

    def clear_panel(self):
        self._series_info = {}
        self._vid_list = []
        self._captured = False
        self._capture_btn.setText("捕获当前剧集")
        self._capture_btn.setEnabled(False)
        self._download_btn.setEnabled(False)
        self._info_card.setVisible(False)
        self._show_placeholder()

    def get_selected_episodes(self) -> list[int]:
        return [btn.number for btn in self._episode_buttons if btn.isChecked()]

    # ==================== 内部 ====================

    def _show_placeholder(self):
        self._status_label.setText("浏览剧集页面自动检测")
        self._status_label.setStyleSheet("color: #888; font-size: 12px;")
        self._clear_episode_grid()
        self._select_count_label.setText("")

    def _populate_episode_grid(self, total: int):
        self._clear_episode_grid()
        for i in range(1, total + 1):
            btn = EpisodeButton(i)
            btn.toggled.connect(self._update_select_count)
            self._episode_layout.addWidget(btn)
            self._episode_buttons.append(btn)
        self._select_count_label.setText(f"共 {total} 集 · 已选 0 集")

    def _clear_episode_grid(self):
        while self._episode_layout.count() > 0:
            item = self._episode_layout.takeAt(0)
            if item is None:
                continue
            w = item.widget() if hasattr(item, 'widget') else item
            if w is not None:
                w.deleteLater()
        self._episode_buttons.clear()

    def _update_select_count(self):
        sel = len(self.get_selected_episodes())
        total = len(self._episode_buttons)
        self._select_count_label.setText(f"共 {total} 集 · 已选 {sel} 集")

    def _select_all(self):
        for btn in self._episode_buttons:
            btn.setChecked(True)

    def _deselect_all(self):
        for btn in self._episode_buttons:
            btn.setChecked(False)

    def _invert(self):
        for btn in self._episode_buttons:
            btn.setChecked(not btn.isChecked())

    def _on_download_clicked(self):
        selected = self.get_selected_episodes()
        if not selected:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.warning("未选择剧集", "请先在下方选集网格中选择要下载的剧集",
                           duration=3000, parent=self.window(), position=InfoBarPosition.BOTTOM_RIGHT)
            return
        self.download_requested.emit(selected)

    def _clear_tags(self):
        while self._tags_flow.count() > 0:
            item = self._tags_flow.takeAt(0)
            if item is None:
                continue
            w = item.widget() if hasattr(item, 'widget') else item
            if w is not None:
                w.deleteLater()

    def _load_cover(self, url: str):
        self._current_cover_url = url
        cache_key = url.split("/")[-1].split("~")[0]
        cache_path = CACHE_DIR / f"{cache_key}_explore.jpg"
        if cache_path.exists():
            pix = QPixmap(str(cache_path))
            if not pix.isNull():
                self._cover_label.setPixmap(pix)
                return
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"Referer", b"https://novelquickapp.com/")
        req.setAttribute(QNetworkRequest.User, str(cache_path))
        self._nam.get(req)

    def _on_cover_loaded(self, reply: QNetworkReply):
        cache_path = reply.request().attribute(QNetworkRequest.User)
        request_url = reply.request().url().toString()
        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            pix = QPixmap()
            pix.loadFromData(data)
            if not pix.isNull() and request_url == self._current_cover_url:
                self._cover_label.setPixmap(pix)
                with open(cache_path, "wb") as f:
                    f.write(data)
        reply.deleteLater()
