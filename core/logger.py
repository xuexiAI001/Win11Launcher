# -*- coding: utf-8 -*-
"""
模块名：core.logger
职责：统一日志系统，输出到 %APPDATA%/Win11Launcher/launcher.log，2MB×3 轮转
依赖：无
"""

import os
import logging
from logging.handlers import RotatingFileHandler

APP_NAME = "Win11Launcher"
LOG_DIR = os.path.join(os.environ.get('APPDATA', '.'), APP_NAME)
LOG_FILE = os.path.join(LOG_DIR, 'launcher.log')

_logger = None


def get_logger() -> logging.Logger:
    """获取全局日志器（单例）"""
    global _logger
    if _logger is not None:
        return _logger

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception:
        pass

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        _logger = logger
        return logger

    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(handler)
    _logger = logger
    return logger
