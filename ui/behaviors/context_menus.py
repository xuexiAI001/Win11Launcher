# -*- coding: utf-8 -*-
"""空白处右键菜单 Mixin：新建文件夹 / 新建文件 / 添加应用等"""
import os
import time

from PySide6.QtWidgets import QInputDialog

from core.logger import get_logger

logger = get_logger()


class ContextMenuMixin:
    """空白处右键菜单与"新建"操作（依赖 MainWindow 提供的方法/状态）"""

    # ------------------------------------------------------------
    # 空白处右键菜单
    # ------------------------------------------------------------
    def _on_blank_right_clicked(self, pos):
        """空白处右键：新建菜单"""
        from ui import context_menu
        menu = context_menu.build_blank_menu(self, self.dark, {
            "new_folder": self._new_folder,
            "new_txt": lambda: self._create_new_file("txt"),
            "new_docx": lambda: self._create_new_file("docx"),
            "new_xlsx": lambda: self._create_new_file("xlsx"),
            "new_pptx": lambda: self._create_new_file("pptx"),
            "add_app": self._on_add_app,
            "settings": self._open_settings,
        })
        global_pos = self.sender().mapToGlobal(pos) if self.sender() else self.mapToGlobal(pos)
        menu.exec(global_pos)

    def _new_folder(self):
        """新建空文件夹"""
        folders = self.config.get_folders(self.config.current_category)
        default = f"文件夹{len(folders) + 1}"
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称:", text=default)
        if not ok or not name.strip():
            return
        folder = {"type": "folder", "name": name.strip(), "apps": []}
        self.config.app_config.setdefault(self.config.current_category, []).append(folder)
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message(f"已创建文件夹 {name}")

    def _create_new_file(self, kind: str):
        """在桌面新建文件并加入当前分类"""
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        ts = time.strftime("%Y%m%d_%H%M%S")
        ext_map = {"txt": ".txt", "docx": ".docx", "xlsx": ".xlsx", "pptx": ".pptx"}
        name_map = {"txt": "新建文本文档", "docx": "新建文档", "xlsx": "新建表格", "pptx": "新建演示"}
        filename = f"{name_map[kind]}_{ts}{ext_map[kind]}"
        path = os.path.join(desktop, filename)
        try:
            if kind == "txt":
                open(path, "w", encoding="utf-8").close()
            else:
                # 尝试用 Office COM 创建，失败则建空文件
                try:
                    import win32com.client
                    app_map = {"docx": "Word.Application", "xlsx": "Excel.Application",
                               "pptx": "PowerPoint.Application"}
                    app = win32com.client.Dispatch(app_map[kind])
                    if kind == "docx":
                        doc = app.Documents.Add()
                        doc.SaveAs(path)
                        doc.Close()
                    elif kind == "xlsx":
                        wb = app.Workbooks.Add()
                        wb.SaveAs(path)
                        wb.Close()
                    else:
                        pres = app.Presentations.Add()
                        pres.SaveAs(path)
                        pres.Close()
                    app.Quit()
                except Exception:
                    open(path, "w", encoding="utf-8").close()
            self.config.add_app(self.config.current_category,
                               {"name": filename, "path": path,
                                "original_path": path, "icon_path": None})
            self.config.save()
            self._card_cache.pop(self.config.current_category, None)
            self._refresh_grid()
            self.show_message(f"已创建 {filename}")
        except Exception as e:
            logger.warning(f"新建文件失败: {e}")
            self.show_message("新建文件失败")
