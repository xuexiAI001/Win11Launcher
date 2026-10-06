# -*- coding: utf-8 -*-
"""
模块名：services.autostart
职责：开机自启动——注册表 Run 项读写
依赖：core.logger
"""

import sys
import os

from core.logger import get_logger

logger = get_logger()

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Win11Launchpad"


def _get_exe_path() -> str:
    """获取当前程序路径（兼容打包）"""
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    # 源码运行：用 pythonw + main.py
    py = sys.executable.replace("python.exe", "pythonw.exe")
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return f'"{py}" "{main_py}"'


def is_autostart_enabled() -> bool:
    """检查是否已设置开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.debug(f"检查自启动失败: {e}")
        return False


def set_autostart(enabled: bool) -> bool:
    """设置/取消开机自启"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _get_exe_path())
                logger.debug("已设置开机自启")
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                    logger.debug("已取消开机自启")
                except FileNotFoundError:
                    pass
            return True
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.warning(f"设置自启动失败: {e}")
        return False
