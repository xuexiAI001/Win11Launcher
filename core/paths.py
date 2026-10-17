# -*- coding: utf-8 -*-
"""
模块名：core.paths
职责：跨平台数据目录解析（配置 / 日志 / 图标缓存共用）
依赖：无
"""

import os
import sys

APP_NAME = "Win11Launcher"


def get_appdata_dir() -> str:
    """返回本程序的数据目录。

    Windows：%APPDATA%\\Win11Launcher（与原行为逐字节一致）
    Linux：  $XDG_CONFIG_HOME/Win11Launcher，默认 ~/.config/Win11Launcher
             （遵循 freedesktop XDG 基本目录规范，麒麟 UKUI 同样适用）
    """
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", "."), APP_NAME)
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(xdg, APP_NAME)
