"""乐乐动漫助手 —— 主入口。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
APP_ICON = PROJECT_ROOT / "1.ico"

sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon

from qfluentwidgets import (
    FluentWindow, TitleLabel, BodyLabel,
    PrimaryPushButton,
    setTheme, Theme, FluentIcon,
    NavigationItemPosition,
)

from settings_page import SettingsPage
from image_gen_page import ImageGenPage
from log_page import LogPage


class HomePage(QWidget):
    """首页内容。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("homePage")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        logo = TitleLabel("乐乐动漫助手")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        subtitle = BodyLabel("AI 驱动的动漫内容创作工具")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(24)

        row = QHBoxLayout()
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn = PrimaryPushButton(FluentIcon.PLAY, "开始创作")
        btn.setFixedWidth(160)
        row.addWidget(btn)
        layout.addLayout(row)


class MainWindow(FluentWindow):
    """主窗口 —— 侧边栏导航。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("乐乐动漫助手")
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1264, 855)

        self._home_page = HomePage()
        self._image_gen_page = ImageGenPage()
        self._log_page = LogPage()
        self._settings_page = SettingsPage()

        self.addSubInterface(
            self._home_page, FluentIcon.HOME, "首页",
            position=NavigationItemPosition.SCROLL,
        )
        self.addSubInterface(
            self._image_gen_page, FluentIcon.PHOTO, "图片生成",
            position=NavigationItemPosition.SCROLL,
        )
        self.addSubInterface(
            self._log_page, FluentIcon.DOCUMENT, "运行日志",
            position=NavigationItemPosition.SCROLL,
        )
        self.addSubInterface(
            self._settings_page, FluentIcon.SETTING, "设置",
            position=NavigationItemPosition.BOTTOM,
        )


def main() -> None:
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    app.setWindowIcon(QIcon(str(APP_ICON)))
    app.setFont(QFont("Microsoft YaHei", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
