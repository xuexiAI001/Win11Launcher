# -*- coding: utf-8 -*-
"""
窗口效果工具模块 - 统一管理亚克力透明效果
所有弹窗窗口创建后调用 apply_acrylic(window, parent=self) 即可
透明度自动与主窗口设置同步
"""
import sys
import logging

logger = logging.getLogger("Win11Launcher")


def apply_acrylic(window, parent=None, alpha=None):
    """
    为窗口设置亚克力透明效果，透明度与主窗口同步

    Args:
        window: tkinter/CTk 窗口对象
        parent: 父窗口，用于获取透明度设置（alpha_var）
        alpha: 透明度 (0.0-1.0)，优先使用此值；None则从parent获取
    """
    try:
        if sys.platform != "win32":
            return

        # 确定透明度：优先使用传入的alpha，其次从parent获取alpha_var，最后默认0.96
        if alpha is None and parent is not None:
            # 直接从parent获取
            if hasattr(parent, 'alpha_var') and parent.alpha_var is not None:
                try:
                    alpha = parent.alpha_var.get()
                except Exception:
                    pass
            # 从parent的parent_window获取（AppItem等子组件）
            elif hasattr(parent, 'parent_window') and hasattr(parent.parent_window, 'alpha_var'):
                try:
                    alpha = parent.parent_window.alpha_var.get()
                except Exception:
                    pass
            # 从parent的master获取
            elif hasattr(parent, 'master') and hasattr(parent.master, 'alpha_var'):
                try:
                    alpha = parent.master.alpha_var.get()
                except Exception:
                    pass

        if alpha is None or alpha <= 0 or alpha > 1.0:
            alpha = 0.96

        # 设置透明度
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
            logger.debug(f"窗口亚克力效果设置成功: {window.title()}, alpha={alpha}")
        else:
            logger.debug(f"窗口亚克力效果失败 result={result}: {window.title()}")
    except Exception as e:
        logger.debug(f"设置窗口亚克力效果失败: {e}")
