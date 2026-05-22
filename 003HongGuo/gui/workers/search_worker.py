"""搜索与解析 Worker — 在 QThread 中执行网络操作"""
import json
import logging
import time as _time
import urllib.parse
import requests
from PySide6.QtCore import QThread, Signal

from search import HongguoDatabase
from hgDown import (
    extract_ssr_data, parse_page_data, parse_base_params,
    get_page_path, build_episode_url, save_template_params,
    HEADERS,
)

logger = logging.getLogger("hongguo")


class LoadHomepageWorker(QThread):
    """后台加载首页数据"""
    finished = Signal(int)  # series count
    error = Signal(str)

    def __init__(self, db: HongguoDatabase, force_refresh: bool = False):
        super().__init__()
        self._db = db
        self._force_refresh = force_refresh

    def run(self):
        try:
            count = self._db.load_from_homepage(force_refresh=self._force_refresh)
            self.finished.emit(count)
        except Exception as e:
            logger.error(f"加载首页数据失败: {e}")
            self.error.emit(str(e))


class SearchWorker(QThread):
    """搜索短剧"""
    finished = Signal(list)  # list[Series]
    error = Signal(str)

    def __init__(self, db: HongguoDatabase, keyword: str, limit: int = 50, sort_by: str = "relevance"):
        super().__init__()
        self._db = db
        self._keyword = keyword
        self._limit = limit
        self._sort_by = sort_by

    def run(self):
        try:
            results = self._db.search(self._keyword, self._limit, self._sort_by)
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            self.error.emit(str(e))


class ParseWorker(QThread):
    """解析短剧信息
    mode: "share_link" — 从分享链接解析
    mode: "series_id" — 从剧集ID解析
    """
    finished = Signal(dict, list, str)  # series_info, vid_list, page_type
    progress = Signal(str)              # 状态文字
    error = Signal(str)

    def __init__(self, mode: str, input_data: str):
        super().__init__()
        self._mode = mode
        self._input = input_data
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    def run(self):
        try:
            if self._mode == "share_link":
                self._parse_share_link()
            elif self._mode == "series_id":
                self._parse_series_id()
        except Exception as e:
            logger.error(f"解析失败: {e}")
            self.error.emit(str(e))

    def _parse_share_link(self):
        self.progress.emit("正在访问分享链接...")
        resp = self._session.get(self._input, allow_redirects=True, timeout=30)
        final_url = resp.url
        logger.info(f"分享链接重定向: {final_url}")

        base_params = parse_base_params(final_url)
        page_path = get_page_path(final_url)
        save_template_params({**base_params, "_page_path": page_path})
        logger.info("已保存模板参数")

        ssr = extract_ssr_data(resp.text)
        if not ssr:
            raise RuntimeError("无法提取 SSR 数据")

        page_data, page_type = parse_page_data(ssr)
        if not page_data:
            raise RuntimeError("无法解析 pageData")

        sd = page_data["series_data"]
        series_id = sd.get("series_id", "") or self._extract_series_id_from_zlink(
            base_params.get("zlink", "")
        )
        series_info = {
            "series_id": series_id,
            "series_name": sd.get("title", sd.get("series_name", "")),
            "series_cover": sd.get("series_cover", ""),
            "series_intro": sd.get("series_intro", ""),
            "tags": sd.get("tags", sd.get("category", "").split()),
            "episode_count": str(len(page_data.get("chapter_ids", []))),
            "popularity": sd.get("popularity", 0),
            "category": sd.get("category", ""),
        }
        vid_list = page_data.get("chapter_ids", [])
        self.finished.emit(series_info, vid_list, page_type)

    @staticmethod
    def _extract_series_id_from_zlink(zlink: str) -> str:
        """从 zlink URL 的 schemeParams 中提取 video_series_id"""
        if not zlink:
            return ""
        try:
            parsed = urllib.parse.urlparse(zlink)
            params = urllib.parse.parse_qs(parsed.query)
            scheme_str = params.get("schemeParams", [""])[0]
            if scheme_str:
                scheme = json.loads(scheme_str)
                return scheme.get("video_series_id", "")
        except Exception:
            pass
        return ""

    def _parse_series_id(self):
        self.progress.emit("正在获取剧集详情...")
        resp = self._session.get(
            f"https://novelquickapp.com/detail?series_id={self._input}",
            allow_redirects=True, timeout=30,
        )
        final_url = resp.url
        logger.info(f"详情页重定向: {final_url}")

        # 尝试从重定向 URL 提取并保存模板参数
        base_params = parse_base_params(final_url)
        page_path = get_page_path(final_url)
        if base_params.get("zlink"):
            save_template_params({**base_params, "_page_path": page_path})
            logger.info("已从详情页保存模板参数")
        else:
            logger.warning("详情页缺少 zlink 参数, 下载可能需要先解析分享链接")

        ssr = extract_ssr_data(resp.text)
        if not ssr:
            raise RuntimeError("无法获取剧集详情")

        sd = ssr["loaderData"]["detail_page"]["seriesDetail"]
        series_info = {
            "series_id": sd.get("series_id", self._input),
            "series_name": sd.get("series_name", ""),
            "series_cover": sd.get("series_cover", ""),
            "series_intro": sd.get("series_intro", ""),
            "tags": sd.get("tags", []),
            "episode_count": str(sd.get("episode_cnt", "")),
            "popularity": sd.get("popularity", 0),
            "category": " ".join(sd.get("tags", [])[:3]),
        }
        vid_list: list = sd.get("vid_list", [])
        if not vid_list:
            # 尝试从 chapter_ids 获取
            page_data_alt = ssr["loaderData"]["detail_page"].get("chapter_ids", [])
            if page_data_alt:
                vid_list = page_data_alt
        self.finished.emit(series_info, vid_list, "detail_page")


class FetchEpisodeUrlWorker(QThread):
    """批量获取剧集播放地址"""
    progress = Signal(int, int)          # current, total
    episode_ready = Signal(int, str)     # episode_index (1-based), play_url
    finished = Signal(dict)              # {index: play_url}
    log_msg = Signal(str, str)           # message, level
    error = Signal(str)

    def __init__(self, vid_list: list, base_params: dict, page_path: str):
        super().__init__()
        self._vid_list = vid_list
        self._base_params = base_params
        self._page_path = page_path
        self._stop_flag = False

    def run(self):
        session = requests.Session()
        session.headers.update(HEADERS)
        play_urls = {}
        total = len(self._vid_list)

        for idx, vid in enumerate(self._vid_list, 1):
            if self._stop_flag:
                break

            episode_url = build_episode_url(self._base_params, vid, self._page_path)
            try:
                resp = session.get(episode_url, allow_redirects=True, timeout=30)
                ssr = extract_ssr_data(resp.text)
                if ssr:
                    page_data, _ = parse_page_data(ssr)
                    if page_data and page_data["series_data"].get("play_url"):
                        play_urls[idx] = page_data["series_data"]["play_url"]
                        self.episode_ready.emit(idx, play_urls[idx])
                        self.log_msg.emit(f"第 {idx}/{total} 集 [OK]", "SUCCESS")
                    else:
                        self.log_msg.emit(f"第 {idx}/{total} 集 [NO URL]", "WARNING")
                else:
                    self.log_msg.emit(f"第 {idx}/{total} 集 [PARSE ERR]", "ERROR")
            except Exception as e:
                self.log_msg.emit(f"第 {idx}/{total} 集 [FAIL]: {e}", "ERROR")

            self.progress.emit(idx, total)
            _time.sleep(1)

        self.finished.emit(play_urls)

    def stop(self):
        self._stop_flag = True
