from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import APP_NAME, app_icon_path
from ui.main_window import MainWindow


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # 抑制第三方库的 DEBUG 噪音
    for lib in ("asyncio", "aiohttp", "urllib3", "requests"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def main():
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    # 图标
    icon_path = app_icon_path()
    app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
