"""乐乐剧集下载器 - 入口"""
import sys
import logging
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme, setThemeColor

from gui.ui.main_window import MainWindow

logger = logging.getLogger("hongguo")


def main():
    try:
        # 高 DPI 支持 (Qt6 默认启用)
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("乐乐剧集下载器")
        app.setOrganizationName("HongGuo")

        # 图标
        icon_path = PROJECT_ROOT / "1.ico"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

        # 主题
        setTheme(Theme.LIGHT)
        setThemeColor("#0078D4")

        window = MainWindow()
        window.show()

        sys.exit(app.exec())
    except Exception:
        logger.exception("应用程序崩溃")
        raise


if __name__ == "__main__":
    main()
