# GPT Image 2 API 调用完整指南

> 基于豹剪 API (bj.nfai.lol) 的 GPT Image 2 图片生成接口文档。
> 适用于接入团队的二次开发参考。

---

## 1. 服务概览

| 项目 | 值 |
|------|-----|
| 服务名称 | 豹剪 API (New API v0.12.12) |
| 根地址 | `https://bj.nfai.lol` |
| 图片生成 endpoint | `POST /pg/chat/completions` |
| 状态检查 endpoint | `GET /api/status` |
| 充值页面 | `https://bj.nfai.lol/console/topup` |
| 协议 | OpenAI Chat Completions 兼容 + SSE 流式 |

---

## 2. 认证

采用 **Session Cookie + 用户 ID** 方式，不需要 API Key。

### 请求头

```
Content-Type: application/json
Cookie: session=<session_cookie>
new-api-user: <user_id>
```

### 获取 Session Cookie

Session Cookie 通过浏览器登录获取。两种方式：

**方式一：手动从浏览器 DevTools 获取**
1. 打开 `https://bj.nfai.lol/` 并登录
2. F12 → Application → Cookies → 找到 `session` 字段的值

**方式二：嵌入式 WebView 自动提取（推荐）**
```python
from PySide6.QtWebEngineWidgets import QWebEngineView
# 加载 https://bj.nfai.lol/，用户登录后
# 通过 QWebEngineProfile.cookieStore() 监听 cookieAdded 信号
# 提取 name=="session" 的 cookie
```

关键代码（见 `cookie_util.py`）：
```python
cookie_store = web_view.page().profile().cookieStore()
cookie_store.cookieAdded.connect(self._on_cookie_added)

def _on_cookie_added(self, cookie):
    name = cookie.name().data().decode("utf-8")
    if name == "session":
        self._session_cookie = cookie.value().data().decode("utf-8")
```

User ID 默认值：`13679`（可通过 `localStorage.getItem('user')` 动态获取）。

### 认证失败的错误表现

- HTTP 200 但返回 HTML 登录页面（Content-Type: text/html）
- HTTP 401/403

---

## 3. 可用模型与定价

### 图片生成模型

| 模型 ID | 单价 | 说明 |
|---------|------|------|
| `gpt-image-2` | $0.042/次 | 基础版，自动分辨率 |
| `gpt-image-2-1k` | $0.042/次 | 1K 分辨率 |
| `gpt-image-2-2k` | $0.082/次 | 2K 分辨率 |
| `gpt-image-2-4k` | $0.082/次 | 4K 分辨率 |
| `gemini-2.5-flash-image` | $0.033/次 | Gemini 图片（返回 base64 嵌入） |
| `gemini-2.5-flash-image-preview` | $0.033/次 | Gemini 预览版 |
| `gemini-3.1-flash-image-preview-url` | $0.090/次 | Gemini 3.1 |
| `gemini-3-pro-image-preview-url` | $0.180/次 | Gemini 3 Pro |

### 文本对话模型

| 模型 ID | 说明 |
|---------|------|
| `gemini-2.5-pro` | Gemini 2.5 Pro，支持流式/非流式 |

> 文本模型使用同一端点 `/pg/chat/completions`，认证方式相同。详见第 7 节。

> 注意：`gpt-image-2` 不带分辨率后缀时也会自动适配。后缀模型（-1k/-2k/-4k）锁定输出分辨率。

---

## 4. 请求格式

### 基础文本生图

