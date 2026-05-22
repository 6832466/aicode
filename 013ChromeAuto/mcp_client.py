"""MCP Streamable HTTP 客户端 — JSON-RPC 2.0 协议"""
import json
import time
import subprocess

import httpx


def _kill_bridge() -> bool:
    """杀掉 12306 端口的 node 进程，返回是否成功"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "127.0.0.1:12306" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid],
                              capture_output=True, timeout=5)
                return True
    except Exception:
        pass
    return False


def _wait_for_bridge(timeout: float = 10) -> bool:
    """等待 bridge 重新启动"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "127.0.0.1:12306" in line and "LISTENING" in line:
                    time.sleep(0.5)  # 让服务完全就绪
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _parse_sse_or_json(text: str) -> dict:
    """解析 SSE 事件流或纯 JSON 响应"""
    text = text.strip()
    # 先尝试纯 JSON
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    # 解析 SSE 格式: "event: xxx\ndata: {...}\n\n"
    data_blocks = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            data_blocks.append(line[5:].strip())
    if data_blocks:
        # 返回最后一个 data 块 (最终响应)
        for block in reversed(data_blocks):
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
    return {"error": text or "空响应"}


class McpClient:
    MAX_RETRIES = 3

    def __init__(self, url: str = "http://127.0.0.1:12306/mcp", timeout: float = 30):
        self.url = url
        self.session_id: str | None = None
        self._request_id = 0
        self.client = httpx.Client(timeout=timeout)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def initialize(self) -> dict:
        return self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "BaiduSearchTool", "version": "1.0"}
        })

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        return self._send("tools/call", {
            "name": name,
            "arguments": arguments or {}
        })

    def _send(self, method: str, params: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                resp = self.client.post(self.url, json=payload, headers=self._headers())

                # 保存 session ID
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                if sid:
                    self.session_id = sid

                # 解析响应体（可能是纯 JSON 或 SSE 格式）
                data = _parse_sse_or_json(resp.text)

                # 组合所有错误信息
                error_texts = []
                if isinstance(data.get("error"), dict):
                    error_texts.append(data["error"].get("message", ""))
                elif isinstance(data.get("error"), str):
                    error_texts.append(data["error"])
                if isinstance(data.get("message"), str):
                    error_texts.append(data["message"])
                full_error = " ".join(error_texts).lower()

                # 连接冲突 → 杀 bridge 重试
                if "already connected" in full_error or "expecting value" in full_error:
                    if attempt < self.MAX_RETRIES - 1:
                        _kill_bridge()
                        _wait_for_bridge()
                        self.session_id = None
                        continue
                    return {"error": error_texts[0] if error_texts else "连接冲突"}

                if error_texts:
                    return {"error": error_texts[0]}

                return data

            except httpx.ConnectError:
                if attempt < self.MAX_RETRIES - 1:
                    _kill_bridge()
                    _wait_for_bridge()
                    self.session_id = None
                    continue
                return {"error": "无法连接到 MCP 服务器"}

            except httpx.ReadTimeout:
                return {"error": "请求超时"}

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(1)
                    continue
                return {"error": str(e)}

        return {"error": "重试次数已用完"}

    def close(self):
        self.client.close()
