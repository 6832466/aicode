"""按剧分组的下载卡片 — 封面 + 剧名 + 各集进度 (带播放/停止/删除)"""
import logging
import os
import subprocess
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from qfluentwidgets import (
    CardWidget, StrongBodyLabel, BodyLabel, CaptionLabel,
    TransparentPushButton, FluentIcon,
)

logger = logging.getLogger("hongguo")


class EpisodeRow(QWidget):
    """单集下载行: 集号 | 进度条 | 状态 | 操作按钮"""
    play_requested = Signal(int, int)   # group_id, episode_index
    stop_requested = Signal(int, int)   # group_id, episode_index
    retry_requested = Signal(int, int)  # group_id, episode_index

    def __init__(self, group_id: int, episode_index: int, episode_name: str, parent=None):
        super().__init__(parent)
        self._group_id = group_id
        self._episode_index = episode_index
        self._episode_name = episode_name
        self._finished = False
        self._success = False
        self._filepath = ""
        self._setup_ui()

    @property
    def episode_index(self) -> int:
        return self._episode_index

    def set_filepath(self, filepath: str):
        self._filepath = filepath
        self._play_btn.setVisible(True)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(6)

        # 集号
        self._ep_label = BodyLabel(f"第{self._episode_index:02d}集")
        self._ep_label.setFixedWidth(50)
        self._ep_label.setStyleSheet("font-size: 12px; color: #333;")
        layout.addWidget(self._ep_label)

        # 进度条
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFixedHeight(16)
        self._progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0; border-radius: 3px;
                background: #f5f5f5; text-align: center; font-size: 10px;
            }
            QProgressBar::chunk { background-color: #0078d4; border-radius: 2px; }
        """)
        layout.addWidget(self._progress, stretch=1)

        # 状态
        self._status_label = CaptionLabel("等待中")
        self._status_label.setFixedWidth(75)
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_label)

        # 操作按钮 (只在有文件后显示)
        btns = QHBoxLayout()
        btns.setSpacing(2)

        self._stop_btn = QPushButton("✕")
        self._stop_btn.setFixedSize(22, 22)
        self._stop_btn.setToolTip("取消下载")
        self._stop_btn.setStyleSheet(self._icon_btn_style("#f44336"))
        self._stop_btn.clicked.connect(
            lambda: self.stop_requested.emit(self._group_id, self._episode_index)
        )
        btns.addWidget(self._stop_btn)

        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(22, 22)
        self._play_btn.setToolTip("打开文件")
        self._play_btn.setStyleSheet(self._icon_btn_style("#4caf50"))
        self._play_btn.clicked.connect(
            lambda: self.play_requested.emit(self._group_id, self._episode_index)
        )
        self._play_btn.setVisible(False)
        btns.addWidget(self._play_btn)

        self._retry_btn = QPushButton("↻")
        self._retry_btn.setFixedSize(22, 22)
        self._retry_btn.setToolTip("重试下载")
        self._retry_btn.setStyleSheet(self._icon_btn_style("#ff9800"))
        self._retry_btn.clicked.connect(
            lambda: self.retry_requested.emit(self._group_id, self._episode_index)
        )
        self._retry_btn.setVisible(False)
        btns.addWidget(self._retry_btn)

        layout.addLayout(btns)

    def set_status(self, text: str, color: str = "#888"):
        """设置状态文字和颜色 (用于获取链接/等待下载等中间状态)"""
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 11px;")

    def reset_for_retry(self):
        """重试前重置行状态"""
        self._finished = False
        self._success = False
        self._stop_btn.setVisible(True)
        self._retry_btn.setVisible(False)
        self._play_btn.setVisible(False)
        self._progress.setValue(0)
        self._progress.setFormat("")
        self._progress.setStyleSheet(self._progress.styleSheet().replace(
            "background-color: #f44336;", "background-color: #0078d4;"
        ).replace(
            "background-color: #4caf50;", "background-color: #0078d4;"
        ))
        self.set_status("获取链接...", "#f0ad4e")

    def update_progress(self, done: int, total: int, speed: str, eta: str):
        if total > 0:
            pct = min(int(done / total * 100), 100)
            self._progress.setValue(pct)
            self._progress.setFormat(f"{self._fmt(done)} / {self._fmt(total)}")
        else:
            self._progress.setFormat(f"{self._fmt(done)}")
        parts = []
        if speed:
            parts.append(speed)
        if eta:
            parts.append(f"剩{eta}")
        self._status_label.setText("  ".join(parts) if parts else "下载中")
        self._status_label.setStyleSheet("color: #0078d4; font-size: 11px;")

    def mark_completed(self, success: bool, message: str = "", filepath: str = ""):
        self._finished = True
        self._success = success
        self._stop_btn.setVisible(False)

        if success:
            self._progress.setValue(100)
            self._progress.setStyleSheet(self._progress.styleSheet().replace(
                "background-color: #0078d4;", "background-color: #4caf50;"
            ))
            self._status_label.setText(message or "完成")
            self._status_label.setStyleSheet("color: #4caf50; font-size: 11px;")
            if filepath:
                self.set_filepath(filepath)
        else:
            self._progress.setStyleSheet(self._progress.styleSheet().replace(
                "background-color: #0078d4;", "background-color: #f44336;"
            ))
            self._status_label.setText(message or "失败")
            self._status_label.setStyleSheet("color: #f44336; font-size: 11px;")
            self._retry_btn.setVisible(True)

    @staticmethod
    def _fmt(size: int) -> str:
        if size >= 1024 * 1024 * 1024:
            return f"{size / 1024 ** 3:.1f} GB"
        elif size >= 1024 * 1024:
            return f"{size / 1024 ** 2:.1f} MB"
        elif size >= 1024:
            return f"{size / 1024:.0f} KB"
        return f"{size} B"

    @staticmethod
    def _icon_btn_style(color: str) -> str:
        return f"""
            QPushButton {{
                background: #fafafa; border: 1px solid {color}40;
                border-radius: 3px; color: {color};
                font-size: 10px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {color}18; border-color: {color}; }}
        """


class SeriesDownloadCard(CardWidget):
    """一个短剧的下载分组卡片"""
    cancel_group_requested = Signal(int)
    retry_episode_requested = Signal(int, int)  # group_id, episode_index

    def __init__(self, group_id: int, series_name: str, cover_url: str,
                 total_episodes: int, parent=None):
        super().__init__(parent)
        self._group_id = group_id
        self._series_name = series_name
        self._total_episodes = total_episodes
        self._episode_rows: dict[int, EpisodeRow] = {}
        self._completed_count = 0
        self._failed_count = 0
        self._task_filepaths: dict[int, str] = {}  # task_id -> filepath
        self._cover_nam: QNetworkAccessManager | None = None
        self._episodes_visible = True

        self._setup_ui()
        if cover_url:
            try:
                self._load_cover(cover_url)
            except Exception:
                logger.exception(f"加载封面失败: {cover_url[:80]}")

    @property
    def group_id(self) -> int:
        return self._group_id

    def _setup_ui(self):
        self.setStyleSheet("SeriesDownloadCard { background: white; border-radius: 10px; }")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(8)

        # === 头部 ===
        header = QHBoxLayout()
        header.setSpacing(12)

        self._cover_label = QLabel()
        self._cover_label.setFixedSize(48, 64)
        self._cover_label.setScaledContents(True)
        self._cover_label.setStyleSheet(
            "QLabel { background-color: #f0f0f0; border-radius: 6px; border: 1px solid #e0e0e0; }"
        )
        header.addWidget(self._cover_label)

        info = QVBoxLayout()
        info.setSpacing(2)

        self._toggle_btn = QPushButton(f"▼ {self._series_name}")
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                text-align: left; font-size: 14px; font-weight: 600;
                color: #1a1a1a; border: none; background: transparent;
                padding: 0px;
            }
            QPushButton:hover { color: #0078d4; }
        """)
        self._toggle_btn.clicked.connect(self._toggle_episodes)
        info.addWidget(self._toggle_btn)

        self._stats_label = CaptionLabel(
            f"共 {self._total_episodes} 集 · 完成 0 · 失败 0"
        )
        self._stats_label.setStyleSheet("color: #888;")
        info.addWidget(self._stats_label)
        header.addLayout(info, stretch=1)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedSize(52, 28)
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                background: #fff0f0; border: 1px solid #f44336;
                border-radius: 4px; color: #f44336;
                font-size: 12px; font-weight: 600;
            }
            QPushButton:hover { background: #ffebee; }
        """)
        self._cancel_btn.clicked.connect(lambda: self.cancel_group_requested.emit(self._group_id))
        header.addWidget(self._cancel_btn)

        main_layout.addLayout(header)

        # === 剧集列表 (可折叠) ===
        self._episodes_container = QWidget()
        self._episodes_container.setStyleSheet("background: transparent;")
        self._episodes_layout = QVBoxLayout(self._episodes_container)
        self._episodes_layout.setContentsMargins(0, 0, 0, 0)
        self._episodes_layout.setSpacing(1)
        main_layout.addWidget(self._episodes_container)

        # 底部操作
        footer = QHBoxLayout()
        footer.addStretch()
        self._open_folder_btn = QPushButton("打开文件夹")
        self._open_folder_btn.setFixedHeight(28)
        self._open_folder_btn.setStyleSheet("""
            QPushButton {
                background: #f5f5f5; border: 1px solid #ddd;
                border-radius: 4px; padding: 0 12px;
                color: #555; font-size: 12px;
            }
            QPushButton:hover { background: #e3f2fd; border-color: #0078d4; color: #0078d4; }
        """)
        self._open_folder_btn.clicked.connect(self._open_output_folder)
        footer.addWidget(self._open_folder_btn)
        main_layout.addLayout(footer)

    def _toggle_episodes(self):
        self._episodes_visible = not self._episodes_visible
        self._episodes_container.setVisible(self._episodes_visible)
        arrow = "▼" if self._episodes_visible else "▶"
        self._toggle_btn.setText(f"{arrow} {self._series_name}")

    def set_output_dir(self, path: str):
        self._output_dir = path

    def _open_output_folder(self):
        if hasattr(self, '_output_dir') and self._output_dir:
            subprocess.Popen(['explorer', self._output_dir])

    def add_episode_row(self, episode_index: int, episode_name: str = "", task_id: int = 0):
        if episode_index in self._episode_rows:
            return self._episode_rows[episode_index]
        row = EpisodeRow(self._group_id, episode_index, episode_name or f"第{episode_index:02d}集")
        row.play_requested.connect(self._on_play_episode)
        row.stop_requested.connect(self._on_stop_episode)
        row.retry_requested.connect(self._on_retry_episode)
        self._episode_rows[episode_index] = row
        self._episodes_layout.addWidget(row)
        return row

    def get_episode_row(self, episode_index: int):
        return self._episode_rows.get(episode_index)

    def _on_play_episode(self, group_id: int, ep: int):
        row = self._episode_rows.get(ep)
        if row and row._filepath:
            os.startfile(row._filepath)

    def _on_retry_episode(self, group_id: int, ep: int):
        if ep in self._episode_rows:
            self._episode_rows[ep].reset_for_retry()
            self._failed_count = max(0, self._failed_count - 1)
            self._stats_label.setText(
                f"共 {self._total_episodes} 集 · 完成 {self._completed_count} · 失败 {self._failed_count}"
            )
        self.retry_episode_requested.emit(group_id, ep)

    def _on_stop_episode(self, group_id: int, ep: int):
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox()
        msg.setWindowTitle("确认取消")
        msg.setText(f"确定要取消第{ep}集的下载吗?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        if msg.exec() == QMessageBox.Yes:
            if ep in self._episode_rows:
                self._episode_rows[ep].hide()
                self._episode_rows[ep].deleteLater()
                del self._episode_rows[ep]

    def update_task_progress(self, done: int, total: int, speed: str, eta: str, episode_index: int = 0):
        if episode_index in self._episode_rows:
            self._episode_rows[episode_index].update_progress(done, total, speed, eta)

    def mark_task_finished(self, success: bool, episode_index: int = 0, filepath: str = "", message: str = ""):
        if episode_index in self._episode_rows:
            self._episode_rows[episode_index].mark_completed(success, message, filepath)
        if success:
            self._completed_count += 1
        else:
            self._failed_count += 1
        self._stats_label.setText(
            f"共 {self._total_episodes} 集 · 完成 {self._completed_count} · 失败 {self._failed_count}"
        )

    @property
    def all_done(self) -> bool:
        return self._completed_count + self._failed_count >= self._total_episodes

    def _load_cover(self, url: str):
        """加载封面 (带缓存 + Referer)"""
        try:
            from pathlib import Path as _Path
            cache_dir = _Path(__file__).parent.parent / ".cover_cache"
            cache_dir.mkdir(exist_ok=True)
            cache_key = url.split("/")[-1].split("~")[0] if "/" in url else url
            cache_path = cache_dir / f"{cache_key}_card.jpg"
            if cache_path.exists():
                pix = QPixmap(str(cache_path))
                if not pix.isNull():
                    self._cover_label.setPixmap(pix)
                    return

            self._cover_nam = QNetworkAccessManager()
            def handle(reply):
                try:
                    if reply.error() == QNetworkReply.NoError:
                        data = reply.readAll()
                        pix = QPixmap()
                        pix.loadFromData(data)
                        if not pix.isNull():
                            self._cover_label.setPixmap(pix)
                            try:
                                with open(cache_path, "wb") as f:
                                    f.write(data)
                            except OSError:
                                logger.exception(f"保存封面缓存失败: {cache_path}")
                except Exception:
                    logger.exception("下载卡片封面加载回调异常")
                finally:
                    reply.deleteLater()
            self._cover_nam.finished.connect(handle)
            req = QNetworkRequest(QUrl(url))
            req.setRawHeader(b"Referer", b"https://novelquickapp.com/")
            self._cover_nam.get(req)
        except Exception:
            logger.exception(f"封面加载初始化失败: {url[:80]}")
