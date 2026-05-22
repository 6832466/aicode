"""主窗口 - 应用逻辑编排"""
import json
import re
import time
import logging
import random
import zipfile
import requests
from io import BytesIO
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QAction, QClipboard
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSplitter, QProgressBar, QPushButton, QCheckBox, QMessageBox,
    QApplication, QScrollArea, QFrame, QFileDialog,
)

from .widgets import (
    Sidebar, CardGrid, LogPanel, ToastManager, ImageZoomDialog,
    RefImageItem, safe_filename, is_male_description,
)
from .api import ApiClient, ApiConfig, ApiError, is_recaptcha_error, is_account_banned

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
MAX_POLLS = 12
POLL_INTERVAL = 5


# ═══════════════════════════════════════════════════════════════════
# 后台生图 Worker
# ═══════════════════════════════════════════════════════════════════

class GenerateWorker(QObject):
    """后台线程执行 API 调用"""
    finished = Signal(int, object)  # index, result (url str or Exception)
    log = Signal(str, str)

    def __init__(self, index: int, prompt: str, config: ApiConfig):
        super().__init__()
        self.index = index
        self.prompt = prompt
        self.config = config

    def run(self):
        client = ApiClient(self.config, lambda msg, lvl: self.log.emit(msg, lvl))
        try:
            url = client.call_image_api(self.prompt)
            self.finished.emit(self.index, url)
        except Exception as e:
            self.finished.emit(self.index, e)


class GenerateThread(QThread):
    """后台生成线程"""
    result_ready = Signal(int, object)

    def __init__(self, index: int, prompt: str, config: ApiConfig, log_callback):
        super().__init__()
        self._index = index
        self._prompt = prompt
        self._config = config
        self._log = log_callback

    def run(self):
        client = ApiClient(self._config, self._log)
        try:
            url = client.call_image_api(self._prompt)
            self.result_ready.emit(self._index, url)
        except Exception as e:
            self.result_ready.emit(self._index, e)


# ═══════════════════════════════════════════════════════════════════
# ZIP 打包线程
# ═══════════════════════════════════════════════════════════════════

class ZipThread(QThread):
    result = Signal(bool, str, bytes)

    def __init__(self, chars: list, parent=None):
        super().__init__(parent)
        self._chars = chars

    def run(self):
        buf = BytesIO()
        try:
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, c in enumerate(self._chars):
                    sname = safe_filename(c["name"]) or f"角色_{i + 1}"
                    try:
                        resp = requests.get(c["imageUrl"], timeout=60)
                        if not resp.ok:
                            continue
                        content_type = resp.headers.get("content-type", "")
                        ext_map = {
                            "image/jpeg": "jpg", "image/jpg": "jpg",
                            "image/png": "png", "image/webp": "webp",
                            "image/gif": "gif",
                        }
                        ext = ext_map.get(content_type, "png")
                        zf.writestr(f"{sname}.{ext}", resp.content)
                    except Exception:
                        pass
            self.result.emit(True, f"ZIP 打包完成，共 {len(self._chars)} 张", buf.getvalue())
        except Exception as e:
            self.result.emit(False, str(e), b"")


