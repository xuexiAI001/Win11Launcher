# -*- coding: utf-8 -*-
"""
窗口效果工具模块 - 统一管理亚克力透明效果
所有弹窗窗口创建后调用 apply_acrylic(window) 即可
"""
import sys
import logging

logger = logging.getLogger("Win11Launcher")


def apply_acrylic(window, alpha=None):
    """
    为窗口设置亚克力透明效果

    Args:
        window: tkinter/CTk 窗口对象
        alpha: 透明度 (0.0-1.0)，None则不设置透明度
    """
    try:
        if sys.platform != "win32":
            return

        # 设置透明度
        if alpha is not None and 0.0 < alpha <= 1.0:
            try:
                window.attributes('-alpha', alpha)
            except Exception:
                pass

        import ctypes
        from ctypes import wintypes

        hwnd = window.winfo_id()
        user32 = ctypes.windll.user32

        # 获取根窗口句柄（CTkToplevel可能有包装层）
        GetAncestor = user32.GetAncestor
        GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
        GetAncestor.restype = wintypes.HWND
        root_hwnd = GetAncestor(hwnd, 2)  # GA_ROOT = 2
        if root_hwnd:
            hwnd = root_hwnd

        DwmSetWindowAttribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.POINTER(ctypes.c_int), ctypes.c_uint]
        DwmSetWindowAttribute.restype = wintypes.HRESULT

        # DWMWA_SYSTEMBACKDROP_TYPE = 38, 2 = DWMSBT_ACRYLIC (亚克力效果)
        backdrop_type = ctypes.c_int(2)
        result = DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type))

        if result == 0:
            logger.debug(f"窗口亚克力效果设置成功: {window.title()}")
        else:
            logger.debug(f"窗口亚克力效果失败 result={result}: {window.title()}")
    except Exception as e:
        logger.debug(f"设置窗口亚克力效果失败: {e}")
