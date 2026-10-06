# -*- coding: utf-8 -*-
"""
模块名：services.hotkey
职责：全局快捷键——pynput 监听，回调主线程
依赖：core.logger
"""

from core.logger import get_logger

logger = get_logger()

try:
    from pynput import keyboard
    HAS_HOTKEY = True
except ImportError:
    HAS_HOTKEY = False
    logger.debug("pynput 未安装，全局快捷键不可用")


def convert_hotkey_format(hotkey: str) -> str:
    """把 'Ctrl+Shift+L' 转成 pynput 的 '<ctrl>+<shift>+l'"""
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    mapped = []
    for p in parts:
        if p in ("ctrl", "control"):
            mapped.append("<ctrl>")
        elif p == "shift":
            mapped.append("<shift>")
        elif p in ("alt", "menu"):
            mapped.append("<alt>")
        elif p in ("win", "super", "cmd"):
            mapped.append("<cmd>")
        else:
            mapped.append(p)
    return "+".join(mapped)


class HotkeyManager:
    """全局快捷键管理器"""

    def __init__(self, callback):
        self.callback = callback
        self.listener = None

    def start(self, hotkey: str) -> bool:
        """启动监听"""
        if not HAS_HOTKEY:
            return False
        self.stop()
        try:
            combo = convert_hotkey_format(hotkey)
            self.listener = keyboard.GlobalHotKeys({combo: self.callback})
            self.listener.daemon = True
            self.listener.start()
            logger.debug(f"全局快捷键已启动: {hotkey} -> {combo}")
            return True
        except Exception as e:
            logger.warning(f"启动全局快捷键失败: {e}")
            return False

    def stop(self):
        """停止监听"""
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None
