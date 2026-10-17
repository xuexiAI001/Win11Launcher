# -*- coding: utf-8 -*-
"""窗口事件 Mixin：关闭、最小化/恢复状态变化"""
from PySide6.QtCore import QEvent

from core.logger import get_logger

logger = get_logger()


class WindowEventsMixin:
    """窗口关闭与状态变化的事件处理（依赖 MainWindow 提供的方法/状态）"""

    def closeEvent(self, event):
        """关闭时：最小化到任务栏（若启用），否则退出

        用 showMinimized() 而非 hide()，让窗口真正最小化到任务栏，
        这样点击任务栏图标恢复时是 Windows 原生动画。
        """
        # 正在退出流程中，直接放行
        if getattr(self, '_quitting', False):
            event.accept()
            return
        minimize = getattr(self.config, 'minimize_to_tray', True)
        logger.debug(f"[CLOSE] minimize={minimize} visible={self.isVisible()}")
        if minimize:
            event.ignore()
            self.showMinimized()
            logger.debug("窗口已最小化到任务栏")
        else:
            event.accept()
            self._force_quit()

    def changeEvent(self, event):
        """窗口状态变化：最小化时暂停安装监控，恢复时继续"""
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            if not hasattr(self, 'install_monitor'):
                return
            if self.isMinimized():
                self.install_monitor.pause()
            else:
                self.install_monitor.resume()
