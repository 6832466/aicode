"""日志工具模块"""
import os
import sys
import logging
import traceback
from datetime import datetime
from pathlib import Path


def setup_logging(log_dir: str = None) -> logging.Logger:
    """初始化日志系统，返回 root logger"""
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger('VideoDownLoad')
    logger.setLevel(logging.DEBUG)

    # 文件 handler - 详细日志
    log_file = os.path.join(log_dir, f'app_{datetime.now().strftime("%Y%m%d")}.log')
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s | %(threadName)s | %(message)s'
    ))
    logger.addHandler(fh)

    # 错误文件 - 只记录 ERROR+
    err_file = os.path.join(log_dir, f'error_{datetime.now().strftime("%Y%m%d")}.log')
    eh = logging.FileHandler(err_file, encoding='utf-8')
    eh.setLevel(logging.ERROR)
    eh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s\n%(exc_info)s'
    ))
    logger.addHandler(eh)

    # 控制台 handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'
    ))
    logger.addHandler(ch)

    # 全局异常捕获
    def _excepthook(exc_type, exc_value, exc_tb):
        logger.critical('未捕获的异常:', exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    logger.info(f'日志系统已启动, 文件: {log_file}')
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """获取指定名称的 logger"""
    if name:
        return logging.getLogger(f'VideoDownLoad.{name}')
    return logging.getLogger('VideoDownLoad')


def log_exceptions(logger=None):
    """装饰器：记录函数异常"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                lg = logger or get_logger(func.__module__)
                lg.exception(f'{func.__name__} 异常: {e}')
                raise
        return wrapper
    return decorator
