import sys
import asyncio
import logging
import os
import ctypes

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from qasync import QEventLoop

from app.config import app_icon_path
from ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def _set_taskbar_icon():
    """Set Windows taskbar AppUserModelID."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ModelScope.Manager.1.0"
        )
    except Exception:
        pass


def setup_logging():
    """Configure basic logging before UI is ready."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    root.handlers.clear()
    root.addHandler(handler)

    # Suppress noisy libraries
    for lib in ("asyncio", "aiohttp", "urllib3", "PIL", "qfluentwidgets"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def main():
    _set_taskbar_icon()
    setup_logging()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("ModelScope Manager")
    app.setOrganizationName("ModelScopeManager")
    app.setApplicationDisplayName("魔塔管理器")

    # Load icon
    icon_p = str(app_icon_path())
    if os.path.exists(icon_p):
        app_icon = QIcon(icon_p)
        app.setWindowIcon(app_icon)

    # Setup async event loop
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Global async exception handler
    def _async_exception_handler(_loop, context):
        exc = context.get("exception")
        msg = context.get("message", "")
        if exc:
            logger.error("Async 异常: %s\n%s", exc, context)
        else:
            logger.error("Async 异常: %s", msg)

    loop.set_exception_handler(_async_exception_handler)

    # Create and show main window
    window = MainWindow()
    if os.path.exists(icon_p):
        window.setWindowIcon(QIcon(icon_p))
    window.show()

    # Load config
    window.load_config()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("主循环致命异常")
    sys.exit(0)


if __name__ == "__main__":
    main()
