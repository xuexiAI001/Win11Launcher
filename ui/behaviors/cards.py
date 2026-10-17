# -*- coding: utf-8 -*-
"""卡片交互 Mixin：单击启动、打开文件夹、右键菜单、拖拽释放"""
import os

from core.logger import get_logger
from ui.app_card import AppCard

logger = get_logger()


class CardActionsMixin:
    """应用卡片的点击/打开/右键/拖拽交互（依赖 MainWindow 提供的方法）"""

    # ------------------------------------------------------------
    # 卡片交互
    # ------------------------------------------------------------
    def _on_card_clicked(self, app_data: dict):
        """单击卡片：启动应用或打开文件夹"""
        if app_data.get("type") == "folder":
            self._open_folder(app_data)
            return
        from services.platform import launch_app, IS_LINUX
        path = app_data.get("path", "")
        # Linux 下 path 为 Exec 命令（非文件路径），跳过 os.path.exists 检查
        if path and (IS_LINUX or os.path.exists(path)):
            try:
                launch_app(path)
                logger.debug(f"启动应用: {path}")
            except Exception as e:
                logger.warning(f"启动失败 {path}: {e}")
                self.show_message(f"启动失败: {app_data.get('name')}")
        else:
            self.show_message(f"文件不存在: {app_data.get('name')}")

    def _open_folder(self, folder_data: dict):
        """打开文件夹弹窗（单例）"""
        from ui.folder_window import FolderWindow
        key = f"{self.config.current_category}_{folder_data.get('name')}"
        win = self._folder_windows.get(key)
        if win is not None:
            try:
                win.show()
                win.raise_()
                win.activateWindow()
                return
            except RuntimeError:
                self._folder_windows.pop(key, None)

        win = FolderWindow(self, folder_data, self.dark)
        self._folder_windows[key] = win
        win.show()
        logger.debug(f"打开文件夹: {folder_data.get('name')}")

    def _on_card_right_clicked(self, app_data: dict, pos):
        """右键卡片：弹出菜单"""
        from ui import context_menu
        handlers = {
            "launch": self._launch_app,
            "launch_admin": self._launch_as_admin,
            "categories": self.config.categories,
            "move_category": self._move_app_to_category,
            "folders": self.config.get_folders(self.config.current_category),
            "move_to_folder": self._move_app_to_folder,
            "create_folder": self._create_folder_with_app,
            "in_folder": False,
            "change_icon": self._change_icon,
            "rename": self._rename_app,
            "delete_app": self._delete_app,
            "clear_category": self._clear_category,
            "open_location": self._open_file_location,
            "properties": self._show_properties,
            "settings": self._open_settings,
        }
        if app_data.get("type") == "folder":
            menu = context_menu.build_folder_menu(self, app_data, self.dark, {
                "open_folder": self._open_folder,
                "rename_folder": self._rename_folder,
                "delete_folder": self._delete_folder,
            })
        else:
            menu = context_menu.build_app_menu(self, app_data, self.dark, handlers)
        menu.exec(pos)

    def _on_card_drag_released(self, app_data: dict, pos):
        """拖拽释放：检测是否落在文件夹卡片上"""
        target = self.childAt(self.mapFromGlobal(pos))
        if isinstance(target, AppCard) and target.is_folder:
            self._move_app_to_folder(app_data, target.app_data)
            logger.debug(f"移动 {app_data.get('name')} 到文件夹 {target.app_data.get('name')}")
