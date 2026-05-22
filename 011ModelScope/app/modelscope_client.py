import asyncio
import logging
import json
from typing import Optional
from dataclasses import dataclass
import aiohttp

from app.models import QuotaInfo, ChatRole
from app.config import API_BASE_OPENAI, API_BASE_IMAGE

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds
RETRYABLE_STATUSES = {429, 502, 503, 504}


@dataclass
class ChatResponse:
    """Chat completion response"""
    content: str
    model_id: str
    finish_reason: str
    usage: dict
    quota: Optional[QuotaInfo] = None


@dataclass
class ImageResponse:
    """Image generation response"""
    image_url: str
    model_id: str
    quota: Optional[QuotaInfo] = None


class ModelScopeClient:
    """ModelScope API client with OpenAI-compatible interface"""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_key: str = ""
        self._proxy: Optional[str] = None

    def configure(self, api_key: str, proxy: Optional[str] = None) -> None:
        """Configure API key and optional proxy."""
        self._api_key = api_key
        self._proxy = proxy
        # Reset session to apply new config
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())
        self._session = None

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure session is initialized."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=120)
            connector = None
            if self._proxy:
                # Parse proxy for connector
                pass  # aiohttp handles proxy via request params
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=timeout,
            )
        return self._session

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _retry_request(self, url: str, body: dict) -> aiohttp.ClientResponse:
        """Execute HTTP request with retry logic for transient errors."""
        session = await self._ensure_session()

        for attempt in range(MAX_RETRIES + 1):
            try:
                proxy = self._proxy if self._proxy else None
                resp = await session.post(url, json=body, proxy=proxy)

                if resp.status in RETRYABLE_STATUSES and attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "可重试 HTTP %s (attempt %s/%s)，%ss 后重试...",
                        resp.status, attempt + 1, MAX_RETRIES + 1, delay,
                    )
                    await resp.release()
                    await asyncio.sleep(delay)
                    continue

                return resp

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "网络异常 %s (attempt %s/%s)，%ss 后重试...",
                        type(e).__name__, attempt + 1, MAX_RETRIES + 1, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        raise Exception(f"Request failed after {MAX_RETRIES + 1} attempts")

    @staticmethod
    def _parse_quota_headers(resp_headers, model_id: str) -> QuotaInfo:
        """Extract quota info from response headers (case-insensitive)."""
        h = resp_headers  # CIMultiDict, case-insensitive
        return QuotaInfo(
            model_id=model_id,
            daily_limit=int(h.get("modelscope-ratelimit-requests-limit", 0)),
            daily_remaining=int(h.get("modelscope-ratelimit-requests-remaining", 0)),
            model_limit=int(h.get("modelscope-ratelimit-model-requests-limit", 0)),
            model_remaining=int(h.get("modelscope-ratelimit-model-requests-remaining", 0)),
        )

    async def query_quota(self, model_id: str) -> QuotaInfo:
        """
        Query quota by sending a minimal request and extracting headers.
        This is the official way to get quota info from ModelScope API.
        """
        url = f"{API_BASE_OPENAI}chat/completions"
        body = {
            "model": model_id,
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 1,
        }

        try:
            resp = await self._retry_request(url, body)
            async with resp:
                quota = self._parse_quota_headers(resp.headers, model_id)

                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"Quota query failed for {model_id}: {resp.status} - {text}")

                return quota
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Network error querying quota for {model_id}: {e}")
            return QuotaInfo(model_id=model_id)
        except Exception as e:
            logger.exception(f"Unexpected error querying quota for {model_id}")
            return QuotaInfo(model_id=model_id)

    async def batch_query_quota(self, model_ids: list[str], max_concurrent: int = 5) -> dict[str, QuotaInfo]:
        """Query quota for multiple models concurrently."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _query_with_semaphore(model_id: str) -> tuple[str, QuotaInfo]:
            async with semaphore:
                quota = await self.query_quota(model_id)
                await asyncio.sleep(0.1)  # Small delay to avoid rate limiting
                return model_id, quota

        tasks = [_query_with_semaphore(mid) for mid in model_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        quotas = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Batch quota query error: {result}")
            else:
                model_id, quota = result
                quotas[model_id] = quota

        return quotas

    async def chat_completion(
        self,
        model_id: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """Send a chat completion request. Always uses streaming internally
        because some models return null choices for non-streaming."""
        url = f"{API_BASE_OPENAI}chat/completions"

        msg_list = []
        if system_prompt:
            msg_list.append({"role": "system", "content": system_prompt})
        msg_list.extend(messages)

        body = {
            "model": model_id,
            "messages": msg_list,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        resp = await self._retry_request(url, body)
        async with resp:
            headers = dict(resp.headers)
            quota = self._parse_quota_headers(headers, model_id)

            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"API error {resp.status}: {text}")

            content = ""
            usage = {}
            finish_reason = "stop"
            async for line in resp.content:
                line = line.decode("utf-8").strip()
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices")
                        if choices and len(choices) > 0:
                            delta = choices[0].get("delta", {})
                            if "content" in delta:
                                content += delta["content"]
                            if choices[0].get("finish_reason"):
                                finish_reason = choices[0]["finish_reason"]
                        if "usage" in chunk:
                            usage = chunk["usage"]
                    except json.JSONDecodeError:
                        continue

            self._record_usage(model_id, usage)
            return ChatResponse(
                content=content,
                model_id=model_id,
                finish_reason=finish_reason,
                usage=usage,
                quota=quota,
            )

    async def stream_chat(
        self,
        model_id: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None,
    ):
        """Stream chat completion, yielding content chunks."""
        url = f"{API_BASE_OPENAI}chat/completions"

        msg_list = []
        if system_prompt:
            msg_list.append({"role": "system", "content": system_prompt})
        msg_list.extend(messages)

        body = {
            "model": model_id,
            "messages": msg_list,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        resp = await self._retry_request(url, body)
        async with resp:
            headers = dict(resp.headers)
            quota = self._parse_quota_headers(headers, model_id)

            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"API error {resp.status}: {text}")

            yield ("quota", quota)

            usage = {}
            async for line in resp.content:
                line = line.decode("utf-8").strip()
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            yield ("content", delta["content"])
                        if "usage" in chunk:
                            usage = chunk["usage"]
                    except json.JSONDecodeError:
                        continue

            self._record_usage(model_id, usage)
            yield ("done", None)

    async def generate_image(
        self,
        model_id: str,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
        seed: Optional[int] = None,
    ) -> ImageResponse:
        """Generate image from text prompt."""
        url = API_BASE_IMAGE

        body = {
            "model": model_id,
            "prompt": prompt,
            "n": n,
            "size": size,
        }
        if seed is not None:
            body["seed"] = seed

        resp = await self._retry_request(url, body)
        async with resp:
            headers = dict(resp.headers)
            quota = self._parse_quota_headers(headers, model_id)

            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Image API error {resp.status}: {text}")

            data = await resp.json()
            image_url = data["data"][0].get("url", "")

            return ImageResponse(
                image_url=image_url,
                model_id=model_id,
                quota=quota,
            )

    def _record_usage(self, model_id: str, usage: dict) -> None:
        """Record API usage statistics to file."""
        if not usage:
            return
        try:
            from datetime import datetime
            from app.config import usage_stats_path

            path = usage_stats_path()
            today = datetime.now().strftime("%Y-%m-%d")

            # Load existing
            existing = []
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    existing = []

            # Find or create today's entry for this model
            found = False
            for entry in existing:
                if entry.get("date") == today and entry.get("model_id") == model_id:
                    entry["request_count"] = entry.get("request_count", 0) + 1
                    entry["input_tokens"] = entry.get("input_tokens", 0) + usage.get("prompt_tokens", 0)
                    entry["output_tokens"] = entry.get("output_tokens", 0) + usage.get("completion_tokens", 0)
                    found = True
                    break

            if not found:
                existing.append({
                    "date": today,
                    "model_id": model_id,
                    "request_count": 1,
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                })

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to record usage stats: {e}")

    async def validate_api_key(self) -> bool:
        """Validate API key by making a test request."""
        if not self._api_key:
            return False

        try:
            quota = await self.query_quota("Qwen/Qwen3-8B")
            return quota.daily_limit > 0 or quota.model_limit > 0
        except Exception as e:
            logger.error(f"API key validation failed: {e}")
            return False

    def get_openai_client_config(self) -> dict:
        """Get config for OpenAI SDK if needed."""
        return {
            "api_key": self._api_key,
            "base_url": API_BASE_OPENAI,
        }


# Singleton instance
_client_instance: Optional[ModelScopeClient] = None


def get_client() -> ModelScopeClient:
    """Get the singleton client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = ModelScopeClient()
    return _client_instance