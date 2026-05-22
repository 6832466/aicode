import sys
import asyncio
import logging
import traceback
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
    """Set Windows taskbar AppUserModelID so taskbar shows 1.ico not python icon."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RunwayML.BatchGenerator.1.0")
    except Exception:
        pass


def main():
    _set_taskbar_icon()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("RunwayML Batch Generator")
    app.setOrganizationName("RunwayMLApp")
    app.setApplicationDisplayName("乐乐RunwayML批量生视频工具")

    icon_p = str(app_icon_path())
    if os.path.exists(icon_p):
        app_icon = QIcon(icon_p)
        app.setWindowIcon(app_icon)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Global asyncio exception handler
    def _async_exception_handler(loop_ctx, context):
        exc = context.get('exception')
        msg = context.get('message', '')
        if exc:
            logger.error("Async 异常: %s\n%s", exc, traceback.format_exc())
        else:
            logger.error("Async 异常: %s", msg)

    loop.set_exception_handler(_async_exception_handler)

    # --- License check ---
    from app.license import is_verified
    if not is_verified():
        from ui.widgets.license_dialog import LicenseDialog
        license_dlg = LicenseDialog()
        if license_dlg.exec() != LicenseDialog.Accepted:
            # We need to run the event loop briefly so Qt can clean up,
            # then exit without ever showing the main window.
            sys.exit(0)

    window = MainWindow()
    if os.path.exists(icon_p):
        window.setWindowIcon(QIcon(icon_p))
    window.show()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("主循环致命异常")
    sys.exit(0)


if __name__ == "__main__":
    main()
