# -*- coding: utf-8 -*-
"""
模块名：ui.tray
职责：系统托盘——显示/隐藏、退出
依赖：core.constants, core.logger
"""

import os
import sys

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont

from core import constants as C
from core.logger import get_logger

logger = get_logger()


def _make_default_icon() -> QIcon:
    """生成默认托盘图标（蓝底白 L）"""
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(0, 120, 212))
    painter.setPen(QColor(0, 0, 0, 0))
    painter.drawRoundedRect(0, 0, 64, 64, 12, 12)
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Segoe UI", 36)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pix.rect(), 0x84, "L")  # AlignCenter
    painter.end()
    return QIcon(pix)


class TrayManager:
    """系统托盘管理器"""

    def __init__(self, main_window):
        self.main_window = main_window
        self.tray = None

    def start(self):
        """创建托盘图标"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.debug("系统托盘不可用")
            return

        # 图标：优先 assets/app.ico
        icon = None
        base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ico = os.path.join(base, "assets", "app.ico")
        if os.path.exists(ico):
            icon = QIcon(ico)
        if icon is None or icon.isNull():
            icon = _make_default_icon()

        self.tray = QSystemTrayIcon(icon, self.main_window)
        self.tray.setToolTip("Win11 启动台")

        menu = QMenu()
        toggle_action = QAction("显示/隐藏", menu)
        toggle_action.triggered.connect(self._toggle_window)
        menu.addAction(toggle_action)
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()
        logger.debug("托盘图标已启动")

    def _on_activated(self, reason):
        """左键单击托盘图标"""
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_window()

    def _toggle_window(self):
        """显示/隐藏主窗口"""
        w = self.main_window
        if w.isVisible():
            w.hide()
        else:
            w.show()
            w.raise_()
            w.activateWindow()

    def _quit(self):
        """退出程序"""
        from PySide6.QtWidgets import QApplication
        if self.tray is not None:
            self.tray.hide()
        self.main_window._force_quit()

    def stop(self):
        """停止托盘"""
        if self.tray is not None:
            self.tray.hide()
            self.tray = None
