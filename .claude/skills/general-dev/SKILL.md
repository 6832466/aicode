---
name: general-dev
description: 通用开发经验 — 架构设计、异常处理、日志、编码兼容、任务队列等最佳实践。在每次开始写代码时自动参考。
---

# 通用开发经验

## 项目约定（每次必查）

- **微信**：rpalele（窗口标题和注册信息中嵌入）
- **图标**：所有窗口 + EXE 统一使用项目根目录的 `1.ico`
- **软件标题**：所有窗口标题必须以「乐乐」开头（如 `乐乐BatchImageGen`）

## 开发流程

**开发前 — 先搜索开源方案**
- 有现成库就不要自己造轮子：pip / npm / GitHub 搜一圈再动手
- 重点关注：维护活跃度、最近更新时间、issue 数量、API 是否简洁

**开发中 — 遇到难题联网搜索**
- 报错信息直接搜、框架用法查文档、复杂逻辑搜技术方案
- 别硬猜，特别是 API 参数、框架限制、平台差异这类

**开发完 — 自己先测试**
- 正常流程走一遍、边界情况试一下、错误场景模拟一下
- 确认功能可用再交付，不把明显 bug 留给用户

## 架构设计

**共享工具集中管理，避免循环导入**
- 所有模块共用的常量、路径函数、配置键统一放 `config.py`
- 各模块从 config 导入，不要模块间相互 import

**数据路径隔离，支持多实例**
- 按业务维度分目录存储文件和配置
- 读写路径分离：读可回退到旧路径（向后兼容），写始终用新路径

## 异常处理

**API 调用分层处理可重试错误**
- 临时性错误（限流 429、服务器忙 502/503/504）→ 自动重试，不直接标失败
- 即使响应码是 200，也要检查响应体中的错误关键词
- 网络异常也是临时的，应该重试

**长时间运行的循环需要防死循环**
- 轮询外部状态的任务要有失败计数器，连续失败 N 次后主动放弃
- 队列 + 活跃任务都为空时立即退出，不要 idle sleep

## 日志

**DEBUG 级别会吸入所有第三方库的噪音**
- `root.setLevel(logging.DEBUG)` 会把 asyncio、aiohttp、urllib3 的底层 I/O 事件全吸进来
- 必须单独抑制第三方库：`logging.getLogger("asyncio").setLevel(logging.WARNING)` 等
- 应用代码用 `logger = logging.getLogger(__name__)`，通过 handler 级别控制

## Windows 文件路径

**路径长度限制**
- 总路径长度可能超出 MAX_PATH (260 字符)，文件名截断要留余量
- PowerShell `Compress-Archive` 遇到长路径会失败，用 Python `zipfile` 替代

**编码兼容**
- Python 默认 GBK 读 Windows 文件会乱码，`read_text()` / `write_text()` 始终显式传 `encoding="utf-8"`
- CSV 导出给 Excel 用 `utf-8-sig`（带 BOM），否则 Excel 打开中文乱码
- JSON 用 `utf-8`，`ensure_ascii=False` 保留中文可读

## Shell 环境差异

- PowerShell 5.1 默认 UTF-16 LE，管道编码可能不一致，输出文件时用 `-Encoding utf8`
- Bash on Windows（Git Bash）通常是 UTF-8
- Python `subprocess` 捕获输出时指定 `text=True` 会自动用系统编码

**API 通信**
- HTTP 请求/响应体通常是 UTF-8，`aiohttp` 默认处理
- 日志输出中文时确认终端/控件编码支持，Qt 控件天然支持 Unicode

## Windows 桌面应用

**PyInstaller COLLECT 模式路径陷阱**
- frozen 后数据文件在 `_internal/` 子目录，不是 exe 同级
- `app_root()` 返回 `Path(sys.executable).parent`，读写文件用这个
- 资源文件（如图标）要同时检查 `_internal/` 回退路径

**文件路径兼容**
- 中文路径在 Windows NTFS 上没问题（UTF-16），Python 的 `pathlib` 和 `open()` 都支持

**Qt 图标设置**
- 所有窗口统一从一个加载函数获取图标，不要每个窗口自己拼路径
- EXE 嵌入式图标（任务栏显示）由 PyInstaller spec 的 `icon=` 控制
- 窗口标题栏图标由 `setWindowIcon()` 控制，两者独立

## 任务队列

**状态机要完整覆盖所有分支**
- 每个状态明确：进入条件 → 可转移到哪些状态 → 退出动作
- 未识别的状态会被静默跳过，导致任务卡住，应当有兜底处理
- `finally` 块中的清理要区分"正常完成"和"被停止"，用标志位区分

**暂停/继续/停止的联动**
- 停止要同时清空队列、取消异步任务、重置标志位
- 停止后不应触发"全部完成"回调
- 新任务开始时要重置所有状态标志
