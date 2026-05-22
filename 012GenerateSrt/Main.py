"""
乐乐音视频转字幕工具 — 入口
"""

import sys
import asyncio
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme
from qasync import QEventLoop

from app.config import WINDOW_TITLE, app_icon_path
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(app_icon_path())))

    # qasync 事件循环 — 让 asyncio 协程在 Qt 中运行
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # 浅色主题
    setTheme(Theme.LIGHT)

    window = MainWindow()
    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()