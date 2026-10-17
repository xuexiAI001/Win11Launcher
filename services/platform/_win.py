# -*- coding: utf-8 -*-
"""Windows 后端：直接委托既有 Windows 模块，行为与原实现完全一致。

本模块只在 Windows 上被 services.platform 导入，因此可以安全 import
仅 Windows 可用的模块（ctypes.wintypes / winreg / win32com 等）。
"""

import os

from services.icon_extractor import get_app_icon
from services.app_info import get_app_info
from services.install_monitor import (
    InstallMonitor,
    scan_start_menu_names,
    find_lnk_by_name,
)
from services import autostart as _autostart


def launch_app(path: str) -> None:
    """启动应用/文件——与重构前 cards.py / app_ops.py 的 os.startfile 一致。"""
    os.startfile(path)


def make_install_monitor(*args, **kwargs):
    return InstallMonitor(*args, **kwargs)


def scan_app_names():
    return scan_start_menu_names()


def find_app_by_name(name):
    return find_lnk_by_name(name)


def autostart_is_enabled():
    return _autostart.is_autostart_enabled()


def autostart_set(enabled):
    return _autostart.set_autostart(enabled)
