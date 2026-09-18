# -*- coding: utf-8 -*-
"""
文件夹窗口模块 - 点击文件夹后弹出，显示文件夹内的应用
"""
import os
import sys
import logging
import customtkinter as ctk

logger = logging.getLogger("Win11Launcher")


class FolderWindow(ctk.CTkToplevel):
    """文件夹内容窗口"""

    def __init__(self, parent, folder_data, folder_key, on_changed=None, anchor_x=None, anchor_y=None):
        """
        Args:
            parent: 主窗口
            folder_data: 文件夹数据 dict (含 name, apps)
            folder_key: 文件夹标识 (分类名_文件夹名)
            on_changed: 内容变更回调
            anchor_x, anchor_y: 动画起始位置（文件夹图标中心），None则居中
        """
        super().__init__(parent)
        # 先隐藏窗口，设置好标题栏颜色后再显示，避免白色闪烁
        self.withdraw()
        self.parent_window = parent
        self.folder_data = folder_data
        self.folder_key = folder_key
        self.on_changed = on_changed
        self._anchor_x = anchor_x
        self._anchor_y = anchor_y
        self._target_w = 500
        self._target_h = 400
        self._is_closing = False

        self.title(folder_data.get("name", "文件夹"))
        self.configure(fg_color=("#F3F3F3", "#202020"))

        # 设置目标透明度（与主窗口保持一致）
        alpha = getattr(parent, 'alpha_var', None)
        self._target_alpha = alpha.get() if alpha and alpha.get() > 0 else 0.96

        # 设置亚克力透明效果（与主窗口保持一致）
        self._setup_acrylic_effect()

        # 关键：设置为父窗口的临时窗口，确保始终在主窗口之上
        self.transient(parent)
        self.attributes("-topmost", True)
        self.lift()

        # 普通展开：窗口直接以目标大小居中显示
        self.update_idletasks()
        self._target_x = (self.winfo_screenwidth() - self._target_w) // 2
        self._target_y = (self.winfo_screenheight() - self._target_h) // 2
        self.geometry(f"{self._target_w}x{self._target_h}+{self._target_x}+{self._target_y}")
        self.attributes('-alpha', self._target_alpha)
        self.update_idletasks()
        # 窗口句柄就绪后立即设置DWM标题栏颜色（此时窗口仍隐藏，无闪烁）
        self._setup_titlebar_color()

        # 顶部标题栏
        title_frame = ctk.CTkFrame(self, fg_color="transparent", height=40)
        title_frame.pack(fill="x", padx=10, pady=(10, 5))

        app_count = len(folder_data.get("apps", []))
        ctk.CTkLabel(
            title_frame,
            text=f"{folder_data.get('name', '文件夹')}  ({app_count} 个应用)",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w"
        ).pack(side="left", padx=10)

        # 内容区域自然填充窗口
        self._content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._content_frame.pack(fill="both", expand=True)

        self.scroll_frame = ctk.CTkScrollableFrame(self._content_frame, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._render_apps()

        # 关闭时从主窗口字典中移除
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 显示窗口（标题栏颜色已设置好，无白色闪烁）
        self.deiconify()
        self.focus_force()
        self.after(50, self._ensure_on_top)
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

    def _setup_titlebar_color(self):
        """设置DWM标题栏颜色（与主窗口一致）"""
        try:
            if sys.platform != "win32":
                return
            import ctypes
            from ctypes import wintypes
            is_dark = ctk.get_appearance_mode().lower() == "dark"
            hwnd = self.winfo_id()
            user32 = ctypes.windll.user32
            root_hwnd = user32.GetAncestor(hwnd, 2)
            if root_hwnd:
                hwnd = root_hwnd
            dwmapi = ctypes.windll.dwmapi
            # ImmersiveDarkMode
            try:
                dark_val = ctypes.c_int(1 if is_dark else 0)
                dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_val), ctypes.sizeof(dark_val))
            except Exception:
                pass
            # CaptionColor
            try:
                rgb = (31, 31, 31) if is_dark else (243, 243, 243)
                caption = (rgb[2] << 16) | (rgb[1] << 8) | rgb[0]
                color_val = ctypes.c_int(caption)
                dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color_val), ctypes.sizeof(color_val))
            except Exception:
                pass
            # 强制刷新非客户区
            try:
                user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004)
                user32.SendMessageW(hwnd, 0x031A, 0, 0)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"文件夹窗口标题栏着色失败: {e}")

    def update_theme(self):
        """主题切换时调用：更新标题栏颜色 + 重新应用亚克力"""
        try:
            self._setup_titlebar_color()
            self._setup_acrylic_effect()
        except Exception as e:
            logger.debug(f"文件夹窗口主题更新失败: {e}")

    def _on_close(self):
        """窗口关闭：直接销毁"""
        try:
            open_windows = getattr(self.parent_window, '_open_folder_windows', {})
            if self.folder_key in open_windows:
                del open_windows[self.folder_key]
                logger.debug(f"关闭文件夹窗口，移除引用: {self.folder_key}")
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

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
                lazy_load=False,
                in_folder=True
            )
            item.folder_window = self  # 设置文件夹窗口引用
            item.grid(row=row, column=col, padx=8, pady=8)

            # 给应用卡片额外加一个"移出文件夹"的右键选项

            col += 1
            if col >= 4:
                col = 0
                row += 1

    def _open_file_location(self, app_data):
        """打开应用文件所在位置"""
        try:
            import subprocess
            app_path = app_data.get("path", "")
            if app_path and os.path.exists(app_path):
                subprocess.Popen(['explorer.exe', '/select,', app_path])
        except Exception as e:
            logger.debug(f"打开文件位置失败: {e}")

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
