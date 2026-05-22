"""
bj.nfai.lol New API — 远程 AI 生图客户端
==========================================
轻量级、无 GUI 依赖，仅需 `requests`。

适用场景：通过 bj.nfai.lol 的 New API 调用 Gemini / GPT 图像生成模型。

快速开始
--------
    from bj_nfai_api import NfaiClient

    # 方式 1：直接传入 session cookie
    client = NfaiClient(session_cookie="你的session值", user_id="13679")

    # 方式 2：从环境变量读取（推荐）
    # export NFAI_SESSION=你的session值
    client = NfaiClient.from_env()

    # 生图
    result = client.generate("一个美丽的风景画")
    if result.ok:
        result.save("output.png")
    else:
        print(result.error)

认证方式
--------
bj.nfai.lol 的 New API 使用 Session Cookie 认证（Bearer Token 已禁用）。
从浏览器 F12 → Application → Cookies → 复制 session 字段的值即可。

模型列表
--------
    图生图（Gemini）:
    - gemini-2.5-flash-image          $0.033/次
    - gemini-2.5-flash-image-preview  $0.033/次
    - gemini-3.1-flash-image-preview-url  $0.090/次
    - gemini-3-pro-image-preview-url  $0.180/次
    - gemini-3-pro-image-preview      $0.190/次

    图生图（GPT）:
    - gpt-image-2                     $0.042/次
    - gpt-image-2-1k                  $0.042/次
    - gpt-image-2-2k                  $0.082/次
    - gpt-image-2-4k                  $0.082/次

注意事项
--------
- 远程 API 使用裸模型名，不需要拼接 aspect ratio / resolution 后缀
- 请求体需包含 "group": "default" 字段用于令牌分组选择
- 充值地址：https://bj.nfai.lol/console/topup
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

# ── 模型列表 ──────────────────────────────────────────
GEMINI_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-2.5-flash-image-preview",
    "gemini-3.1-flash-image-preview-url",
    "gemini-3-pro-image-preview-url",
    "gemini-3-pro-image-preview",
]

GPT_MODELS = [
    "gpt-image-2",
    "gpt-image-2-1k",
    "gpt-image-2-2k",
    "gpt-image-2-4k",
]

ALL_MODELS = GEMINI_MODELS + GPT_MODELS

# ── 结果 ──────────────────────────────────────────────
@dataclass
class NfaiResult:
    """生图结果"""
    ok: bool
    data: Optional[bytes] = None
    error: Optional[str] = None
    model: Optional[str] = None
    elapsed: float = 0.0

    def save(self, path: str) -> bool:
        """保存图片到文件"""
        if not self.data:
            return False
        with open(path, "wb") as f:
            f.write(self.data)
        return True


# ── 客户端 ────────────────────────────────────────────
class NfaiClient:
    """bj.nfai.lol New API 客户端"""

    BASE_URL = "https://bj.nfai.lol/pg"
    ENDPOINT = "/chat/completions"
    DEFAULT_MODEL = "gemini-2.5-flash-image"
    TIMEOUT = 300

    def __init__(
        self,
        session_cookie: str = "",
        user_id: str = "13679",
        group: str = "default",
        base_url: str = "",
        endpoint: str = "",
        timeout: int = 0,
    ):
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.endpoint = endpoint or self.ENDPOINT
        self.session_cookie = session_cookie
        self.user_id = user_id
        self.group = group
        self.timeout = timeout or self.TIMEOUT

    # ── 工厂方法 ───────────────────────────────────
    @classmethod
    def from_env(cls) -> "NfaiClient":
        """从环境变量创建：NFAI_SESSION, NFAI_USER_ID(可选), NFAI_GROUP(可选)"""
        cookie = os.environ.get("NFAI_SESSION", "")
        user_id = os.environ.get("NFAI_USER_ID", "13679")
        group = os.environ.get("NFAI_GROUP", "default")
        return cls(session_cookie=cookie, user_id=user_id, group=group)

    # ── 属性 ───────────────────────────────────────
    @property
    def url(self) -> str:
        return f"{self.base_url}{self.endpoint}"

    @property
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.session_cookie:
            h["Cookie"] = f"session={self.session_cookie}"
            if self.user_id:
                h["new-api-user"] = self.user_id
        return h

    # ── 连接检查 ───────────────────────────────────
    def check(self) -> tuple[bool, str]:
        """测试连接是否正常。返回 (ok, message)。"""
        from urllib.parse import urlparse
        parsed = urlparse(self.base_url)
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
            return False, f"Server returned {resp.status_code}: {resp.text[:200]}"
        except requests.exceptions.ConnectionError:
            return False, f"Cannot reach {root}"
        except Exception as e:
            return False, str(e)

    # ── 生图 ───────────────────────────────────────
    def generate(
        self,
        prompt: str,
        model: str = "",
        reference_image: bytes | None = None,
    ) -> NfaiResult:
        """生成一张图片。

        Args:
            prompt: 提示词
            model: 模型名，默认 gemini-2.5-flash-image
            reference_image: 参考图（垫图）的字节数据，可选

        Returns:
            NfaiResult（ok=True 时可通过 .save(path) 保存）
        """
        model = model or self.DEFAULT_MODEL
        t0 = time.time()

        # 构建消息
        if reference_image:
            import base64
            b64 = base64.b64encode(reference_image).decode()
            content = [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": prompt}]

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "group": self.group,
        }

        try:
            resp = requests.post(
                self.url,
                headers=self._headers,
                json=payload,
                timeout=self.timeout,
                stream=True,
            )
        except requests.exceptions.ConnectionError:
            return NfaiResult(ok=False, error=f"无法连接 {self.base_url}", model=model, elapsed=time.time() - t0)
        except requests.exceptions.Timeout:
            return NfaiResult(ok=False, error="请求超时 (300s)", model=model, elapsed=time.time() - t0)
        except Exception as e:
            return NfaiResult(ok=False, error=f"{type(e).__name__}: {e}", model=model, elapsed=time.time() - t0)

        # 非流式响应（错误或直接返回）
        ct = resp.headers.get("Content-Type", "")
        if "text/event-stream" not in ct:
            body = resp.text
            if resp.status_code != 200:
                try:
                    err = json.loads(body)
                    detail = err.get("message", "") or json.dumps(err, ensure_ascii=False)
                except json.JSONDecodeError:
                    detail = body[:500]
                return NfaiResult(ok=False, error=f"HTTP {resp.status_code}: {detail}", model=model, elapsed=time.time() - t0)

            # 非流式成功
            try:
                data = json.loads(body)
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    url = _extract_image_url(content)
                    if url:
                        img = _download(url)
                        if img:
                            return NfaiResult(ok=True, data=img, model=model, elapsed=time.time() - t0)
                return NfaiResult(ok=False, error=f"No image URL in response", model=model, elapsed=time.time() - t0)
            except json.JSONDecodeError:
                return NfaiResult(ok=False, error=f"Bad JSON response: {body[:300]}", model=model, elapsed=time.time() - t0)

        # SSE 流式解析
        resp.raise_for_status()
        image_url = ""
        accumulated = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if "error" in chunk:
                err = chunk["error"]
                msg = err.get("message", json.dumps(err, ensure_ascii=False))
                return NfaiResult(ok=False, error=f"SSE error: {msg}", model=model, elapsed=time.time() - t0)

            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                text = delta.get("content", "")
                if text:
                    accumulated += text
                    u = _extract_image_url(text)
                    if u:
                        image_url = u
                if choice.get("finish_reason") == "stop":
                    break

        if not image_url:
            image_url = _extract_image_url(accumulated)
        if not image_url:
            detail = accumulated[:300] if accumulated else "(empty)"
            return NfaiResult(ok=False, error=f"No image URL in stream. Content: {detail}", model=model, elapsed=time.time() - t0)

        img = _download(image_url)
        if not img:
            return NfaiResult(ok=False, error=f"Failed to download image: {image_url[:150]}", model=model, elapsed=time.time() - t0)

        return NfaiResult(ok=True, data=img, model=model, elapsed=time.time() - t0)

    def __repr__(self):
        return f"NfaiClient(url={self.url}, auth={'cookie' if self.session_cookie else 'none'})"


# ── 内部工具函数 ─────────────────────────────────────
def _extract_image_url(text: str) -> str:
    """从 Markdown 或原始文本中提取图片 URL。"""
    import re
    # Gemini markdown: ![image](url)
    m = re.search(r'!\[.*?\]\((https?://[^\s)]+)\)', text)
    if m:
        return m.group(1)
    # 直接的 https URL
    m = re.search(r'(https?://[^\s"\'<>]+\.(?:png|jpg|jpeg|webp|gif)[^\s"\'<>]*)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def _download(url: str) -> Optional[bytes]:
    """下载图片，支持 base64 data URI。"""
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


# ── 命令行测试入口 ────────────────────────────────────
if __name__ == "__main__":
    import sys

    client = NfaiClient.from_env()
    ok, msg = client.check()
    print(f"连接: {msg}")
    if not ok:
        sys.exit(1)

    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "a beautiful landscape, 4k"
    model = os.environ.get("NFAI_MODEL", NfaiClient.DEFAULT_MODEL)
    print(f"模型: {model}")
    print(f"提示词: {prompt[:80]}...")
    print("生成中...")

    result = client.generate(prompt, model=model)
    if result.ok:
        fn = f"nfai_output_{int(time.time())}.png"
        result.save(fn)
        print(f"成功! 保存到 {fn} ({len(result.data):,} bytes, {result.elapsed:.1f}s)")
    else:
        print(f"失败: {result.error}")
        sys.exit(1)
