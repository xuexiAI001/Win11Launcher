# -*- coding: utf-8 -*-
"""
模块名：main
职责：程序入口——DPI 设置、单实例、启动主窗口
依赖：core.*, ui.main_window
"""

import os
import sys
import ctypes

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.logger import get_logger

logger = get_logger()

# 高 DPI（必须在创建 QApplication 之前）
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception as e:
        logger.debug(f"DPI 设置失败: {e}")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.config import Config
from ui.main_window import MainWindow

MUTEX_NAME = "Win11Launcher_Qt_SingleInstance_v1"


def _is_already_running() -> bool:
    """单实例检测：已运行则唤起已有窗口并返回 True"""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
            return False

        logger.debug("检测到已有实例，尝试唤起")
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "Win11 Launchpad")
        if hwnd:
            WM_SYSCOMMAND = 0x0112
            SC_RESTORE = 0xF120
            user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_RESTORE, 0)
            user32.SetForegroundWindow(hwnd)
            logger.debug(f"已唤起已有窗口 hwnd={hwnd}")
        return True
    except Exception as e:
        logger.debug(f"单实例检测失败: {e}")
        return False


def main():
    if _is_already_running():
        return

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Win11Launcher")

    config = Config()
    config.load()

    window = MainWindow(config)
    window.show()

    logger.debug("主窗口已启动")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
