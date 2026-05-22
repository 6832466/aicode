"""Batch Image Generation Tool — entry point."""
import sys
import os
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from qfluentwidgets import FluentTranslator, setTheme, Theme


def _icon_path() -> str:
    """Resolve icon path, works in both source and PyInstaller bundles."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "1.ico")


def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    icon = QIcon(_icon_path())
    app.setWindowIcon(icon)

    translator = FluentTranslator()
    app.installTranslator(translator)

    setTheme(Theme.AUTO)

    # Lazy import to avoid circular dependencies
    from main_window import MainWindow
    w = MainWindow()
    w.setWindowIcon(icon)
    w.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
