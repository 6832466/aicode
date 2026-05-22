"""全局日志服务 —— 所有模块通过单例发送日志，LogPage 订阅显示。"""

from PySide6.QtCore import QObject, Signal


class LogService(QObject):
    log_message = Signal(str, str)  # message, level


# 全局单例
log_service = LogService()
