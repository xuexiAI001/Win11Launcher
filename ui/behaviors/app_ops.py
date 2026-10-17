# -*- coding: utf-8 -*-
"""应用操作 Mixin：启动/移动/重命名/删除/属性等全部应用级操作"""
import os
import ctypes

from PySide6.QtWidgets import QInputDialog, QMessageBox, QFileDialog

from core.logger import get_logger

logger = get_logger()


class AppOpsMixin:
    """应用与文件夹的增删改、启动、属性等操作（依赖 MainWindow 提供的方法/状态）"""

    # ------------------------------------------------------------
    # 应用操作
    # ------------------------------------------------------------
    def _launch_app(self, app_data: dict):
        """启动应用"""
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

    def _launch_as_admin(self, app_data: dict):
        """管理员身份启动（Windows 专有；Linux 无等价提权入口）"""
        from services.platform import IS_LINUX
        if IS_LINUX:
            self.show_message("当前系统不支持管理员身份启动")
            return
        path = app_data.get("path", "")
        if not path:
            return
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", path, None, None, 1)
            logger.debug(f"管理员启动: {path}")
        except Exception as e:
            logger.warning(f"管理员启动失败: {e}")
            self.show_message("管理员启动失败")

    def _move_app_to_category(self, app_data: dict, category: str):
        """移动应用到其他分类"""
        cur = self.config.current_category
        if category == cur:
            return
        self.config.remove_app(cur, app_data)
        self.config.add_app(category, app_data)
        self.config.save()
        self._card_cache.pop(cur, None)
        self._refresh_grid()
        self.show_message(f"已移动到 {category}")

    def _move_app_to_folder(self, app_data: dict, folder: dict):
        """移动应用到文件夹"""
        cur = self.config.current_category
        self.config.remove_app(cur, app_data)
        folder.setdefault("apps", []).append(app_data)
        self.config.save()
        self._card_cache.pop(cur, None)
        self._refresh_grid()
        self.show_message(f"已移动到 {folder.get('name')}")

    def _create_folder_with_app(self, app_data: dict):
        """新建文件夹并移入应用"""
        folders = self.config.get_folders(self.config.current_category)
        default = f"文件夹{len(folders) + 1}"
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称:", text=default)
        if not ok or not name.strip():
            return
        folder = {"type": "folder", "name": name.strip(), "apps": []}
        cur = self.config.current_category
        self.config.remove_app(cur, app_data)
        folder["apps"].append(app_data)
        self.config.app_config.setdefault(cur, []).append(folder)
        self.config.save()
        self._card_cache.pop(cur, None)
        self._refresh_grid()
        self.show_message(f"已创建文件夹 {name}")

    def _change_icon(self, app_data: dict):
        """更换图标"""
        path, _ = QFileDialog.getOpenFileName(self, "选择图标", "", "图标文件 (*.ico *.png)")
        if not path:
            return
        app_data["icon_path"] = path
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message("图标已更换")

    def _rename_app(self, app_data: dict):
        """重命名应用"""
        name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=app_data.get("name", ""))
        if not ok or not name.strip():
            return
        app_data["name"] = name.strip()
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message("已重命名")

    def _delete_app(self, app_data: dict):
        """删除应用"""
        ret = QMessageBox.question(
            self, "删除应用",
            f"确定要删除「{app_data.get('name')}」吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        self.config.remove_app(self.config.current_category, app_data)
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message("已删除")

    def _clear_category(self):
        """清空当前分类"""
        cat = self.config.current_category
        ret = QMessageBox.question(
            self, "清空分类",
            f"确定要清空「{cat}」的所有应用吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        self.config.app_config[cat] = []
        self.config.save()
        self._card_cache.pop(cat, None)
        self._refresh_grid()
        self.show_message("已清空")

    def _open_file_location(self, app_data: dict):
        """打开文件位置"""
        from services.platform import IS_LINUX
        path = app_data.get("path", "")
        if not path:
            return
        if IS_LINUX:
            self._open_file_location_linux(path)
            return
        try:
            if os.path.isdir(path):
                os.startfile(path)
            else:
                import subprocess
                subprocess.Popen(f'explorer /select,"{path}"')
        except Exception as e:
            logger.warning(f"打开位置失败: {e}")

    def _open_file_location_linux(self, cmd: str):
        """Linux 打开文件位置：定位 Exec 命令的真实路径并打开所在目录"""
        import shlex
        import shutil
        import subprocess
        try:
            argv = shlex.split(cmd)
            exe = argv[0] if argv else ""
            target = None
            if exe and os.path.isfile(exe):
                target = os.path.dirname(exe)
            elif exe:
                real = shutil.which(exe)
                if real:
                    target = os.path.dirname(real)
            if not target:
                # 回退：打开 .desktop 文件所在目录
                target = "/usr/share/applications"
            subprocess.Popen(["xdg-open", target], start_new_session=True)
        except Exception as e:
            logger.warning(f"打开位置失败: {e}")
            self.show_message("打开位置失败")

    def _show_properties(self, app_data: dict):
        """显示属性（Windows 资源管理器属性页；Linux 展示应用路径）"""
        from services.platform import IS_LINUX
        path = app_data.get("path", "")
        if not path:
            return
        if IS_LINUX:
            self.show_message(f"应用命令: {path}")
            return
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "properties", path, None, None, 1)
        except Exception as e:
            logger.warning(f"显示属性失败: {e}")

    def _rename_folder(self, app_data: dict):
        """重命名文件夹"""
        name, ok = QInputDialog.getText(self, "重命名文件夹", "新名称:",
                                        text=app_data.get("name", ""))
        if not ok or not name.strip():
            return
        app_data["name"] = name.strip()
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message("文件夹已重命名")

    def _delete_folder(self, app_data: dict):
        """删除文件夹（内部应用移回主分类）"""
        ret = QMessageBox.question(
            self, "删除文件夹",
            f"确定要删除文件夹「{app_data.get('name')}」吗？\n内部应用将移回当前分类。",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        cat = self.config.current_category
        apps = self.config.app_config.get(cat, [])
        if app_data in apps:
            apps.remove(app_data)
        for a in app_data.get("apps", []):
            apps.append(a)
        self.config.save()
        self._card_cache.pop(cat, None)
        self._refresh_grid()
        self.show_message("文件夹已删除")

    def _on_add_app(self):
        """添加应用（文件选择）"""
        from services.platform import get_app_info, IS_LINUX
        if IS_LINUX:
            start_dir, name_filter = "/usr/share/applications", "应用文件 (*.desktop);;所有文件 (*.*)"
        else:
            start_dir = os.environ.get("PROGRAMFILES", "")
            name_filter = "可执行文件 (*.exe *.lnk *.bat *.cmd);;所有文件 (*.*)"
        paths, _ = QFileDialog.getOpenFileNames(self, "选择应用", start_dir, name_filter)
        if not paths:
            return
        added = 0
        for path in paths:
            info = get_app_info(path)
            if not info:
                continue
            if self.config.add_app(self.config.current_category, info):
                added += 1
        if added:
            self.config.save()
            self._card_cache.pop(self.config.current_category, None)
            self._refresh_grid()
        self.show_message(f"已添加 {added} 个应用")

    def _open_settings(self):
        """打开设置面板"""
        from ui.dialogs import SettingsDialog
        dlg = SettingsDialog(self)
        self.register_dialog(dlg)
        dlg.exec()

    def register_dialog(self, dlg):
        """登记模态弹窗，主题变化时同步刷新；关闭后自动移除"""
        self._open_dialogs.append(dlg)
        dlg.finished.connect(lambda _=0, d=dlg: self._unregister_dialog(d))

    def _unregister_dialog(self, dlg):
        try:
            self._open_dialogs.remove(dlg)
        except ValueError:
            pass

    def show_message(self, text: str, duration_ms: int = 3000):
        """底部状态提示"""
        self.status_label.setText(text)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(duration_ms, lambda: self.status_label.setText(""))