```json
POST /pg/chat/completions
Content-Type: application/json
Cookie: session=<cookie>
new-api-user: 13679

{
    "model": "gpt-image-2",
    "messages": [
        {"role": "user", "content": "画一只可爱的猫，纯色背景"}
    ],
    "stream": true,
    "size": "1024x1024",
    "group": "default"
}
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 模型 ID（见上方模型表） |
| `messages` | array | 是 | 标准 OpenAI messages 格式 |
| `stream` | bool | 是 | 必须为 `true`，不支持非流式 |
| `size` | string | **强烈建议** | 输出尺寸，格式 `WxH`，如 `1792x1024` |
| `group` | string | 否 | 分组标识，默认 `"default"` |

### size 参数与宽高比对照

| 比例 | size 值 | 说明 |
|------|---------|------|
| 1:1 方形 | `1024x1024` | 默认方形 |
| 16:9 横屏 | `1792x1024` | 宽屏 |
| 9:16 竖屏 | `1024x1792` | 竖屏 |
| 4:3 | `1440x1080` | 传统比例 |
| 3:4 | `1080x1440` | 竖版传统 |

> **关键发现**：不传 `size` 参数也能生成，但输出尺寸不确定。**建议始终传 size**。

---

### 带参考图（垫图）生图

参考图通过 base64 编码内嵌在 `messages` 的 `content` 数组中：

```json
{
    "model": "gpt-image-2",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/webp;base64,<base64编码>",
                        "detail": "high"
                    }
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64,<base64编码>",
                        "detail": "high"
                    }
                },
                {
                    "type": "text",
                    "text": "请参考图片中的人物外貌，创作一张16:9图片..."
                }
            ]
        }
    ],
    "stream": true,
    "size": "1792x1024",
    "group": "default"
}
```

### 垫图注意事项

1. **支持多张参考图**：在 `content` 数组中放多个 `image_url` 对象即可
2. **格式**：支持 JPEG、PNG、WebP，自动识别 MIME 类型
3. **detail**：建议设为 `"high"` 保持画质
4. **大小限制**：单张图建议 < 2MB，三张图 base64 编码后总 payload 约 2-3MB，API 可正常处理
5. **垫图顺序**：图片在前、文本在后，文本指令优先级高于图片参考

---

## 5. 响应格式

### SSE 流式响应

API 固定返回 `Content-Type: text/event-stream`：

```
data: {"choices":[{"delta":{"content":"!["},"index":0}]}

data: {"choices":[{"delta":{"content":"Generated Image"},"index":0}]}

data: {"choices":[{"delta":{"content":"](https://pro.filesystem.site/cdn/20260521/xxx.png)"},"index":0}]}

data: [DONE]
```

### 图片 URL 提取

响应内容是 Markdown 格式，图片 URL 嵌入在 `![alt](url)` 语法中：

#### GPT 模型 — 直接 URL
```
![Generated Image](https://pro.filesystem.site/cdn/download/20260521/xxxx.png)
```
提取正则：
```python
re.search(r"!\[.*?\]\((https?://\S+)\)", content)
```

#### Gemini 模型 — Base64 嵌入
```
![image](data:image/png;base64,iVBORw0KGgoAAAA...)
```
提取正则（需回溯匹配完整 base64）：
```python
re.search(r"!\[.*?\]\((data:image/\S+;base64,\S+)\)", content)
```

### 图片下载

```
GET <extracted_url>
```
返回原始图片字节。CDN 域名为 `pro.filesystem.site`，无需额外认证。

**基准测试数据**（2026-05-21）：
- `gpt-image-2` + `1024x1024` → 1672×941（约 16:9），2.2 MB
- 三张垫图生图耗时约 15-30 秒

---

## 6. 完整 Python 调用示例

```python
import requests, json, base64, re

# === 配置 ===
BASE = "https://bj.nfai.lol/pg"
ENDPOINT = "/chat/completions"
SESSION_COOKIE = "<your-session-cookie>"
USER_ID = "13679"

headers = {
    "Content-Type": "application/json",
    "Cookie": f"session={SESSION_COOKIE}",
    "new-api-user": USER_ID,
}

# === 编码参考图 ===
def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    ext = path.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
    b64 = base64.b64encode(data).decode()
    return f"data:image/{mime};base64,{b64}"

# === 构建请求 ===
payload = {
    "model": "gpt-image-2",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": encode_image("ref1.jpg"), "detail": "high"}},
            {"type": "image_url", "image_url": {"url": encode_image("ref2.jpg"), "detail": "high"}},
            {"type": "text", "text": "请参考人物特征，生成16:9图片，背景为都市街景"},
        ]
    }],
    "stream": True,
    "size": "1792x1024",
    "group": "default",
}

