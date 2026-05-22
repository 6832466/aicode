"""首页 - 搜索/解析输入, 剧集信息, 选集网格, 搜索结果"""
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QPushButton, QSplitter, QFrame,
)
from PySide6.QtCore import Qt, Signal, QUrl, QThread
from PySide6.QtGui import QFont, QPixmap
from qfluentwidgets import (
    BodyLabel, CaptionLabel, StrongBodyLabel, PrimaryPushButton,
    ComboBox, LineEdit, FlowLayout, InfoBar, InfoBarPosition,
    CardWidget, FluentIcon,
)

from search import HongguoDatabase, Series
from gui.widgets.series_info_widget import SeriesInfoWidget
from gui.widgets.episode_button import EpisodeButton
from gui.workers.search_worker import (
    LoadHomepageWorker, SearchWorker, ParseWorker, FetchEpisodeUrlWorker,
)
logger = logging.getLogger("hongguo")


class HomePage(QWidget):
    start_download = Signal(list, str, list, dict, str)  # episodes, output_dir, vid_list, base_params, page_path

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._db = HongguoDatabase()
        self._session = None
        self._base_params: dict = {}
        self._page_path: str = ""
        self._current_vid_list: list = []
        self._current_series_info: dict = {}
        self._play_urls: dict[int, str] = {}
        self._search_results: list[Series] = []
        self._pending_download: tuple = ()
        self._pending_re_download_eps: list = []  # 历史页重下: 待选剧集编号
        self._fetch_worker = None  # 当前正在获取 URL 的 worker
        self._parse_worker = None  # 当前正在解析的 worker
        self._workers: list = []
        self._cover_nams: list = []  # 防止 QNetworkAccessManager GC

        self._setup_ui()
        self._load_database()

    def _add_worker(self, worker: QThread):
        """添加 worker 并自动在完成后清理"""
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        self._workers.append(worker)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === 顶部输入栏 ===
        toolbar_frame = QFrame()
        toolbar_frame.setStyleSheet("QFrame { background: transparent; }")
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(20, 14, 20, 14)
        toolbar.setSpacing(10)

        self._input_edit = LineEdit()
        self._input_edit.setPlaceholderText("粘贴分享链接 (可含文字) 或输入关键词搜索...")
        self._input_edit.setMinimumHeight(38)
        self._input_edit.returnPressed.connect(self._on_parse)
        toolbar.addWidget(self._input_edit, stretch=1)

        self._sort_combo = ComboBox()
        self._sort_combo.addItems(["相关性", "名称", "集数多→少", "最新"])
        self._sort_combo.setCurrentIndex(0)
        self._sort_combo.setFixedWidth(120)
        self._sort_combo.hide()
        toolbar.addWidget(self._sort_combo)

        self._parse_btn = PrimaryPushButton(FluentIcon.LINK, "解析")
        self._parse_btn.clicked.connect(self._on_parse)
        toolbar.addWidget(self._parse_btn)

        self._search_btn = QPushButton("搜索")
        self._search_btn.setFixedHeight(36)
        self._search_btn.clicked.connect(self._on_search)
        self._search_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f0; border: 1px solid #ddd;
                border-radius: 6px; padding: 0 18px;
                font-size: 13px; color: #444;
            }
            QPushButton:hover { background: #e3f2fd; border-color: #0078d4; color: #0078d4; }
        """)
        toolbar.addWidget(self._search_btn)

        main_layout.addWidget(toolbar_frame)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("QFrame { color: #e8e8e8; max-height: 1px; }")
        main_layout.addWidget(sep)

        # 状态栏
        self._status_label = CaptionLabel("就绪 — 输入分享链接或关键词开始")
        self._status_label.setContentsMargins(20, 6, 20, 6)
        self._status_label.setStyleSheet("color: #888;")
        main_layout.addWidget(self._status_label)

        # === 主内容区 ===
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        # 左侧: 短剧信息
        self._info_widget = SeriesInfoWidget()
        self._info_widget.download_requested.connect(self._on_start_download)
        self._info_widget.stop_requested.connect(self._on_stop_fetch)
        self._info_widget.fetch_urls_requested.connect(self._on_fetch_play_urls)
        content.addWidget(self._info_widget)

        # 分隔线
        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine)
        vsep.setStyleSheet("QFrame { color: #e8e8e8; max-width: 1px; }")
        content.addWidget(vsep)

        # 右侧: 选集 + 搜索结果
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 8, 16, 8)
        right_layout.setSpacing(8)

        # 选集统计栏
        ep_bar = QHBoxLayout()
        self._episode_count_label = CaptionLabel("")
        self._episode_count_label.setStyleSheet("color: #888;")
        ep_bar.addWidget(self._episode_count_label)
        ep_bar.addStretch()
        right_layout.addLayout(ep_bar)

        # 选集网格 (可滚动)
        self._episode_scroll = QScrollArea()
        self._episode_scroll.setWidgetResizable(True)
        self._episode_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._episode_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._episode_container = QWidget()
        self._episode_container.setStyleSheet("background: transparent;")
        self._episode_layout = FlowLayout(self._episode_container, needAni=False)
        self._episode_scroll.setWidget(self._episode_container)
        right_layout.addWidget(self._episode_scroll, stretch=1)

        # 搜索结果区域 (初始隐藏)
        self._search_scroll = QScrollArea()
        self._search_scroll.setWidgetResizable(True)
        self._search_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._search_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._search_container = QWidget()
        self._search_container.setStyleSheet("background: transparent;")
        self._search_layout = QVBoxLayout(self._search_container)
        self._search_layout.setSpacing(8)
        self._search_layout.addStretch()
        self._search_scroll.setWidget(self._search_container)
        self._search_scroll.hide()
        right_layout.addWidget(self._search_scroll, stretch=1)

        content.addWidget(right_panel, stretch=1)
        main_layout.addLayout(content, stretch=1)

    def set_re_download_episodes(self, episodes: list):
        """历史页重下: 预存待选剧集, 解析完成后自动选中并触发下载"""
        self._pending_re_download_eps = list(episodes)
        logger.info(f"[HOME] 预存重下剧集: {episodes}")

    # ========== 数据库加载 ==========

    def _load_database(self, force: bool = False):
        self._status_label.setText("正在加载短剧数据...")
        self._set_buttons_enabled(False)
        worker = LoadHomepageWorker(self._db, force_refresh=force)
        worker.finished.connect(self._on_database_loaded)
        worker.error.connect(self._on_worker_error)
        self._add_worker(worker)
        worker.start()

    def _on_database_loaded(self, count: int):
        self._status_label.setText(f"就绪 — 已加载 {count} 部短剧数据")
        self._set_buttons_enabled(True)

    # ========== 解析 ==========

    def _on_parse(self):
        import re
        text = self._input_edit.text().strip()
        if not text:
            return

        url_match = re.search(r'https?://\S+', text)
        if url_match:
            url = url_match.group().rstrip("/")
            mode = "share_link"
            target = url
        else:
            num_match = re.search(r'\b(\d{19,})\b', text)
            if num_match:
                mode = "series_id"
                target = num_match.group(1)
            else:
                self._on_search()
                return

        # 取消上一次正在进行的解析 (避免竞态)
        if self._parse_worker and self._parse_worker.isRunning():
            self._parse_worker.terminate()
            self._parse_worker.wait(2000)
        self._status_label.setText("正在解析...")
        self._set_buttons_enabled(False)

        self._parse_worker = ParseWorker(mode, target)
        worker = self._parse_worker
        worker.finished.connect(self._on_parse_finished)
        worker.progress.connect(lambda msg: self._status_label.setText(msg))
        worker.error.connect(self._on_worker_error)
        self._add_worker(worker)
        worker.start()

    def _on_parse_finished(self, series_info: dict, vid_list: list, page_type: str):
        self._parse_worker = None
        if not series_info or not vid_list:
            self._pending_re_download_eps = []
            InfoBar.error("解析失败", "未能获取剧集数据, 请检查链接", duration=5000,
                          parent=self, position=InfoBarPosition.TOP_RIGHT)
            self._status_label.setText("解析失败 — 请检查链接是否有效")
            self._set_buttons_enabled(True)
            return
        self._current_series_info = series_info
        self._current_vid_list = vid_list
        self._play_urls = {}
        total = len(vid_list)

        logger.info(f"解析完成: {series_info.get('series_name', '')} — {total} 集")

        self._info_widget.set_series_info(series_info, vid_list)
        self._populate_episode_grid(total)

        self._status_label.setText(f"解析完成: {series_info.get('series_name', '')} — 共 {total} 集")
        self._set_buttons_enabled(True)

        # 历史页重下: 自动选中剧集并触发下载
        if self._pending_re_download_eps:
            re_eps = self._pending_re_download_eps
            self._pending_re_download_eps = []
            # 过滤超出范围的集数
            valid_eps = [e for e in re_eps if 1 <= e <= total]
            if valid_eps:
                for e in valid_eps:
                    for btn in self._info_widget.get_episode_buttons():
                        if btn.number == e:
                            btn.setChecked(True)
                logger.info(f"[HOME] 重下: 已自动选中 {len(valid_eps)} 集, 开始下载")
                self._on_start_download(valid_eps)
            else:
                logger.warning(f"[HOME] 重下: 历史集数 {re_eps} 超出范围 (共 {total} 集)")

    # ========== 搜索 ==========

    def _on_search(self):
        keyword = self._input_edit.text().strip()
        if not keyword:
            return

        sort_map = {0: "relevance", 1: "name", 2: "episode", 3: "newest"}
        sort_by = sort_map.get(self._sort_combo.currentIndex(), "relevance")

        self._status_label.setText(f"正在搜索: {keyword}...")
        self._set_buttons_enabled(False)

        worker = SearchWorker(self._db, keyword, limit=50, sort_by=sort_by)
        worker.finished.connect(self._on_search_finished)
        worker.error.connect(self._on_worker_error)
        self._add_worker(worker)
        worker.start()

    def _on_search_finished(self, results: list[Series]):
        self._search_results = results
        self._show_search_results(results)
        self._status_label.setText(f"搜索完成: 找到 {len(results)} 部短剧")
        self._set_buttons_enabled(True)

    def _show_search_results(self, results: list[Series]):
        while self._search_layout.count() > 1:
            item = self._search_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not results:
            label = BodyLabel("未找到相关短剧")
            label.setAlignment(Qt.AlignCenter)
            self._search_layout.insertWidget(0, label)
        else:
            for s in results:
                card = self._create_search_card(s)
                self._search_layout.insertWidget(self._search_layout.count() - 1, card)

        self._episode_scroll.hide()
        self._search_scroll.show()

    def _create_search_card(self, series: Series) -> QFrame:
        card = CardWidget()
        card.setMinimumHeight(110)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet("CardWidget { background: white; border-radius: 10px; }")
        card.setToolTip(f"点击查看「{series.series_name}」详情")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        # 封面
        cover = QLabel()
        cover.setFixedSize(60, 80)
        cover.setScaledContents(True)
        cover.setStyleSheet(
            "QLabel { background-color: #f0f0f0; border-radius: 6px; border: 1px solid #e8e8e8; }"
        )
        if series.series_cover:
            self._load_card_cover(cover, series.series_cover)
        cover.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(cover)

        # 文字信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        name_label = StrongBodyLabel(series.series_name)
        name_label.setStyleSheet("font-size: 13px;")
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        info_layout.addWidget(name_label)

        # 简介 (截取前60字)
        intro_text = series.series_intro or ""
        if len(intro_text) > 60:
            intro_text = intro_text[:60] + "..."
        if intro_text:
            intro_label = CaptionLabel(intro_text)
            intro_label.setWordWrap(True)
            intro_label.setStyleSheet("color: #888; font-size: 11px;")
            intro_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            info_layout.addWidget(intro_label)

        # 标签 + 集数
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        tags_str = "  ".join(series.tags[:4]) if series.tags else ""
        if tags_str:
            tags_label = CaptionLabel(tags_str)
            tags_label.setStyleSheet("color: #0078d4; font-size: 11px;")
            tags_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            bottom_row.addWidget(tags_label)
        bottom_row.addStretch()
        eps_label = CaptionLabel(series.episode_count)
        eps_label.setStyleSheet("color: #aaa; font-size: 11px;")
        eps_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        bottom_row.addWidget(eps_label)
        info_layout.addLayout(bottom_row)

        layout.addLayout(info_layout, stretch=1)

        # 点击事件 — 让所有子控件透传鼠标事件
        card.mousePressEvent = lambda e: self._on_search_result_clicked(series)
        return card

    def _load_card_cover(self, label: QLabel, url: str):
        """加载搜索卡片封面 (带缓存)"""
        from pathlib import Path as _Path
        cache_dir = _Path(__file__).parent.parent / ".cover_cache"
        cache_dir.mkdir(exist_ok=True)
        cache_key = url.split("/")[-1].split("~")[0]
        cache_path = cache_dir / f"{cache_key}_thumb.jpg"
        if cache_path.exists():
            pix = QPixmap(str(cache_path))
            if not pix.isNull():
                label.setPixmap(pix)
                return

        from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
        nam = QNetworkAccessManager()
        self._cover_nams.append(nam)
        def handle(reply, lbl=label, cp=cache_path):
            if reply.error() == QNetworkReply.NoError:
                data = reply.readAll()
                pix = QPixmap()
                pix.loadFromData(data)
                if not pix.isNull():
                    lbl.setPixmap(pix)
                    with open(cp, "wb") as f:
                        f.write(data)
            reply.deleteLater()
        nam.finished.connect(handle)
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"Referer", b"https://novelquickapp.com/")
        nam.get(req)

    def _on_search_result_clicked(self, series: Series):
        """点击搜索结果 → 直接解析剧集, 不改变搜索框内容"""
        self._search_scroll.hide()
        self._episode_scroll.show()
        # 直接用 series_id 解析，不修改输入框
        self._status_label.setText("正在解析...")
        self._set_buttons_enabled(False)

        self._parse_worker = ParseWorker("series_id", series.series_id)
        worker = self._parse_worker
        worker.finished.connect(self._on_parse_finished)
        worker.progress.connect(lambda msg: self._status_label.setText(msg))
        worker.error.connect(self._on_worker_error)
        self._add_worker(worker)
        worker.start()

    # ========== 选集网格 ==========

    def _populate_episode_grid(self, total: int):
        while self._episode_layout.count() > 0:
            item = self._episode_layout.takeAt(0)
            if item is None:
                continue
            w = item.widget() if hasattr(item, 'widget') else item
            if w is not None:
                w.deleteLater()
        self._info_widget.get_episode_buttons().clear()

        for i in range(1, total + 1):
            btn = EpisodeButton(i)
            btn.toggled.connect(self._update_episode_count)
            self._episode_layout.addWidget(btn)
            self._info_widget.get_episode_buttons().append(btn)

        self._episode_count_label.setText(f"共 {total} 集 · 已选 0 集")
        self._episode_scroll.show()
        self._search_scroll.hide()

    def _update_episode_count(self):
        selected = self._info_widget.get_selected_episodes()
        total = len(self._info_widget.get_episode_buttons())
        self._episode_count_label.setText(f"共 {total} 集 · 已选 {len(selected)} 集")

    # ========== 获取播放地址 ==========

    def _on_fetch_play_urls(self):
        if not self._current_vid_list:
            return

        from hgDown import load_template_params
        template = load_template_params()
        if not template:
            InfoBar.error("缺少模板参数", "请先使用分享链接解析一次", duration=5000,
                          parent=self, position=InfoBarPosition.TOP_RIGHT)
            return

        base_params = dict(template)
        page_path = base_params.pop("_page_path", "/hongguo/ug/pages/video-animation-share")

        self._status_label.setText("正在准备下载...")
        self._set_buttons_enabled(False)

        self._fetch_worker = FetchEpisodeUrlWorker(self._current_vid_list, base_params, page_path)
        worker = self._fetch_worker
        worker.finished.connect(self._on_play_urls_ready)
        worker.progress.connect(self._on_fetch_progress)
        worker.episode_ready.connect(self._on_episode_url_ready)
        worker.log_msg.connect(lambda msg, lvl: logger.info(msg))
        worker.error.connect(self._on_worker_error)
        self._add_worker(worker)
        worker.start()

    def _on_episode_url_ready(self, index: int, play_url: str):
        self._play_urls[index] = play_url
        for btn in self._info_widget.get_episode_buttons():
            if btn.number == index:
                btn.status = "ready"

    def _on_fetch_progress(self, current: int, total: int):
        self._status_label.setText(f"准备下载: {current}/{total}")

    def _on_play_urls_ready(self, play_urls: dict):
        self._play_urls = play_urls
        self._fetch_worker = None
        self._info_widget.set_play_urls(play_urls)
        self._status_label.setText(f"已获取 {len(play_urls)} 个播放地址, 请选择要下载的剧集")
        self._set_buttons_enabled(True)

    # ========== 开始下载 ==========

    def _on_start_download(self, selected_episodes: list):
        """立即将下载任务入队, URL 由队列管理器后台多线程获取"""
        logger.info(f"[HOME] _on_start_download called: episodes={selected_episodes}")
        if not selected_episodes:
            InfoBar.warning("未选择剧集", "请先选择要下载的剧集", parent=self)
            return

        if not self._current_vid_list:
            InfoBar.error("无剧集数据", "请先解析短剧链接", parent=self)
            return

        from hgDown import load_template_params
        template = load_template_params()
        if not template:
            InfoBar.error("缺少模板参数", "请先使用分享链接解析一次", duration=5000,
                          parent=self, position=InfoBarPosition.TOP_RIGHT)
            return

        base_params = dict(template)
        page_path = base_params.pop("_page_path", "/hongguo/ug/pages/video-animation-share")

        try:
            selected_vids = [self._current_vid_list[i - 1] for i in selected_episodes]
        except IndexError as e:
            logger.error(f"[HOME] IndexError building selected_vids: vid_list len={len(self._current_vid_list)}, episodes={selected_episodes}")
            InfoBar.error("数据错误", "选集索引超出范围, 请重新解析链接", parent=self)
            return

        series_name = self._current_series_info.get("series_name", "?")
        logger.info(f"[HOME] series={series_name}, n_eps={len(selected_episodes)}, total_vids={len(self._current_vid_list)}")
        logger.info(f"[HOME] page_path={page_path}, selected_vids[:3]={selected_vids[:3]}")

        self._info_widget._set_downloading_state(False)
        self._status_label.setText(f"已加入下载队列, 共 {len(selected_episodes)} 集")
        self._set_buttons_enabled(True)

        output_dir = self.config.download_path
        logger.info(f"[HOME] emitting start_download signal: {len(selected_episodes)} eps, {len(selected_vids)} vids, output_dir={output_dir}")
        self.start_download.emit(selected_episodes, output_dir,
                                 selected_vids, base_params, page_path)
        InfoBar.success(
            "已加入下载队列", f"共 {len(selected_episodes)} 集, 后台获取链接中",
            duration=2000, parent=self, position=InfoBarPosition.BOTTOM_RIGHT,
        )

    # ========== 工具方法 ==========

    def _set_buttons_enabled(self, enabled: bool):
        self._parse_btn.setEnabled(enabled)
        self._search_btn.setEnabled(enabled)

    def _on_stop_fetch(self):
        """用户点击停止获取播放地址"""
        if self._fetch_worker:
            self._fetch_worker.stop()
            self._fetch_worker = None
        self._info_widget._set_downloading_state(False)
        self._pending_download = ()
        self._status_label.setText("已取消")
        self._set_buttons_enabled(True)

    def _on_worker_error(self, error_msg: str):
        self._fetch_worker = None
        self._parse_worker = None
        self._info_widget._set_downloading_state(False)
        self._pending_download = ()
        self._pending_re_download_eps = []
        self._status_label.setText(f"错误: {error_msg}")
        self._set_buttons_enabled(True)
        InfoBar.error("操作失败", error_msg, duration=5000, parent=self)
