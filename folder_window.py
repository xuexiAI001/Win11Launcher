# -*- coding: utf-8 -*-
"""
文件夹窗口模块 - 点击文件夹后弹出，显示文件夹内的应用
"""
import os
import logging
import customtkinter as ctk

logger = logging.getLogger("Win11Launcher")


class FolderWindow(ctk.CTkToplevel):
    """文件夹内容窗口"""

    def __init__(self, parent, folder_data, folder_key, on_changed=None):
        """
        Args:
            parent: 主窗口
            folder_data: 文件夹数据 dict (含 name, apps)
            folder_key: 文件夹标识 (分类名_文件夹名)
            on_changed: 内容变更回调
        """
        super().__init__(parent)
        self.parent_window = parent
        self.folder_data = folder_data
        self.folder_key = folder_key
        self.on_changed = on_changed

        self.title(folder_data.get("name", "文件夹"))
        self.geometry("500x400")
        self.configure(fg_color=("#F3F3F3", "#202020"))

        # 设置透明度（与主窗口保持一致）
        alpha = getattr(parent, 'alpha_var', None)
        alpha_val = alpha.get() if alpha and alpha.get() > 0 else 0.96
        self.attributes('-alpha', alpha_val)

        # 设置亚克力透明效果（与主窗口保持一致）
        self._setup_acrylic_effect()

        # 关键：设置为父窗口的临时窗口，确保始终在主窗口之上
        self.transient(parent)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        # 延迟再次提升，防止主窗口抢焦点
        self.after(100, self._ensure_on_top)

        # 居中
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 400) // 2
        self.geometry(f"+{x}+{y}")

        # 顶部标题栏
        title_frame = ctk.CTkFrame(self, fg_color="transparent", height=40)
        title_frame.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            title_frame,
            text=folder_data.get("name", "文件夹"),
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left", padx=10)

        app_count = len(folder_data.get("apps", []))
        ctk.CTkLabel(
            title_frame,
            text=f"({app_count} 个应用)",
            font=ctk.CTkFont(size=12),
            text_color=("#888888", "#666666")
        ).pack(side="left")

        # 滚动区域
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._render_apps()

        # 关闭时从主窗口字典中移除
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_acrylic_effect(self):
        """使用Windows DWM API设置亚克力效果（与主窗口保持一致）"""
        try:
            if sys.platform != "win32":
                return
            import ctypes
            from ctypes import wintypes

            hwnd = self.winfo_id()
            user32 = ctypes.windll.user32

            GetAncestor = user32.GetAncestor
            GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
            GetAncestor.restype = wintypes.HWND
            root_hwnd = GetAncestor(hwnd, 2)
            if root_hwnd:
                hwnd = root_hwnd

            DwmSetWindowAttribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.POINTER(ctypes.c_int), ctypes.c_uint]
            DwmSetWindowAttribute.restype = wintypes.HRESULT

            # DWMWA_SYSTEMBACKDROP_TYPE = 38, 2 = DWMSBT_ACRYLIC (亚克力效果)
            backdrop_type = ctypes.c_int(2)
            result = DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type))

            if result == 0:
                logger.debug("文件夹窗口亚克力效果设置成功")
            else:
                logger.debug(f"文件夹窗口亚克力效果失败 result={result}")
        except Exception as e:
            logger.debug(f"文件夹窗口亚克力效果异常: {e}")

    def _on_close(self):
        """窗口关闭时清理引用"""
        try:
            open_windows = getattr(self.parent_window, '_open_folder_windows', {})
            if self.folder_key in open_windows:
                del open_windows[self.folder_key]
                logger.debug(f"关闭文件夹窗口，移除引用: {self.folder_key}")
        except Exception:
            pass
        self.destroy()

    def _ensure_on_top(self):
        """确保窗口在最顶层"""
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _render_apps(self):
        """渲染文件夹内的应用"""
        # 清空
        for child in self.scroll_frame.winfo_children():
            child.destroy()

        apps = self.folder_data.get("apps", [])
        if not apps:
            ctk.CTkLabel(
                self.scroll_frame,
                text="文件夹为空\n从主界面右键应用可移动到这里",
                font=ctk.CTkFont(size=13),
                text_color=("#888888", "#666666"),
                justify="center"
            ).pack(pady=50)
            return

        # 网格布局
        from app_item import AppGridItem
        col = 0
        row = 0
        for app_data in apps:
            item = AppGridItem(
                self.scroll_frame,
                app_data=app_data,
                parent_window=self.parent_window,
                lazy_load=True
            )
            item.grid(row=row, column=col, padx=8, pady=8)

            # 给应用卡片额外加一个"移出文件夹"的右键选项
            self._add_remove_from_folder_menu(item, app_data)

            col += 1
            if col >= 4:
                col = 0
                row += 1

    def _add_remove_from_folder_menu(self, item, app_data):
        """给文件夹内的应用添加'移出文件夹'右键菜单"""
        original_right_click = item._on_right_click

        def enhanced_right_click(event):
            # 先显示原始菜单
            original_right_click(event)
            # 额外添加移出选项（通过在菜单后追加）
            # 简化处理：直接提供移出功能
            self._remove_app_from_folder(app_data)

        # 绑定中键点击移出文件夹（避免干扰原右键菜单）
        item.bind("<Button-2>", lambda e: self._remove_app_from_folder(app_data))
        item.icon_label.bind("<Button-2>", lambda e: self._remove_app_from_folder(app_data))

    def _remove_app_from_folder(self, app_data):
        """将应用移出文件夹，回到主分类"""
        try:
            apps = self.folder_data.get("apps", [])
            # 找到并移除
            target_path = app_data.get("path", "")
            for i, app in enumerate(apps):
                if app.get("path", "") == target_path:
                    removed = apps.pop(i)
                    # 加回到当前分类
                    current_cat = self.parent_window.current_category
                    if current_cat not in self.parent_window.app_config:
                        self.parent_window.app_config[current_cat] = []
                    self.parent_window.app_config[current_cat].append(removed)
                    break

            self.parent_window._save_config()
            self.parent_window._refresh_grid(force=True)
            self._render_apps()

            if self.on_changed:
                self.on_changed()

            logger.debug(f"应用已移出文件夹: {app_data.get('name')}")
        except Exception as e:
            logger.debug(f"移出文件夹失败: {e}")