# === 发送请求 ===
resp = requests.post(
    f"{BASE}{ENDPOINT}",
    headers=headers,
    json=payload,
    timeout=300,
    stream=True,
)

# === 解析 SSE 流 ===
content_parts = []
for line in resp.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    data_str = line[6:].strip()
    if data_str == "[DONE]":
        break
    try:
        data = json.loads(data_str)
        if "error" in data:
            raise RuntimeError(data["error"])
        for c in data.get("choices", []):
            delta = c.get("delta", {})
            if delta.get("content"):
                content_parts.append(delta["content"])
    except json.JSONDecodeError:
        continue

full_content = "".join(content_parts)

# === 提取图片 URL ===
match = re.search(r"!\[.*?\]\((https?://\S+)\)", full_content)
if match:
    image_url = match.group(1)
    img_data = requests.get(image_url, timeout=60).content
    with open("output.png", "wb") as f:
        f.write(img_data)
    print(f"Saved: {len(img_data)} bytes")
else:
    print(f"No image URL in: {full_content[:500]}")
```

---

## 7. 文本对话（Chat）支持

该 API 不仅支持图片生成，也可以用于常规文本对话。可用的文本模型包括：

| 模型 ID | 说明 |
|---------|------|
| `gemini-2.5-pro` | Gemini 2.5 Pro，支持流式/非流式 |

### 文本对话 — 非流式（推荐）

```json
POST /pg/chat/completions
Content-Type: application/json
Cookie: session=<cookie>
new-api-user: 13679

{
    "model": "gemini-2.5-pro",
    "messages": [
        {"role": "user", "content": "用中文简要解释什么是量子纠缠"}
    ],
    "stream": false
}
```

响应格式为标准的 OpenAI Chat Completions JSON：

```json
{
    "id": "chatcmpl-xxx",
    "model": "gemini-2.5-pro",
    "object": "chat.completion",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": "我是一个由谷歌训练的大型语言模型。"
        },
        "finish_reason": "stop"
    }],
    "usage": {
        "prompt_tokens": 9,
        "completion_tokens": 10,
        "total_tokens": 19
    }
}
```

**特点**：中文直接正常显示，无需额外处理。

### 文本对话 — 流式

流式模式与图片生成共用同一 SSE 机制，但有一个重要差异：

**中文双重编码问题**：流式模式下，服务端将 UTF-8 中文先编码为 Latin-1 再放入 JSON 字符串，导致客户端直接读取时显示乱码。

**修复方法**：

```python
# 取出 content 后做反向解码
content = content.encode('latin-1').decode('utf-8')
```

完整的流式文本请求示例：

```python
import requests, json

headers = {
    "Content-Type": "application/json",
    "Cookie": f"session={SESSION_COOKIE}",
    "new-api-user": "13679",
}

payload = {
    "model": "gemini-2.5-pro",
    "messages": [{"role": "user", "content": "说一个冷笑话"}],
    "stream": True,
}

resp = requests.post(
    "https://bj.nfai.lol/pg/chat/completions",
    headers=headers,
    json=payload,
    timeout=120,
    stream=True,
)

content_parts = []
for line in resp.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    data_str = line[6:].strip()
    if data_str == "[DONE]":
        break
    try:
        data = json.loads(data_str)
        for c in data.get("choices", []):
            content = c.get("delta", {}).get("content", "")
            if content:
                # 修复中文双重编码
                try:
                    content = content.encode('latin-1').decode('utf-8')
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass  # ASCII 内容无需修复
                content_parts.append(content)
    except json.JSONDecodeError:
        continue

full_text = "".join(content_parts)
print(full_text)
```

> **建议**：文本对话场景优先使用非流式（`stream: false`），响应简洁且无编码问题。仅在需要实时逐字输出时使用流式。

---

## 8. 中间遇到的问题 & 解决方案

### 8.1 HTTP API 不可用（Chrome 144+）

**现象**：`chrome://inspect/#remote-debugging` 开启后，`GET /json/version` 返回 404。

**原因**：Chrome 144+ 的 chrome://inspect 模式禁用了 HTTP REST API。

