# -*- coding: utf-8 -*-
"""主题监听 Mixin：系统主题变化 + 单实例唤起请求（原生消息）"""
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core import constants as C
from core.logger import get_logger
from ui.theme_filter import _ThemeChangeFilter

logger = get_logger()


class ThemeWatcherMixin:
    """提供系统主题变化监听与单实例唤起能力（依赖 MainWindow 提供的方法）"""

    # ------------------------------------------------------------
    # 系统主题监听
    # ------------------------------------------------------------
    def _setup_theme_watcher(self):
        """监听系统主题变化 + 单实例唤起请求"""
        if sys.platform != "win32":
            return
        try:
            self._theme_filter = _ThemeChangeFilter(
                self._on_system_theme_changed, self._on_show_request
            )
            QApplication.instance().installNativeEventFilter(self._theme_filter)
            logger.debug("系统主题变化监听已安装")
        except Exception as e:
            logger.debug(f"安装主题监听失败: {e}")

    def _on_show_request(self):
        """收到新实例的唤起请求（原生事件线程，需投递到主线程）"""
        # 防抖：同一消息可能被 Qt 投递两次，短时间内只处理一次
        now = time.monotonic()
        if now - getattr(self, '_last_show_req', 0) < 0.3:
            return
        self._last_show_req = now
        QTimer.singleShot(0, self._show_from_tray)

    def _show_from_tray(self):
        """从最小化状态恢复窗口（触发 Windows 原生还原动画）"""
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        logger.debug("已响应唤起请求，显示窗口")

    def _on_system_theme_changed(self):
        """系统主题变化回调（原生事件线程，需投递到主线程）"""
        # 仅"跟随系统"时才响应
        if self.config.theme != C.THEME_SYSTEM:
            return
        # 用 QTimer 投递到主线程执行，避免在原生事件回调里操作 UI
        QTimer.singleShot(0, self._apply_system_theme)

    def _apply_system_theme(self):
        """重新解析系统主题并应用"""
        new_dark = self._resolve_dark()
        if new_dark == self.dark:
            return
        logger.debug(f"检测到系统主题变化，切换为{'深色' if new_dark else '浅色'}")
        self.apply_theme()
