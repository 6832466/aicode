"""SystemTray - tray icon, context menu, bubble notifications."""
from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from _icon import get_icon_bytes
from . import styles


def _create_tray_icon() -> QIcon:
    pixmap = QPixmap()
    pixmap.loadFromData(get_icon_bytes())
    return QIcon(pixmap)


class SystemTray(QSystemTrayIcon):
    settings_requested = Signal()
    show_hide_requested = Signal()
    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIcon(_create_tray_icon())
        self.setToolTip("Gold Monitor")
        self._rebuild_menu()
        self.show()

    def _rebuild_menu(self) -> None:
        menu = QMenu()

        menu.addAction("显示/隐藏").triggered.connect(self.show_hide_requested.emit)
        menu.addSeparator()

        # Themes as direct actions (no submenu — Windows tray doesn't support nested menus)
        current = styles.CURRENT
        for name in styles.get_theme_names():
            prefix = "● " if name == current else "◦ "
            action = menu.addAction(f"{prefix}{name}")
            action.triggered.connect(lambda checked, n=name: self.theme_changed.emit(n))

        menu.addSeparator()

        menu.addAction("设置").triggered.connect(self.settings_requested.emit)
        menu.addSeparator()
        menu.addAction("退出").triggered.connect(QApplication.instance().quit)

        menu.setStyleSheet(styles.menu_qss())
        self.setContextMenu(menu)

    def rebuild(self) -> None:
        self._rebuild_menu()

    def notify(self, title: str, message: str) -> None:
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)
