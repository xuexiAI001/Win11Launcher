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
from core import constants as C
from services.platform import IS_LINUX

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
APP_USER_MODEL_ID = "Win11Launcher.Launcher.1"

# 保存互斥体句柄，防止被垃圾回收导致互斥体销毁、单实例检测失效
_mutex_handle = None
# Linux 单实例服务引用（同理防止 GC）
_linux_single_instance = None


def _set_app_user_model_id():
    """设置 AppUserModelID，让任务栏使用本程序图标而非 Python 图标

    Windows 任务栏按 AppUserModelID 分组并决定显示图标。未设置时，
    任务栏会使用宿主进程（python.exe）的图标。必须在创建窗口前设置。
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception as e:
        logger.debug(f"设置 AppUserModelID 失败: {e}")


def _is_already_running() -> bool:
    """单实例检测：已运行则唤起已有窗口并返回 True"""
    global _mutex_handle
    try:
        kernel32 = ctypes.windll.kernel32
        # 必须保存句柄，否则被 GC 回收后互斥体销毁，检测失效
        _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        # GetLastError 必须紧接 CreateMutexW 调用
        if kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
            return False

        logger.debug("检测到已有实例，尝试唤起")
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "Win11 Launchpad")
        if hwnd:
            # 发送自定义消息，让已有实例自己 show() 窗口
            # （窗口可能是 Qt hide() 隐藏的，SC_RESTORE 无法恢复）
            WM_LAUNCHER_SHOW = 0x8000 + 1
            user32.PostMessageW(hwnd, WM_LAUNCHER_SHOW, 0, 0)
            user32.SetForegroundWindow(hwnd)
            logger.debug(f"已唤起已有窗口 hwnd={hwnd}")
        else:
            logger.debug("未找到已有窗口句柄")
        return True
    except Exception as e:
        logger.debug(f"单实例检测失败: {e}")
        return False


def main():
    global _linux_single_instance
    if IS_LINUX:
        # Linux（麒麟）：QLocalServer 单实例
        from services.single_instance import LinuxSingleInstance
        si = LinuxSingleInstance()
        if not si.try_start():
            return
        _linux_single_instance = si  # 持引用，防止被 GC 回收
    else:
        if _is_already_running():
            return

    # 必须在创建 QApplication / 窗口前设置，否则任务栏显示 Python 图标
    _set_app_user_model_id()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Win11Launcher")

    # Linux（麒麟）无微软雅黑：QApplication 创建后解析本机可用中文字体
    if IS_LINUX:
        fam = C.resolve_font_family()
        if fam:
            C.FONT_FAMILY = fam
            logger.debug(f"Linux 字体族解析为: {fam}")

    config = Config()
    config.load()

    window = MainWindow(config)
    if _linux_single_instance is not None:
        # 其他实例唤起请求 → 主线程显示窗口（ThemeWatcherMixin 提供）
        _linux_single_instance.activated.connect(window._on_show_request)
    window.show()

    logger.debug("主窗口已启动")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
