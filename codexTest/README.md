# Gold Monitor

PySide6 + Fluent 风格的桌面黄金行情悬浮窗。

## 功能

- 同时轮询沪金 AU 与国际金 XAUUSD。
- 无边框、置顶、透明、可拖拽，窗口位置写入 `config.json`。
- 托盘常驻，右键打开设置或退出。
- 支持 AU / 国际金上破、下破阈值提醒。
- 支持指定时间窗口内异动监测，触发后卡片红/绿闪烁。
- 支持本地配置持久化和可选 SMTP 邮件提醒。
- 内置 7 套高级质感皮肤，可在托盘右键菜单中切换。

## 运行

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

脚本会安装依赖、用 PyInstaller 生成 `dist\GoldMonitor.exe`，并复制到当前用户桌面。

如果系统没有可用 Python，先安装 Python 3.10+。