**解决**：读取 `%LOCALAPPDATA%\Google\Chrome\User Data\DevToolsActivePort` 文件获取 WebSocket URL：
```
9222
/devtools/browser/<TARGET_ID>
```
使用 `ws://127.0.0.1:9222/devtools/browser/<TARGET_ID>` 直连。

### 8.2 Gemini 返回 base64 嵌入而非 URL

**现象**：`gemini-2.5-flash-image` 模型返回 `![image](data:image/png;base64,...)` 而非 HTTP URL。

**解决**：扩展提取正则同时覆盖两种格式：
```python
# GPT 格式: https://...
re.search(r"!\[.*?\]\((https?://\S+)\)", content)
# Gemini 格式: data:image/...;base64,...
re.search(r"!\[.*?\]\((data:image/\S+;base64,\S+)\)", content)
```

### 8.3 base64 正则的回溯问题

**现象**：`data:image/png;base64,<大量字符>)` 的正则匹配可能失败。

**原因**：base64 字符串包含 `+`、`/`、`=`，都属于 `\S`。使用贪婪 `\S+` 后接 `\)`，依赖正则引擎回溯。

**解决**：上述正则已正确处理。测试中 1.5MB base64 字符串匹配正常。

### 8.4 垫图 payload 过大

**现象**：三张参考图（~500KB 每张）base64 编码后 payload ~2.2MB。

**解决**：API 接受此大小，无需压缩。如需优化，可先压缩图片到 < 300KB。

### 8.5 Chrome 反复被杀死

**现象**：程序检测到端口未开就 `taskkill /f /im chrome.exe`，导致浏览器数据损坏。

**解决**：先 TCP 检测端口是否已监听；已监听则只做 WebSocket 连接（不杀进程）；未监听且 Chrome 不在运行时才启动 Chrome。

### 8.6 Session 过期

**现象**：关闭所有 Gemini 标签页后，新标签页变成未登录。

**解决**：不关闭用户标签页，通过 `page.goto("/app")` 重用现有页面开启新对话。

### 8.7 流式文本对话中文乱码

**现象**：`gemini-2.5-pro` 流式模式下，`choices[].delta.content` 取出的中文显示为乱码（如 `éå­çº ç¼`）。

**原因**：服务端将 UTF-8 中文先编码为 Latin-1 再嵌入 JSON 字符串，相当于双重编码。非流式模式无此问题。

**解决**：取出 content 后做反向解码：
```python
content = content.encode('latin-1').decode('utf-8')
```
ASCII 内容（英文、数字、URL）不受影响，`try/except` 包裹即可。非流式模式直接返回正确中文，无需此处理。

---

## 9. 接口配置汇总

### 环境变量 / 配置项

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `api_base_url` | `http://localhost:8000` | API 基础 URL |
| `api_key` | `""` | Bearer Token（本服务不用） |
| `api_session_cookie` | `""` | Session Cookie |
| `api_user_id` | `"13679"` | 用户 ID |
| `model_name` | `"gemini-3.1-flash-image"` | 默认模型 |
| `api_endpoint_path` | `"/v1/chat/completions"` | API 路径 |
| `remote_preset` | `"bj.nfai.lol"` | 预设标识 |

### 预设配置

```python
API_PRESETS = {
    "bj.nfai.lol": {
        "name": "豹剪 API (bj.nfai.lol)",
        "url": "https://bj.nfai.lol/pg",
        "key": "",
        "model": "gemini-2.5-flash-image",
        "path": "/chat/completions",
        "user_id": "13679",
        "group": "default",
    },
}
```

### 可用端点

