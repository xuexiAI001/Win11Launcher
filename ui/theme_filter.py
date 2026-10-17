# -*- coding: utf-8 -*-
"""原生 Windows 消息监听：系统主题变化 + 单实例唤起请求"""
import ctypes

from PySide6.QtCore import QAbstractNativeEventFilter
from core.logger import get_logger

logger = get_logger()

# Windows 消息：系统设置变化（含主题切换）
WM_SETTINGCHANGE = 0x001A
# 自定义消息：新实例请求唤起已有窗口（WM_APP + 1）
WM_LAUNCHER_SHOW = 0x8000 + 1


class _MSG(ctypes.Structure):
    """Windows MSG 结构（64 位下 hwnd/wParam/lParam 均为 8 字节）"""
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_void_p),
        ("lParam", ctypes.c_void_p),
    ]


class _ThemeChangeFilter(QAbstractNativeEventFilter):
    """监听 Windows 原生消息

    1. WM_SETTINGCHANGE + "ImmersiveColorSet"：系统主题变化
    2. WM_LAUNCHER_SHOW：新实例请求唤起已有窗口（单实例唤起）
    """

    def __init__(self, theme_callback, show_callback):
        super().__init__()
        self._theme_callback = theme_callback
        self._show_callback = show_callback

    def nativeEventFilter(self, event_type, message):
        try:
            if event_type == b"windows_generic_MSG":
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
                if msg.message == WM_SETTINGCHANGE:
                    lparam = msg.lParam
                    if lparam:
                        name = ctypes.c_wchar_p(lparam).value or ""
                        if name == "ImmersiveColorSet":
                            self._theme_callback()
                elif msg.message == WM_LAUNCHER_SHOW:
                    self._show_callback()
        except Exception as e:
            logger.debug(f"原生消息监听异常: {e}")
        return False, 0