# ═══════════════════════════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("乐乐角色卡生成器 微信：rpalele")
        self.resize(1400, 900)

        # 状态
        self._characters = []
        self._ref_images = []
        self._is_generating = False
        self._generating_indices = set()  # 正在生成的卡牌索引
        self._active_threads = []  # 活跃的后台线程
        self._gen_queue = []
        self._gen_done = 0
        self._gen_total = 0

        self._toast = ToastManager(self)
        self._setup_ui()
        self._connect_signals()
        self._update_ui_state()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar()
        main_layout.addWidget(self._sidebar)

        # 右侧主区域
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 主区域 Header
        header = QWidget()
        header.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.8);
                border-bottom: 1px solid #d2d2d7;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 18, 28, 14)

        left_header = QHBoxLayout()
        h2 = QLabel("角色卡列表")
        h2.setStyleSheet("font-size: 17px; font-weight: 600; color: #1d1d1f; border: none;")
        left_header.addWidget(h2)

        self._card_count_badge = QLabel("0 个角色")
        self._card_count_badge.setStyleSheet("""
            font-size: 11px; font-weight: 600; color: #0071e3;
            background: #e8f0fe; border: none;
            border-radius: 10px; padding: 2px 8px;
        """)
        left_header.addWidget(self._card_count_badge)
        header_layout.addLayout(left_header)
        header_layout.addStretch()

        # 进度条
        self._progress_wrap = QWidget()
        self._progress_wrap.setVisible(False)
        prog_layout = QHBoxLayout(self._progress_wrap)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedWidth(200)
        prog_layout.addWidget(self._progress_bar)
        self._progress_text = QLabel("0 / 0")
        self._progress_text.setStyleSheet("font-size: 12px; color: #6e6e73; border: none;")
        prog_layout.addWidget(self._progress_text)
        header_layout.addWidget(self._progress_wrap)

        right_layout.addWidget(header)

        # 选择栏
        self._select_bar = QWidget()
        self._select_bar.setVisible(False)
        self._select_bar.setStyleSheet("""
            QWidget {
                background: #e8f0fe;
                border-bottom: 1px solid rgba(0,113,227,0.15);
            }
        """)
        sel_layout = QHBoxLayout(self._select_bar)
        sel_layout.setContentsMargins(28, 6, 28, 6)
        sel_layout.setSpacing(10)

        self._check_all = QCheckBox("全选")
        self._check_all.setStyleSheet("font-size: 13px; font-weight: 500; color: #0071e3;")
        sel_layout.addWidget(self._check_all)

        self._selected_count_label = QLabel("已选 0 张")
        self._selected_count_label.setStyleSheet("font-size: 13px; font-weight: 500; color: #0071e3; border: none;")
        sel_layout.addWidget(self._selected_count_label)
        sel_layout.addStretch()

        for text, slot in [
            ("生成所选", self._generate_selected),
            ("打包所选", self._download_selected),
            ("删除所选", self._delete_selected),
        ]:
            btn = QPushButton(text)
            btn.setFixedHeight(28)
            if "删除" in text:
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 12px; padding: 0 12px; font-weight: 500;
                        background: rgba(255,59,48,0.1); color: #ff3b30;
                        border: 1px solid rgba(255,59,48,0.2); border-radius: 14px;
                    }
                    QPushButton:hover { background: rgba(255,59,48,0.18); }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 12px; padding: 0 12px; font-weight: 500;
                        background: #f5f5f7; color: #1d1d1f;
                        border: 1px solid #d2d2d7; border-radius: 14px;
                    }
                    QPushButton:hover { background: #e8e8ed; }
                """)
            btn.clicked.connect(slot)
            sel_layout.addWidget(btn)

        right_layout.addWidget(self._select_bar)

        # 卡片网格
        self._card_grid = CardGrid()
        right_layout.addWidget(self._card_grid, 1)

        # 日志面板
        self._log_panel = LogPanel()
        right_layout.addWidget(self._log_panel)

        main_layout.addWidget(right, 1)

    def _connect_signals(self):
        # Sidebar signals
        self._sidebar.generate_cards_clicked.connect(self._generate_cards)
        self._sidebar.generate_all_clicked.connect(self._generate_all_images)
        self._sidebar.retry_failed_clicked.connect(self._retry_failed)
        self._sidebar.download_all_clicked.connect(self._download_all)
        self._sidebar.clear_all_clicked.connect(self._clear_all)
        self._sidebar.quick_generate.connect(self._quick_generate)
        self._sidebar.ratio_changed.connect(self._on_ratio_changed)

        # Card grid signals
        self._card_grid.card_generate.connect(self._generate_single)
        self._card_grid.card_download.connect(self._download_single)
        self._card_grid.card_delete.connect(self._delete_card)
        self._card_grid.card_select_toggled.connect(self._on_select_toggled)
        self._card_grid.card_copy_prompt.connect(self._copy_prompt)
        self._card_grid.card_zoom.connect(self._zoom_image)
        self._card_grid.card_retry.connect(self._retry_single)

        # Select bar
        self._check_all.toggled.connect(self._on_select_all)

    # ═══════════════════════════════════════════════════════════════
    # Prompt 构建
    # ═══════════════════════════════════════════════════════════════

    def _build_prompt(self, char: dict) -> str:
        prefix = self._sidebar.get_prefix()
        suffix = self._sidebar.get_suffix()

        # 男性角色去掉女性化描述
        if is_male_description(
            char.get("description", "")
            + char.get("name", "")
            + char.get("aliases", "")
        ):
            suffix = suffix.replace("身材曲线优美，", "").replace("身材曲线优美", "")

        # 有参考图片时去掉"亚洲面孔"
        ref_idx = char.get("refImageIndex")
        if ref_idx is not None and ref_idx < len(self._ref_images):
            prefix = prefix.replace("亚洲面孔，", "").replace("亚洲面孔", "")

        return prefix + char.get("description", "") + suffix

    # ═══════════════════════════════════════════════════════════════
    # API 配置
    # ═══════════════════════════════════════════════════════════════

    def _get_api_config(self) -> ApiConfig:
        cfg = self._sidebar.get_api_config()
        return ApiConfig(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            model=cfg["model"],
            ratio=cfg["ratio"],
        )

    def _get_ref_image_url(self, index: Optional[int]) -> Optional[str]:
        if index is not None and 0 <= index < len(self._ref_images):
            return self._ref_images[index].get("dataUrl")
        return None

    # ═══════════════════════════════════════════════════════════════
    # 生成状态管理
    # ═══════════════════════════════════════════════════════════════

    def _start_generating(self, index: int) -> bool:
        """标记开始生成，返回是否成功"""
        if index in self._generating_indices:
            return False
        if self._is_generating and index not in self._generating_indices:
            # 批量模式下也允许单独重试
            pass
        self._generating_indices.add(index)
        self._is_generating = True
        return True

    def _finish_generating(self, index: int):
        """标记生成完成"""
        self._generating_indices.discard(index)
        if not self._generating_indices:
            self._is_generating = False

    # ═══════════════════════════════════════════════════════════════
    # 单张图片生成
    # ═══════════════════════════════════════════════════════════════

    def _generate_single(self, index: int):
        char = self._characters[index]
        if char.get("status") == "generating":
            self._toast.show("该角色正在生成中，请等待完成")
            return
        if not self._start_generating(index):
            self._toast.show("该角色正在生成中")
            return

        char["status"] = "generating"
        char["retryAttempt"] = 0
        char["pollAttempt"] = 0
        char["prompt"] = self._build_prompt(char)
        self._card_grid.update_card(index)
        self._log_panel.add_log(f"开始生成「{char['name']}」", "req")

        ref_url = self._get_ref_image_url(char.get("refImageIndex"))
        self._run_generation(index, char["prompt"], ref_url)

    def _retry_single(self, index: int):
        char = self._characters[index]
        if char.get("status") != "error":
            return
        if not self._start_generating(index):
            self._toast.show("该角色已在生成队列中")
            return

        char["status"] = "generating"
        char["imageUrl"] = None
        char["retryAttempt"] = 0
        char["pollAttempt"] = 0
        char["prompt"] = self._build_prompt(char)
        self._card_grid.update_card(index)
        self._log_panel.add_log(f"重试生成「{char['name']}」", "req")

        ref_url = self._get_ref_image_url(char.get("refImageIndex"))
        self._run_generation(index, char["prompt"], ref_url)

    def _run_generation(self, index: int, prompt: str, ref_url: Optional[str]):
        """在后台线程中运行 API 调用"""
        config = self._get_api_config()

        def log_cb(msg, level):
            self._log_panel.add_log(msg, level)

        thread = GenerateThread(index, prompt, config, log_cb)
        thread.result_ready.connect(self._on_generation_result)
        thread.finished.connect(lambda t=thread: self._cleanup_thread(t))
        self._active_threads.append(thread)
        thread.start()

    def _cleanup_thread(self, thread):
        if thread in self._active_threads:
            self._active_threads.remove(thread)

    def _on_generation_result(self, index: int, result):
        """处理生成结果（在主线程中回调）"""
        char = self._characters[index]

        if isinstance(result, str):
            char["imageUrl"] = result
            char["status"] = "done"
            char["pollAttempt"] = 0
            self._log_panel.add_log(f"「{char['name']}」图片已生成", "ok")
            self._toast.show(f"「{char['name']}」图片已生成", "success")
        elif isinstance(result, Exception):
            error_msg = str(result)
            if is_recaptcha_error(error_msg):
                max_p = MAX_POLLS if is_account_banned(error_msg) else min(MAX_POLLS, 6)
                self._log_panel.add_log(
                    f"「{char['name']}」触发 reCAPTCHA，开始轮询（最多{max_p}次）…", "warn"
                )
                self._toast.show(f"「{char['name']}」reCAPTCHA，自动轮询中…", "warn")
                self._start_polling(index, max_p)
                return
            else:
                char["status"] = "error"
                self._log_panel.add_log(f"「{char['name']}」失败：{error_msg}", "error")
                self._toast.show(f"生成失败：{error_msg}", "error")
        else:
            char["status"] = "error"

        self._finish_generating(index)
        self._log_panel.set_idle()
        self._card_grid.update_card(index)
        self._update_ui_state()

    def _start_polling(self, index: int, remaining: int):
        """开始 reCAPTCHA 轮询"""
        char = self._characters[index]
        char["pollAttempt"] = (MAX_POLLS if remaining < MAX_POLLS else 0) - remaining + 1
        self._card_grid.update_card(index)

        if remaining <= 0:
            char["status"] = "error"
            self._finish_generating(index)
            self._log_panel.add_log(f"「{char['name']}」轮询全部失败", "warn")
            self._log_panel.set_idle()
            self._card_grid.update_card(index)
            self._update_ui_state()
            return

        self._log_panel.add_log(
            f"  [轮询 {char['pollAttempt']}/{char['pollAttempt'] + remaining - 1}] 尝试获取…", "req"
        )

        config = self._get_api_config()
        prompt = char.get("prompt", self._build_prompt(char))
        ref_url = self._get_ref_image_url(char.get("refImageIndex"))

        def log_cb(msg, level):
            self._log_panel.add_log(msg, level)

        self._poll_thread = GenerateThread(index, prompt, config, log_cb)
        self._poll_thread.result_ready.connect(
            lambda i, r: self._on_poll_result(i, r, remaining - 1)
        )
        self._poll_thread.start()

    def _on_poll_result(self, index: int, result, remaining: int):
        """处理轮询结果"""
        char = self._characters[index]

        if isinstance(result, str):
            char["imageUrl"] = result
            char["status"] = "done"
            char["pollAttempt"] = 0
            self._log_panel.add_log(f"「{char['name']}」轮询成功！", "ok")
            self._toast.show(f"「{char['name']}」轮询成功！", "success")
            self._finish_generating(index)
            self._log_panel.set_idle()
            self._card_grid.update_card(index)
            self._update_ui_state()
        elif isinstance(result, Exception):
            error_msg = str(result)
            if not is_recaptcha_error(error_msg):
                char["status"] = "error"
                self._finish_generating(index)
                self._log_panel.add_log(f"轮询中断：{error_msg}", "error")
                self._log_panel.set_idle()
                self._card_grid.update_card(index)
                self._update_ui_state()
            else:
                # 仍是 reCAPTCHA，继续轮询
                QTimer.singleShot(POLL_INTERVAL * 1000, lambda: self._start_polling(index, remaining))

    # ═══════════════════════════════════════════════════════════════
    # JSON 解析 → 生成角色卡
    # ═══════════════════════════════════════════════════════════════

    def _generate_cards(self):
        raw = self._sidebar.get_json_text().strip()
        if not raw:
            self._toast.show("请先输入 JSON 角色数据")
            return

        # 兼容 markdown 代码块
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
        json_str = match.group(1) if match else raw

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            self._toast.show(f"JSON 格式错误：{e}", "error")
            return

        if not isinstance(data, list):
            self._toast.show("请输入 JSON 数组格式", "error")
            return

        # 获取参考图片
        self._ref_images = self._sidebar.get_ref_images()

        if self._ref_images:
            # 参考图片模式：每张图片生成一个角色卡
            self._characters = []
            for i, img in enumerate(self._ref_images):
                desc = img.get("prompt", "").strip()
                char = {
                    "name": img.get("fileName", f"参考图{i + 1}"),
                    "aliases": "",
                    "description": desc,
                    "imageUrl": None,
                    "status": "idle",
                    "prompt": "",
                    "refImageIndex": i,
                    "_selected": False,
                }
                prefix = self._sidebar.get_prefix()
                suffix = self._sidebar.get_suffix()
                if desc:
                    char["prompt"] = prefix + desc + suffix
                else:
                    char["prompt"] = prefix + suffix
                self._characters.append(char)
        else:
            self._characters = []
            for d in data:
                self._characters.append({
                    "name": d.get("name", "未知角色"),
                    "aliases": d.get("aliases", ""),
                    "description": d.get("description", ""),
                    "imageUrl": None,
                    "status": "idle",
                    "prompt": "",
                    "_selected": False,
                })

        self._card_grid.set_characters(self._characters)
        self._update_ui_state()
        self._toast.show(f"已生成 {len(self._characters)} 个角色卡", "success")

    # ═══════════════════════════════════════════════════════════════
    # 批量生成
    # ═══════════════════════════════════════════════════════════════

    def _generate_all_images(self):
        if self._is_generating:
            self._toast.show("正在生成中，请等待当前任务完成")
            return
        indices = [
            i for i, c in enumerate(self._characters)
            if c.get("status") != "generating" and i not in self._generating_indices
        ]
        self._run_batch(indices)

    def _generate_selected(self):
        if self._is_generating:
            self._toast.show("正在生成中，请等待当前任务完成")
            return
        indices = [
            i for i, c in enumerate(self._characters)
            if c.get("_selected") and c.get("status") != "generating" and i not in self._generating_indices
        ]
        if not indices:
            self._toast.show("请先选择角色")
            return
        self._run_batch(indices)

    def _retry_failed(self):
        if self._is_generating:
            self._toast.show("正在生成中，请等待当前任务完成")
            return
        indices = [
            i for i, c in enumerate(self._characters)
            if c.get("status") == "error"
        ]
        if not indices:
            self._toast.show("没有失败的角色可重试")
            return
        for i in indices:
            self._characters[i]["status"] = "idle"
            self._characters[i]["imageUrl"] = None
        self._card_grid.update_all()
        self._log_panel.add_log(f"开始重试 {len(indices)} 个失败角色", "req")
        self._run_batch(indices)

    def _run_batch(self, indices: list):
        if not indices:
            self._toast.show("没有可生图的角色")
            return

        self._is_generating = True
        for idx in indices:
            self._generating_indices.add(idx)
        self._gen_total = len(indices)
        self._gen_done = 0
        self._set_progress(0, self._gen_total)
        self._log_panel.add_log(f"批量生图开始，共 {self._gen_total} 个角色", "req")

        self._queue = list(indices)
        self._process_next_batch()

    def _process_next_batch(self):
        if not self._queue:
            self._is_generating = False
            self._generating_indices.clear()
            self._update_ui_state()
            self._log_panel.add_log(
                f"批量生图完成 {self._gen_done}/{self._gen_total}",
                "ok" if self._gen_done == self._gen_total else "warn",
            )
            self._log_panel.set_idle()
            self._toast.show(f"批量生图完成 {self._gen_done}/{self._gen_total}", "success")
            self._hide_progress_delayed()
            return

        index = self._queue.pop(0)
        char = self._characters[index]

        char["status"] = "generating"
        char["retryAttempt"] = 0
        char["prompt"] = self._build_prompt(char)
        self._card_grid.update_card(index)
        self._log_panel.add_log(
            f"[{self._gen_done + 1}/{self._gen_total}] 开始「{char['name']}」", "req"
        )

        ref_url = self._get_ref_image_url(char.get("refImageIndex"))
        config = self._get_api_config()

        def log_cb(msg, level):
            self._log_panel.add_log(msg, level)

        self._batch_thread = GenerateThread(index, char["prompt"], config, log_cb)
        self._batch_thread.result_ready.connect(self._on_batch_result)
        self._batch_thread.start()

    def _on_batch_result(self, index: int, result):
        char = self._characters[index]
        error_msg = None

        if isinstance(result, str):
            char["imageUrl"] = result
            char["status"] = "done"
            self._finish_generating(index)
            self._log_panel.add_log(
                f"[{self._gen_done + 1}/{self._gen_total}] 「{char['name']}」成功", "ok"
            )
        elif isinstance(result, Exception):
            error_msg = str(result)

            if is_account_banned(error_msg):
                char["status"] = "error"
                self._finish_generating(index)
                self._log_panel.add_log(
                    f"[{self._gen_done + 1}/{self._gen_total}] 「{char['name']}」账号风控，跳过", "warn"
                )
            elif is_recaptcha_error(error_msg):
                # 指数退避重试 — 不调用 _finish_generating，继续占用该索引
                self._log_panel.add_log(f"「{char['name']}」reCAPTCHA，准备重试…", "warn")
                QTimer.singleShot(5000, lambda: self._batch_retry(index, 1, MAX_RETRIES - 1))
                return
            else:
                char["status"] = "error"
                self._finish_generating(index)
                self._log_panel.add_log(
                    f"[{self._gen_done + 1}/{self._gen_total}] 「{char['name']}」失败：{error_msg}", "error"
                )

        self._gen_done += 1
        self._set_progress(self._gen_done, self._gen_total)
        self._card_grid.update_card(index)

        # 延迟 30-45 秒后处理下一个
        delay = random.randint(30, 45) * 1000
        QTimer.singleShot(delay, self._process_next_batch)

    def _batch_retry(self, index: int, attempt: int, max_attempts: int):
        if attempt > max_attempts:
            self._characters[index]["status"] = "error"
            self._finish_generating(index)
            self._log_panel.add_log(f"「{self._characters[index]['name']}」最终失败", "error")
            self._gen_done += 1
            self._set_progress(self._gen_done, self._gen_total)
            self._card_grid.update_card(index)
            delay = random.randint(30, 45) * 1000
            QTimer.singleShot(delay, self._process_next_batch)
            return

        char = self._characters[index]
        self._log_panel.add_log(
            f"[重试 {attempt}/{max_attempts}] 「{char['name']}」正在请求…", "req"
        )

        config = self._get_api_config()
        prompt = char.get("prompt", self._build_prompt(char))

        def log_cb(msg, level):
            self._log_panel.add_log(msg, level)

        thread = GenerateThread(index, prompt, config, log_cb)

        def on_retry_result(i, r):
            char = self._characters[i]
            if isinstance(r, str):
                char["imageUrl"] = r
                char["status"] = "done"
                self._finish_generating(i)
                self._log_panel.add_log(f"「{char['name']}」重试成功", "ok")
                self._gen_done += 1
                self._set_progress(self._gen_done, self._gen_total)
                self._card_grid.update_card(i)
                delay = random.randint(30, 45) * 1000
                QTimer.singleShot(delay, self._process_next_batch)
            elif isinstance(r, Exception):
                error_msg = str(r)
                if is_account_banned(error_msg):
                    char["status"] = "error"
                    self._finish_generating(i)
                    self._log_panel.add_log(f"「{char['name']}」账号被风控，停止重试", "warn")
                    self._gen_done += 1
                    self._set_progress(self._gen_done, self._gen_total)
                    self._card_grid.update_card(i)
                    delay = random.randint(30, 45) * 1000
                    QTimer.singleShot(delay, self._process_next_batch)
                else:
                    self._log_panel.add_log(
                        f"[重试 {attempt}/{max_attempts}] 失败：{error_msg}", "error"
                    )
                    backoff = [5000, 15000, 30000][attempt - 1] if attempt <= 3 else 30000
                    QTimer.singleShot(backoff, lambda: self._batch_retry(i, attempt + 1, max_attempts))

        thread.result_ready.connect(on_retry_result)
        self._active_threads.append(thread)
        thread.start()

    # ═══════════════════════════════════════════════════════════════
    # 快速生成
    # ═══════════════════════════════════════════════════════════════

    def _quick_generate(self, name: str, desc: str):
        if self._is_generating:
            self._toast.show("正在生成中，请等待当前任务完成")
            return

        char = {
            "name": name,
            "aliases": "",
            "description": desc,
            "imageUrl": None,
            "status": "generating",
            "prompt": "",
            "_selected": False,
        }
        char["prompt"] = self._build_prompt(char)

        idx = len(self._characters)
        self._characters.append(char)
        self._card_grid.set_characters(self._characters)
        self._update_ui_state()
        self._start_generating(idx)
        self._sidebar.set_quick_generating(True)
        self._log_panel.add_log(f"快速生成「{name}」", "req")

        config = self._get_api_config()

        def log_cb(msg, level):
            self._log_panel.add_log(msg, level)

        thread = GenerateThread(idx, char["prompt"], config, log_cb)
        self._active_threads.append(thread)

        def on_result(i, r):
            self._sidebar.set_quick_generating(False)
            self._finish_generating(i)
            if isinstance(r, str):
                self._characters[i]["imageUrl"] = r
                self._characters[i]["status"] = "done"
                self._log_panel.add_log(f"「{name}」快速生成成功", "ok")
                self._toast.show(f"「{name}」生成成功！", "success")
            elif isinstance(r, Exception):
                self._characters[i]["status"] = "error"
                self._log_panel.add_log(f"「{name}」快速生成失败：{r}", "error")
                self._toast.show(f"生成失败：{r}", "error")
            self._log_panel.set_idle()
            self._card_grid.update_card(i)
            self._update_ui_state()

        thread.result_ready.connect(on_result)
        thread.start()

    # ═══════════════════════════════════════════════════════════════
    # 下载
    # ═══════════════════════════════════════════════════════════════

    def _download_single(self, index: int):
        char = self._characters[index]
        url = char.get("imageUrl")
        if not url:
            self._toast.show("该角色尚无图片")
            return
        self._fetch_and_download(url, safe_filename(char["name"]))

    def _download_all(self):
        chars_with_images = [c for c in self._characters if c.get("imageUrl")]
        if not chars_with_images:
            self._toast.show("没有可下载的图片")
            return
        self._toast.show(f"正在打包 {len(chars_with_images)} 张图片为 ZIP…")
        self._do_zip_download(chars_with_images, f"角色卡_{len(chars_with_images)}张")

    def _download_selected(self):
        selected = [c for c in self._characters if c.get("_selected") and c.get("imageUrl")]
        if not selected:
            self._toast.show("所选角色中没有已生成的图片")
            return
        self._toast.show(f"正在打包 {len(selected)} 张图片为 ZIP…")
        self._do_zip_download(selected, f"角色卡_所选_{len(selected)}张")

    def _do_zip_download(self, chars: list, prefix: str):
        """使用 QThread 在后台打包 ZIP"""
        self._log_panel.add_log(f"开始打包 ZIP，共 {len(chars)} 张", "req")

        self._zip_thread = ZipThread(chars)
        self._zip_thread.result.connect(self._on_zip_done)
        self._zip_thread.start()

    def _on_zip_done(self, success: bool, message: str, data: bytes):
        if success:
            self._log_panel.add_log(message, "ok")
            path, _ = QFileDialog.getSaveFileName(
                self, "保存 ZIP", f"角色卡_{int(time.time())}.zip", "ZIP Files (*.zip)"
            )
            if path:
                with open(path, "wb") as f:
                    f.write(data)
                self._toast.show("ZIP 保存成功", "success")
        else:
            self._log_panel.add_log(f"ZIP 失败：{message}", "error")
            self._toast.show(f"打包失败：{message}", "error")

    def _fetch_and_download(self, url: str, filename: str):
        try:
            resp = requests.get(url, timeout=60)
            if not resp.ok:
                self._toast.show(f"下载失败: HTTP {resp.status_code}", "error")
                return
            content_type = resp.headers.get("content-type", "")
            ext_map = {"image/jpeg": "jpg", "image/jpg": "jpg",
                       "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
            ext = ext_map.get(content_type, "png")
            path, _ = QFileDialog.getSaveFileName(
                self, "保存图片", f"{filename}.{ext}", "Images (*.png *.jpg *.webp)"
            )
            if path:
                with open(path, "wb") as f:
                    f.write(resp.content)
                self._toast.show("图片保存成功", "success")
        except Exception as e:
            self._toast.show(f"下载失败：{e}", "error")

    # ═══════════════════════════════════════════════════════════════
    # 其他操作
    # ═══════════════════════════════════════════════════════════════

    def _copy_prompt(self, index: int):
        char = self._characters[index]
        prompt = self._build_prompt(char)
        QApplication.clipboard().setText(prompt)
        self._toast.show(f"「{char['name']}」提示词已复制", "success")

    def _zoom_image(self, url: str):
        dialog = ImageZoomDialog(self)
        dialog.show_image(url)

    def _delete_card(self, index: int):
        if 0 <= index < len(self._characters):
            self._characters.pop(index)
            self._card_grid.set_characters(self._characters)
            self._update_ui_state()

    def _delete_selected(self):
        selected = [c for c in self._characters if c.get("_selected")]
        if not selected:
            self._toast.show("请先勾选要删除的角色卡")
            return
        count = len(selected)
        ret = QMessageBox.question(
            self, "确认删除", f"确定删除选中的 {count} 个角色卡吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self._characters = [c for c in self._characters if not c.get("_selected")]
            self._card_grid.set_characters(self._characters)
            self._update_ui_state()
            self._toast.show(f"已删除 {count} 个角色卡", "success")

    def _clear_all(self):
        if not self._characters:
            return
        ret = QMessageBox.question(
            self, "确认清空", "确定要清空所有角色卡吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self._characters.clear()
            self._is_generating = False
            self._generating_indices.clear()
            self._card_grid.set_characters([])
            self._update_ui_state()

    def _on_select_toggled(self, index: int, selected: bool):
        if 0 <= index < len(self._characters):
            self._characters[index]["_selected"] = selected
            self._update_selected_count()

    def _on_select_all(self, checked: bool):
        for c in self._characters:
            c["_selected"] = checked
        self._card_grid.update_all()
        self._update_selected_count()

    def _on_ratio_changed(self, ratio: str):
        pass  # ratio change is handled at API config level

    # ═══════════════════════════════════════════════════════════════
    # UI 状态更新
    # ═══════════════════════════════════════════════════════════════

    def _update_ui_state(self):
        n = len(self._characters)
        self._card_count_badge.setText(f"{n} 个角色")

        has_cards = n > 0
        has_images = any(c.get("imageUrl") for c in self._characters)
        has_failed = any(c.get("status") == "error" for c in self._characters)

        self._sidebar.set_buttons_enabled(has_cards, has_images, has_failed)
        self._select_bar.setVisible(has_cards)
        self._update_selected_count()

    def _update_selected_count(self):
        n = sum(1 for c in self._characters if c.get("_selected"))
        self._selected_count_label.setText(f"已选 {n} 张")
        self._check_all.blockSignals(True)
        self._check_all.setChecked(n == len(self._characters) and n > 0)
        self._check_all.blockSignals(False)

    def _set_progress(self, done: int, total: int):
        self._progress_wrap.setVisible(True)
        pct = int(done / total * 100) if total > 0 else 0
        self._progress_bar.setValue(pct)
        self._progress_text.setText(f"{done} / {total}")

    def _hide_progress_delayed(self):
        QTimer.singleShot(2000, lambda: self._progress_wrap.setVisible(False))