| 端点 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/pg/chat/completions` | POST | Cookie | 图片生成 / 文本对话（SSE） |
| `/api/status` | GET | Cookie | 服务器状态 |
| `/console/topup` | GET | Cookie | 充值页面 |

---

## 10. 远程 API 设置窗口 UI 设计

本节记录 `SettingsDialog` 的完整 UI 设计，方便新项目直接复刻。

### 10.1 窗口概览

| 属性 | 值 |
|------|-----|
| 窗口标题 | `API 连接设置` |
| 最小尺寸 | 560×780 |
| 模态 | `True` |
| 框架 | PySide6 + qfluentwidgets |

### 10.2 布局结构（从上到下）

```
┌──────────────────────────────────────────┐
│ OpenAI 兼容协议配置             (header)  │
│ 本地模式通过 Chrome CDP...     (hint)     │
├──────────────────────────────────────────┤
│ API 模式                                  │
│ ○ 本地 Chrome (CDP 直连 Gemini)           │
│ ● 远程 API (OpenAI 兼容)                  │
├──────────────────────────────────────────┤
│ [仅本地模式显示]                          │
│ Chrome 浏览器路径  [__________] [浏览]    │
├──────────────────────────────────────────┤
│ [仅远程模式显示]                          │
│ API 预设  [豹剪 API (bj.nfai.lol)  ▾]    │
│ API Base URL          [_______________]   │
│ API Endpoint Path     [_______________]   │
│ API Key               [_______________]👁 │
│ Session Cookie (会话认证)                 │
│                       [_______________]👁 │
│                       [获取]              │
│ ↳ 提示：点击按钮→登录→自动填充            │
│ User ID (new-api-user)[_______________]   │
│ 默认模型  [gemini-2.5-flash-image ▾][充值]│
├──────────────────────────────────────────┤
│         [测试连接]  状态文字  [取消][保存]│
└──────────────────────────────────────────┘
```

### 10.3 字段详细说明

#### API 模式切换（RadioButton 组）

| 模式 | RadioButton 文本 | 触发行为 |
|------|-----------------|---------|
| 本地 | `本地 Chrome (CDP 直连 Gemini)` | 隐藏远程字段，显示 Chrome 路径字段 |
| 远程 | `远程 API (OpenAI 兼容)` | 显示所有远程字段，隐藏 Chrome 路径 |

模式切换时自动应用预设默认值，并恢复已保存的模型和认证信息。

#### API 预设（ComboBox）

| 预设 key | 显示名称 | Base URL | Path |
|----------|---------|----------|------|
| `bj.nfai.lol` | 豹剪 API (bj.nfai.lol) | `https://bj.nfai.lol/pg` | `/chat/completions` |
| `custom` | 自定义 | (空) | `/chat/completions` |

选择预设时自动填充 URL、Path、User ID、默认模型；切换预设会重新填充模型下拉列表。

#### API Base URL（LineEdit）

- placeholder: `http://localhost:8000`
- 对应配置键: `api_base_url`

#### API Endpoint Path（LineEdit）

- placeholder: `/v1/chat/completions`
- 对应配置键: `api_endpoint_path`
- 保存时空值自动回退为 `/v1/chat/completions`

#### API Key（LineEdit + ToolButton）

- 密码模式（默认隐藏），右侧眼睛按钮切换可见性
- placeholder: `输入 API Key`
- 对应配置键: `api_key`
- 本服务（bj.nfai.lol）不使用此字段，留空即可

#### Session Cookie（LineEdit + ToolButton + PushButton）

- 密码模式（默认隐藏），右侧眼睛按钮切换可见性
- placeholder: `从浏览器中获取 session cookie 值`
- **获取按钮**：弹出 `CookieLoginDialog`（内嵌 WebView 加载 `bj.nfai.lol`），用户登录后自动提取 session cookie 和 user ID 并填入
- 对应配置键: `api_session_cookie`

#### User ID（LineEdit）

- placeholder: `13679`
- 对应配置键: `api_user_id`
- 与 Session Cookie 配对使用，作为 `new-api-user` 请求头

#### 默认模型（Editable ComboBox + PushButton）

- 可编辑、可下拉选择
- placeholder: `输入模型名或从下拉列表选择`
- 下拉列表项（显示名 + 模型 ID）：

