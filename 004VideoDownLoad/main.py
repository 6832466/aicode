"""乐乐短视频下载器 - 入口文件
基于 videodl 库，支持抖音、快手平台的视频下载。
"""
import sys
import os

# 将当前目录和 eaglepy310 加入 Python 路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)
sys.path.insert(0, os.path.join(CURRENT_DIR, '..', 'eaglepy310', 'Lib', 'site-packages'))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme

from app.main_window import MainWindow
from app.utils.logger import setup_logging, get_logger


def resource_path(relative_path):
    """获取资源文件路径，兼容 PyInstaller 打包"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def main():
    # 初始化日志
    log = setup_logging()

    # 高DPI支持（Qt6 默认启用，显式设置消除警告）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName('乐乐短视频下载器')
    app.setOrganizationName('VideoDownloader')
    app.setApplicationVersion('1.0.0')

    # 设置应用图标
    icon_path = resource_path('1.ico')
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
        # 让所有子窗口默认继承此图标
        QApplication.setWindowIcon(app_icon)

    # 全局样式
    app.setStyleSheet("""
        QWidget {
            font-family: 'Microsoft YaHei', 'Segoe UI', 'PingFang SC', sans-serif;
        }
    """)

    window = MainWindow()
    window.setWindowIcon(QIcon(icon_path) if os.path.exists(icon_path) else QIcon())
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
