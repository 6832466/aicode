"""图片生成页面 —— 垫图生图 + 排队系统。"""

import base64
import io
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

import requests
from requests.exceptions import ConnectTimeout, ReadTimeout, ConnectionError as ReqConnectionError
from PIL import Image

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QFileDialog, QScrollArea,
    QGridLayout, QSplitter, QPlainTextEdit, QMenu, QMessageBox, QPushButton,
)
from PySide6.QtCore import (
    Qt, Signal, QThreadPool, QRunnable, QObject, QSize, QTimer,
)
from PySide6.QtGui import (
    QDragEnterEvent, QDropEvent, QPixmap, QFont, QPainter, QPen, QColor,
    QDesktopServices,
)
from PySide6.QtCore import QUrl

from qfluentwidgets import (
    TitleLabel, BodyLabel, CaptionLabel,
    ComboBox,
    PrimaryPushButton, PushButton,
    FluentIcon, InfoBar, InfoBarPosition,
)

from api_config import api_config, get_session_cookie, get_user_id, get_img_save_dir, MODEL_CHOICES
from log_service import log_service

# ── 尺寸选项 ─────────────────────────────────────────────────

SIZE_CHOICES = [
    ("9:16 (竖屏) — 1024×1792", "1024x1792"),
    ("16:9 (横屏) — 1792×1024", "1792x1024"),
    ("3:4 — 1024×1365", "1024x1365"),
    ("4:3 — 1365×1024", "1365x1024"),
    ("1:1 (方形) — 1024×1024", "1024x1024"),
]

IMAGE_MODELS = [(d, v) for d, v in MODEL_CHOICES if v.startswith("gpt-image")]

BJ_BASE_URL = "https://bj.nfai.lol/pg"


def _out_dir() -> Path:
    d = get_img_save_dir()
    return Path(d) if d else Path(__file__).parent / "generated"


def _make_filename(seq: int, prompt: str) -> str:
    """序号 + 描述词前10字，去除文件名非法字符。"""
    safe = re.sub(r'[\\/:*?"<>|]', "", prompt)[:10]
    return f"{seq}_{safe}.png"


# ── 拖放区域 ──────────────────────────────────────────────────

