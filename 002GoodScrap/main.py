"""Gold Monitor - Desktop gold price monitor with PySide6 Fluent UI."""
import sys

from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QApplication

from _icon import get_icon_bytes
from core.config import ConfigManager
from core.autostart import set_enabled as set_autostart
from core.monitor import PriceMonitor
from ui import styles
from ui.window import FloatingWindow
from ui.settings import SettingsDialog
from ui.tray import SystemTray


class GoldMonitorApp:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setApplicationName("Gold Monitor")
        self._app.setQuitOnLastWindowClosed(False)

        pixmap = QPixmap()
        pixmap.loadFromData(get_icon_bytes())
        self._app.setWindowIcon(QIcon(pixmap))

        self._config = ConfigManager()

        # Apply saved theme before creating UI
        saved_theme = self._config.get("theme", "鎏金")
        styles.set_theme(saved_theme)

        self._settings_dialog: SettingsDialog | None = None

        self._window = FloatingWindow(
            config_getter=lambda: self._config.data,
            config_setter=self._config.set,
            save_position=self._config.save_window_position,
        )

        self._tray = SystemTray()
        self._monitor = PriceMonitor(self._config)

        self._connect_signals()
        self._window.show()
        self._monitor.start()

    def _connect_signals(self) -> None:
        self._monitor.price_updated.connect(self._window.update_prices)
        self._monitor.alert_message.connect(self._on_alert)

        self._window.settings_requested.connect(self._open_settings)
        self._window.theme_changed.connect(self._apply_theme)
        self._tray.settings_requested.connect(self._open_settings)
        self._tray.show_hide_requested.connect(self._toggle_window)
        self._tray.theme_changed.connect(self._apply_theme)

    def _apply_theme(self, name: str) -> None:
        self._config.set("theme", name)
        self._window.apply_theme(name)
        self._tray.rebuild()
        # Refresh settings dialog if open
        if self._settings_dialog and self._settings_dialog.isVisible():
            self._settings_dialog.setStyleSheet(styles.dialog_qss())

    def _on_alert(self, title: str, message: str, metal: str) -> None:
        try:
            self._tray.notify(title, message)
            if metal:
                direction = "up" if "涨" in message or "上破" in message else "down"
                self._window.flash_alert(direction)
        except Exception:
            pass

    def _open_settings(self) -> None:
        if self._settings_dialog and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        self._settings_dialog = SettingsDialog(self._config.data)
        self._settings_dialog.settings_applied.connect(self._apply_settings)
        self._settings_dialog.show()

    def _apply_settings(self, updates: dict) -> None:
        self._config.update(updates)
        try:
            if "autostart" in updates:
                set_autostart(updates["autostart"])
        except Exception:
            pass
        if "opacity" in updates:
            self._window.apply_opacity(updates["opacity"])
        if "refresh_interval" in updates:
            self._monitor.set_interval(updates["refresh_interval"])

    def _toggle_window(self) -> None:
        if self._window.isVisible():
            self._window.hide()
        else:
            self._window.show()

    def run(self) -> None:
        sys.exit(self._app.exec())


def main():
    app = GoldMonitorApp()
    app.run()


if __name__ == "__main__":
    main()
