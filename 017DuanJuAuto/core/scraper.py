"""Playwright 抓取逻辑 —— 运行在专用长期线程中，通过信号与 UI 通信。"""
import os
import time
import queue

from PySide6.QtCore import QThread, Signal

from playwright.sync_api import sync_playwright

from utils.excel_export import export_to_excel

LIST_URL = "https://www.shortdramas.com/page/copyright/book-manage?tab=motion_comic"
CATEGORIES = ["高光-剧情回顾", "高光-剧情解析", "高光-预告片", "花絮", "高光-其他"]
ALL_CATS = ["高光-剧情回顾", "高光-剧情解析", "高光-预告片", "花絮", "高光-其他"]

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

TOTAL_STEPS = 7 + len(CATEGORIES)


def _is_login_page(page):
    return "login" in page.url.lower() or "signin" in page.url.lower()


class BrowserThread(QThread):
    """Dedicated long-lived thread that owns all Playwright objects.
    All scraping runs on this one thread — no cross-thread access."""

    log_message = Signal(str, str)
    progress_update = Signal(int, str)
    finished = Signal(bool, str)
    page_loaded = Signal(list)
    list_loaded = Signal(list)
    login_expired = Signal()

    def __init__(self, user_data_dir: str, headless: bool, parent=None):
        super().__init__(parent)
        self.user_data_dir = user_data_dir
        self.headless = headless
        self._queue: queue.Queue = queue.Queue()
        self._stop_flag = False
        self._page = None

    # ── Public API (called from UI thread) ──

    def submit_list_scrape(self):
        self._queue.put(("list", None))

    def submit_detail_scrape(self, target_name: str, output_dir: str, detail_url: str):
        self._queue.put(("scrape", (target_name, output_dir, detail_url)))

    def request_stop(self):
        self._stop_flag = True

    def shutdown(self):
        self._stop_flag = True
        self._queue.put(None)

    # ── Thread run ──

    def run(self):
        self._log("正在启动浏览器...")
        self._pw = sync_playwright().start()
        launch_args = [] if self.headless else ["--start-maximized"]
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
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
                if self._stop_flag:
                    break
                continue

            if task is None:
                break

            task_type, task_data = task
            self._stop_flag = False

            try:
                if task_type == "list":
                    self._do_list_scrape()
                elif task_type == "scrape":
                    self._do_detail_scrape(*task_data)
            except Exception as e:
                self._log(f"任务异常: {e}", "error")
                self.finished.emit(False, str(e))

        try:
            self._page.close()
        except Exception:
            pass
        try:
            self._context.close()
        except Exception:
            pass
        try:
            self._pw.stop()
        except Exception:
            pass

    # ── Internal helpers ──

    def _log(self, msg: str, level: str = "info"):
        self.log_message.emit(msg, level)

    def _step(self, step: int, desc: str):
        self.progress_update.emit(step, desc)
        self._log(desc)

    def _check_stop(self):
        if self._stop_flag:
            self._log("用户取消", "warning")
            self.finished.emit(False, "已取消")
            return True
        return False

    def _ensure_page(self):
        """如果页面被关闭（如登录退出导致），从 context 重建新页面。"""
        try:
            self._page.url
        except Exception:
            self._log("页面已关闭，正在重建...", "warning")
            self._page = self._context.new_page()
            self._page.set_default_timeout(15000)

    # ── Page helpers ──

    def _click_text(self, text, timeout=10000):
        try:
            elem = self._page.wait_for_selector(f"text='{text}'", timeout=timeout, state="visible")
            elem.click()
            self._log(f"点击了 '{text}'")
            return True
        except Exception as e:
            self._log(f"未找到 '{text}': {e}", "warning")
            return False

    def _handle_popup(self):
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

    def _select_only_category(self, target_cat):
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

    def _scrape_video_cards(self):
        self._page.wait_for_timeout(2000)
        cards_data = []
        cards = self._page.query_selector_all("[class*=positive-card-s]")
        if not cards:
            cards = self._page.query_selector_all("[class*=sortable-item-container]")
        if not cards:
            cards = self._page.query_selector_all("[class*=positiveVideos] > div")
        if not cards:
            cards = self._page.query_selector_all("[class*=content-positive-list] > div > div")
        if not cards:
            self._log("未找到卡片容器", "warning")
            return cards_data
        self._log(f"找到 {len(cards)} 个视频卡片")
        for card in cards:
            try:
                data = {}
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

    def _do_list_scrape(self):
        self._ensure_page()
        self._log("正在打开列表页...")
        self.progress_update.emit(0, "打开列表页...")
        try:
            self._page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            self._log(f"页面加载超时，尝试继续: {e}", "warning")
        self._page.wait_for_timeout(3000)

        self._log(f"当前页面: {self._page.url[:120]}")

        if _is_login_page(self._page):
            if self.headless:
                self._log("静默模式下检测到登录页面，会话已过期", "error")
                self.login_expired.emit()
                self.finished.emit(False, "登录已过期，请关闭静默模式后重试")
                return
            self._log("检测到登录页面，请在浏览器中完成登录...", "warning")
            self.progress_update.emit(0, "等待登录...")
            start = time.time()
            last_logged_30 = 0
            while time.time() - start < 600:
                if self._check_stop():
                    return
                if not _is_login_page(self._page):
                    self._log("登录完成", "success")
                    self._page.wait_for_timeout(2000)
                    break
                elapsed = int(time.time() - start)
                if elapsed // 30 > last_logged_30:
                    self._log(f"已等待 {elapsed} 秒...")
                    last_logged_30 = elapsed // 30
                self._page.wait_for_timeout(1000)
            else:
                self._log("等待登录超时", "error")
                self.finished.emit(False, "等待登录超时")
                return

        self._page.wait_for_timeout(2000)
        all_rows = []
        headers = None
        page_num = 1

        while True:
            if self._check_stop():
                return

            self._log(f"正在抓取第 {page_num} 页...")
            self.progress_update.emit(page_num, f"抓取第 {page_num} 页...")

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
                        page_rows += 1
                except Exception as e:
                    self._log(f"行解析异常: {e}", "warning")
                    continue

            self._log(f"第 {page_num} 页: {page_rows} 条")
            if page_rows > 0:
                self.page_loaded.emit(all_rows[-page_rows:])

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
        self.list_loaded.emit(all_rows)
        self.finished.emit(True, f"共 {len(all_rows)} 条")

    # ── Detail scraping ──

    def _do_detail_scrape(self, target_name: str, output_dir: str, detail_url: str):
        self._ensure_page()
        step = 0
        all_data = {}

        step += 1
        if detail_url:
            self._step(step, f"直接进入详情页: {target_name}")
            self._page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(3000)
            if _is_login_page(self._page):
                if self.headless:
                    self._log("详情页需要登录，会话已过期", "error")
                    self.login_expired.emit()
                    self.finished.emit(False, "登录已过期，请关闭静默模式后重试")
                    return
                step += 1
                self._step(step, "等待登录...")
                start = time.time()
                last_logged_30 = 0
                while time.time() - start < 600:
                    if self._check_stop():
                        return
                    if not _is_login_page(self._page):
                        self._log("登录完成，继续...", "success")
                        self._page.wait_for_timeout(3000)
                        self._page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                        self._page.wait_for_timeout(3000)
                        break
                    elapsed = int(time.time() - start)
                    if elapsed // 30 > last_logged_30:
                        self._log(f"已等待 {elapsed} 秒...")
                        last_logged_30 = elapsed // 30
                    self._page.wait_for_timeout(1000)
                else:
                    self._log("等待登录超时", "error")
                    self.finished.emit(False, "等待登录超时")
                    return
        else:
            self._step(step, "正在打开列表页...")
            try:
                self._page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
            self._page.wait_for_timeout(5000)
            self._log(f"URL: {self._page.url[:100]}")

            if self._check_stop():
                return

            if _is_login_page(self._page):
                if self.headless:
                    self._log("静默模式下检测到登录页面，会话已过期", "error")
                    self.login_expired.emit()
                    self.finished.emit(False, "登录已过期，请关闭静默模式后重试")
                    return
                step += 1
                self._step(step, "等待登录...")
                start = time.time()
                last_logged_30 = 0
                while time.time() - start < 600:
                    if self._check_stop():
                        return
                    if not _is_login_page(self._page):
                        self._log("登录完成，继续...", "success")
                        self._page.wait_for_timeout(3000)
                        break
                    elapsed = int(time.time() - start)
                    if elapsed // 30 > last_logged_30:
                        self._log(f"已等待 {elapsed} 秒...")
                        self.progress_update.emit(step, f"等待登录中 ({elapsed}秒)...")
                        last_logged_30 = elapsed // 30
                    self._page.wait_for_timeout(1000)
                else:
                    self._log("等待登录超时", "error")
                    self.finished.emit(False, "等待登录超时")
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
                if self.headless:
                    self.finished.emit(False, f"未找到'{target_name}'，请确认剧名是否正确")
                    return
                self._log("请在浏览器中手动找到目标并点击详情，5 分钟内有效...", "warning")
                manual_start = time.time()
                last_logged_30 = 0
                while time.time() - manual_start < 300:
                    if self._check_stop():
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
            return

        if _is_login_page(self._page):
            if self.headless:
                self._log("详情页被重定向到登录页面，会话已过期", "error")
                self.login_expired.emit()
                self.finished.emit(False, "登录已过期")
                return
            self._log("检测到登录页面，请在浏览器中登录...", "warning")
            login_start = time.time()
            last_logged = 0
            while time.time() - login_start < 600:
                if self._check_stop():
                    return
                if not _is_login_page(self._page):
                    self._log("登录成功，继续...", "success")
                    self._page.goto(detail_url or self._page.url, wait_until="domcontentloaded", timeout=30000)
                    self._page.wait_for_timeout(3000)
                    break
                elapsed = int(time.time() - login_start)
                if elapsed // 30 > last_logged:
                    self._log(f"等待登录... 已等待 {elapsed} 秒")
                    last_logged = elapsed // 30
                self._page.wait_for_timeout(1000)
            else:
                self._log("等待登录超时", "error")
                self.finished.emit(False, "等待登录超时")
                return

        step += 1
        self._step(step, "点击'抖音原生经营'...")
        douyin_clicked = self._click_text("抖音原生经营")
        if not douyin_clicked:
            if self.headless:
                self._log("未找到'抖音原生经营'按钮，尝试直接查找原生素材", "warning")
            else:
                self._page.wait_for_timeout(60000)
        self._page.wait_for_timeout(2500)

        if self._check_stop():
            return

        step += 1
        self._step(step, "点击'原生素材' tab...")
        tab_clicked = False
        for sel in [
            ".arco-tabs-header-title:has-text('原生素材')",
            "text='原生素材'",
            "span:has-text('原生素材')",
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
            if self.headless:
                self._log("未找到'原生素材'tab，尝试直接抓取当前页面", "warning")
            else:
                self._page.wait_for_timeout(60000)
        self._page.wait_for_timeout(2500)

        if self.headless and not douyin_clicked and not tab_clicked:
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
                self.finished.emit(False, "该剧集无可采集的视频内容")
                return
            self._log(f"直接抓取到 {len(quick_cards)} 个视频卡片")
            all_data = {"原生素材": quick_cards}
            output_path = os.path.join(output_dir, f"{target_name}.xlsx")
            total = export_to_excel(all_data, output_path)
            self._log(f"已保存到: {output_path}", "success")
            self._log(f"共 {total} 条视频记录", "success")
            self.finished.emit(True, output_path)
            return

        if self._check_stop():
            return

        step += 1
        self._step(step, "检查弹窗...")
        for _ in range(3):
            self._handle_popup()
            self._page.wait_for_timeout(1000)
        self._page.wait_for_timeout(2000)
        self._handle_popup()

        if self._check_stop():
            return

        for cat in CATEGORIES:
            step += 1
            self._step(step, f"抓取分类: {cat}")
            self._select_only_category(cat)
            self._page.wait_for_timeout(1000)
            self._handle_popup()
            self._page.wait_for_timeout(1000)
            if self._check_stop():
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
            self.finished.emit(True, output_path)
        else:
            self._log("未采集到数据", "warning")
            self.finished.emit(False, "未采集到数据")
