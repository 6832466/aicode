@echo off
echo === 启动 Chrome 远程调试模式 ===
echo.
echo 正在关闭所有 Chrome 进程...
taskkill /F /IM chrome.exe 2>nul
timeout /t 2 /nobreak >nul

echo 正在启动 Chrome（远程调试端口: 9222）...
echo 请在打开的 Chrome 中登录 RunwayML，然后运行: node runway-batch.js
echo.

set CHROME_PATHS=^
"C:\Program Files\Google\Chrome\Application\chrome.exe"^
"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"^
"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

for %%p in (%CHROME_PATHS%) do (
    if exist %%p (
        start "" %%p --remote-debugging-port=9222 --no-first-run --no-default-browser-check https://app.runwayml.com/video-tools/teams/LeleRpa/ai-tools/generate?tool=video^&mode=tools
        goto :done
    )
)

echo 未找到 Chrome 安装路径，请手动启动 Chrome 并添加参数: --remote-debugging-port=9222
:done
echo.
pause
