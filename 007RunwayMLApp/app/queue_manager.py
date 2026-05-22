import asyncio
import logging
import random
from collections import deque

from PySide6.QtCore import QObject, Signal

from .config import MAX_CONCURRENT
from .models import PromptItem, CharacterAsset, TaskStatus
from .runway_client import RunwayClient
from .download_manager import DownloadManager

logger = logging.getLogger(__name__)

FINAL_STATUSES = {"SUCCEEDED", "COMPLETED", "FAILED", "CANCELLED", "NOT_FOUND"}


class QueueManager(QObject):
    """Core orchestrator for batch video generation.

    Uses session-based tracking: after POST /v1/generations, the generation
    appears in the session's generations list with a real task.id. We poll the
    session (not the client-generated UUID) to track status.
    """

    item_status_changed = Signal(int, str, str)       # index, TaskStatus.value, error
    progress_updated = Signal(int, int, int)           # done, total, active
    all_completed = Signal(int, int)                    # success_count, fail_count
    log_message = Signal(str)

    SESSION_POLL_INTERVAL = 5      # how often to re-fetch session for new gens
    TASK_POLL_INTERVAL = 10        # how often to poll individual task status

    def __init__(self, client: RunwayClient, parent=None):
        super().__init__(parent)
        self._client = client
        self._download_manager: DownloadManager | None = None
        self._items: list[PromptItem] = []
        self._queue: deque[int] = deque()
        self._active: dict[int, str] = {}               # item_index -> real task_id
        self._char_assets: dict[str, CharacterAsset] = {}
        self._asset_group_id: str = ""
        self._poll_interval: int = 75
        self._running: bool = False
        self._paused: bool = False
        self._stopped: bool = False
        self._task: asyncio.Task | None = None
        self._poll_failures: dict[int, int] = {}  # idx -> consecutive failures

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(
        self,
        char_assets: dict[str, CharacterAsset],
        asset_group_id: str = "",
        poll_interval: int = 75,
        download_manager: DownloadManager | None = None,
        resolution: str = "720p",
        generate_audio: bool = True,
    ):
        self._char_assets = char_assets
        self._asset_group_id = asset_group_id
        self._poll_interval = poll_interval
        self._download_manager = download_manager
        self._client.configure(
            token=self._client._token,
            team_id=self._client._team_id,
            resolution=resolution,
            generate_audio=generate_audio,
        )

    # ------------------------------------------------------------------
    # Queue control
    # ------------------------------------------------------------------

    def enqueue(self, items: list[PromptItem]):
        self._items = items
        self._queue.clear()
        self._active.clear()
        self._poll_failures.clear()
        self._stopped = False
        for pos, item in enumerate(items):
            if item.status in (TaskStatus.DOWNLOADED, TaskStatus.DONE, TaskStatus.SUBMITTED):
                continue
            item.status = TaskStatus.QUEUED
            item.gen_id = ""
            item.task_id = ""
            item.error_message = ""
            self._queue.append(pos)  # use current list position, not item.index

    def pause(self):
        self._paused = True
        self.log_message.emit("已暂停 — 不再提交新任务")

    def resume(self):
        self._paused = False
        self.log_message.emit("已恢复")

    def stop(self):
        self._running = False
        self._paused = False
        self._stopped = True

        # Reset all active items back to QUEUED so they can be re-submitted
        for idx in list(self._active.keys()):
            if 0 <= idx < len(self._items):
                item = self._items[idx]
                item.status = TaskStatus.QUEUED
                item.progress_ratio = 0
                item.error_message = ""
                self.item_status_changed.emit(idx, item.status.value, "")
        self._active.clear()
        self._queue.clear()
        self._poll_failures.clear()

        self._emit_progress()
        self.log_message.emit("已停止 — 未完成的任务已重置为排队中")

        if self._task and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------
    # Main processing loop
    # ------------------------------------------------------------------

    async def start_processing(self):
        self._running = True
        self._paused = False
        self._stopped = False
        self._task = asyncio.current_task()

        try:
            while self._running and (self._queue or self._active):
                try:
                    # Submit new tasks if slots available
                    if not self._paused:
                        while len(self._active) < MAX_CONCURRENT and self._queue:
                            idx = self._queue.popleft()
                            await self._submit_one(idx)

                    # Poll all active tasks
                    await self._poll_active()

                    self._emit_progress()

                    if not self._running:
                        break

                    running = len(self._active)
                    queued = len(self._queue)
                    self.log_message.emit(
                        f"队列: {queued} 等待中, {running} 运行中"
                    )

                    # Adaptive sleep: quick check if waiting, bail if nothing left
                    if self._queue and len(self._active) < MAX_CONCURRENT:
                        await asyncio.sleep(10)  # Fast retry when slots available
                    elif self._active:
                        await asyncio.sleep(random.randint(30, 45))  # Normal polling
                    else:
                        break  # Nothing left to do — exit immediately

                except Exception as e:
                    logger.exception("Queue iteration error — continuing")
                    self.log_message.emit(f"循环异常(继续): {e}")
                    await asyncio.sleep(random.randint(45, 60))

        except asyncio.CancelledError:
            self.log_message.emit("处理已取消")
        finally:
            self._running = False
            if not self._stopped:
                success = sum(
                    1 for i in self._items
                    if i.status in (TaskStatus.DOWNLOADED, TaskStatus.DONE)
                )
                failed = sum(1 for i in self._items if i.status == TaskStatus.FAILED)
                self.all_completed.emit(success, failed)
            self._emit_progress()

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    async def submit_only(self, idx: int, display_index: int | None = None) -> bool:
        """Submit a single item and mark as SUBMITTED — no polling or download.

        idx: position in self._items
        display_index: table row for signal emission (defaults to idx)
        """
        signal_idx = display_index if display_index is not None else idx
        if idx < 0 or idx >= len(self._items):
            logger.warning("submit_only: idx=%d out of range", idx)
            return False
        item = self._items[idx]

        # Check website capacity
        try:
            can = await self._client.can_start()
            if not can.get("can_start", False):
                in_prog = can.get("in_progress", "?")
                item.status = TaskStatus.FAILED
                item.error_message = f"网站已有 {in_prog} 个任务运行中，请稍后重试"
                self.item_status_changed.emit(signal_idx, item.status.value, item.error_message)
                self.log_message.emit(f"#{item.index + 1} 提交失败 — 网站已有 {in_prog} 个任务运行中")
                return False
        except Exception:
            pass  # Let the API reject if at capacity

        item.status = TaskStatus.SUBMITTING
        self.item_status_changed.emit(signal_idx, item.status.value, "")
        self._emit_progress()

        try:
            result = await self._client.create_generation(
                item, self._char_assets, asset_group_id=self._asset_group_id
            )
        except Exception as e:
            item.status = TaskStatus.FAILED
            item.error_message = f"提交异常: {e}"
            self.item_status_changed.emit(signal_idx, item.status.value, item.error_message)
            self.log_message.emit(f"#{item.index + 1} 提交异常，已标为失败: {e}")
            return False

        if result is None:
            item.status = TaskStatus.FAILED
            item.error_message = "API 提交返回空响应"
            self.item_status_changed.emit(signal_idx, item.status.value, item.error_message)
            return False

        if result.get("status") == "RATE_LIMITED":
            item.status = TaskStatus.FAILED
            item.error_message = "被限流(429)，请稍后重试"
            self.item_status_changed.emit(signal_idx, item.status.value, item.error_message)
            self.log_message.emit(f"#{item.index + 1} 被限流(429)，已标为失败")
            return False

        if result.get("status") == "SERVER_BUSY":
            item.status = TaskStatus.FAILED
            item.error_message = "Seedance 服务器过载，请稍后重试"
            self.item_status_changed.emit(signal_idx, item.status.value, item.error_message)
            self.log_message.emit(f"#{item.index + 1} 服务器过载，已标为失败")
            return False

        if result.get("status") == "SAFETY_INTERCEPTED":
            item.status = TaskStatus.FAILED
            item.error_message = "内容审核拦截"
            self.item_status_changed.emit(signal_idx, item.status.value, item.error_message)
            self.log_message.emit(f"#{item.index + 1} 内容审核拦截，已标为失败")
            return False

        task_id = result.get("taskId", "")
        if not task_id:
            item.status = TaskStatus.FAILED
            item.error_message = "API 响应中没有任务 ID"
            self.item_status_changed.emit(signal_idx, item.status.value, item.error_message)
            return False

        item.task_id = task_id
        item.status = TaskStatus.SUBMITTED
        self.item_status_changed.emit(signal_idx, item.status.value, "")
        self._emit_progress()
        self.log_message.emit(f"#{item.index + 1} 已提交: {task_id[:8]}...")
        return True

    def find_next_queued(self) -> int | None:
        """Return the index of the first QUEUED item, or None."""
        for idx, item in enumerate(self._items):
            if item.status == TaskStatus.QUEUED:
                return idx
        return None

    async def start_downloading(self, indices: list[int]):
        """Poll and download a batch of previously submitted items."""
        if not indices:
            return

        self._running = True
        self._paused = False
        self._stopped = False
        self._task = asyncio.current_task()

        # Populate _active with items that have task_ids
        for idx in indices:
            if 0 <= idx < len(self._items):
                item = self._items[idx]
                if item.task_id:
                    self._active[idx] = item.task_id
                    self._poll_failures.pop(idx, None)

        try:
            while self._running and self._active:
                try:
                    await self._poll_active()
                    self._emit_progress()

                    if not self._running:
                        break

                    remaining = len(self._active)
                    self.log_message.emit(f"下载队列: {remaining} 个任务等待中")

                    if self._active:
                        await asyncio.sleep(random.randint(30, 45))
                    else:
                        break
                except Exception as e:
                    logger.exception("Download iteration error")
                    self.log_message.emit(f"下载循环异常: {e}")
                    await asyncio.sleep(random.randint(45, 60))
        except asyncio.CancelledError:
            self.log_message.emit("下载已取消")
        finally:
            self._running = False
            if not self._stopped:
                success = sum(
                    1 for i in self._items
                    if i.status in (TaskStatus.DOWNLOADED, TaskStatus.DONE)
                )
                failed = sum(1 for i in self._items if i.status == TaskStatus.FAILED)
                self.all_completed.emit(success, failed)
            self._emit_progress()

    # ------------------------------------------------------------------
    # Submission (batch processing — kept for legacy start_batch)
    # ------------------------------------------------------------------

    async def _submit_one(self, idx: int):
        if idx < 0 or idx >= len(self._items):
            logger.warning("_submit_one: idx=%d out of range (items=%d), skipped", idx, len(self._items))
            return
        item = self._items[idx]

        # Check if we can start a new task (accounts for website tasks too)
        try:
            can = await self._client.can_start()
            if not can.get("can_start", False):
                in_prog = can.get("in_progress", "?")
                item.status = TaskStatus.FAILED
                item.error_message = f"网站已有 {in_prog} 个任务运行中，请稍后重试"
                self.item_status_changed.emit(idx, item.status.value, item.error_message)
                self.log_message.emit(
                    f"#{idx + 1} 提交失败 — 网站已有 {in_prog} 个任务运行中，达到上限"
                )
                return
        except Exception:
            # API call itself failed — fall back to local tracking
            if len(self._active) >= MAX_CONCURRENT:
                item.status = TaskStatus.FAILED
                item.error_message = f"本地已有 {len(self._active)} 个任务运行中，网站状态查询失败，请稍后重试"
                self.item_status_changed.emit(idx, item.status.value, item.error_message)
                self.log_message.emit(
                    f"#{idx + 1} 提交失败 — 本地已有 {len(self._active)} 个任务运行中"
                )
                return
            # Otherwise allow — let the API reject if truly at capacity

        item.status = TaskStatus.SUBMITTING
        self.item_status_changed.emit(idx, item.status.value, "")
        self._emit_progress()

        try:
            result = await self._client.create_generation(
                item, self._char_assets, asset_group_id=self._asset_group_id
            )
        except Exception as e:
            item.status = TaskStatus.FAILED
            item.error_message = f"提交异常: {e}"
            self.item_status_changed.emit(idx, item.status.value, item.error_message)
            self.log_message.emit(f"#{idx + 1} 提交异常，已标为失败: {e}")
            return

        if result is None:
            item.status = TaskStatus.FAILED
            item.error_message = "API 提交返回空响应 (可能是令牌过期或参数错误)"
            self.item_status_changed.emit(idx, item.status.value, item.error_message)
            return

        if result.get("status") == "RATE_LIMITED":
            item.status = TaskStatus.FAILED
            item.error_message = "被限流(429)，请稍后重试"
            self.item_status_changed.emit(idx, item.status.value, item.error_message)
            self.log_message.emit(f"#{idx + 1} 被限流(429)，已标为失败")
            return

        if result.get("status") == "SERVER_BUSY":
            item.status = TaskStatus.FAILED
            item.error_message = "Seedance 服务器过载，请稍后重试"
            self.item_status_changed.emit(idx, item.status.value, item.error_message)
            self.log_message.emit(f"#{idx + 1} 服务器过载，已标为失败")
            return

        if result.get("status") == "SAFETY_INTERCEPTED":
            item.status = TaskStatus.FAILED
            item.error_message = "内容审核拦截 — 请修改提示词或参考图后重试，切勿用相同内容再次提交！"
            self.item_status_changed.emit(idx, item.status.value, item.error_message)
            self.log_message.emit(f"#{idx + 1} 内容审核拦截，已标为失败（请勿重试相同内容）")
            return

        task_id = result.get("taskId", "")
        if not task_id:
            item.status = TaskStatus.FAILED
            item.error_message = "API 响应中没有任务 ID"
            self.item_status_changed.emit(idx, item.status.value, item.error_message)
            return

        item.task_id = task_id
        initial_status = result.get("status", "PENDING")
        self._active[idx] = task_id

        if initial_status == "THROTTLED":
            item.status = TaskStatus.THROTTLED
        else:
            item.status = TaskStatus.RUNNING

        self.item_status_changed.emit(idx, item.status.value, "")
        self.log_message.emit(
            f"已提交 #{idx + 1}: {task_id[:8]}... 状态={initial_status}"
        )

    # ------------------------------------------------------------------
    # Active task polling
    # ------------------------------------------------------------------

    async def _poll_active(self):
        stale = []
        for idx, task_id in list(self._active.items()):
            if idx < 0 or idx >= len(self._items):
                logger.warning("_poll_active: idx=%d out of range, removing", idx)
                stale.append(idx)
                continue
            try:
                info = await self._client.get_task_status(task_id)
                self._poll_failures.pop(idx, None)  # Reset on success
            except Exception as e:
                fails = self._poll_failures.get(idx, 0) + 1
                self._poll_failures[idx] = fails
                logger.warning("Poll failed for %s (attempt %d): %s", task_id, fails, e)
                if fails >= 5:
                    item = self._items[idx]
                    item.status = TaskStatus.FAILED
                    item.error_message = f"轮询失败(重试{fails}次): {e}"
                    self.item_status_changed.emit(idx, item.status.value, item.error_message)
                    self.log_message.emit(f"#{idx + 1} 轮询持续失败，已放弃")
                    stale.append(idx)
                    self._poll_failures.pop(idx, None)
                continue

            status = info.get("status", "UNKNOWN")
            item = self._items[idx]

            # Update progress ratio from API (0.0 - 1.0)
            progress = info.get("progressRatio", info.get("progress", info.get("progress_ratio", 0)))
            try:
                progress = float(progress) if progress else 0.0
            except (TypeError, ValueError):
                progress = 0.0
            if progress != item.progress_ratio:
                item.progress_ratio = progress
                self.item_status_changed.emit(idx, item.status.value, "")
                self.log_message.emit(f"#{idx + 1} 进度: {int(progress * 100)}%")

            if status == "THROTTLED":
                if item.status != TaskStatus.THROTTLED:
                    item.status = TaskStatus.THROTTLED
                    self.item_status_changed.emit(idx, item.status.value, "")

            elif status in ("PENDING", "RUNNING", "PROCESSING"):
                if item.status not in (TaskStatus.RUNNING,):
                    item.status = TaskStatus.RUNNING
                    self.item_status_changed.emit(idx, item.status.value, "")

            elif status in ("SUCCEEDED", "COMPLETED"):
                try:
                    await self._handle_completed(idx, info)
                except Exception as e:
                    logger.exception("handle_completed failed for idx=%d: %s", idx, e)
                stale.append(idx)

            elif status == "CANCELLED":
                # User cancelled on the website — mark failed, do NOT auto-resubmit
                item.status = TaskStatus.FAILED
                item.progress_ratio = 0
                item.task_id = ""
                item.error_message = "用户在网站上取消了该任务"
                self.item_status_changed.emit(idx, item.status.value, item.error_message)
                self.log_message.emit(f"#{idx + 1} 用户在网站上取消了任务，已标记为失败")
                stale.append(idx)

            elif status == "FAILED":
                try:
                    await self._handle_failed(idx, info)
                except Exception as e:
                    logger.exception("handle_failed failed for idx=%d: %s", idx, e)
                stale.append(idx)

            elif status == "NOT_FOUND":
                item.status = TaskStatus.FAILED
                item.error_message = "服务器上未找到任务"
                self.item_status_changed.emit(idx, item.status.value, item.error_message)
                stale.append(idx)

        for idx in stale:
            self._active.pop(idx, None)

    async def _handle_completed(self, idx: int, task_or_info):
        """Handle a completed task — extract video URL and trigger download."""
        item = self._items[idx]

        # Accept both full task objects and get_task_status results
        if isinstance(task_or_info, dict):
            artifacts = task_or_info.get("artifacts", [])
        else:
            artifacts = []

        video_url = ""
        for a in artifacts:
            if isinstance(a, dict) and ".mp4" in a.get("url", ""):
                video_url = a["url"]
                break

        if video_url:
            item.status = TaskStatus.DONE
            item.result_video_url = video_url
            self.item_status_changed.emit(idx, item.status.value, "")
            self.log_message.emit(f"#{idx + 1} 生成完成 — 正在下载…")
            await self._trigger_download(idx)
        else:
            logger.warning("Task %s succeeded but no mp4 artifact found", item.task_id)
            item.status = TaskStatus.DONE
            self.item_status_changed.emit(idx, item.status.value, "")

    async def _handle_failed(self, idx: int, task_or_info):
        """Handle a failed/cancelled task."""
        item = self._items[idx]
        if isinstance(task_or_info, dict):
            raw_error = task_or_info.get("error") or ""
            if isinstance(raw_error, dict):
                reason = raw_error.get("reason", "")
                err_msg = raw_error.get("errorMessage", str(raw_error))
                if "SAFETY" in reason:
                    category = raw_error.get("moderation_category", "UNKNOWN")
                    error = f"内容审核不通过 [{category}]: {err_msg}"
                else:
                    error = err_msg or "任务已失败"
            elif isinstance(raw_error, str):
                error = raw_error
            else:
                error = "任务已失败"
        else:
            error = "任务已失败"
        item.status = TaskStatus.FAILED
        item.error_message = error
        self.item_status_changed.emit(idx, item.status.value, error)
        self.log_message.emit(f"#{idx + 1} 任务失败: {error}")


    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    async def _trigger_download(self, idx: int, max_retries: int = 3):
        item = self._items[idx]
        if not self._download_manager or not item.result_video_url:
            return

        item.status = TaskStatus.DOWNLOADING
        self.item_status_changed.emit(idx, item.status.value, "")

        for attempt in range(1, max_retries + 1):
            try:
                success = await self._download_manager.download(item)
            except Exception as e:
                logger.exception("Download exception for idx=%d attempt %d: %s", idx, attempt, e)
                if attempt < max_retries:
                    self.log_message.emit(f"#{idx + 1} 下载失败(第{attempt}次)，重试中…")
                    await asyncio.sleep(5 * attempt)
                    continue
                item.status = TaskStatus.DONE
                item.error_message = f"下载异常(重试{max_retries}次): {e}"
                self.item_status_changed.emit(idx, item.status.value, item.error_message)
                return

            if success:
                item.status = TaskStatus.DOWNLOADED
                self.item_status_changed.emit(idx, item.status.value, "")
                self.log_message.emit(f"#{idx + 1} 下载完成: {item.result_video_path}")
                return
            else:
                if attempt < max_retries:
                    self.log_message.emit(f"#{idx + 1} 下载失败(第{attempt}次)，重试中…")
                    await asyncio.sleep(5 * attempt)
                    continue

        item.status = TaskStatus.DONE
        self.item_status_changed.emit(idx, item.status.value, f"下载失败(重试{max_retries}次)")

    async def retry_download(self, idx: int):
        """Public method for right-click retry of a DONE item with video URL."""
        item = self._items[idx]
        if not item.result_video_url:
            self.log_message.emit(f"#{idx + 1} 没有视频 URL，无法下载")
            return
        self.log_message.emit(f"#{idx + 1} 手动重试下载…")
        await self._trigger_download(idx)

    def _emit_progress(self):
        done = sum(
            1 for i in self._items
            if i.status in (TaskStatus.DOWNLOADED, TaskStatus.DONE, TaskStatus.SUBMITTED)
        )
        total = len(self._items)
        active = len(self._active)
        self.progress_updated.emit(done, total, active)
