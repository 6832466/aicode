"""HTTP client for flow2api OpenAI-compatible API."""
import json
import time
from dataclasses import dataclass
from typing import Optional

import requests

from utils import extract_image_url_from_content


@dataclass
class GenerationResult:
    """Result of a single image generation request."""
    success: bool
    image_data: Optional[bytes] = None
    error_message: Optional[str] = None
    prompt: Optional[str] = None


class Flow2ApiClient:
    """Synchronous client for flow2api image generation."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 300, endpoint_path: str = "/v1/chat/completions",
                 session_cookie: str = "", user_id: str = "", group: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.endpoint_path = endpoint_path
        self.session_cookie = session_cookie
        self.user_id = user_id
        self.group = group

    @property
    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.session_cookie:
            h["Cookie"] = f"session={self.session_cookie}"
            if self.user_id:
                h["new-api-user"] = self.user_id
        elif self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def generate_image(self, prompt: str, model: str, reference_image: bytes | None = None,
                        image_size: str = "") -> GenerationResult:
        """Generate a single image via flow2api and return the result."""
        if reference_image:
            import base64
            b64 = base64.b64encode(reference_image).decode("utf-8")
            # Strong ratio override: append it at the very end of the prompt,
            # place reference image BEFORE text so text instructions take priority.
            ratio_override = "\n\n【重要】输出图片的宽高比例必须严格遵循上述文字描述中的比例要求。参考图仅用于提供人物面部特征、五官、发型、发色、脸型参考，不得参考其图片尺寸比例。"
            content = [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": prompt + ratio_override},
            ]
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": prompt}]

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if image_size:
            payload["size"] = image_size
        if self.session_cookie and self.group:
            payload["group"] = self.group

        url = f"{self.base_url}{self.endpoint_path}"
        auth_method = "session-cookie" if self.session_cookie else ("bearer-token" if self.api_key else "none")

        def _err(detail: str) -> GenerationResult:
            return GenerationResult(
                success=False,
                error_message=f"[{model}] {detail} (auth={auth_method}, url={url})",
                prompt=prompt,
            )

        try:
            resp = requests.post(
                url,
                headers=self._headers,
                json=payload,
                timeout=self.timeout,
                stream=True,
            )

            content_type = resp.headers.get("Content-Type", "")
            if "text/event-stream" not in content_type:
                body = resp.text
                if resp.status_code != 200:
                    try:
                        err = json.loads(body)
                        detail = err.get("message", err.get("error", "")) or json.dumps(err, ensure_ascii=False)
                        return _err(f"HTTP {resp.status_code}: {detail}")
                    except json.JSONDecodeError:
                        return _err(f"HTTP {resp.status_code}: {body[:500]}")
                # Non-streaming success response
                try:
                    data = json.loads(body)
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        content = msg.get("content", "")
                        image_url = extract_image_url_from_content(content)
                        if image_url:
                            image_data = self._download_image(image_url)
                            if image_data:
                                return GenerationResult(
                                    success=True,
                                    image_data=image_data,
                                    prompt=prompt,
                                )
                    return _err(f"No image URL in response: {json.dumps(data, ensure_ascii=False)[:500]}")
                except json.JSONDecodeError:
                    return _err(f"Unexpected response: {body[:500]}")

            resp.raise_for_status()

            image_url = None
            content_parts: list[str] = []

            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue

                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if "error" in data:
                    err = data["error"]
                    err_msg = err.get("message", json.dumps(err, ensure_ascii=False))
                    return _err(f"SSE error: {err_msg}")

                choices = data.get("choices", [])
                for choice in choices:
                    delta = choice.get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        content_parts.append(content)
                        if not image_url:
                            url_found = extract_image_url_from_content(content)
                            if url_found:
                                image_url = url_found

                    if choice.get("finish_reason") == "stop":
                        break

            if not image_url and content_parts:
                image_url = extract_image_url_from_content("".join(content_parts))

            if not image_url:
                detail = "".join(content_parts)[:300] if content_parts else "(empty)"
                return _err(f"No image URL in SSE stream. Content: {detail}")

            image_data = self._download_image(image_url)
            if image_data is None:
                return _err(f"Failed to download image from: {image_url[:150]}")

            return GenerationResult(
                success=True,
                image_data=image_data,
                prompt=prompt,
            )

        except requests.exceptions.Timeout:
            return _err("Request timed out (300s)")
        except requests.exceptions.ConnectionError:
            return _err(f"Connection failed — server unreachable at {self.base_url}")
        except requests.exceptions.HTTPError as e:
            detail = ""
            try:
                detail = e.response.text[:500]
            except Exception:
                pass
            return _err(f"HTTP {e.response.status_code}: {detail}" if detail else str(e))
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")

    def _download_image(self, url: str) -> Optional[bytes]:
        """Download image from URL, or decode from base64 data URI."""
        if url.startswith("data:image/url;base64,"):
            # The "base64 data" is actually a plain URL to download from
            actual_url = url[len("data:image/url;base64,"):]
            try:
                resp = requests.get(actual_url, timeout=60)
                resp.raise_for_status()
                return resp.content
            except Exception:
                return None
        if url.startswith("data:"):
            import base64
            try:
                _, encoded = url.split(",", 1)
                return base64.b64decode(encoded)
            except Exception:
                return None

        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return resp.content
        except Exception:
            return None

    def check_connection(self) -> tuple[bool, str]:
        """Check connectivity to the API server. Returns (ok, message)."""
        if self.session_cookie:
            # Use New API's internal status endpoint for session-based auth
            base = self.base_url.rstrip("/")
            # Remove path prefix from base_url (e.g. /pg) to reach internal API
            from urllib.parse import urlparse
            parsed = urlparse(base)
            root = f"{parsed.scheme}://{parsed.netloc}"
            try:
                resp = requests.get(
                    f"{root}/api/status",
                    headers=self._headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        return True, f"Connected — {self.base_url}"
                return False, f"Server returned {resp.status_code}"
            except requests.exceptions.ConnectionError:
                return False, f"Cannot reach {root}"
            except Exception as e:
                return False, str(e)
        else:
            # Bearer token: try models endpoint
            models_path = self.endpoint_path.replace("chat/completions", "models")
            try:
                resp = requests.get(
                    f"{self.base_url}{models_path}",
                    headers=self._headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and "data" in data:
                        return True, f"Connected — {self.base_url}"
                    if isinstance(data, list):
                        return True, f"Connected — {self.base_url}"
                return False, f"Server returned {resp.status_code}"
            except requests.exceptions.ConnectionError:
                return False, f"Cannot reach {self.base_url}"
            except Exception as e:
                return False, str(e)
