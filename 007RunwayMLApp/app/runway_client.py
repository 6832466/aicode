import asyncio
import logging
from typing import Callable
import urllib.parse

import aiohttp

from .config import API_BASE, DEFAULT_TEAM_ID
from .models import PromptItem, CharacterAsset

logger = logging.getLogger(__name__)


class RunwayClient:
    """Async HTTP client for RunwayML internal API (api.runwayml.com)."""

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._token: str = ""
        self._team_id: str = DEFAULT_TEAM_ID
        self._resolution: str = "720p"
        self._generate_audio: bool = True

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def configure(self, token: str, team_id: str = DEFAULT_TEAM_ID,
                  resolution: str = "720p", generate_audio: bool = True):
        self._token = token
        self._team_id = team_id
        self._resolution = resolution
        self._generate_audio = generate_audio

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-runway-workspace": self._team_id,
            "x-runway-source-application": "web",
            "Origin": "https://app.runwayml.com",
            "Referer": "https://app.runwayml.com/",
        }

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=timeout,
            )

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Auth check
    # ------------------------------------------------------------------

    async def validate_token(self) -> tuple[bool, str]:
        """Lightweight auth check. Returns (is_valid, email_or_error)."""
        await self._ensure_session()
        try:
            async with self._session.get(
                f"{API_BASE}/sessions",
                params={"asTeamId": self._team_id, "limit": 1},
            ) as resp:
                if resp.status == 401:
                    return False, "Token expired or invalid (401)"
                if resp.status >= 400:
                    body = await resp.text()
                    return False, f"HTTP {resp.status}: {body[:200]}"
                data = await resp.json()
                sessions = data.get("sessions", [])
                return True, f"OK — {len(sessions)} recent sessions found"
        except aiohttp.ClientError as e:
            return False, f"Connection error: {e}"

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    async def list_sessions(self, limit: int = 5) -> list[dict]:
        await self._ensure_session()
        try:
            async with self._session.get(
                f"{API_BASE}/sessions",
                params={"asTeamId": self._team_id, "limit": limit},
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("sessions", [])
        except aiohttp.ClientError as e:
            logger.error("获取会话列表失败: %s", e)
            return []

    async def get_session(self, session_id: str) -> dict | None:
        await self._ensure_session()
        try:
            async with self._session.get(
                f"{API_BASE}/sessions/{session_id}",
                params={"asTeamId": self._team_id},
            ) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as e:
            logger.error("获取会话 %s 失败: %s", session_id, e)
            return None

    # ------------------------------------------------------------------
    # Task creation (POST /v1/tasks — current API as of 2026-05-07)
    # ------------------------------------------------------------------

    async def can_start(self) -> dict:
        """Check if we can start a new task and how many are in progress."""
        await self._ensure_session()
        try:
            async with self._session.get(
                f"{API_BASE}/tasks/can_start",
                params={"asTeamId": self._team_id, "mode": "credits", "feature": "seedance_2"},
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                info = data.get("canStartNewTask", {})
                return {
                    "can_start": info.get("canStartNewTask", False),
                    "limit": info.get("currentLimit", 2),
                    "in_progress": info.get("currentInProgressTasks", 0),
                }
        except aiohttp.ClientError as e:
            logger.error("检查任务上限失败: %s", e)
            return {"can_start": True, "limit": 2, "in_progress": 0}  # allow on error — fall back to 429 handling

    async def create_generation(
        self,
        item: PromptItem,
        char_assets: dict[str, CharacterAsset],
        asset_group_id: str = "",
    ) -> dict | None:
        """
        POST /v1/tasks with taskType: seedance_2.

        Returns {"taskId": real_task_id, "status": ...} on success.
        Returns {"status": "RATE_LIMITED"} on 429.
        Returns None on other errors.
        """
        await self._ensure_session()

        reference_images = []
        for ref_name in item.references:
            asset = char_assets.get(ref_name)
            if asset:
                reference_images.append({
                    "assetId": asset.asset_id,
                    "url": asset.url,
                })

        ref_names = "_".join(item.references) if item.references else "text_only"
        prompt_preview = item.effective_prompt[:30].replace("\n", " ")
        # HTTP headers use latin-1 encoding, Chinese chars cause encoding error
        # Use URL-safe encoding for non-ASCII characters in task name
        raw_name = f"Seedance 2_0 - {ref_names}_{prompt_preview}"
        name = raw_name.encode("ascii", errors="replace").decode("ascii")

        options = {
            "name": name,
            "textPrompt": item.effective_prompt,
            "referenceImages": reference_images,
            "referenceVideos": [],
            "referenceAudio": [],
            "resolution": self._resolution,
            "aspectRatio": item.ratio,
            "duration": item.duration,
            "generateAudio": self._generate_audio,
            "creationSource": "tool-mode",
            "exploreMode": True,
            "recordingEnabled": True,
        }

        if asset_group_id:
            options["assetGroupId"] = asset_group_id

        payload = {
            "taskType": "seedance_2",
            "options": options,
        }

        logger.info("POST /v1/tasks refs=%s dur=%ss", item.references, item.duration)

        try:
            async with self._session.post(
                f"{API_BASE}/tasks",
                params={"asTeamId": self._team_id},
                json=payload,
            ) as resp:
                body = await resp.text()
                if resp.status == 429:
                    logger.warning("create_generation rate-limited: %s", body[:200])
                    return {"status": "RATE_LIMITED", "taskId": ""}
                if resp.status in (502, 503, 504):
                    logger.warning("create_generation server busy (HTTP %s): %s", resp.status, body[:300])
                    return {"status": "SERVER_BUSY", "taskId": ""}
                if resp.status >= 400:
                    logger.error("create_generation failed: HTTP %s — %s", resp.status, body[:500])
                    return None
                # Check for safety interception (content moderation) — must NOT retry
                if "intercepted" in body.lower() or "reusing the same information" in body.lower():
                    logger.warning("create_generation safety intercepted: %s", body[:300])
                    return {"status": "SAFETY_INTERCEPTED", "taskId": "", "error": body[:500]}

                # Check for heavy load in successful response body
                if "heavy load" in body.lower() or "under heavy" in body.lower():
                    logger.warning("create_generation heavy load detected in response")
                    return {"status": "SERVER_BUSY", "taskId": ""}

                data = await resp.json()
                task = data.get("task", {})
                real_task_id = task.get("id", "")
                status = task.get("status", "?")
                logger.info("POST /v1/tasks → taskId=%s status=%s", real_task_id[:8] if real_task_id else "?", status)
                return {"taskId": real_task_id, "status": status, "raw": data}
        except aiohttp.ClientError as e:
            logger.error("创建生成任务网络异常: %s", e)
            return {"status": "SERVER_BUSY", "taskId": ""}  # Retry on transient network errors

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    async def get_task(self, task_id: str) -> dict | None:
        await self._ensure_session()
        try:
            async with self._session.get(
                f"{API_BASE}/tasks/{task_id}",
                params={"asTeamId": self._team_id},
            ) as resp:
                if resp.status == 404:
                    logger.warning("GET /v1/tasks/%s → 404 NOT_FOUND", task_id)
                    return None
                resp.raise_for_status()
                data = await resp.json()
                logger.info("GET /v1/tasks/%s → status=%s", task_id, data.get("task", data).get("status", "?"))
                return data
        except aiohttp.ClientError as e:
            logger.error("获取任务 %s 失败: %s", task_id, e)
            return None

    async def get_task_status(self, task_id: str) -> dict:
        """Return {status, progressRatio, error, artifacts, updatedAt}."""
        data = await self.get_task(task_id)
        if not data:
            return {"status": "NOT_FOUND", "progressRatio": 0, "error": "Task not found"}
        task = data.get("task", data)
        progress = task.get("progressRatio", task.get("progress", 0))
        logger.info("GET /v1/tasks/%s → status=%s progress=%s", task_id, task.get("status", "?"), progress)
        return {
            "status": task.get("status", "UNKNOWN"),
            "progressRatio": progress,
            "error": task.get("error"),
            "artifacts": task.get("artifacts", []),
            "updatedAt": task.get("updatedAt", ""),
        }

    async def delete_task(self, task_id: str) -> bool:
        await self._ensure_session()
        try:
            async with self._session.delete(
                f"{API_BASE}/tasks/{task_id}",
                params={"asTeamId": self._team_id},
            ) as resp:
                return resp.status == 200
        except aiohttp.ClientError as e:
            logger.error("删除任务 %s 失败: %s", task_id, e)
            return False

    # ------------------------------------------------------------------
    # Asset References (Seedance character references)
    # ------------------------------------------------------------------

    async def get_asset_references(self, limit: int = 100) -> list[dict]:
        """Get Seedance asset_references. Returns up to `limit` [{tag, asset: {id, url, previewUrl, ...}}]."""
        await self._ensure_session()
        try:
            async with self._session.get(
                f"{API_BASE}/asset_references",
                params={"asTeamId": self._team_id, "limit": limit},
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                refs = data.get("references", [])
                return refs[:limit]
        except aiohttp.ClientError as e:
            logger.error("获取角色引用失败: %s", e)
            return []

    # ------------------------------------------------------------------
    # Asset URL refresh
    # ------------------------------------------------------------------

    async def refresh_asset_url(self, asset_id: str) -> str:
        """Get a fresh JWT-signed URL for an asset. Returns empty string on failure."""
        await self._ensure_session()
        try:
            async with self._session.get(
                f"{API_BASE}/assets/{asset_id}",
            ) as resp:
                if resp.status >= 400:
                    logger.warning("GET /v1/assets/%s → %s", asset_id, resp.status)
                    return ""
                data = await resp.json()
                return data.get("asset", {}).get("url", "")
        except aiohttp.ClientError as e:
            logger.warning("Failed to refresh asset URL for %s: %s", asset_id, e)
            return ""

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    async def download_video(
        self,
        url: str,
        filepath: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> bool:
        """Stream-download a video from CloudFront URL to filepath."""
        await self._ensure_session()
        try:
            async with self._session.get(url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))
                received = 0
                with open(filepath, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
                        received += len(chunk)
                        if progress_callback:
                            progress_callback(received, total)
            return True
        except aiohttp.ClientError as e:
            logger.error("Download failed: %s", e)
            return False
