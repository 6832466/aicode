# -*- coding: utf-8 -*-
"""视频分镜脚本分析器 - 入口 (Fluent Design)"""
import sys
import os
import warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from qfluentwidgets import setTheme, Theme, setThemeColor

from ui.main_window import MainWindow

if getattr(sys, 'frozen', False):
    ICON_PATH = os.path.join(sys._MEIPASS, "1.ico")
else:
    ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "1.ico")


def main():
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("视频分镜脚本分析器")

        if os.path.exists(ICON_PATH):
            app.setWindowIcon(QIcon(ICON_PATH))

        font = QFont("Microsoft YaHei", 10)
        app.setFont(font)

        setTheme(Theme.LIGHT)
        setThemeColor("#0078d4")

        window = MainWindow()
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[FATAL] 应用启动失败: {e}\n{tb}", file=sys.stderr)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "启动失败", f"应用程序启动失败:\n\n{e}\n\n详情:\n{tb[:500]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
