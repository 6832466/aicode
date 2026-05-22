---
name: chrome-cdp
description: Chrome DevTools Protocol 连接 — Windows 上启动/连接 Chrome 调试端口、chrome://inspect 与命令行标记的区别、Playwright 直连方式
---

# Chrome CDP 连接

## 两种启用远程调试的方式

### 1. 命令行标记（传统方式）
```
chrome.exe --remote-debugging-port=9222
```
- 暴露完整 HTTP REST API：`/json/version`、`/json/list`、`/json/new`
- Playwright `connect_over_cdp("http://127.0.0.1:9222")` 可直接使用

### 2. chrome://inspect/#remote-debugging UI（Chrome 144+）
- 用户在 Chrome 设置中启用："Allow remote debugging for this browser instance"
- 页面显示 "Server running at: 127.0.0.1:9222" 和一个 **Target ID**
- **HTTP REST API 全部返回 404** — `/json/version` 和 `/json/list` 不可用
- **WebSocket 直连可用**：`ws://127.0.0.1:9222/devtools/browser/<TARGET_ID>`
- Playwright 必须用 WS URL，不能用 browser URL

## Playwright 连接（HTTP API 不可用时）

```python
from playwright.sync_api import sync_playwright

WS_URL = "ws://127.0.0.1:9222/devtools/browser/<TARGET_ID>"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(WS_URL)
    # 正常使用 browser.contexts / browser.pages
```

Target ID 从 `chrome://inspect/#remote-debugging` 页面获取。

## Windows 上启动 Chrome 的坑

### 杀进程
```powershell
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
```

### 反复 force-kill 导致用户配置损坏
多次 `taskkill /F` 会损坏 Chrome 用户数据目录，重新启动后 Chrome 卡在崩溃恢复对话框，**调试端口静默不绑定**（进程在跑但端口就是不开）。

**解决**：用临时用户数据目录：
```powershell
Start-Process -FilePath "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--user-data-dir=$env:TEMP\chrome-debug-profile"
```

### Bash 调用 PowerShell 的转义问题
Bash 会解释 PowerShell 中的 `$` 变量——不要用 `-Command` 内联多行脚本，写 `.ps1` 文件通过 `-File` 执行。

### Python 终端编码
Windows 上 Python stdout 默认 GBK，打印含 Unicode 的网页标题会报错 `UnicodeEncodeError`：
```python
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
```
