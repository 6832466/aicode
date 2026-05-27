"""Playwright 采集引擎 —— Singleton 后台线程，通过 WebSocket 广播与前端通信。"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from datetime import datetime

from playwright.sync_api import sync_playwright

from app.core.ws_manager import manager

logger = logging.getLogger(__name__)

LIST_URL = "https://www.shortdramas.com/page/copyright/book-manage?tab=motion_comic"
CATEGORIES = ["高光-剧情回顾", "高光-剧情解析", "高光-预告片", "花絮", "高光-其他"]
ALL_CATS = CATEGORIES.copy()

LIST_HEADERS = [
    "剧集信息", "剧壳状态", "正片状态", "抖音发布账号",
    "红果发布状态", "抖音发布状态", "创建时间", "男女频",
    "分类", "版权状态", "合同状态", "操作",
]
PAGINATION_SELECTORS = [
    ".arco-pagination-item-next:not(.arco-pagination-item-disabled)",
    ".ant-pagination-next:not(.ant-pagination-disabled)",
    ".el-pagination button.btn-next:not([disabled])",
    "li.next:not(.disabled)",
    "button:has-text('下一页'):not([disabled])",
    ".pagination .next:not(.disabled)",
    "[class*=pagination] .next:not(.disabled)",
]
CARD_SELECTORS = [
    "[class*=positive-card-s]",
    "[class*=card-item]",
    "[class*=sortable-item-container]",
    "[class*=positiveVideos] > div",
    "[class*=content-positive-list] > div > div",
    "[class*=video-card]",
    "[class*=material-card]",
    ".semi-card",
    "[class*=semi-card]",
]

TOTAL_STEPS = 7 + len(CATEGORIES)

CLOSED_ERROR_KEYWORDS = ["closed", "crashed", "detached", "target", "protocol error"]


def _is_login_page(page) -> bool:
    return "login" in page.url.lower() or "signin" in page.url.lower()


class ScraperEngine:
    """后台线程，拥有所有 Playwright 对象。
    所有采集都在这一条专用线程上运行，不跨线程访问 Playwright。
    通过 get_scraper_engine() 获取模块级单例。
    """

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._page = None
        self._pw = None
        self._context = None
        self._current_task: str | None = None
        self._current_drama_name: str | None = None
        self._user_data_dir: str = ""
        self._headless: bool = False
        self._total_steps_for_task: int = TOTAL_STEPS

    # ── Lifecycle ──

    def start(self, user_data_dir: str, headless: bool) -> None:
        if self._thread and self._thread.is_alive():
            if self._headless != headless or self._user_data_dir != user_data_dir:
                self.shutdown()
                self._thread.join(timeout=10)
                self._thread = None
                self._queue = queue.Queue()
            else:
                return
        self._user_data_dir = user_data_dir
        self._headless = headless
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._queue.put(None)

    # ── Public API ──

    def submit_list_scrape(self) -> None:
        self._current_task = "list"
        self._queue.put(("list", None))

    def submit_detail_scrape(self, drama_name: str, output_dir: str, detail_url: str) -> None:
        self._current_task = "detail"
        self._current_drama_name = drama_name
        self._total_steps_for_task = TOTAL_STEPS
        self._queue.put(("scrape", (drama_name, output_dir, detail_url)))

    def request_stop(self) -> None:
        self._stop_event.set()

    def get_status(self) -> dict:
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "task_type": self._current_task,
            "drama_name": self._current_drama_name,
        }

    # ── Private: WS broadcast bridge ──

    def _ws_broadcast(self, msg_type: str, payload: dict) -> None:
        msg = {"type": msg_type, **payload}
        manager.broadcast_sync(msg)

    def _log(self, msg: str, level: str = "info") -> None:
        self._ws_broadcast("log", {"level": level, "message": msg, "timestamp": datetime.now().isoformat()})

    def _step(self, step: int, desc: str) -> None:
        percent = int(step / max(self._total_steps_for_task, 1) * 100)
        self._ws_broadcast("progress", {
            "step": step,
            "total_steps": self._total_steps_for_task,
            "description": desc,
            "percent": percent,
        })
        self._log(desc)

    def _check_stop(self) -> bool:
        if self._stop_event.is_set():
            self._log("用户取消", "warning")
            self._ws_broadcast("finished", {"success": False, "message": "已取消", "drama_name": self._current_drama_name or ""})
            return True
        return False

    def _ensure_page(self) -> None:
        if self._page is None:
            self._restart_browser()
            return
        try:
            self._page.evaluate("() => true")
        except Exception:
            self._log("浏览器连接已断开，正在重启...", "warning")
            self._restart_browser()

    def _restart_browser(self) -> None:
        self._cleanup_browser()
        try:
            self._pw = sync_playwright().start()
            launch_args = [] if self._headless else ["--start-maximized"]
            self._context = self._pw.chromium.launch_persistent_context(
                user_data_dir=self._user_data_dir,
                headless=self._headless,
                args=launch_args,
                no_viewport=True,
            )
            self._page = self._context.new_page()
            self._page.set_default_timeout(15000)
            self._log("浏览器已重新启动", "success")
        except Exception as e:
            logger.error(f"浏览器重启失败: {e}")
            self._pw = None
            self._context = None
            self._page = None
            raise

    def _cleanup_browser(self) -> None:
        for attr, method in [("_page", "close"), ("_context", "close"), ("_pw", "stop")]:
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    getattr(obj, method)()
                except Exception as e:
                    logger.warning(f"清理 {attr} 异常: {e}")
            setattr(self, attr, None)

    # ── Login helper ──

    def _wait_for_login(self, step: int | None = None, timeout: int = 600) -> bool:
        """等待用户在浏览器中登录。返回 True 表示登录成功，False 表示超时或取消。"""
        self._log("检测到登录页面，请在浏览器中完成登录...", "warning")
        if step is not None:
            self._ws_broadcast("progress", {"step": step, "total_steps": self._total_steps_for_task, "description": "等待登录...", "percent": int(step / max(self._total_steps_for_task, 1) * 100)})

        start_time = time.time()
        last_logged_30 = 0
        while time.time() - start_time < timeout:
            if self._check_stop():
                return False
            if not _is_login_page(self._page):
                self._log("登录完成", "success")
                self._page.wait_for_timeout(2000)
                return True
            elapsed = int(time.time() - start_time)
            if elapsed // 30 > last_logged_30:
                self._log(f"已等待 {elapsed} 秒...")
                if step is not None:
                    self._ws_broadcast("progress", {"step": step, "total_steps": self._total_steps_for_task, "description": f"等待登录中 ({elapsed}秒)...", "percent": int(step / max(self._total_steps_for_task, 1) * 100)})
                last_logged_30 = elapsed // 30
            self._page.wait_for_timeout(1000)

        self._log("等待登录超时", "error")
        return False

    # ── Page helpers ──

    def _click_text(self, text: str, timeout: int = 10000) -> bool:
        safe_text = text.replace("'", "\\'")
        try:
            elem = self._page.wait_for_selector(f"text='{safe_text}'", timeout=timeout, state="visible")
            elem.click()
            self._log(f"点击了 '{text}'")
            return True
        except Exception:
            pass
        return False

    def _click_any_text(self, texts: list[str], timeout: int = 5000) -> bool:
        """尝试从多个候选文本中点击第一个可见的。"""
        for text in texts:
            try:
                safe_text = text.replace("'", "\\'")
                elem = self._page.wait_for_selector(f"text='{safe_text}'", timeout=timeout, state="visible")
                elem.click()
                self._log(f"点击了 '{text}'")
                return True
            except Exception:
                continue
        self._log(f"未找到任何: {texts}", "warning")
        return False

    def _handle_popup(self) -> bool:
        for btn_text in ["我知道了", "知道了", "确定", "确认"]:
            try:
                btn = self._page.query_selector(f"button:has-text('{btn_text}')")
                if btn and btn.is_visible():
                    btn.click()
                    self._page.wait_for_timeout(1500)
                    return True
            except Exception:
                pass
        return False

    def _select_only_category(self, target_cat: str) -> None:
        try:
            all_span = self._page.query_selector("[class*=meterialTypeTab] span:has-text('全部')")
            if all_span:
                all_span.click()
                self._page.wait_for_timeout(600)
        except Exception:
            pass
        self._page.wait_for_timeout(800)
        for cat in ALL_CATS:
            if cat == target_cat:
                continue
            try:
                span = self._page.query_selector(f"span.semi-checkbox-checked.semi-checkbox-cardType:has-text('{cat}')")
                if span:
                    span.click()
                    self._page.wait_for_timeout(400)
            except Exception:
                pass
        try:
            target_span = self._page.query_selector(
                f"span.semi-checkbox-cardType:has-text('{target_cat}'):not(.semi-checkbox-checked)"
            )
            if target_span:
                target_span.click()
                self._page.wait_for_timeout(400)
        except Exception:
            pass
        self._page.wait_for_timeout(1200)

    def _scrape_video_cards(self) -> list[dict]:
        self._page.wait_for_timeout(2000)
        cards_data: list[dict] = []

        cards = []
        for sel in CARD_SELECTORS:
            cards = self._page.query_selector_all(sel)
            if cards:
                break

        if not cards:
            self._log("未找到卡片容器", "warning")
            return cards_data

        self._log(f"找到 {len(cards)} 个视频卡片")
        for card in cards:
            try:
                data: dict = {}
                title_el = card.query_selector("[class*=positive-card-content-title]:not([class*=block])")
                if title_el:
                    data["标题"] = title_el.inner_text().strip()
                type_el = card.query_selector("[class*=positive-card-cover-material-type]")
                if type_el:
                    data["类型"] = type_el.inner_text().strip()
                dur_el = card.query_selector("[class*=positive-card-cover-duration]")
                if dur_el:
                    data["时长"] = dur_el.inner_text().strip()
                status_el = card.query_selector("[class*=positive-card-content-status]")
                if status_el:
                    data["发布状态"] = status_el.inner_text().strip()
                time_el = card.query_selector("[class*=positive-card-content-time]")
                if time_el:
                    data["时间"] = time_el.inner_text().strip()
                data_items = card.query_selector_all("[class*=positive-card-content-data-item]")
                labels = ["浏览数", "评论数", "点赞数"]
                for i, item in enumerate(data_items):
                    if i < len(labels):
                        data[labels[i]] = item.inner_text().strip()
                order_el = card.query_selector("[class*=positive-card-order]")
                if order_el:
                    data["序号"] = order_el.inner_text().strip()
                if data.get("类型") and data.get("序号"):
                    data["标题"] = f"{data['类型']} #{data['序号']}"
                has_real_data = data.get("类型") or data.get("时长") or data.get("浏览数")
                card_text = card.inner_text()
                is_placeholder = "暂无" in card_text
                if has_real_data and not is_placeholder:
                    cards_data.append(data)
            except Exception as e:
                self._log(f"卡片解析异常: {e}", "warning")
        return cards_data

    # ── List scraping ──

    def _do_list_scrape(self) -> None:
        self._ensure_page()
        self._log("正在打开列表页...")
        self._ws_broadcast("progress", {"step": 0, "total_steps": 1, "description": "打开列表页...", "percent": 0})
        try:
            self._page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            self._log(f"页面加载超时，尝试继续: {e}", "warning")
        self._page.wait_for_timeout(3000)

        self._log(f"当前页面: {self._page.url[:120]}")

        if _is_login_page(self._page):
            if self._headless:
                self._log("静默模式下检测到登录页面，会话已过期", "error")
                self._ws_broadcast("login_expired", {})
                self._ws_broadcast("finished", {"success": False, "message": "登录已过期，请关闭静默模式后重试", "drama_name": ""})
                return
            if not self._wait_for_login():
                self._ws_broadcast("finished", {"success": False, "message": "等待登录超时", "drama_name": ""})
                return

        self._page.wait_for_timeout(2000)
        all_rows = []
        headers = None
        page_num = 1

        while True:
            if self._check_stop():
                return

            self._log(f"正在抓取第 {page_num} 页...")
            self._ws_broadcast("progress", {"step": page_num, "total_steps": page_num, "description": f"抓取第 {page_num} 页...", "percent": 0})

            try:
                self._page.wait_for_selector("table tbody tr", timeout=8000)
            except Exception as e:
                self._log(f"等待表格超时: {e}", "warning")

            self._page.wait_for_timeout(800)

            if headers is None:
                ths = self._page.query_selector_all("thead th")
                headers = []
                for th in ths:
                    txt = th.inner_text().strip()
                    if txt:
                        headers.append(txt)
                if len(headers) > len(LIST_HEADERS):
                    headers = headers[:len(LIST_HEADERS)]
                if not headers:
                    headers = LIST_HEADERS
                self._log(f"表头 ({len(headers)}): {headers}")

            trs = self._page.query_selector_all("table tbody tr")
            page_rows = 0
            new_rows = []
            for tr in trs:
                try:
                    tds = tr.query_selector_all("td")
                    row_data = {}
                    for i, td in enumerate(tds[:12]):
                        row_data[LIST_HEADERS[i] if i < len(LIST_HEADERS) else f"col_{i}"] = td.inner_text().strip()

                    info_text = row_data.get("剧集信息", "")
                    lines = info_text.split("\n")
                    name = lines[0].strip() if lines else ""

                    detail_url = ""
                    links = tr.query_selector_all("a")
                    for link in links:
                        href = link.get_attribute("href") or ""
                        if "short-play-detail" in href:
                            detail_url = href if href.startswith("http") else f"https://www.shortdramas.com{href}"
                            if "/page/" not in detail_url and "/copyright/" in detail_url:
                                detail_url = detail_url.replace("/copyright/", "/page/copyright/")
                            break

                    if name and "暂无" not in name and name != "暂无数据":
                        row_data["_name"] = name
                        row_data["_detail_url"] = detail_url
                        all_rows.append(row_data)
                        new_rows.append(row_data)
                        page_rows += 1
                except Exception as e:
                    self._log(f"行解析异常: {e}", "warning")
                    continue

            self._log(f"第 {page_num} 页: {page_rows} 条")
            if page_rows > 0:
                self._ws_broadcast("page_loaded", {"rows": [_row_to_dto(r) for r in new_rows], "page_num": page_num})

            next_btn = None
            for sel in PAGINATION_SELECTORS:
                try:
                    next_btn = self._page.query_selector(sel)
                    if next_btn and next_btn.is_visible():
                        break
                except Exception:
                    continue

            if next_btn:
                next_btn.click()
                self._page.wait_for_timeout(1500)
                page_num += 1
            else:
                self._log("已到达最后一页")
                break

        self._log(f"列表采集完成，共 {len(all_rows)} 条漫剧", "success")
        self._ws_broadcast("list_complete", {"total_rows": len(all_rows), "all_rows": [_row_to_dto(r) for r in all_rows]})
        self._ws_broadcast("finished", {"success": True, "message": f"共 {len(all_rows)} 条", "drama_name": ""})

    # ── Detail scraping ──

    def _do_detail_scrape(self, target_name: str, output_dir: str, detail_url: str) -> None:
        from app.services.excel_service import export_to_excel
        from app.services.scrape_service import scrape_service

        self._ensure_page()
        step = 0
        all_data: dict[str, list[dict]] = {}

        step += 1
        if detail_url:
            self._step(step, f"直接进入详情页: {target_name}")
            self._page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(3000)
            if _is_login_page(self._page):
                if self._headless:
                    self._log("详情页需要登录，会话已过期", "error")
                    self._ws_broadcast("login_expired", {})
                    self._ws_broadcast("finished", {"success": False, "message": "登录已过期，请关闭静默模式后重试", "drama_name": target_name})
                    self._on_detail_finished(False)
                    return
                step += 1
                if not self._wait_for_login(step=step):
                    self._ws_broadcast("finished", {"success": False, "message": "等待登录超时", "drama_name": target_name})
                    self._on_detail_finished(False)
                    return
                self._page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                self._page.wait_for_timeout(3000)
        else:
            self._step(step, "正在打开列表页...")
            try:
                self._page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
            self._page.wait_for_timeout(5000)
            self._log(f"URL: {self._page.url[:100]}")

            if self._check_stop():
                self._on_detail_finished(False)
                return

            if _is_login_page(self._page):
                if self._headless:
                    self._log("静默模式下检测到登录页面，会话已过期", "error")
                    self._ws_broadcast("login_expired", {})
                    self._ws_broadcast("finished", {"success": False, "message": "登录已过期，请关闭静默模式后重试", "drama_name": target_name})
                    self._on_detail_finished(False)
                    return
                step += 1
                if not self._wait_for_login(step=step):
                    self._ws_broadcast("finished", {"success": False, "message": "等待登录超时", "drama_name": target_name})
                    self._on_detail_finished(False)
                    return

            step += 1
            self._step(step, f"搜索 '{target_name}'...")
            self._page.wait_for_timeout(5000)
            search_input = None
            for ph in ["请输入漫剧名称", "请输入短剧名称", "请输入名称", "搜索"]:
                try:
                    search_input = self._page.query_selector(f"input[placeholder*='{ph}']")
                    if search_input:
                        break
                except Exception:
                    continue
            if search_input:
                search_input.click()
                self._page.wait_for_timeout(500)
                search_input.fill("")
                search_input.type(target_name, delay=50)
                self._page.wait_for_timeout(1000)
                search_input.press("Enter")
                self._page.wait_for_timeout(3000)
                self._log(f"已搜索: {target_name}")

            found = False
            trs = self._page.query_selector_all("table tbody tr")
            for tr in trs:
                try:
                    row_text = tr.inner_text()
                    if "暂无数据" in row_text:
                        continue
                    if target_name in row_text:
                        self._log("找到目标行", "success")
                        links = tr.query_selector_all("a")
                        for link in links:
                            href = link.get_attribute("href") or ""
                            if "short-play-detail" in href:
                                detail_url = href if href.startswith("http") else f"https://www.shortdramas.com{href}"
                                self._page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)
                                found = True
                                break
                        if found:
                            break
                        detail_btn = tr.query_selector("text='查看详情'")
                        if detail_btn:
                            detail_btn.click()
                            self._page.wait_for_timeout(5000)
                            found = True
                            break
                except Exception:
                    continue

            if not found:
                self._log(f"未找到 '{target_name}'", "error")
                if self._headless:
                    self._ws_broadcast("finished", {"success": False, "message": f"未找到'{target_name}'，请确认剧名是否正确", "drama_name": target_name})
                    self._on_detail_finished(False)
                    return
                self._log("请在浏览器中手动找到目标并点击详情，5 分钟内有效...", "warning")
                manual_start = time.time()
                last_logged_30 = 0
                while time.time() - manual_start < 300:
                    if self._check_stop():
                        self._on_detail_finished(False)
                        return
                    if "short-play-detail" in self._page.url:
                        self._log("已进入详情页", "success")
                        break
                    elapsed = int(time.time() - manual_start)
                    if elapsed // 30 > last_logged_30:
                        self._log(f"等待手动操作... 已等待 {elapsed} 秒")
                        last_logged_30 = elapsed // 30
                    self._page.wait_for_timeout(1000)
                else:
                    self._log("等待手动操作超时，继续尝试...", "warning")

        self._page.wait_for_timeout(2000)
        self._log(f"当前 URL: {self._page.url[:120]}")

        if self._check_stop():
            self._on_detail_finished(False)
            return

        if _is_login_page(self._page):
            if self._headless:
                self._log("详情页被重定向到登录页面，会话已过期", "error")
                self._ws_broadcast("login_expired", {})
                self._ws_broadcast("finished", {"success": False, "message": "登录已过期", "drama_name": target_name})
                self._on_detail_finished(False)
                return
            if not self._wait_for_login():
                self._page.goto(detail_url or self._page.url, wait_until="domcontentloaded", timeout=30000)
                self._page.wait_for_timeout(3000)

        step += 1
        self._step(step, "点击'抖音原生经营'...")
        douyin_clicked = self._click_text("抖音原生经营")
        if not douyin_clicked:
            douyin_clicked = self._click_any_text(["抖音", "原生经营", "素材管理", "素材"])
        if not douyin_clicked:
            self._log("未找到'抖音原生经营'按钮，尝试直接查找原生素材", "warning")
        self._page.wait_for_timeout(2000)

        if self._check_stop():
            self._on_detail_finished(False)
            return

        step += 1
        self._step(step, "点击'原生素材' tab...")
        tab_clicked = False
        for sel in [
            ".arco-tabs-header-title:has-text('原生素材')",
            "text='原生素材'",
            "span:has-text('原生素材')",
            "text='素材'",
            ".arco-tabs-header-title:has-text('素材')",
        ]:
            try:
                el = self._page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    tab_clicked = True
                    self._log("点击了原生素材 tab", "success")
                    break
            except Exception:
                continue
        if not tab_clicked:
            self._log("未找到'原生素材'tab，尝试直接抓取当前页面", "warning")
        self._page.wait_for_timeout(2000)

        if not douyin_clicked and not tab_clicked:
            quick_cards = self._scrape_video_cards()
            if not quick_cards:
                fallback_tabs = ["素材", "视频", "原生素材", "内容", "抖音素材"]
                for tab in fallback_tabs:
                    try:
                        el = self._page.query_selector(f"text='{tab}'")
                        if el and el.is_visible():
                            el.click()
                            self._log(f"点击了 '{tab}'")
                            self._page.wait_for_timeout(2000)
                            quick_cards = self._scrape_video_cards()
                            if quick_cards:
                                break
                    except Exception:
                        continue
            if not quick_cards:
                try:
                    body = self._page.query_selector("body")
                    if body:
                        page_text = body.inner_text()[:300].replace("\n", " | ")
                        self._log(f"页面文本摘要: {page_text}")
                except Exception:
                    pass
                self._log("该页面无视频卡片，可能内容不可用", "warning")
                self._ws_broadcast("finished", {"success": False, "message": "该剧集无可采集的视频内容", "drama_name": target_name})
                self._on_detail_finished(False)
                return
            self._log(f"直接抓取到 {len(quick_cards)} 个视频卡片")
            all_data = {"原生素材": quick_cards}
            output_path = os.path.join(output_dir, f"{target_name}.xlsx")
            total = export_to_excel(all_data, output_path)
            self._log(f"已保存到: {output_path}", "success")
            self._log(f"共 {total} 条视频记录", "success")
            self._ws_broadcast("finished", {"success": True, "message": output_path, "drama_name": target_name})
            self._on_detail_finished(True)
            return

        if self._check_stop():
            self._on_detail_finished(False)
            return

        step += 1
        self._step(step, "检查弹窗...")
        for _ in range(3):
            self._handle_popup()
            self._page.wait_for_timeout(1000)
        self._page.wait_for_timeout(2000)
        self._handle_popup()

        if self._check_stop():
            self._on_detail_finished(False)
            return

        for cat in CATEGORIES:
            step += 1
            self._step(step, f"抓取分类: {cat}")
            self._select_only_category(cat)
            self._page.wait_for_timeout(1000)
            self._handle_popup()
            self._page.wait_for_timeout(1000)
            if self._check_stop():
                self._on_detail_finished(False)
                return
            cards = self._scrape_video_cards()
            all_data[cat] = cards
            self._log(f"{cat}: {len(cards)} 条视频", "success")

        step += 1
        output_path = os.path.join(output_dir, f"{target_name}.xlsx")
        self._step(step, f"导出 Excel: {output_path}")

        if any(v for v in all_data.values()):
            total = export_to_excel(all_data, output_path)
            self._log(f"已保存到: {output_path}", "success")
            self._log(f"共 {total} 条视频记录", "success")
            self._ws_broadcast("finished", {"success": True, "message": output_path, "drama_name": target_name})
            self._on_detail_finished(True)
        else:
            self._log("未采集到数据", "warning")
            self._ws_broadcast("finished", {"success": False, "message": "未采集到数据", "drama_name": target_name})
            self._on_detail_finished(False)

    def _on_detail_finished(self, success: bool) -> None:
        """通知 scrape_service 推进批量队列。"""
        from app.services.scrape_service import scrape_service
        try:
            scrape_service.on_batch_item_finished(success)
        except Exception:
            pass

    # ── Private: thread run ──

    def _run(self) -> None:
        self._log("正在启动浏览器...")
        self._pw = sync_playwright().start()
        launch_args = [] if self._headless else ["--start-maximized"]
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=self._user_data_dir,
            headless=self._headless,
            args=launch_args,
            no_viewport=True,
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(15000)
        self._log("浏览器已启动", "success")

        while True:
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                if self._stop_event.is_set():
                    break
                continue

            if task is None:
                break

            task_type, task_data = task
            self._stop_event.clear()

            try:
                if task_type == "list":
                    self._do_list_scrape()
                elif task_type == "scrape":
                    self._do_detail_scrape(*task_data)
            except Exception as e:
                self._log(f"任务异常: {e}", "error")
                if any(kw in str(e).lower() for kw in CLOSED_ERROR_KEYWORDS):
                    try:
                        self._restart_browser()
                        self._log("浏览器已恢复，重试当前任务...", "info")
                        if task_type == "list":
                            self._do_list_scrape()
                        elif task_type == "scrape":
                            self._do_detail_scrape(*task_data)
                        continue
                    except Exception as retry_error:
                        self._log(f"重试失败: {retry_error}", "error")
                self._ws_broadcast("finished", {"success": False, "message": str(e), "drama_name": self._current_drama_name or ""})
                self._on_detail_finished(False)

        self._cleanup_browser()

_engine_instance: ScraperEngine | None = None
_engine_lock = threading.Lock()


def get_scraper_engine() -> ScraperEngine:
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = ScraperEngine()
    return _engine_instance


def _row_to_dto(row: dict) -> dict:
    info_text = row.get("剧集信息", "")
    manju_id = ""
    for line in info_text.split("\n"):
        if "漫剧ID:" in line or "ID:" in line:
            manju_id = line.split(":", 1)[-1].strip()
            break
    if not manju_id:
        manju_id = row.get("_detail_url", "").rsplit("/", 1)[-1].split("?")[0]

    return {
        "name": row.get("_name", ""),
        "manju_id": manju_id,
        "publisher": row.get("抖音发布账号", ""),
        "publish_status": row.get("抖音发布状态", ""),
        "created_time": row.get("创建时间", ""),
        "gender": row.get("男女频", ""),
        "category": row.get("分类", ""),
        "detail_url": row.get("_detail_url", ""),
    }
