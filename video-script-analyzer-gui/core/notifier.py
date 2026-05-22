# -*- coding: utf-8 -*-
"""钉钉机器人通知

安全提醒：ACCESS_TOKEN 和 SECRET 硬编码在代码中。
生产环境应从环境变量或配置文件读取，避免泄露到版本控制。
"""
import time
import hmac
import hashlib
import base64
import urllib.request
import json
import sys
import traceback
import threading

ACCESS_TOKEN = "12f8430963b934a675e665576c9e8d60867818ac97afe989b8aa268b73bf4b5e"  # noqa: E501
SECRET = "SEC947b7ef333cf85f4ced29f1677486bd2fd681675b7f22139822059b94e18b5ba"  # noqa: E501

TIMEOUT_KEYWORDS = ["超时", "timeout", "Timeout", "TIMEOUT"]
SKIP_KEYWORDS = ["重试", "连接失败"]


def _should_skip(msg):
    try:
        return any(kw in msg for kw in TIMEOUT_KEYWORDS) or any(kw in msg for kw in SKIP_KEYWORDS)
    except Exception:
        return False


def send_error_notification(message):
    """Send error notification to DingTalk robot (skips timeout errors)."""
    try:
        if _should_skip(message):
            return
    except Exception as e:
        print(f"[WARN] 通知过滤检查异常: {e}", file=sys.stderr)
        return

    def _send():
        try:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = timestamp + "\n" + SECRET
            sign = base64.b64encode(
                hmac.new(SECRET.encode(), string_to_sign.encode(), hashlib.sha256).digest()
            ).decode()
            sign_encoded = urllib.request.quote(sign)

            url = (
                f"https://oapi.dingtalk.com/robot/send"
                f"?access_token={ACCESS_TOKEN}&timestamp={timestamp}&sign={sign_encoded}"
            )

            body = json.dumps({
                "msgtype": "text",
                "text": {
                    "content": "【乐乐视频分镜脚本提取】\n\n异常信息：" + message[:800]
                }
            }).encode()

            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.URLError as e:
            print(f"[WARN] 钉钉通知发送失败(网络): {e}", file=sys.stderr)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[ERROR] 钉钉通知发送异常: {e}\n{tb[:300]}", file=sys.stderr)

    try:
        t = threading.Thread(target=_send, daemon=True)
        t.start()
    except Exception as e:
        print(f"[ERROR] 钉钉通知线程启动失败: {e}", file=sys.stderr)
