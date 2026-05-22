"""NVIDIA 驱动 / CUDA / cuDNN / PyTorch 推荐 — 精简界面。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QFrame,
    QLabel,
)

from qfluentwidgets import (
    FluentIcon,
    PrimaryPushButton,
    PushButton,
    CardWidget,
    InfoBar,
    InfoBarPosition,
    BodyLabel,
    StrongBodyLabel,
    CaptionLabel,
    setTheme,
    Theme,
)

from config import CONTACT_HINT, app_icon_path
from services.gpu_detector import detect_gpus
from services.recommender import ComponentRec, RecommendationBundle, build_recommendations
from ui.link_utils import copy_text, is_web_url, open_url


class ScanWorker(QThread):
    finished_ok = Signal(object)
    finished_err = Signal(str)

    def run(self):
        detection = detect_gpus()
        if not detection.gpus:
            msg = "；".join(detection.errors) if detection.errors else "未检测到 NVIDIA 显卡"
            self.finished_err.emit(msg)
            return
        try:
            self.finished_ok.emit(build_recommendations(detection))
        except Exception as exc:
            self.finished_err.emit(str(exc))


class ItemCard(CardWidget):
    def __init__(self, rec: ComponentRec, index: int, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(10)

        head = QHBoxLayout()
        num = QLabel(str(index))
        num.setFixedSize(28, 28)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet(
            "background:#0078d4;color:white;border-radius:14px;font-weight:bold;"
        )
        head.addWidget(num)
        col = QVBoxLayout()
        col.addWidget(StrongBodyLabel(rec.name))
        if rec.version:
            col.addWidget(CaptionLabel(f"推荐版本：{rec.version}"))
        head.addLayout(col, 1)
        layout.addLayout(head)

        url = rec.download_url or rec.copy_text
        show = url if len(url) <= 100 else url[:97] + "..."
        link = QLabel(
            f'<a href="{url}" style="color:#0078d4;">{show}</a>'
            if is_web_url(url)
            else f"<span>{show}</span>"
        )
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setOpenExternalLinks(is_web_url(url))
        link.setWordWrap(True)
        layout.addWidget(link)

        row = QHBoxLayout()
        if is_web_url(rec.download_url):
            ob = PrimaryPushButton(FluentIcon.LINK, "打开链接")
            ob.setFixedHeight(36)
            ob.clicked.connect(lambda u=rec.download_url: _open_link(self, u))
            row.addWidget(ob)
        cb = PushButton(
            FluentIcon.COPY,
            "复制 pip 命令" if rec.name == "PyTorch" else "复制链接",
        )
        cb.setFixedHeight(36)
        text = rec.copy_text or rec.download_url
        cb.clicked.connect(lambda t=text: _copy(self, t))
        row.addWidget(cb)
        row.addStretch()
        layout.addLayout(row)


def _open_link(widget: QWidget, url: str):
    if open_url(url):
        InfoBar.success("已打开", "", duration=1500, parent=widget.window())
    else:
        InfoBar.error("打开失败", "", duration=2000, parent=widget.window())


def _copy(widget: QWidget, text: str):
    copy_text(text)
    InfoBar.success("已复制", "", duration=1500, parent=widget.window())


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._worker: ScanWorker | None = None
        self._cards: list[QWidget] = []
        self._setup_ui()
        self._scan()

    def _setup_ui(self):
        self.setWindowTitle(f"NVIDIA 组件推荐 · {CONTACT_HINT}")
        self.setMinimumSize(720, 520)
        self.resize(820, 620)

        icon = app_icon_path()
        if icon:
            self.setWindowIcon(QIcon(str(icon)))

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        self._gpu_label = BodyLabel("检测中...")
        self._gpu_label.setStyleSheet("color:#666;")
        top.addWidget(self._gpu_label, 1)
        self._btn = PrimaryPushButton(FluentIcon.SYNC, "重新检测")
        self._btn.clicked.connect(self._scan)
        top.addWidget(self._btn)
        root.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")

        self._box = QWidget()
        self._layout = QVBoxLayout(self._box)
        self._layout.setSpacing(12)
        self._hint = QLabel("正在检测...")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet("color:#aaa;padding:40px;")
        self._layout.addWidget(self._hint)
        self._layout.addStretch()

        scroll.setWidget(self._box)
        root.addWidget(scroll, 1)

    def _clear(self):
        for w in self._cards:
            self._layout.removeWidget(w)
            w.deleteLater()
        self._cards.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item and item.spacerItem():
                del item

    def _scan(self):
        if self._worker and self._worker.isRunning():
            return
        self._clear()
        self._hint = QLabel("正在检测...")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._hint)
        self._btn.setEnabled(False)
        self._gpu_label.setText("检测中...")

        self._worker = ScanWorker()
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.finished_err.connect(self._on_err)
        self._worker.start()

    def _on_ok(self, bundle: RecommendationBundle):
        self._clear()
        self._btn.setEnabled(True)
        g = bundle.gpu
        self._gpu_label.setText(
            f"{g.name}　驱动 {g.driver_version or '—'}　显存 {g.vram_total_mb} MB"
        )

        for i, rec in enumerate(
            [bundle.driver, bundle.cuda, bundle.cudnn, bundle.pytorch], start=1
        ):
            card = ItemCard(rec, i, self)
            self._layout.addWidget(card)
            self._cards.append(card)
        self._layout.addStretch()
        self._worker = None

    def _on_err(self, msg: str):
        self._clear()
        self._btn.setEnabled(True)
        self._gpu_label.setText(msg)
        self._hint = QLabel(msg)
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._hint)
        self._worker = None

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        event.accept()


def run_app():
    import sys

    app = QApplication(sys.argv)
    setTheme(Theme.AUTO)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
