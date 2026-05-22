"""Qt 日志处理器 - 将 Python logging 转发为 Qt Signal"""
import logging
from PySide6.QtCore import QObject, Signal


class QtLogHandler(QObject, logging.Handler):
    """线程安全的日志处理器, 将日志消息通过 Signal 发送到 UI"""
    log_signal = Signal(str, str)  # message, level

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        self.log_signal.emit(msg, record.levelname)


def setup_logging() -> QtLogHandler:
    """配置全局日志系统, 返回 QtLogHandler 实例"""
    logger = logging.getLogger("hongguo")
    logger.setLevel(logging.DEBUG)

    handler = QtLogHandler()
    logger.addHandler(handler)

    # 同时输出到控制台
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(console)

    return handler


def get_logger(name: str = "hongguo") -> logging.Logger:
    return logging.getLogger(f"hongguo.{name}")
