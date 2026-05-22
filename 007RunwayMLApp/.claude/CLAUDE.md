# RunwayML Batch Generator

通用开发经验继承自父级 `.claude/CLAUDE.md`，本文件仅补充项目特有信息。

## 项目专属约定

- **微信**：rpalele（窗口标题: "乐乐RunwayML批量生视频工具    微信：rpalele"）
- **图标**：项目根 `1.ico`，通过 `app.config.app_icon_path()` 获取
- **默认团队 ID**：空字符串 `""`
- **多账户**：按 team_id 隔离数据目录和 QSettings
- **UI 语言**：全中文
- **编码**：所有文件读写显式 `encoding="utf-8"`

## 关键文件

```
app/config.py          - 全局常量、路径工具
app/models.py          - 数据类 (PromptItem, CharacterAsset, BatchLogEntry)
app/runway_client.py   - RunwayML API (生成/轮询/下载/引用)
app/queue_manager.py   - 任务队列调度核心
app/download_manager.py - 视频下载 (进度信号, 文件命名 max_len=50)
app/excel_parser.py    - Excel 导入 (人物对照表 + 提示词)
app/log_manager.py     - batch_log.json 读写
app/license.py         - 硬件绑定许可证
ui/main_window.py      - FluentWindow 主窗口
ui/pages/settings_page.py - 设置页 (JWT/团队/分辨率/前缀后缀)
ui/pages/history_page.py  - 历史记录 (重新加载/导出 CSV)
ui/widgets/log_widget.py  - 实时日志控件
```

## 常见问题速查

| 现象 | 根因 | 修复位置 |
|------|------|----------|
| 窗口/任务栏无图标 | frozen 下 `_internal/` 路径未匹配 | `config.py:app_icon_path()` |
| 任务完成不停止 | idle sleep 60-90s / 轮询异常死循环 | `queue_manager.py` break + 失败计数器 |
| 日志被 DEBUG 刷屏 | root logger 吸入 asyncio I/O 事件 | `log_widget.py` 抑制第三方 logger |
| 历史记录为空 | LogManager 从未被调用 | `main_window.py` 接信号写日志 |
| heavy load 直接失败 | 502/503 未按可重试处理 | `runway_client.py` + `queue_manager.py` |
| 循环导入 | 模块间相互 import | 共享函数统一放 `app/config.py` |
