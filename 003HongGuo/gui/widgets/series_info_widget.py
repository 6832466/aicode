"""短剧信息展示组件 - Fluent 卡片式布局, 操作区固定在底部"""
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QUrl, Signal, QSize
from PySide6.QtGui import QPixmap, QFont, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from qfluentwidgets import (
    BodyLabel, CaptionLabel, StrongBodyLabel,
    ComboBox, FluentIcon, CardWidget, FlowLayout,
    InfoBar, InfoBarPosition,
)

from gui.widgets.episode_button import EpisodeButton

logger = logging.getLogger("hongguo")

CACHE_DIR = Path(__file__).parent.parent.parent / ".cover_cache"
CACHE_DIR.mkdir(exist_ok=True)


class SeriesInfoWidget(QWidget):
    """左侧面板: 封面 + 剧名 + 标签 + 简介 (可滚动) + 操作区 (固定底部)"""
    download_requested = Signal(list)  # selected_episodes
    stop_requested = Signal()         # 停止获取播放地址
    fetch_urls_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vid_list: list[str] = []
        self._play_urls: dict[int, str] = {}
        self._episode_buttons: list[EpisodeButton] = []
        self._loading_cover_url = ""
        self._nam = QNetworkAccessManager()
        self._nam.finished.connect(self._on_cover_loaded)

        self.setFixedWidth(380)
        self.setStyleSheet("background: transparent;")
        self._setup_ui()
        self._clear()

    # ==================== UI 搭建 ====================

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 8)
        root.setSpacing(8)

        # ---- 上半部分: 可滚动的信息卡片 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._info_card = CardWidget()
        info_layout = QVBoxLayout(self._info_card)
        info_layout.setContentsMargins(16, 16, 16, 12)
        info_layout.setSpacing(10)

        # 封面
        self._cover_label = QLabel()
        self._cover_label.setFixedSize(260, 346)
        self._cover_label.setAlignment(Qt.AlignCenter)
        self._cover_label.setStyleSheet("""
            QLabel {
                background-color: #f5f5f5;
                border-radius: 10px;
                border: 1px solid #e8e8e8;
            }
        """)
        self._cover_label.setScaledContents(True)
        cover_wrap = QHBoxLayout()
        cover_wrap.addStretch()
        cover_wrap.addWidget(self._cover_label)
        cover_wrap.addStretch()
        info_layout.addLayout(cover_wrap)

        # 剧名
        self._title_label = StrongBodyLabel("")
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet("font-size: 18px; color: #1a1a1a;")
        info_layout.addWidget(self._title_label)

        # 标签
        self._tags_flow = FlowLayout(needAni=False)
        info_layout.addLayout(self._tags_flow)

        # 统计
        self._stats_label = CaptionLabel("")
        self._stats_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self._stats_label)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("QFrame { color: #e8e8e8; max-height: 1px; }")
        info_layout.addWidget(sep)

        # 简介
        self._intro_label = BodyLabel("")
        self._intro_label.setWordWrap(True)
        self._intro_label.setStyleSheet("color: #666; font-size: 12px; line-height: 1.5;")
        info_layout.addWidget(self._intro_label)

        scroll.setWidget(self._info_card)
        root.addWidget(scroll, stretch=1)

        # ---- 下半部分: 固定在底部的操作卡片 ----
        self._action_card = CardWidget()
        action_layout = QVBoxLayout(self._action_card)
        action_layout.setContentsMargins(16, 14, 16, 16)
        action_layout.setSpacing(12)

        # 选集操作行
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        sel_label = BodyLabel("选集")
        sel_label.setStyleSheet("font-size: 13px;")
        sel_label.setFixedWidth(50)
        sel_row.addWidget(sel_label)

        self._select_all_btn = QPushButton("全选")
        self._select_all_btn.setFixedSize(68, 34)
        self._select_all_btn.clicked.connect(self._select_all)
        self._select_all_btn.setStyleSheet(self._small_btn_style())
        sel_row.addWidget(self._select_all_btn)

        self._deselect_btn = QPushButton("取消")
        self._deselect_btn.setFixedSize(68, 34)
        self._deselect_btn.clicked.connect(self._deselect_all)
        self._deselect_btn.setStyleSheet(self._small_btn_style())
        sel_row.addWidget(self._deselect_btn)

        self._invert_btn = QPushButton("反选")
        self._invert_btn.setFixedSize(68, 34)
        self._invert_btn.clicked.connect(self._invert_selection)
        self._invert_btn.setStyleSheet(self._small_btn_style())
        sel_row.addWidget(self._invert_btn)
        sel_row.addStretch()
        action_layout.addLayout(sel_row)

        # 下载 / 停止 按钮行 (两个大按钮并排)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._download_btn = QPushButton("  开始下载")
        self._download_btn.setIcon(FluentIcon.DOWNLOAD.icon())
        self._download_btn.setIconSize(QSize(22, 22))
        self._download_btn.setMinimumHeight(48)
        self._download_btn.setCursor(Qt.PointingHandCursor)
        self._download_btn.setStyleSheet(self._primary_btn_style())
        self._download_btn.clicked.connect(self._on_download_clicked)
        self._download_btn.setEnabled(False)
        btn_row.addWidget(self._download_btn, stretch=1)

        self._stop_btn = QPushButton("✕  取消")
        self._stop_btn.setMinimumHeight(48)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setStyleSheet(self._danger_btn_style())
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.hide()
        btn_row.addWidget(self._stop_btn, stretch=1)

        action_layout.addLayout(btn_row)
        root.addWidget(self._action_card)

    # ==================== 按钮样式 ====================

    @staticmethod
    def _primary_btn_style() -> str:
        return """
            QPushButton {
                background: #0078d4;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 700;
                padding: 10px 0px;
            }
            QPushButton:hover {
                background: #1084d8;
            }
            QPushButton:pressed {
                background: #005a9e;
            }
            QPushButton:disabled {
                background: #c0c0c0;
                color: #ffffff;
            }
        """

    @staticmethod
    def _danger_btn_style() -> str:
        return """
            QPushButton {
                background: #f44336;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 700;
                padding: 10px 0px;
            }
            QPushButton:hover {
                background: #ef5350;
            }
            QPushButton:pressed {
                background: #c62828;
            }
            QPushButton:disabled {
                background: #ef9a9a;
                color: #ffffff;
            }
        """

    @staticmethod
    def _small_btn_style() -> str:
        return """
            QPushButton {
                background: #f5f5f5;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                color: #555;
                font-size: 12px;
                font-weight: 600;
                padding: 4px 0px;
            }
            QPushButton:hover {
                background: #e3f2fd;
                border-color: #0078d4;
                color: #0078d4;
            }
            QPushButton:disabled {
                background: #f5f5f5;
                color: #c0c0c0;
                border-color: #e8e8e8;
            }
        """

    # ==================== 数据方法 ====================

    def _clear(self):
        self._cover_label.clear()
        self._cover_label.setText("暂无封面")
        self._title_label.setText("")
        self._clear_tags()
        self._stats_label.setText("")
        self._intro_label.setText("")
        self._vid_list.clear()
        self._play_urls.clear()
        self._episode_buttons.clear()
        self._download_btn.setEnabled(False)
        self._select_all_btn.setEnabled(False)
        self._deselect_btn.setEnabled(False)
        self._invert_btn.setEnabled(False)

    def _clear_tags(self):
        while self._tags_flow.count() > 0:
            item = self._tags_flow.takeAt(0)
            if item is None:
                continue
            if hasattr(item, 'widget'):
                w = item.widget()
            else:
                w = item
            if w is not None:
                w.deleteLater()

    def set_series_info(self, info: dict, vid_list: list):
        self._clear()
        self._vid_list = vid_list
        total = len(vid_list)

        cover_url = info.get("series_cover", "")
        if cover_url:
            self._load_cover(cover_url)

        self._title_label.setText(info.get("series_name", ""))

        tags = info.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split() if t.strip()]
        for tag in tags[:8]:
            tag_label = self._create_tag_label(tag)
            self._tags_flow.addWidget(tag_label)

        popularity = info.get("popularity", 0)
        pop_str = f"{popularity / 10000:.1f}万热度" if popularity > 0 else ""
        self._stats_label.setText(f"{pop_str}  ·  共 {total} 集")

        intro = info.get("series_intro", "")
        if intro:
            self._intro_label.setText(intro[:200] + ("..." if len(intro) > 200 else ""))
        else:
            self._intro_label.setText("暂无简介")

        self._download_btn.setEnabled(True)
        self._select_all_btn.setEnabled(True)
        self._deselect_btn.setEnabled(True)
        self._invert_btn.setEnabled(True)

    def _create_tag_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("""
            QLabel {
                background: #e3f2fd;
                color: #0078d4;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }
        """)
        return label

    def set_play_urls(self, urls: dict[int, str]):
        self._play_urls = urls
        for btn in self._episode_buttons:
            if btn.number in urls:
                btn.status = "ready"

    def get_episode_buttons(self) -> list[EpisodeButton]:
        return self._episode_buttons

    def get_selected_episodes(self) -> list[int]:
        return [btn.number for btn in self._episode_buttons if btn.isChecked()]

    # ==================== 封面 ====================

    def _load_cover(self, url: str):
        self._loading_cover_url = url
        cache_key = url.split("/")[-1].split("~")[0]
        cache_path = CACHE_DIR / f"{cache_key}.jpg"
        if cache_path.exists():
            pixmap = QPixmap(str(cache_path))
            self._cover_label.setPixmap(pixmap)
            return

        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"Referer", b"https://novelquickapp.com/")
        request.setAttribute(QNetworkRequest.User, str(cache_path))
        self._nam.get(request)

    def _on_cover_loaded(self, reply: QNetworkReply):
        try:
            cache_path = reply.request().attribute(QNetworkRequest.User)
            request_url = reply.request().url().toString()
            if reply.error() == QNetworkReply.NoError:
                data = reply.readAll()
                pixmap = QPixmap()
                pixmap.loadFromData(data)
                if not pixmap.isNull() and request_url == self._loading_cover_url:
                    self._cover_label.setPixmap(pixmap)
                    try:
                        with open(cache_path, "wb") as f:
                            f.write(data)
                    except OSError:
                        logger.exception(f"保存封面缓存失败: {cache_path}")
        except Exception:
            logger.exception("封面加载回调异常")
        finally:
            reply.deleteLater()

    # ==================== 选集操作 ====================

    def _select_all(self):
        for btn in self._episode_buttons:
            btn.setChecked(True)

    def _deselect_all(self):
        for btn in self._episode_buttons:
            btn.setChecked(False)

    def _invert_selection(self):
        for btn in self._episode_buttons:
            btn.setChecked(not btn.isChecked())

    # ==================== 下载 / 停止 ====================

    def _on_download_clicked(self):
        selected = self.get_selected_episodes()
        if not selected:
            InfoBar.warning(
                "未选择剧集", "请先在右侧选集网格中选择要下载的剧集",
                duration=3000, parent=self.window(), position=InfoBarPosition.TOP,
            )
            return
        self._set_downloading_state(True)
        self.download_requested.emit(selected)

    def _on_stop_clicked(self):
        self._set_downloading_state(False)
        self.stop_requested.emit()

    def _set_downloading_state(self, downloading: bool):
        """切换下载/停止按钮可见性"""
        self._download_btn.setVisible(not downloading)
        self._stop_btn.setVisible(downloading)
        if downloading:
            self._download_btn.setEnabled(False)
            self._select_all_btn.setEnabled(False)
            self._deselect_btn.setEnabled(False)
            self._invert_btn.setEnabled(False)
        else:
            self._download_btn.setEnabled(True)
            self._select_all_btn.setEnabled(True)
            self._deselect_btn.setEnabled(True)
            self._invert_btn.setEnabled(True)