| 显示名 | 模型 ID |
|--------|---------|
| `gemini-2.5-flash-image — $0.033/次` | `gemini-2.5-flash-image` |
| `gemini-2.5-flash-image-preview — $0.033/次` | `gemini-2.5-flash-image-preview` |
| `gpt-image-2 — $0.042/次` | `gpt-image-2` |
| `gpt-image-2-1k — $0.042/次` | `gpt-image-2-1k` |
| `gpt-image-2-2k — $0.082/次` | `gpt-image-2-2k` |
| `gpt-image-2-4k — $0.082/次` | `gpt-image-2-4k` |
| `gemini-3.1-flash-image-preview-url — $0.090/次` | `gemini-3.1-flash-image-preview-url` |
| `gemini-3-pro-image-preview-url — $0.180/次` | `gemini-3-pro-image-preview-url` |
| `gemini-3-pro-image-preview — $0.190/次` | `gemini-3-pro-image-preview` |

- **充值按钮**：打开系统浏览器跳转 `https://bj.nfai.lol/console/topup`
- 对应配置键: `model_name`

#### 本地模式专属字段

| 字段 | 控件 | 说明 |
|------|------|------|
| Chrome 浏览器路径 | LineEdit + PushButton("浏览") | 对应配置键 `chrome_exe_path`，留空自动检测 |
| 提示文字 | QLabel | "留空则自动检测 Chrome 安装位置" |

### 10.4 操作按钮

| 按钮 | 类型 | 行为 |
|------|------|------|
| **测试连接** | PushButton (FluentIcon.WIFI) | 异步后台线程检测连通性，更新状态文字（成功绿色 / 失败红色） |
| **取消** | PushButton | `reject()` 关闭窗口，不保存 |
| **保存** | PrimaryPushButton | 写入所有配置到 QConfig，`accept()` 关闭窗口 |

#### 测试连接逻辑

- **本地模式**：实例化 `GeminiCDPClient`，调用 `check_connection()` 通过 DevToolsActivePort 直连 Chrome
- **远程模式**：实例化 `Flow2ApiClient`，调用 `check_connection()` 访问 `/api/status` 端点（session 认证）或 `/models` 端点（Bearer 认证）
- 测试在 `QThread` 子线程中执行，不阻塞 UI
- 按钮在测试期间禁用，完成后恢复

### 10.5 配置持久化

所有字段通过 `qfluentwidgets.QConfig` 持久化到本地配置文件。

| 配置键 | 类型 | 默认值 | UI 控件 |
|--------|------|--------|---------|
| `api_base_url` | ConfigItem | `""` | url_edit |
| `api_key` | ConfigItem | `""` | key_edit |
| `api_endpoint_path` | ConfigItem | `"/v1/chat/completions"` | path_edit |
| `api_session_cookie` | ConfigItem | `""` | cookie_edit |
| `api_user_id` | ConfigItem | `"13679"` | uid_edit |
| `model_name` | ConfigItem | `"gemini-3.1-flash-image"` | model_combo |
| `use_local_server` | ConfigItem | `True` | local_radio/remote_radio |
| `remote_preset` | ConfigItem | `"bj.nfai.lol"` | preset_combo |
| `chrome_exe_path` | ConfigItem | `""` | chrome_path_edit |
| `chrome_debug_port` | ConfigItem | `9222` | (无 UI，固定值) |
| `chrome_debug_host` | ConfigItem | `"127.0.0.1"` | (无 UI，固定值) |

### 10.6 认证方式自动识别

保存设置后，`_connect_client()` 方法根据配置自动选择认证策略：

```python
if session_cookie:
    # 使用 Session Cookie + User ID 认证
    headers = {
        "Cookie": f"session={session_cookie}",
        "new-api-user": user_id,
    }
elif api_key:
    # 使用 Bearer Token 认证
    headers = {"Authorization": f"Bearer {api_key}"}
else:
    # 无认证 → 提示用户配置
```

### 10.7 Cookie 获取子窗口

`CookieLoginDialog` 是一个独立的模态对话框：

- 内嵌 `QWebEngineView` 加载 `https://bj.nfai.lol/`
- 监听 `QWebEngineProfile.cookieStore().cookieAdded` 信号
- 提取 `name == "session"` 的 cookie 值
- 通过 JavaScript `localStorage.getItem('user')` 获取 user ID
- 用户接受后自动填入父窗口的 Cookie 和 User ID 字段
- 组件代码：[cookie_util.py](../cookie_util.py)
