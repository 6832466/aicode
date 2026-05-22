"""API 通信层 - 调用 OpenAI 兼容接口生成图片"""
import json
import re
import time
import logging
from typing import Optional, Callable
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
MAX_POLLS = 12
POLL_INTERVAL = 5  # 秒
TIMEOUT_SECONDS = 360  # 6分钟

# 已知的比例后缀
RATIO_SUFFIXES = ["-square", "-portrait", "-landscape", "-four-three", "-three-four",
                  "-square-2k", "-portrait-2k", "-landscape-2k",
                  "-square-4k", "-portrait-4k", "-landscape-4k"]


@dataclass
class ApiConfig:
    base_url: str = "http://localhost:8000"
    api_key: str = "sk-MuEiwKWLDIpAX68VCmxcZV6cwuHHQR102Qke5P6xKFgYOmRT"
    model: str = "gemini-3-pro-image-preview"
    ratio: str = "square"  # square, portrait, landscape


def is_flow2api_style(base_url: str) -> bool:
    """检测是否是 flow2api 风格 API（模型名含比例后缀）"""
    return "localhost" in base_url or "127.0.0.1" in base_url


def build_model_with_ratio(base_model: str, ratio: str) -> str:
    """为 flow2api 构建含比例后缀的模型名"""
    # 先去掉已有的比例后缀
    clean = base_model
    for suffix in sorted(RATIO_SUFFIXES, key=len, reverse=True):
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)]
            break
    ratio_suffix = {"square": "-square", "portrait": "-portrait", "landscape": "-landscape"}
    return clean + ratio_suffix.get(ratio, "-square")


class ApiClient:
    """OpenAI 兼容 API 客户端 — 支持 flow2api 和 geeknow 两种 API"""

    def __init__(self, config: ApiConfig, log_callback: Optional[Callable] = None):
        self.config = config
        self.log = log_callback or (lambda msg, level: None)

    def _build_url(self) -> str:
        base = self.config.base_url.rstrip("/")
        return f"{base}/v1/chat/completions"

    def _aspect_ratio(self) -> str:
        mapping = {"square": "1:1", "portrait": "9:16", "landscape": "16:9"}
        return mapping.get(self.config.ratio, "1:1")

    def _effective_model(self) -> str:
        """根据 API 类型返回实际使用的模型名"""
        if is_flow2api_style(self.config.base_url):
            return build_model_with_ratio(self.config.model, self.config.ratio)
        return self.config.model

    def call_image_api(
        self, prompt: str, ref_image_data_url: Optional[str] = None
    ) -> str:
        """调用 API 生成图片，返回图片 URL"""
        url = self._build_url()
        effective_model = self._effective_model()
        is_flow2api = is_flow2api_style(self.config.base_url)

        self.log(f"-> 请求 {effective_model}", "req")
        self.log(f"  URL: {url}", "info")
        self.log(f"  Prompt: {prompt[:200]}...", "info")
        if ref_image_data_url:
            self.log("  参考图片: 已上传", "info")

        t0 = time.time()
        timeout = TIMEOUT_SECONDS

        # 构建消息
        if ref_image_data_url:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": ref_image_data_url},
                        },
                    ],
                }
            ]
        else:
            messages = [{"role": "user", "content": prompt}]

        body = {
            "model": effective_model,
            "messages": messages,
            "stream": False,
        }
        # geeknow 风格需要 generationConfig
        if not is_flow2api:
            body["generationConfig"] = {"aspectRatio": self._aspect_ratio()}

        try:
            resp = requests.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config.api_key}",
                },
                json=body,
                timeout=timeout,
            )
        except requests.Timeout:
            cost = time.time() - t0
            msg = f"请求超时（等待了 {cost:.1f}s），请检查 API 服务或网络连接"
            self.log(f"✗ {msg}", "error")
            raise ApiError(msg)
        except requests.RequestException as e:
            cost = time.time() - t0
            msg = f"网络错误（{cost:.1f}s 后断开）：{e}"
            self.log(f"✗ {msg}", "error")
            raise ApiError(msg)

        cost = time.time() - t0
        self.log(
            f"← HTTP {resp.status_code} {resp.reason}（耗时 {cost:.1f}s）",
            "resp" if resp.ok else "error",
        )

        if not resp.ok:
            err_msg = f"HTTP {resp.status_code}"
            raw_body = resp.text
            try:
                err_data = resp.json()
                err_msg = (
                    err_data.get("error", {}).get("message")
                    or err_data.get("message")
                    or err_msg
                )
            except Exception:
                if raw_body:
                    err_msg += f" — {raw_body[:200]}"
            self.log(f"✗ 错误详情：{err_msg}", "error")
            if raw_body and len(raw_body) <= 500:
                self.log(f"  原始响应：{raw_body}", "error")
            raise ApiError(err_msg)

        try:
            data = resp.json()
        except Exception as e:
            msg = f"响应解析失败（非 JSON）：{e}"
            self.log(f"✗ {msg}", "error")
            raise ApiError(msg)

        # 提取图片 URL
        if data.get("url"):
            self.log("✓ 获取图片 URL 成功", "ok")
            return data["url"]

        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        match = re.search(r"!\[.*?\]\((https?://[^\s)]+)\)", content)
        if match:
            url = match.group(1)
            self.log("✓ 从响应 content 中提取图片 URL 成功", "ok")
            return url

        resp_str = json.dumps(data)[:400]
        self.log("✗ 响应中未找到图片 URL", "error")
        self.log(f"  响应内容：{resp_str}", "error")
        raise ApiError("响应中未找到图片 URL")


class ApiError(Exception):
    """API 错误"""
    pass


def is_recaptcha_error(msg: str) -> bool:
    """检测是否是 reCAPTCHA 相关错误"""
    return (
        "PUBLIC_ERROR_UNUSUAL_ACTIVITY" in msg
        or "reCAPTCHA" in msg
    )


def is_account_banned(msg: str) -> bool:
    """检测是否是账号被封/风控"""
    return (
        "PUBLIC_ERROR_UNUSUAL_ACTIVITY" in msg
        and "reCAPTCHA evaluation failed" in msg
    )