class DropZone(QWidget):
    """虚线边框图片拖放区，支持拖放文件或点击选择。"""

    image_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumSize(140, 140)
        self.setMaximumSize(200, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._path: Path | None = None
        self._thumbnail: QPixmap | None = None

        # 鼠标悬停时显示的删除按钮
        self._del_btn = QPushButton("ⓧ", self)
        self._del_btn.setFixedSize(22, 22)
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.setStyleSheet(
            "QPushButton { color: #f85149; background: rgba(255,255,255,200); "
            "border: none; border-radius: 11px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #f85149; color: #fff; }"
        )
        self._del_btn.clicked.connect(self.clear)
        self._del_btn.hide()

    @property
    def path(self) -> Path | None:
        return self._path

    def set_image(self, path: Path) -> None:
        self._path = path
        img = Image.open(path)
        img.thumbnail((200, 200), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self._thumbnail = QPixmap()
        self._thumbnail.loadFromData(buf.getvalue())
        self.image_changed.emit()
        self.update()

    def clear(self) -> None:
        self._path = None
        self._thumbnail = None
        self._del_btn.hide()
        self.image_changed.emit()
        self.update()

    def enterEvent(self, event) -> None:
        if self._thumbnail:
            self._del_btn.move(self.width() - 26, 4)
            self._del_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._del_btn.hide()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(3, 3, -3, -3)
        pen = QPen(QColor("#a0a0a0"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor("#fafafa"))
        painter.drawRoundedRect(r, 10, 10)

        if self._thumbnail:
            pm = self._thumbnail.scaled(
                self.size() - QSize(10, 10),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - pm.width()) // 2
            y = (self.height() - pm.height()) // 2
            painter.drawPixmap(x, y, pm)
        else:
            painter.setPen(QColor("#909090"))
            font = QFont()
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "拖放图片\n或点击选择")

    def mousePressEvent(self, event) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if path:
            self.set_image(Path(path))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            p = Path(urls[0].toLocalFile())
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                self.set_image(p)


# ── 历史记录行 ──────────────────────────────────────────────

class HistoryRow(QFrame):
    """单条记录：序号 | 缩略图/状态 | 描述词 | 计时 | 右键菜单。"""

    retry_requested = Signal(dict)   # job_data for full retry
    retry_download = Signal(str)     # download_url
    delete_requested = Signal(int)   # seq

    def __init__(self, seq: int, prompt: str, submit_time: datetime,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self.seq = seq
        self.prompt = prompt
        self.submit_time = submit_time
        self.result_path: str | None = None
        self.error_msg: str | None = None
        self.download_url: str | None = None  # 下载失败时保留
        self.job_data: dict | None = None
        self._done = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # 序号
        seq_label = BodyLabel(f"#{seq}")
        seq_label.setFixedWidth(30)
        layout.addWidget(seq_label)

        # 缩略图 / 状态
        self._thumb = QLabel()
        self._thumb.setFixedSize(48, 48)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setText("…")
        self._thumb.setStyleSheet("color: #999; border: 1px solid #ddd; border-radius: 4px; font-size: 10px;")
        layout.addWidget(self._thumb)

        # 描述词
        desc = (prompt[:50] + "…") if len(prompt) > 50 else prompt
        self._desc_label = BodyLabel(desc)
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._desc_label, stretch=1)

        # 重试按钮（初始隐藏，失败/超时时显示）
        self._retry_btn = PushButton("重试")
        self._retry_btn.setFixedSize(52, 28)
        self._retry_btn.setStyleSheet(
            "PushButton { color: #f85149; border: 1px solid #f85149; border-radius: 4px; font-size: 11px; }"
            "PushButton:hover { background: #f85149; color: #fff; }"
        )
        self._retry_btn.clicked.connect(self._on_retry)
        self._retry_btn.hide()
        layout.addWidget(self._retry_btn)

        # 计时
        self._time_label = CaptionLabel("00:00")
        self._time_label.setFixedWidth(36)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._time_label)

        # 让所有子控件右键事件穿透到 HistoryRow
        for child in self.findChildren(QWidget):
            child.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        self._thumb.setPixmap(pixmap.scaled(
            48, 48, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        self._thumb.setStyleSheet("")

    def set_success(self, result_path: str, pixmap: QPixmap) -> None:
        self.result_path = result_path
        self._done = True
        self.set_thumbnail(pixmap)

    def set_failed(self, error: str) -> None:
        self.error_msg = error
        self._done = True
        self._thumb.setText("失败")
        self._thumb.setStyleSheet("color: #f85149; border: 1px solid #f85149; border-radius: 4px; font-size: 11px;")
        self._retry_btn.show()

    def set_timeout(self) -> None:
        """超时：图片可能已生成，可右键重试下载或点击重试按钮重新提交。"""
        self.error_msg = "超时（图片可能已生成）"
        self._done = True
        self._thumb.setText("超时")
        self._thumb.setStyleSheet("color: #f85149; border: 1px solid #f85149; border-radius: 4px; font-size: 11px;")
        self._retry_btn.show()

    def update_timer(self) -> None:
        if self._done:
            return
        elapsed = int((datetime.now() - self.submit_time).total_seconds())
        m, s = divmod(min(elapsed, 5999), 60)
        self._time_label.setText(f"{m:02d}:{s:02d}")

    # ── 右键菜单 ──

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self)

        if self.result_path and Path(self.result_path).exists():
            act_view = menu.addAction("查看图片")
            act_view.triggered.connect(self._view_image)

            act_folder = menu.addAction("打开目录")
            act_folder.triggered.connect(self._open_folder)

            menu.addSeparator()

        if self.download_url:
            act_dl = menu.addAction("重试下载")
            act_dl.triggered.connect(lambda: self.retry_download.emit(self.download_url))

        act_del = menu.addAction("删除")
        act_del.triggered.connect(self._confirm_delete)

        menu.exec(self.mapToGlobal(pos))

    def _view_image(self) -> None:
        if self.result_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.result_path).resolve())))

    def _open_folder(self) -> None:
        if self.result_path:
            folder = str(Path(self.result_path).parent.resolve())
            subprocess.Popen(["explorer", folder])

    def _confirm_delete(self) -> None:
        reply = QMessageBox.question(
            self, "确认删除", f"确定删除 #{self.seq} 的记录及生成文件？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.delete_requested.emit(self.seq)

    def _on_retry(self) -> None:
        # 只有已完成且失败的记录才能重试，防止运行时重复提交
        if self.job_data and self._done and self.error_msg:
            self.retry_requested.emit(self.job_data)


# ── Worker 信号 ──────────────────────────────────────────────

class WorkerSignals(QObject):
    # seq, status("ok"/"error"/"retry_dl"), detail(path or errmsg), download_url
    finished = Signal(int, str, str, str)
    thumbnail = Signal(int, QPixmap)
    log_msg = Signal(int, str, str)  # seq, message, level


# ── 生图 Worker ──────────────────────────────────────────────

class GenWorker(QRunnable):
    """调用豹剪 API 生成单张图片。"""

    def __init__(self, seq: int, prompt: str, image_paths: list[Path],
                 model: str, size: str) -> None:
        super().__init__()
        self.seq = seq
        self.prompt = prompt
        self.image_paths = image_paths
        self.model = model
        self.size = size
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.log_msg.emit(self.seq, f"开始生成，模型={self.model}，尺寸={self.size}，参考图={len(self.image_paths)}张<br>提示词: {self.prompt}", "info")
            content = []
            for p in self.image_paths:
                b64 = self._encode_image(p)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": b64, "detail": "high"},
                })
            content.append({"type": "text", "text": self.prompt})

            headers = {
                "Content-Type": "application/json",
                "Cookie": f"session={get_session_cookie()}",
                "new-api-user": get_user_id(),
            }

            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": content}],
                "stream": False,
                "size": self.size,
                "group": "default",
            }

            url = f"{BJ_BASE_URL}{api_config.api_endpoint_path.value}"

            try:
                resp = requests.post(url, headers=headers, json=payload,
                                     timeout=(10, 300))
                if resp.status_code in (401, 403):
                    self.signals.log_msg.emit(self.seq, "认证失败 (401/403)，请更新 Session Cookie", "error")
                    self.signals.finished.emit(self.seq, "error",
                                               "认证失败，请更新 Session Cookie", "")
                    return
                if resp.status_code == 429:
                    self.signals.log_msg.emit(self.seq, "请求过于频繁 (429)", "error")
                    self.signals.finished.emit(self.seq, "error", "请求过于频繁 (429)", "")
                    return
                if resp.status_code != 200:
                    self.signals.log_msg.emit(self.seq, f"HTTP {resp.status_code}", "error")
                    self.signals.finished.emit(self.seq, "error",
                                               f"HTTP {resp.status_code}", "")
                    return

                data = resp.json()
                if "error" in data:
                    err_info = data["error"]
                    err_msg = err_info.get("message", str(err_info))
                    self.signals.log_msg.emit(self.seq, f"API 返回错误: {err_msg}", "error")
                    self.signals.finished.emit(self.seq, "error", err_msg, "")
                    return

                full = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not full:
                    self.signals.log_msg.emit(self.seq, "空响应", "error")
                    self.signals.finished.emit(self.seq, "error", "空响应", "")
                    return

                match = re.search(r"!\[.*?\]\((https?://\S+)\)", full)
                if not match:
                    self.signals.log_msg.emit(self.seq, "响应中未找到图片 URL", "error")
                    self.signals.finished.emit(self.seq, "error",
                                               "响应中未找到图片 URL", "")
                    return

                img_url = match.group(1)
                _out_dir().mkdir(parents=True, exist_ok=True)
                out_path = _out_dir() / _make_filename(self.seq, self.prompt)

                try:
                    dl_resp = requests.get(img_url, timeout=120)
                    dl_resp.raise_for_status()
                    out_path.write_bytes(dl_resp.content)
                except Exception as dl_err:
                    self.signals.log_msg.emit(self.seq, f"下载失败: {dl_err}", "error")
                    self.signals.finished.emit(self.seq, "retry_dl",
                                               f"下载失败: {dl_err}", img_url)
                    return

                self.signals.log_msg.emit(self.seq, f"生成成功 → {out_path.name}", "success")
                pm = QPixmap()
                pm.load(str(out_path))
                self.signals.thumbnail.emit(self.seq, pm)
                self.signals.finished.emit(self.seq, "ok", str(out_path), "")

            except ConnectTimeout:
                self.signals.log_msg.emit(self.seq, "无法连接服务器，请检查网络", "error")
                self.signals.finished.emit(self.seq, "error", "无法连接服务器", "")
            except ReadTimeout:
                self.signals.log_msg.emit(self.seq, "请求超时（300秒无响应）", "error")
                self.signals.finished.emit(self.seq, "timeout",
                                           "超时（300秒无响应）", "")
            except ReqConnectionError:
                self.signals.log_msg.emit(self.seq, "网络连接失败", "error")
                self.signals.finished.emit(self.seq, "error", "网络连接失败", "")

        except Exception as e:
            self.signals.log_msg.emit(self.seq, f"异常: {e}", "error")
            self.signals.finished.emit(self.seq, "error", str(e), "")

    @staticmethod
    def _encode_image(path: Path, max_dim: int = 1024) -> str:
        img = Image.open(path).convert("RGB")
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80, optimize=True)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"


