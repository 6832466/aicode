"""探索页 — 内嵌手机浏览器 + JS 嗅探 + 一键捕获下载"""
import json
import logging
from pathlib import Path

from PySide6.QtWidgets import QWidget, QHBoxLayout, QSplitter
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage

import hgDown
from gui.workers.web_sniffer import (
    WebSnifferBridge, create_persistent_profile,
    setup_web_channel, INJECT_SCRIPT,
)
from gui.widgets.phone_frame import PhoneFrame
from gui.widgets.explore_right_panel import ExploreRightPanel

logger = logging.getLogger("hongguo")

QWEBCHANNEL_JS = Path(__file__).parent.parent / "js" / "qwebchannel.js"
HOME_URL = "https://novelquickapp.com/"


class ExplorePage(QWidget):
    """沉浸式刷剧探索页: 左侧手机框浏览器 + 右侧剧集信息面板"""

    start_download = Signal(list, str, list, dict, str)
    # episodes, output_dir, vid_list, base_params, page_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_series_info: dict = {}
        self._current_vid_list: list = []
        self._current_base_params: dict = {}
        self._current_page_path = ""
        self._captured = False

        self._bridge = WebSnifferBridge()
        self._bridge.router_data_received.connect(self._on_sniffed_data)

        # Must configure WebEngine BEFORE adding view to layout:
        # QWebEngineView() creates a default page whose renderer starts
        # when added to a layout; replacing it after layout causes a crash.
        self._profile = create_persistent_profile()
        self._web_page = QWebEnginePage(self._profile, self)
        self._web_page.loadFinished.connect(self._on_page_loaded)
        self._web_page.urlChanged.connect(self._on_url_changed)
        setup_web_channel(self._web_page, self._bridge)

        # Create view and assign configured page BEFORE any layout.addWidget
        self._web_view = QWebEngineView()
        self._web_view.setPage(self._web_page)

        self._setup_ui()
        self._web_view.load(QUrl(HOME_URL))

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background: #e0e0e0; }")

        # 左侧: 手机框 + pre-configured web view
        self._phone_frame = PhoneFrame(self._web_view)
        splitter.addWidget(self._phone_frame)

        # 右侧: 信息面板
        self._right_panel = ExploreRightPanel()
        self._right_panel.capture_requested.connect(self._on_capture)
        self._right_panel.download_requested.connect(self._on_start_download)
        splitter.addWidget(self._right_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([600, 400])

        layout.addWidget(splitter)

    # ==================== 页面加载 / 嗅探 ====================

    def _on_page_loaded(self, ok: bool):
        if not ok:
            return
        qwebchannel = QWEBCHANNEL_JS.read_text(encoding="utf-8")
        self._web_view.page().runJavaScript(qwebchannel)
        self._web_view.page().runJavaScript(INJECT_SCRIPT)

    def _on_url_changed(self, url: QUrl):
        url_str = url.toString()
        if "video-animation-share" in url_str or "video-list-share-ssr" in url_str:
            logger.info(f"[Explore] 检测到剧集页面: {url_str[:120]}")

    def _on_sniffed_data(self, json_str: str, current_url: str):
        """JS 嗅探到 _ROUTER_DATA → 解析并填充右侧面板"""
        try:
            router_data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("[Explore] 无法解析 router_data JSON")
            return

        page_data, page_type = hgDown.parse_page_data(router_data)
        if not page_data:
            return

        sd = page_data["series_data"]
        tags = sd.get("tags", sd.get("category", ""))
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split() if t.strip()]
        elif not isinstance(tags, list):
            tags = []
        series_info = {
            "series_id": sd.get("series_id", ""),
            "series_name": sd.get("title", sd.get("series_name", "")),
            "series_cover": sd.get("series_cover", ""),
            "series_intro": sd.get("series_intro", ""),
            "tags": tags,
            "episode_count": str(len(page_data.get("chapter_ids", []))),
            "popularity": sd.get("popularity", 0),
            "category": sd.get("category", ""),
        }
        vid_list = page_data.get("chapter_ids", [])
        page_path = hgDown.get_page_path(current_url)

        self._current_series_info = series_info
        self._current_vid_list = vid_list
        self._current_page_path = page_path
        self._captured = False

        self._right_panel.set_series_info(series_info, vid_list)
        logger.info(
            f"[Explore] 嗅探到: {series_info['series_name']} — {len(vid_list)} 集 "
            f"(type={page_type})"
        )

    # ==================== 捕获 / 下载 ====================

    def _on_capture(self):
        """从当前页面 URL 提取并保存模板参数"""
        url = self._web_view.url().toString()
        base_params = hgDown.parse_base_params(url)
        if not base_params.get("zlink"):
            logger.warning("[Explore] 捕获失败: URL 中缺少 zlink 参数")
            return

        page_path = self._current_page_path or hgDown.get_page_path(url)
        template = dict(base_params)
        template["_page_path"] = page_path
        hgDown.save_template_params(template)

        self._current_base_params = base_params
        self._current_page_path = page_path
        self._captured = True
        self._right_panel.mark_captured()

        name = self._current_series_info.get("series_name", "")
        logger.info(f"[Explore] 已捕获: {name} — page_path={page_path}")

    def _on_start_download(self, selected_episodes: list):
        """选集后点击下载 → emit 到 MainWindow"""
        if not self._captured:
            logger.warning("[Explore] 尚未捕获, 无法下载")
            return
        if not self._current_vid_list:
            logger.warning("[Explore] vid_list 为空")
            return

        selected_vids = [self._current_vid_list[i - 1] for i in selected_episodes]

        from PySide6.QtWidgets import QFileDialog
        output_dir = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if not output_dir:
            return

        self.start_download.emit(
            selected_episodes, output_dir, selected_vids,
            self._current_base_params, self._current_page_path,
        )
        logger.info(
            f"[Explore] 请求下载: {len(selected_episodes)} 集 → {output_dir}"
        )
