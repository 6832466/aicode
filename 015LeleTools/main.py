"""
智能工具箱 — 入口
"""

import sys
from pathlib import Path

# 确保项目根目录优先于其他路径，避免被 eaglepy310 下的空 app 目录遮蔽
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme

from app.constants import app_icon_path
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    setTheme(Theme.LIGHT)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