# ── 图片生成页面 ────────────────────────────────────────────

class ImageGenPage(QWidget):
    """图片生成页面：左侧设置，右侧历史记录。"""

    MAX_CONCURRENT = 5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imageGenPage")
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(self.MAX_CONCURRENT)
        self._pending: list[dict] = []
        self._active_count = 0
        self._counter = 0
        self._history_rows: dict[int, HistoryRow] = {}  # seq → row
        self._records_file = Path(__file__).parent / "config" / "generation_records.json"

        self._build_ui()

        # 每秒刷新计时
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_timers)
        self._timer.start(1000)

        # 恢复上次的记录
        self._load_records()

    # ── UI ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # ── 左侧 ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(32, 24, 16, 24)
        left_layout.setSpacing(12)

        left_layout.addWidget(TitleLabel("图片生成"))

        # 三个拖放区域
        dz_grid = QGridLayout()
        dz_grid.setSpacing(12)
        self._drop_zones: list[DropZone] = []
        for i in range(3):
            dz = DropZone()
            self._drop_zones.append(dz)
            dz_grid.addWidget(dz, 0, i)
        left_layout.addLayout(dz_grid)

        dz_hint = CaptionLabel("参考图（可选），支持拖放或点击，最多 3 张")
        dz_hint.setWordWrap(True)
        left_layout.addWidget(dz_hint)

        # 描述词（占左侧 40% 高度）
        self._prompt_edit = QPlainTextEdit()
        self._prompt_edit.setPlaceholderText("输入描述词…")
        left_layout.addWidget(self._prompt_edit, stretch=4)

        # 模型 + 尺寸
        row = QHBoxLayout()
        row.setSpacing(12)

        row.addWidget(BodyLabel("模型"))
        self._model_combo = ComboBox()
        for display, model_id in IMAGE_MODELS:
            self._model_combo.addItem(display, userData=model_id)
        self._model_combo.setCurrentIndex(2)
        row.addWidget(self._model_combo, stretch=1)

        row.addWidget(BodyLabel("尺寸"))
        self._size_combo = ComboBox()
        for display, size_id in SIZE_CHOICES:
            self._size_combo.addItem(display, userData=size_id)
        self._size_combo.setCurrentIndex(1)
        row.addWidget(self._size_combo, stretch=1)

        left_layout.addLayout(row)

        # 生成 + 排队状态
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        self._queue_label = CaptionLabel("")
        btn_row.addWidget(self._queue_label)
        btn_row.addStretch()

        self._gen_btn = PrimaryPushButton(FluentIcon.PLAY, "生成")
        self._gen_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self._gen_btn)

        left_layout.addLayout(btn_row)
        left_layout.addStretch(stretch=6)

        splitter.addWidget(left)

        # ── 右侧（历史记录）──
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 24, 32, 24)
        right_layout.setSpacing(10)

        right_layout.addWidget(TitleLabel("生成记录"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._history_widget = QWidget()
        self._history_layout = QVBoxLayout(self._history_widget)
        self._history_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._history_layout.setSpacing(6)
        self._history_layout.addStretch()

        scroll.setWidget(self._history_widget)
        right_layout.addWidget(scroll)

        # ── 批量操作按钮 ──
        batch_row = QHBoxLayout()
        batch_row.setSpacing(8)

        retry_all_btn = PushButton("一键重试")
        retry_all_btn.clicked.connect(self._on_retry_all)
        batch_row.addWidget(retry_all_btn)

        clear_all_btn = PushButton("清空记录")
        clear_all_btn.clicked.connect(self._on_clear_all)
        batch_row.addWidget(clear_all_btn)

        batch_row.addStretch()
        right_layout.addLayout(batch_row)

        splitter.addWidget(right)
        splitter.setSizes([390, 390])

        root.addWidget(splitter)

    # ── 计时 ────────────────────────────────────────────

    def _tick_timers(self) -> None:
        for row in self._history_rows.values():
            row.update_timer()

    # ── 交互 ────────────────────────────────────────────

    def _selected_images(self) -> list[Path]:
        return [dz.path for dz in self._drop_zones if dz.path is not None]

    def _on_generate(self) -> None:
        images = self._selected_images()
        prompt = self._prompt_edit.toPlainText().strip()

        if not prompt:
            InfoBar.warning("提示", "请输入描述词",
                            position=InfoBarPosition.TOP, parent=self.window())
            return

        # 防止快速双击提交重复任务
        self._gen_btn.setEnabled(False)
        QTimer.singleShot(500, lambda: self._gen_btn.setEnabled(True))

        prefix = api_config.img_prefix.value or ""
        suffix = api_config.img_suffix.value or ""
        full_prompt = f"{prefix} {prompt} {suffix}".strip()

        self._counter += 1
        model = self._model_combo.currentData()
        size = self._size_combo.currentData()

        job = {
            "seq": self._counter,
            "prompt": full_prompt,
            "short_prompt": prompt[:55],
            "images": list(images),
            "model": model,
            "size": size,
            "submit_time": datetime.now(),
        }
        self._pending.append(job)

        row = HistoryRow(job["seq"], job["short_prompt"], job["submit_time"])
        row.job_data = job
        row.retry_requested.connect(self._on_retry_job)
        row.retry_download.connect(self._on_retry_download)
        row.delete_requested.connect(self._on_delete_row)
        self._history_rows[job["seq"]] = row
        self._insert_history_row(row)

        self._update_queue_label()
        log_service.log_message.emit(f"#{job['seq']} 已加入队列 — {prompt[:40]}", "info")
        InfoBar.info(f"已加入队列",
                     f"#{job['seq']} — 排队 {len(self._pending)} / 处理中 {self._active_count}",
                     position=InfoBarPosition.TOP, parent=self.window())

        self._process_queue()

    def _insert_history_row(self, row: HistoryRow) -> None:
        # 最新记录插入到最上方
        self._history_layout.insertWidget(0, row)

    def _update_queue_label(self) -> None:
        t = len(self._pending)
        if t:
            self._queue_label.setText(f"排队 {t} / 处理中 {self._active_count}")
        else:
            self._queue_label.setText(
                "" if self._active_count == 0 else f"处理中 {self._active_count}"
            )

    def _process_queue(self) -> None:
        while self._pending and self._active_count < self.MAX_CONCURRENT:
            job = self._pending.pop(0)
            self._active_count += 1
            self._update_queue_label()

            worker = GenWorker(
                job["seq"], job["prompt"], job["images"],
                job["model"], job["size"],
            )
            worker.signals.finished.connect(self._on_job_done)
            worker.signals.thumbnail.connect(self._on_thumbnail)
            worker.signals.log_msg.connect(
                lambda seq, msg, lvl: log_service.log_message.emit(f"#{seq} {msg}", lvl)
            )
            self._pool.start(worker)

    def _on_thumbnail(self, seq: int, pm: QPixmap) -> None:
        row = self._history_rows.get(seq)
        if row:
            row.set_thumbnail(pm)

    def _on_job_done(self, seq: int, status: str, detail: str, dl_url: str) -> None:
        self._active_count -= 1
        self._update_queue_label()

        row = self._history_rows.get(seq)
        if not row:
            self._process_queue()
            return

        if status == "ok":
            row.set_success(detail, QPixmap(detail))
            log_service.log_message.emit(f"#{seq} 完成 → {Path(detail).name}", "success")
            InfoBar.success(f"#{seq} 完成",
                            f"已保存至 {detail}",
                            position=InfoBarPosition.TOP, parent=self.window())
        elif status == "retry_dl":
            row.download_url = dl_url
            row.set_failed(detail)
            log_service.log_message.emit(f"#{seq} 下载失败，可右键重试下载", "error")
            InfoBar.warning(f"#{seq} 下载失败",
                            f"{detail}\n右键可重试下载",
                            position=InfoBarPosition.TOP, parent=self.window())
        elif status == "timeout":
            row.set_timeout()
            log_service.log_message.emit(f"#{seq} 超时，图片可能已生成", "error")
            InfoBar.warning(f"#{seq} 超时",
                            "超过300秒未响应，可点击重试按钮重新提交",
                            duration=5000,
                            position=InfoBarPosition.TOP, parent=self.window())
        else:
            row.set_failed(detail)
            log_service.log_message.emit(f"#{seq} 失败: {detail}", "error")
            InfoBar.error(f"#{seq} 失败", detail,
                          position=InfoBarPosition.TOP, parent=self.window())

        self._save_records()
        self._process_queue()

    def _on_retry_download(self, dl_url: str) -> None:
        """重试下载已生成的图片 URL。"""
        # 找到发射信号的 row
        row = self.sender()
        if not isinstance(row, HistoryRow):
            return

        _out_dir().mkdir(parents=True, exist_ok=True)
        out_path = _out_dir() / _make_filename(row.seq, row.prompt)

        try:
            dl_resp = requests.get(dl_url, timeout=120)
            dl_resp.raise_for_status()
            out_path.write_bytes(dl_resp.content)

            pm = QPixmap()
            pm.load(str(out_path))

            row.result_path = str(out_path)
            row.download_url = None
            row.error_msg = None
            row.set_success(str(out_path), pm)
            row._retry_btn.hide()

            log_service.log_message.emit(f"#{row.seq} 重试下载成功 → {out_path.name}", "success")

            InfoBar.success(f"#{row.seq} 下载成功",
                            f"已保存至 {out_path}",
                            position=InfoBarPosition.TOP, parent=self.window())
            self._save_records()
        except Exception as e:
            row.error_msg = f"下载失败: {e}"
            self._save_records()
            InfoBar.error(f"#{row.seq} 下载仍失败",
                          str(e),
                          position=InfoBarPosition.TOP, parent=self.window())

    def _on_retry_job(self, job_data: dict) -> None:
        """重试失败任务，在当前位置保留。"""
        seq = job_data["seq"]
        row = self._history_rows.get(seq)
        if not row:
            return
        # 防止重入：只有已完成且失败的行才能重试
        if not row._done or not row.error_msg:
            return

        # 重置当前行的状态（先清 error_msg 防止重入）
        row._done = False
        row.error_msg = None
        row.download_url = None
        row.result_path = None
        row._retry_btn.hide()
        row._thumb.setText("…")
        row._thumb.setStyleSheet("color: #999; border: 1px solid #ddd; border-radius: 4px; font-size: 10px;")
        row.submit_time = datetime.now()

        job = {
            "seq": seq,
            "prompt": job_data["prompt"],
            "short_prompt": job_data["short_prompt"],
            "images": job_data["images"],
            "model": job_data["model"],
            "size": job_data["size"],
            "submit_time": row.submit_time,
        }
        row.job_data = job
        self._pending.append(job)

        self._update_queue_label()
        log_service.log_message.emit(f"#{seq} 重新加入队列", "info")
        self._process_queue()

    def _on_retry_all(self) -> None:
        """一键重试所有失败记录（重新提交任务）。"""
        to_retry: list[dict] = []
        for row in list(self._history_rows.values()):
            # 只有已完成且失败的行才能重试
            if row._done and row.error_msg and row.job_data:
                to_retry.append(row.job_data)

        if not to_retry:
            InfoBar.info("提示", "没有可重试的记录",
                        position=InfoBarPosition.TOP, parent=self.window())
            return

        log_service.log_message.emit(f"一键重试 {len(to_retry)} 条记录", "info")
        for job_data in to_retry:
            self._on_retry_job(job_data)

    def _save_records(self) -> None:
        """持久化当前所有生成记录到 JSON 文件。"""
        records = []
        for seq, row in self._history_rows.items():
            rec = {
                "seq": seq,
                "short_prompt": row.prompt,
                "submit_time": row.submit_time.isoformat(),
                "result_path": row.result_path,
                "error_msg": row.error_msg,
                "download_url": row.download_url,
                "done": row._done,
            }
            if row.job_data:
                jd = row.job_data
                rec["job_data"] = {
                    "seq": jd["seq"],
                    "prompt": jd["prompt"],
                    "short_prompt": jd["short_prompt"],
                    "images": [str(p) for p in jd["images"]],
                    "model": jd["model"],
                    "size": jd["size"],
                    "submit_time": jd["submit_time"].isoformat(),
                }
            records.append(rec)
        data = {"records": records, "counter": self._counter}
        try:
            self._records_file.parent.mkdir(parents=True, exist_ok=True)
            self._records_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )
        except OSError:
            pass

    def _load_records(self) -> None:
        """从 JSON 文件恢复上次的生成记录。"""
        try:
            data = json.loads(self._records_file.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return

        self._counter = data.get("counter", 0)
        for rec in data.get("records", []):
            seq = rec["seq"]
            submit_time = datetime.fromisoformat(rec["submit_time"])
            row = HistoryRow(seq, rec["short_prompt"], submit_time)
            row._done = rec.get("done", True)
            row.result_path = rec.get("result_path")
            row.error_msg = rec.get("error_msg")
            row.download_url = rec.get("download_url")

            jd = rec.get("job_data")
            if jd:
                row.job_data = {
                    "seq": jd["seq"],
                    "prompt": jd["prompt"],
                    "short_prompt": jd["short_prompt"],
                    "images": [Path(p) for p in jd.get("images", [])],
                    "model": jd["model"],
                    "size": jd["size"],
                    "submit_time": datetime.fromisoformat(jd["submit_time"]),
                }

            if row.result_path and Path(row.result_path).exists():
                pm = QPixmap()
                pm.load(row.result_path)
                row.set_thumbnail(pm)
                row._retry_btn.hide()
            elif row.error_msg and "超时" in row.error_msg:
                row.set_timeout()
            elif row.error_msg:
                row.set_failed(row.error_msg)

            row.retry_requested.connect(self._on_retry_job)
            row.retry_download.connect(self._on_retry_download)
            row.delete_requested.connect(self._on_delete_row)
            self._history_rows[seq] = row
            self._insert_history_row(row)

    def _on_delete_row(self, seq: int) -> None:
        """删除单条记录及对应的图片文件。"""
        row = self._history_rows.pop(seq, None)
        if row is None:
            return
        if row.result_path:
            try:
                Path(row.result_path).unlink(missing_ok=True)
            except OSError:
                pass
        row.setParent(None)
        row.deleteLater()
        self._save_records()

    def _on_clear_all(self) -> None:
        """清空所有生成记录（需用户确认）。"""
        if not self._history_rows:
            return

        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要清空全部 {len(self._history_rows)} 条生成记录吗？\n"
            "已生成的图片文件不会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for row in list(self._history_rows.values()):
            row.setParent(None)
            row.deleteLater()
        self._history_rows.clear()
        # 清除持久化文件
        try:
            self._records_file.unlink(missing_ok=True)
        except OSError:
            pass
        log_service.log_message.emit("已清空全部生成记录", "info")
        InfoBar.success("已清空", "全部生成记录已清除",
                        position=InfoBarPosition.TOP, parent=self.window())
