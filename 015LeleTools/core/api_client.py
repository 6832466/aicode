"""
OpenAI 协议 API 客户端 — 支持流式/非流式对话
"""

import json
import logging
import time
from typing import Iterator, Optional

import requests

from app.constants import MAX_RETRIES, RETRY_DELAY, RETRY_STATUSES

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    pass


class APIClient:
    """OpenAI 兼容 API 客户端"""

    def __init__(self, base_url: str = "", api_key: str = "", model: str = ""):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = 60
        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json"
        self._session.headers["Connection"] = "close"
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    def configure(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._session.headers["Connection"] = "close"

    # ------------------------------------------------------------------
    # Test Connection
    # ------------------------------------------------------------------

    def test_connection(self) -> tuple[bool, str]:
        """测试 API 连接，返回 (成功, 消息)"""
        if not self._base_url:
            return False, "请先配置 API 地址"
        try:
            models = self.get_models()
            if models:
                return True, f"连接成功，可用模型: {len(models)} 个"
            return True, "连接成功"
        except APIClientError as e:
            return False, str(e)
        except Exception as e:
            return False, f"连接失败: {e}"

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    def get_models(self) -> list[str]:
        """获取可用模型列表"""
        try:
            resp = self._session.get(
                f"{self._base_url}/v1/models",
                timeout=(15, self._timeout),
            )
            resp.raise_for_status()
            data = resp.json()
            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                if model_id:
                    models.append(model_id)
            return sorted(models)
        except requests.RequestException as e:
            raise APIClientError(f"获取模型列表失败: {e}") from e
        except (ValueError, KeyError) as e:
            raise APIClientError(f"解析模型列表失败: {e}") from e

    # ------------------------------------------------------------------
    # Chat Completion
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        model: str = "",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> dict | Iterator[str]:
        """
        发送对话请求

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称，默认使用实例配置
            stream: 是否流式输出
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            stream=False: 完整响应 dict
            stream=True: 生成器，逐条 yield delta 文本
        """
        url = f"{self._base_url}/v1/chat/completions"
        payload = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }

        if stream:
            return self._chat_stream(url, payload)
        else:
            return self._chat_sync(url, payload)

    def _chat_sync(self, url: str, payload: dict) -> dict:
        last_error: Optional[Exception] = None

        for attempt in range(MAX_RETRIES):
            try:
                resp = self._session.post(
                    url, json=payload, timeout=(30, self._timeout)
                )
                if resp.status_code in RETRY_STATUSES:
                    wait = RETRY_DELAY * (2**attempt)
                    logger.warning(
                        "retry %d/%d after %ds (status %d)",
                        attempt + 1, MAX_RETRIES, wait, resp.status_code,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                # 检查 200 响应中的错误关键词
                if "error" in data:
                    err_info = data["error"]
                    err_msg = err_info if isinstance(err_info, str) else err_info.get("message", str(err_info))
                    raise APIClientError(f"API 返回错误: {err_msg}")
                content = data["choices"][0]["message"]["content"]
                return {
                    "content": content,
                    "model": data.get("model", ""),
                    "usage": data.get("usage", {}),
                }
            except requests.RequestException as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (2**attempt)
                    logger.warning(
                        "retry %d/%d after %ds (error: %s)",
                        attempt + 1, MAX_RETRIES, wait, e,
                    )
                    time.sleep(wait)
                else:
                    raise APIClientError(f"API 调用失败: {e}") from e
            except (KeyError, IndexError, ValueError) as e:
                raise APIClientError(f"解析响应失败: {e}") from e

        raise APIClientError(str(last_error))

    def _chat_stream(self, url: str, payload: dict) -> Iterator[str]:
        """流式对话，逐条 yield delta 文本 — 每次独立连接，不复用 Session"""
        last_error: Optional[Exception] = None
        headers = {
            "Content-Type": "application/json",
            "Connection": "close",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(
                    url, json=payload, timeout=(30, self._timeout),
                    stream=True, headers=headers,
                )
                if resp.status_code in RETRY_STATUSES:
                    wait = RETRY_DELAY * (2**attempt)
                    logger.warning(
                        "retry %d/%d after %ds (status %d)",
                        attempt + 1, MAX_RETRIES, wait, resp.status_code,
                    )
                    resp.close()
                    time.sleep(wait)
                    continue
                resp.raise_for_status()

                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        return
                    try:
                        data = json.loads(data_str)
                        if "error" in data:
                            err = data["error"]
                            msg = err if isinstance(err, str) else err.get("message", str(err))
                            raise APIClientError(f"API 返回错误: {msg}")
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            reasoning = delta.get("reasoning_content", "")
                            if content:
                                yield content
                            elif reasoning:
                                yield reasoning
                    except json.JSONDecodeError:
                        continue
                return

            except requests.RequestException as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (2**attempt)
                    logger.warning(
                        "retry %d/%d after %ds (error: %s)",
                        attempt + 1, MAX_RETRIES, wait, e,
                    )
                    time.sleep(wait)
                else:
                    raise APIClientError(f"流式调用失败: {e}") from e

        raise APIClientError(str(last_error))
