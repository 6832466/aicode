"""乐乐角色卡生成器 - PySide6 Fluent Design Edition"""
import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

# Ensure package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from card_generator.main_window import MainWindow
from card_generator.style import GLOBAL_QSS


def main():
    # 高 DPI 支持
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_QSS)

    # 设置默认字体
    font = QFont("Segoe UI", 13)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
