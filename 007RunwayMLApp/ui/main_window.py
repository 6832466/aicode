import asyncio
import json
import logging

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
    InfoBar, InfoBarPosition,
)

from app.config import (
    SETTINGS_KEY_TOKEN, SETTINGS_KEY_TEAM_ID, SETTINGS_KEY_OUTPUT_DIR,
    SETTINGS_KEY_POLL, SETTINGS_KEY_RESOLUTION, SETTINGS_KEY_AUDIO,
    SETTINGS_KEY_PREFIX, SETTINGS_KEY_SUFFIX,
    SETTINGS_KEY_SESSION_ID, SETTINGS_KEY_ASSET_GROUP_ID,
    app_root, app_icon_path, data_dir, char_assets_path, char_assets_write_path,
    batch_log_path, settings_scope,
)
from app.models import PromptItem, CharacterAsset, BatchLogEntry, TaskStatus
from app.runway_client import RunwayClient
from app.queue_manager import QueueManager
from app.download_manager import DownloadManager
from app.log_manager import LogManager

from ui.pages.home_page import HomePage
from ui.pages.settings_page import SettingsPage
from ui.pages.history_page import HistoryPage

logger = logging.getLogger(__name__)


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("乐乐RunwayML批量生视频工具    微信：rpalele")
        self.resize(1280, 800)
        self._set_app_icon()

        # Core instances
        self.client = RunwayClient()
        self.queue_manager = QueueManager(self.client)
        self.download_manager = DownloadManager(self.client)
        self._char_assets: dict[str, CharacterAsset] = {}
        self._processing = False

        # Build UI
        self._init_pages()
        self._init_navigation()
        self._connect_signals()

        # Set up logging to home page log widget
        from ui.widgets.log_widget import setup_app_logging
        setup_app_logging(self.home_page._log_widget)

        self._load_settings()

    # ------------------------------------------------------------------
    # Pages and navigation
    # ------------------------------------------------------------------

    def _set_app_icon(self):
        p = app_icon_path()
        if p.exists():
            icon = QIcon(str(p))
            self.setWindowIcon(icon)
            from PySide6.QtWidgets import QApplication
            QApplication.instance().setWindowIcon(icon)

    def _init_pages(self):
        self.home_page = HomePage(self)
        self.settings_page = SettingsPage(self)
        self.history_page = HistoryPage(self)

    def _init_navigation(self):
        self.addSubInterface(
            self.home_page, FluentIcon.HOME, "主页",
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.settings_page, FluentIcon.SETTING, "设置",
            position=NavigationItemPosition.BOTTOM,
        )
        self.addSubInterface(
            self.history_page, FluentIcon.HISTORY, "历史记录",
            position=NavigationItemPosition.BOTTOM,
        )

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.queue_manager.item_status_changed.connect(
            self.home_page.on_item_status_changed
        )
        self.queue_manager.item_status_changed.connect(
            self._on_item_status_for_log
        )
        self.queue_manager.progress_updated.connect(
            self.home_page.on_progress_updated
        )
        self.queue_manager.all_completed.connect(
            self.home_page.on_all_completed
        )
        self.queue_manager.all_completed.connect(
            self._on_all_completed_for_log
        )
        self.queue_manager.log_message.connect(
            self.home_page.on_log_message
        )

    # ------------------------------------------------------------------
    # Batch log writing (keeps history up to date live)
    # ------------------------------------------------------------------

    def _batch_log_file(self) -> str:
        return str(batch_log_path(self.client._team_id))

    def _on_item_status_for_log(self, idx: int, status: str, error: str):
        item = self.queue_manager._items[idx] if idx < len(self.queue_manager._items) else None
        if not item:
            return
        terminal_statuses = {"已完成", "已下载", "失败", "已提交"}
        if status not in terminal_statuses:
            return

        entry = BatchLogEntry(
            index=item.index,
            references=item.references,
            prompt=item.raw_prompt or item.prompt_text,
            gen_id=item.gen_id,
            task_id=item.task_id,
            status="failed" if status == "失败" else "completed",
            error=error,
            video_path=item.result_video_path,
        )
        try:
            LogManager.append_entry(entry, self._batch_log_file())
        except Exception:
            logger.exception("写入历史记录失败")

    def _on_all_completed_for_log(self, success: int, failed: int):
        # Reload history page after batch finishes
        try:
            self.history_page._model.load(self._batch_log_file())
        except Exception:
            logger.exception("刷新历史记录失败")

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _load_settings(self):
        # First read team_id from global settings to scope everything else
        global_s = QSettings("RunwayMLApp", "settings")
        team_id = global_s.value(SETTINGS_KEY_TEAM_ID, "57508622")

        s = settings_scope(team_id)
        token = s.value(SETTINGS_KEY_TOKEN, "")
        poll = int(s.value(SETTINGS_KEY_POLL, 75))
        output_dir = s.value(SETTINGS_KEY_OUTPUT_DIR, "")

        self.client.configure(token, team_id)

        # Load character assets (team-specific path)
        self._load_char_assets(team_id)

        # Update queue manager config
        self.queue_manager.configure(
            char_assets=self._char_assets,
            asset_group_id=s.value(SETTINGS_KEY_ASSET_GROUP_ID, ""),
            poll_interval=poll,
            download_manager=self.download_manager,
            resolution=s.value(SETTINGS_KEY_RESOLUTION, "720p"),
            generate_audio=s.value(SETTINGS_KEY_AUDIO, "true") == "true",
        )

        if output_dir:
            self.download_manager.set_output_dir(output_dir)
            self.home_page._output_dir_edit.setText(output_dir)

        # Restore prefix/suffix to home page
        self.home_page._prefix_suffix.set_prefix(s.value(SETTINGS_KEY_PREFIX, ""))
        self.home_page._prefix_suffix.set_suffix(s.value(SETTINGS_KEY_SUFFIX, ""))

        # Load history (team-specific path)
        self.history_page._model.load(str(batch_log_path(team_id)))

    def _apply_settings(self):
        """Called when settings are saved. Reloads with current team scope."""
        self._load_settings()

    def _load_char_assets(self, team_id: str = ""):
        path = char_assets_path(team_id)
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._char_assets = {
                name: CharacterAsset(ref_name=name, asset_id=d["assetId"], url=d["url"])
                for name, d in raw.items()
            }
            logger.info("Loaded %d character assets from %s", len(self._char_assets), path)
        else:
            logger.warning("character_assets.json not found at %s", path)

    # ------------------------------------------------------------------
    # Batch control — called from HomePage
    # ------------------------------------------------------------------

    def start_batch(self, items: list[PromptItem]):
        try:
            if self._processing:
                return

            team_id = self.client._team_id
            s = settings_scope(team_id)
            output_dir = self.home_page.output_dir

            self.download_manager.set_output_dir(output_dir)
            s.setValue(SETTINGS_KEY_OUTPUT_DIR, output_dir)

            self._load_char_assets(team_id)
            self.queue_manager.configure(
                char_assets=self._char_assets,
                asset_group_id=s.value(SETTINGS_KEY_ASSET_GROUP_ID, ""),
                poll_interval=int(s.value(SETTINGS_KEY_POLL, 75)),
                download_manager=self.download_manager,
                resolution=s.value(SETTINGS_KEY_RESOLUTION, "720p"),
                generate_audio=s.value(SETTINGS_KEY_AUDIO, "true") == "true",
            )

            # Check for missing character assets before starting
            missing_refs = set()
            for item in items:
                for ref in item.references:
                    if ref not in self._char_assets:
                        cn_name = next((cn for cn, rn in self.home_page._char_map.items() if rn == ref), ref)
                        missing_refs.add(cn_name)
            if missing_refs:
                names = "、".join(missing_refs)
                InfoBar.warning(
                    "缺少角色素材",
                    f"以下角色未在素材库中找到: {names}\n将不使用这些角色的参考图继续生成",
                    duration=8000,
                    position=InfoBarPosition.TOP,
                    parent=self.home_page,
                )

            self._processing = True
            self.queue_manager.enqueue(items)

            async def _run():
                try:
                    await self.queue_manager.start_processing()
                except Exception as e:
                    logger.exception("start_batch _run 异常")
                finally:
                    self._processing = False

            asyncio.ensure_future(_run())

            InfoBar.info(
                "开始处理",
                f"正在处理 {len(items)} 条提示词…",
                position=InfoBarPosition.TOP,
                parent=self.home_page,
            )
        except Exception as e:
            logger.exception("start_batch 异常")

    def pause_batch(self):
        try:
            self.queue_manager.pause()
        except Exception as e:
            logger.exception("pause_batch 异常")

    def resume_batch(self):
        try:
            self.queue_manager.resume()
        except Exception as e:
            logger.exception("resume_batch 异常")

    def stop_batch(self):
        try:
            self.queue_manager.stop()
            InfoBar.warning(
                "已停止",
                "批量处理已停止",
                position=InfoBarPosition.TOP,
                parent=self.home_page,
            )
        except Exception as e:
            logger.exception("stop_batch 异常")

    def submit_single(self, item: PromptItem, row: int = -1):
        """Submit a single prompt item (right-click context menu).

        Submits to API then marks as SUBMITTED — no polling or download.
        """
        try:
            team_id = self.client._team_id
            s = settings_scope(team_id)
            output_dir = self.home_page.output_dir

            self.download_manager.set_output_dir(output_dir)
            s.setValue(SETTINGS_KEY_OUTPUT_DIR, output_dir)

            self._load_char_assets(team_id)
            self.queue_manager.configure(
                char_assets=self._char_assets,
                asset_group_id=s.value(SETTINGS_KEY_ASSET_GROUP_ID, ""),
                poll_interval=int(s.value(SETTINGS_KEY_POLL, 75)),
                download_manager=self.download_manager,
                resolution=s.value(SETTINGS_KEY_RESOLUTION, "720p"),
                generate_audio=s.value(SETTINGS_KEY_AUDIO, "true") == "true",
            )

            # Append to items list for tracking
            idx = len(self.queue_manager._items)
            self.queue_manager._items.append(item)
            item.gen_id = ""
            item.task_id = ""
            item.error_message = ""

            display = row if row >= 0 else idx

            async def _run():
                await self.queue_manager.submit_only(idx, display_index=display)

            asyncio.ensure_future(_run())

            InfoBar.info(
                "正在提交",
                f"第 {item.index + 1} 条正在提交…",
                position=InfoBarPosition.TOP,
                parent=self.home_page,
            )
        except Exception as e:
            logger.exception("submit_single 异常")

    def submit_next(self):
        """Find the first QUEUED item in the table and submit it (submit-only mode)."""
        try:
            # Scan home_page._items (the table source) for first QUEUED item
            target_row = -1
            target_item = None
            for row, item in enumerate(self.home_page._items):
                if item.status == TaskStatus.QUEUED:
                    target_row = row
                    target_item = item
                    break

            if target_item is None:
                InfoBar.info(
                    "无待提交任务",
                    "所有任务已提交完毕",
                    position=InfoBarPosition.TOP,
                    parent=self.home_page,
                )
                return

            team_id = self.client._team_id
            s = settings_scope(team_id)
            output_dir = self.home_page.output_dir

            self.download_manager.set_output_dir(output_dir)
            s.setValue(SETTINGS_KEY_OUTPUT_DIR, output_dir)

            self._load_char_assets(team_id)
            self.queue_manager.configure(
                char_assets=self._char_assets,
                asset_group_id=s.value(SETTINGS_KEY_ASSET_GROUP_ID, ""),
                poll_interval=int(s.value(SETTINGS_KEY_POLL, 75)),
                download_manager=self.download_manager,
                resolution=s.value(SETTINGS_KEY_RESOLUTION, "720p"),
                generate_audio=s.value(SETTINGS_KEY_AUDIO, "true") == "true",
            )

            # Append to queue_manager for tracking
            idx = len(self.queue_manager._items)
            target_item.gen_id = ""
            target_item.task_id = ""
            target_item.error_message = ""
            self.queue_manager._items.append(target_item)

            async def _run():
                await self.queue_manager.submit_only(idx, display_index=target_row)

            asyncio.ensure_future(_run())

            InfoBar.info(
                "正在提交",
                f"正在提交第 {target_item.index + 1} 条…",
                position=InfoBarPosition.TOP,
                parent=self.home_page,
            )
        except Exception as e:
            logger.exception("submit_next 异常")

    def download_all(self):
        """Download all submitted/done items that have video URLs."""
        try:
            if self._processing:
                InfoBar.warning(
                    "下载进行中",
                    "已有下载任务在运行中",
                    position=InfoBarPosition.TOP,
                    parent=self.home_page,
                )
                return

            team_id = self.client._team_id
            s = settings_scope(team_id)
            output_dir = self.home_page.output_dir

            self.download_manager.set_output_dir(output_dir)
            s.setValue(SETTINGS_KEY_OUTPUT_DIR, output_dir)

            self._load_char_assets(team_id)
            self.queue_manager.configure(
                char_assets=self._char_assets,
                asset_group_id=s.value(SETTINGS_KEY_ASSET_GROUP_ID, ""),
                poll_interval=int(s.value(SETTINGS_KEY_POLL, 75)),
                download_manager=self.download_manager,
                resolution=s.value(SETTINGS_KEY_RESOLUTION, "720p"),
                generate_audio=s.value(SETTINGS_KEY_AUDIO, "true") == "true",
            )

            # Collect all SUBMITTED items (with task_ids) and DONE items (with video URLs)
            indices = []
            for idx, item in enumerate(self.queue_manager._items):
                if item.status == TaskStatus.SUBMITTED and item.task_id:
                    indices.append(idx)
                elif item.status == TaskStatus.DONE and item.result_video_url and not item.result_video_path:
                    # Download didn't happen yet — but for now, SUBMITTED items need polling first
                    pass

            if not indices:
                InfoBar.info(
                    "无待下载任务",
                    "没有已提交待下载的任务",
                    position=InfoBarPosition.TOP,
                    parent=self.home_page,
                )
                return

            self._processing = True

            async def _run():
                try:
                    await self.queue_manager.start_downloading(indices)
                except Exception as e:
                    logger.exception("download_all _run 异常")
                finally:
                    self._processing = False

            asyncio.ensure_future(_run())

            InfoBar.info(
                "开始下载",
                f"正在等待 {len(indices)} 个任务完成并下载…",
                position=InfoBarPosition.TOP,
                parent=self.home_page,
            )
        except Exception as e:
            logger.exception("download_all 异常")

    def retry_download(self, item: PromptItem):
        """Retry download for a completed item (right-click context menu)."""
        try:
            async def _run():
                try:
                    await self.queue_manager.retry_download(item.index)
                except Exception as e:
                    logger.exception("retry_download _run 异常")

            asyncio.ensure_future(_run())

            InfoBar.info(
                "重试下载",
                f"正在重试下载第 {item.index + 1} 条…",
                position=InfoBarPosition.TOP,
                parent=self.home_page,
            )
        except Exception as e:
            logger.exception("retry_download 异常")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def cleanup(self):
        self.queue_manager.stop()
        await self.client.close()

    def closeEvent(self, event):
        asyncio.ensure_future(self.cleanup())
        super().closeEvent(event)
