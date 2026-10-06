# -*- coding: utf-8 -*-
"""
模块名：ui.window_effects
职责：Windows 11 窗口特效——亚克力背景、圆角、标题栏着色
依赖：core.logger
说明：与旧版 window_effects.py 使用同一套 DWM API，保证视觉一致
"""

import sys
import ctypes
from ctypes import wintypes

from core.logger import get_logger

logger = get_logger()

# DWM 属性常量
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_CAPTION_COLOR = 35
DWMWA_SYSTEMBACKDROP_TYPE = 38

DWMWCP_ROUND = 2
DWMSBT_ACRYLIC = 2
DWMSBT_NONE = 1


def _get_hwnd(widget) -> int:
    """从 Qt 控件取顶层窗口句柄"""
    try:
        return int(widget.winId())
    except Exception:
        return 0


def apply_acrylic(widget, alpha: float = 0.96) -> bool:
    """应用亚克力磨砂效果 + 窗口透明度

    Args:
        widget: Qt 顶层窗口（QWidget/QMainWindow）
        alpha: 窗口透明度 0.0-1.0

    Returns:
        是否成功
    """
    if sys.platform != "win32":
        return False

    try:
        # 透明度
        if alpha and 0 < alpha <= 1:
            widget.setWindowOpacity(alpha)

        hwnd = _get_hwnd(widget)
        if not hwnd:
            return False

        dwmapi = ctypes.windll.dwmapi
        backdrop = ctypes.c_int(DWMSBT_ACRYLIC)
        result = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_SYSTEMBACKDROP_TYPE),
            ctypes.byref(backdrop),
            ctypes.sizeof(backdrop)
        )
        if result == 0:
            logger.debug("亚克力效果已启用")
            return True
        logger.debug(f"亚克力效果设置失败，返回码: {result}")
        return False
    except Exception as e:
        logger.debug(f"亚克力效果设置异常: {e}")
        return False


def set_acrylic_enabled(widget, enabled: bool) -> None:
    """开启/关闭亚克力（用于诊断）"""
    if sys.platform != "win32":
        return
    try:
        hwnd = _get_hwnd(widget)
        if not hwnd:
            return
        dwmapi = ctypes.windll.dwmapi
        backdrop = ctypes.c_int(DWMSBT_ACRYLIC if enabled else DWMSBT_NONE)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_SYSTEMBACKDROP_TYPE),
            ctypes.byref(backdrop),
            ctypes.sizeof(backdrop)
        )
    except Exception as e:
        logger.debug(f"切换亚克力失败: {e}")


def set_round_corner(widget) -> None:
    """设置窗口圆角（Win11）"""
    if sys.platform != "win32":
        return
    try:
        hwnd = _get_hwnd(widget)
        if not hwnd:
            return
        dwmapi = ctypes.windll.dwmapi
        pref = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(pref),
            ctypes.sizeof(pref)
        )
    except Exception as e:
        logger.debug(f"设置圆角失败: {e}")


def set_titlebar_color(widget, dark: bool) -> None:
    """设置标题栏颜色（浅色/深色）"""
    if sys.platform != "win32":
        return
    try:
        hwnd = _get_hwnd(widget)
        if not hwnd:
            return
        dwmapi = ctypes.windll.dwmapi
        user32 = ctypes.windll.user32

        # 深色模式
        dark_mode = ctypes.c_int(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_USE_IMMERSIVE_DARK_MODE),
            ctypes.byref(dark_mode),
            ctypes.sizeof(dark_mode)
        )

        # 标题栏颜色（BGR 打包）
        if dark:
            r, g, b = 31, 31, 31
        else:
            r, g, b = 243, 243, 243
        color = ctypes.c_int((b << 16) | (g << 8) | r)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_CAPTION_COLOR),
            ctypes.byref(color),
            ctypes.sizeof(color)
        )

        # 强制刷新非客户区
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        user32.SetWindowPos(
            wintypes.HWND(hwnd), None, 0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED
        )
        WM_THEMECHANGED = 0x031A
        user32.SendMessageW(wintypes.HWND(hwnd), WM_THEMECHANGED, 0, 0)
    except Exception as e:
        logger.debug(f"设置标题栏颜色失败: {e}")
