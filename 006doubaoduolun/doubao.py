import sys
import os
import logging

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme

from main_window import MainWindow


def main():
    # high-DPI support
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("乐乐豆包多轮对话自动化工具")
    app.setOrganizationName("DoubaoAuto")

    icon_path = os.path.join(os.path.dirname(__file__), "1.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    setTheme(Theme.AUTO)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
