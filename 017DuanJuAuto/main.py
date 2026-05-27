"""短剧素材采集工具 —— 入口。"""
import sys
import os
from pathlib import Path

if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys._MEIPASS)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(sys.executable).parent / "ms-playwright")
else:
    PROJECT_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon

from qfluentwidgets import setTheme, Theme, FluentTranslator

from core.config import app_config
from ui.main_window import MainWindow

APP_ICON = PROJECT_ROOT / "1.ico"


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("短剧素材采集工具")
    if APP_ICON.exists():
        app.setWindowIcon(QIcon(str(APP_ICON)))

    translator = FluentTranslator()
    app.installTranslator(translator)
    app._translator = translator

    setTheme(Theme.AUTO)
    app.setFont(QFont("Microsoft YaHei", 10))

    app_config.load(file=PROJECT_ROOT / "config" / "config.json")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
