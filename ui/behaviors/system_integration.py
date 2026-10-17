# -*- coding: utf-8 -*-
"""系统集成 Mixin：托盘、全局快捷键、安装监控、强制退出"""
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from core import constants as C
from core.logger import get_logger

logger = get_logger()


class SystemIntegrationMixin:
    """托盘 / 全局快捷键 / 安装监控 / 退出流程（依赖 MainWindow 提供的方法）"""

    # ------------------------------------------------------------
    # 系统集成
    # ------------------------------------------------------------
    def _setup_system_integration(self):
        """托盘、全局快捷键、安装监控"""
        # 托盘
        from ui.tray import TrayManager
        self.tray = TrayManager(self)
        self.tray.start()

        # 全局快捷键
        from services.hotkey import HotkeyManager
        hotkey = self.config.__dict__.get("hotkey", C.DEFAULT_HOTKEY)
        # pynput 回调运行在监听线程，必须经信号投递到主线程再操作 GUI
        self._hotkey_signal.connect(self._on_hotkey, Qt.QueuedConnection)
        self.hotkey_mgr = HotkeyManager(self._hotkey_signal.emit)
        self.hotkey_mgr.start(hotkey)

        # 安装监控
        from services.platform import make_install_monitor
        self.install_monitor = make_install_monitor()
        self.install_monitor.new_apps_found.connect(self._on_new_apps)
        QTimer.singleShot(3000, self.install_monitor.start)

    def _on_hotkey(self):
        """全局快捷键触发：切换窗口显示"""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _on_new_apps(self, paths: list):
        """检测到新安装应用"""
        from services.platform import get_app_info
        names = [os.path.splitext(os.path.basename(p))[0] for p in paths]
        ret = QMessageBox.question(
            self, "发现新应用",
            "检测到新安装的应用:\n" + "\n".join(names[:10]) +
            ("\n..." if len(names) > 10 else "") +
            f"\n\n是否添加到「{self.config.current_category}」？",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        added = 0
        for p in paths:
            info = get_app_info(p)
            if self.config.add_app(self.config.current_category, info):
                added += 1
        if added:
            self.config.save()
            self._card_cache.pop(self.config.current_category, None)
            self._refresh_grid()
            self.show_message(f"已添加 {added} 个新应用")

    def _force_quit(self):
        """强制退出程序"""
        # 标记正在退出，避免 close() 再次触发 closeEvent 造成递归
        self._quitting = True
        try:
            if hasattr(self, 'hotkey_mgr'):
                self.hotkey_mgr.stop()
            if hasattr(self, 'install_monitor'):
                self.install_monitor.stop()
            if hasattr(self, 'tray'):
                self.tray.stop()
            if hasattr(self, 'icon_loader'):
                self.icon_loader.shutdown()
        except Exception:
            pass
        # 先关闭窗口，再退出应用，确保进程真正结束
        self.close()
        QApplication.quit()
