#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
即梦AI视频批量生成管理工具
"""

import sys
from pathlib import Path

# 确保项目根目录在模块搜索路径中
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from config.settings_manager import get_config
from core.task_manager import TaskManager
from core.material_matcher import MaterialMatcher
from core.dreamina_cli import DreaminaCLI
from core.download_manager import DownloadManager
from ui.main_window import MainWindow
from utils.logger import setup_logging, get_logger
from utils.theme import apply_dark_theme


def main():
    """应用入口"""
    # 日志初始化
    setup_logging()
    logger = get_logger("main")
    logger.info("启动 即梦AI视频批量生成管理工具")

    # 高DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("即梦AI视频批量生成")
    app.setOrganizationName("JiMengAuto")

    # 应用深色主题
    apply_dark_theme(app)

    # 全局字体
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)

    # 加载配置
    config = get_config()

    # 初始化核心管理器
    material_matcher = MaterialMatcher()
    task_manager = TaskManager()
    dreamina_cli = DreaminaCLI()
    download_manager = DownloadManager(
        save_dir=config.save_dir.value,
        max_concurrent=config.max_concurrent.value,
        resume_enabled=config.resume_enabled.value,
    )

    # 创建主窗口
    window = MainWindow(
        task_manager=task_manager,
        download_manager=download_manager,
        material_matcher=material_matcher,
        dreamina_cli=dreamina_cli,
    )
    window.show()

    # 启动时检测 CLI
    if config.auto_check_cli.value:
        ok = dreamina_cli.check_available()
        if not ok:
            logger.warning("dreamina CLI 未安装, 请运行: curl -fsSL https://jimeng.jianying.com/cli | bash")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
