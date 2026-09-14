# -*- coding: utf-8 -*-
"""
应用网格项组件 - 单个应用卡片的UI和交互
包含：点击启动、右键菜单（移动分类/更换图标/重命名/删除等）、异步图标加载
"""
import os
import logging
import customtkinter as ctk
from tkinter import filedialog
from PIL import ImageTk
from icon_extractor import get_app_icon

logger = logging.getLogger("Win11Launcher")


class AppGridItem(ctk.CTkFrame):
    """应用网格项"""

    def __init__(self, parent, app_data: dict, parent_window=None, lazy_load=True):
        super().__init__(
            parent,
            width=100,
            height=100,
            fg_color=("#FFFFFF", "#2D2D2D"),
            corner_radius=8
        )
        self.app_data = app_data
        self.hover = False
        self.parent_window = parent_window
        self.icon_loaded = False

        self.pack_propagate(False)
        self._setup_ui(lazy_load=lazy_load)

        self.bind("<Button-1>", self._on_click)
        self.icon_label.bind("<Button-1>", self._on_click)
        self.bind("<Button-3>", self._on_right_click)
        self.icon_label.bind("<Button-3>", self._on_right_click)
        self.bind("<Enter>", self._on_enter)
        self.icon_label.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.icon_label.bind("<Leave>", self._on_leave)

    def _on_enter(self, event):
        """鼠标进入 - 高亮效果"""
        self.hover = True
        self.configure(
            fg_color=("#F0F8FF", "#3D3D3D"),
            border_width=2,
            border_color=("#0078D4", "#0078D4")
        )

    def _on_leave(self, event):
        """鼠标离开 - 恢复原状"""
        self.hover = False
        self.configure(
            fg_color=("#FFFFFF", "#2D2D2D"),
            border_width=0
        )

    def _on_click(self, event):
        """鼠标左键点击启动应用"""
        app_path = self.app_data.get("path", "")
        if app_path and os.path.exists(app_path):
            try:
                self._click_animation()
                logger.debug(f"启动应用: {app_path}")
                os.startfile(app_path)
            except Exception as e:
                logger.debug(f"启动失败: {e}")

    def _click_animation(self):
        """点击动画 - 闪烁效果"""
        self.configure(fg_color=("#D0D0D0", "#4D4D4D"))
        self.after(50, lambda: self._animate_stage2())

    def _animate_stage2(self):
        self.configure(fg_color=("#F0F8FF", "#3D3D3D"))
        self.after(100, lambda: self._animate_stage3())

    def _animate_stage3(self):
        if self.hover:
            self.configure(fg_color=("#F0F8FF", "#3D3D3D"))
        else:
            self.configure(fg_color=("#FFFFFF", "#2D2D2D"))

    def _on_right_click(self, event):
        """右键点击 - 显示上下文菜单"""
        self._show_context_menu(event.x_root, event.y_root)

    def _show_context_menu(self, x, y):
        """显示右键菜单 - Win11 风格"""
        appearance_mode = ctk.get_appearance_mode()

        if appearance_mode == "Dark":
            bg_color = "#2B2B2B"
            fg_color = "#FFFFFF"
            hover_color = "#404040"
            separator_color = "#3C3C3C"
        else:
            bg_color = "#F3F3F3"
            fg_color = "#000000"
            hover_color = "#E5E5E5"
            separator_color = "#E1E1E1"

        root = self.winfo_toplevel()

        def close_all_menus():
            if hasattr(root, '_global_context_menus'):
                for menu_win in root._global_context_menus[:]:
                    try:
                        if menu_win.winfo_exists():
                            menu_win.destroy()
                    except Exception:
                        pass
                root._global_context_menus.clear()
            if hasattr(root, '_current_submenu') and root._current_submenu:
                try:
                    if root._current_submenu.winfo_exists():
                        root._current_submenu.destroy()
                except Exception:
                    pass
                root._current_submenu = None
            for attr in ['_open_submenu_timer', '_close_submenu_timer', '_hover_timer']:
                if hasattr(root, attr):
                    timer = getattr(root, attr)
                    if timer:
                        try:
                            root.after_cancel(timer)
                        except Exception:
                            pass
                        setattr(root, attr, None)

        close_all_menus()

        menu_window = ctk.CTkToplevel(self)
        menu_window.overrideredirect(True)
        menu_window.attributes("-topmost", True)
        menu_window.attributes("-transparentcolor", "#000001")
        menu_window.attributes("-alpha", 0.95)

        if not hasattr(root, '_global_context_menus'):
            root._global_context_menus = []
        root._global_context_menus.append(menu_window)

        menu_frame = ctk.CTkFrame(menu_window, fg_color=bg_color, corner_radius=8)
        menu_frame.pack(fill="both", expand=True, padx=3, pady=3)

        submenu = None

        def close_submenu():
            nonlocal submenu
            if hasattr(root, '_close_submenu_timer') and root._close_submenu_timer:
                root.after_cancel(root._close_submenu_timer)
                root._close_submenu_timer = None
            if hasattr(root, '_open_submenu_timer') and root._open_submenu_timer:
                root.after_cancel(root._open_submenu_timer)
                root._open_submenu_timer = None
            if submenu and submenu.winfo_exists():
                submenu.destroy()
            submenu = None
            root._current_submenu = None

        def create_submenu():
            nonlocal submenu
            if submenu and submenu.winfo_exists():
                return

            submenu = ctk.CTkToplevel(self)
            submenu.overrideredirect(True)
            submenu.attributes("-topmost", True)

            submenu_height = len(self.parent_window.categories) * 28 + 8
            submenu_x = x + 165
            submenu_y = y + 50

            screen_height = submenu.winfo_screenheight()
            if submenu_y + submenu_height > screen_height:
                submenu_y = submenu_y - submenu_height - 50

            submenu.geometry(f"80x{submenu_height}+{submenu_x}+{submenu_y}")

            submenu_frame = ctk.CTkFrame(submenu, fg_color=bg_color, corner_radius=8)
            submenu_frame.pack(fill="both", expand=True, padx=3, pady=3)

            for cat in self.parent_window.categories:
                btn = ctk.CTkButton(
                    submenu_frame,
                    text=cat,
                    fg_color="transparent",
                    hover_color=hover_color,
                    text_color=fg_color,
                    command=lambda c=cat: (self._do_move_category(c), menu_window.destroy()),
                    anchor="w",
                    height=28,
                    font=ctk.CTkFont(size=13)
                )
                btn.pack(fill="x", padx=3)

            root._current_submenu = submenu

            def on_submenu_enter(event):
                if hasattr(root, '_close_submenu_timer') and root._close_submenu_timer:
                    root.after_cancel(root._close_submenu_timer)
                    root._close_submenu_timer = None

            def on_submenu_leave(event):
                if hasattr(root, '_open_submenu_timer') and root._open_submenu_timer:
                    root.after_cancel(root._open_submenu_timer)
                    root._open_submenu_timer = None
                if hasattr(root, '_close_submenu_timer') and root._close_submenu_timer:
                    root.after_cancel(root._close_submenu_timer)
                root._close_submenu_timer = root.after(120, close_submenu)

            submenu.bind("<Enter>", on_submenu_enter)
            submenu.bind("<Leave>", on_submenu_leave)

        def on_move_btn_enter(event):
            if hasattr(root, '_close_submenu_timer') and root._close_submenu_timer:
                root.after_cancel(root._close_submenu_timer)
                root._close_submenu_timer = None
            if hasattr(root, '_open_submenu_timer') and root._open_submenu_timer:
                root.after_cancel(root._open_submenu_timer)
            root._open_submenu_timer = root.after(120, create_submenu)

        def on_move_btn_leave(event):
            if hasattr(root, '_open_submenu_timer') and root._open_submenu_timer:
                root.after_cancel(root._open_submenu_timer)
                root._open_submenu_timer = None
            if hasattr(root, '_close_submenu_timer') and root._close_submenu_timer:
                root.after_cancel(root._close_submenu_timer)
            root._close_submenu_timer = root.after(120, close_submenu)

        def add_menu_item(label, command, is_separator=False):
            if is_separator:
                sep = ctk.CTkFrame(menu_frame, height=2, fg_color=separator_color)
                sep.pack(fill="x", padx=10, pady=4)
            else:
                btn = ctk.CTkButton(
                    menu_frame,
                    text=label,
                    fg_color="transparent",
                    hover_color=hover_color,
                    text_color=fg_color,
                    command=lambda: (command(), menu_window.destroy()),
                    anchor="w",
                    height=28,
                    font=ctk.CTkFont(size=13)
                )
                btn.pack(fill="x", padx=3)

        add_menu_item("启动", self._launch_app)
        add_menu_item("管理员身份启动", self._launch_as_admin)
        add_menu_item("", None, is_separator=True)

        move_btn = ctk.CTkButton(
            menu_frame,
            text="移动分类            ＞",
            fg_color="transparent",
            hover_color=hover_color,
            text_color=fg_color,
            anchor="w",
            height=28,
            font=ctk.CTkFont(size=13)
        )
        move_btn.pack(fill="x", padx=3)
        move_btn.bind("<Enter>", on_move_btn_enter)
        move_btn.bind("<Leave>", on_move_btn_leave)

        add_menu_item("", None, is_separator=True)
        add_menu_item("更换图标", self._change_icon)
        add_menu_item("重命名", self._rename_app)
        add_menu_item("", None, is_separator=True)
        add_menu_item("删除应用", self._delete_app)
        add_menu_item("清空当前分类", self._clear_category)
        add_menu_item("", None, is_separator=True)
        add_menu_item("打开文件位置", self._open_file_location)
        add_menu_item("属性", self._show_properties)

        width = 130
        height = 295

        screen_height = menu_window.winfo_screenheight()
        window_bottom = self.winfo_toplevel().winfo_y() + self.winfo_toplevel().winfo_height()

        if y + height > screen_height or (window_bottom - y < 250):
            y = y - height - 60

        menu_window.geometry(f"{width}x{height}+{x}+{y}")

        def on_esc(event):
            close_submenu()
            if menu_window.winfo_exists():
                menu_window.destroy()

        root.bind("<Escape>", on_esc, add=True)

        def on_click_outside(event):
            if menu_window.winfo_exists():
                mx, my = event.x_root, event.y_root
                wx, wy = menu_window.winfo_rootx(), menu_window.winfo_rooty()
                ww, wh = menu_window.winfo_width(), menu_window.winfo_height()
                in_menu = wx <= mx < wx + ww and wy <= my < wy + wh

                in_submenu = False
                if submenu and submenu.winfo_exists():
                    sx, sy = submenu.winfo_rootx(), submenu.winfo_rooty()
                    sw, sh = submenu.winfo_width(), submenu.winfo_height()
                    in_submenu = sx <= mx < sx + sw and sy <= my < sy + sh

                if not in_menu and not in_submenu:
                    close_submenu()
                    menu_window.destroy()

        root.bind("<Button-1>", on_click_outside, add=True)

        def on_destroy():
            close_submenu()
            root.unbind("<Escape>", on_esc)
            root.unbind("<Button-1>", on_click_outside)
            if hasattr(root, '_global_context_menus') and menu_window in root._global_context_menus:
                root._global_context_menus.remove(menu_window)

        menu_window.protocol("WM_DELETE_WINDOW", on_destroy)
        menu_window.bind("<Destroy>", lambda e: on_destroy())

    def _launch_app(self):
        """启动应用"""
        app_path = self.app_data.get("path", "")

        if app_path and os.path.exists(app_path):
            os.startfile(app_path)
            return

        original_path = self.app_data.get("original_path")
        if original_path and os.path.exists(original_path):
            try:
                import win32com.client
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortCut(original_path)
                target_path = shortcut.Targetpath
                if target_path and os.path.exists(target_path):
                    logger.debug(f"原始路径失效，从快捷方式解析新路径: {target_path}")
                    os.startfile(target_path)
                    return
            except Exception as e:
                logger.debug(f"从快捷方式解析目标路径失败: {e}")

        app_name = self.app_data.get("name", "")
        if app_name:
            found_path = self._search_app_in_common_paths(app_name)
            if found_path:
                logger.debug(f"在常见目录中找到程序: {found_path}")
                os.startfile(found_path)
                return

        if app_path:
            if hasattr(self.parent_window, '_show_message'):
                self.parent_window._show_message(f"程序不存在: {os.path.basename(app_path)}")

    def _search_app_in_common_paths(self, app_name: str) -> str:
        """在常见安装目录中搜索程序"""
        import glob

        search_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), '*', app_name + '.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), '*', app_name + '.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', 'C:\\Users\\' + os.environ.get('USERNAME', '') + '\\AppData\\Local'), 'Programs', '*', app_name + '.exe'),
        ]

        for pattern in search_paths:
            try:
                matches = glob.glob(pattern, recursive=True)
                if matches:
                    for match in matches:
                        if os.path.exists(match):
                            return match
            except Exception as e:
                logger.debug(f"搜索目录失败 {pattern}: {e}")

        try:
            import winreg
            app_name_lower = app_name.lower()

            for hkey_root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                for subkey in [r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                               r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"]:
                    try:
                        key = winreg.OpenKey(hkey_root, subkey)
                        if key:
                            i = 0
                            while True:
                                try:
                                    name, data, _ = winreg.EnumValue(key, i)
                                    i += 1
                                    if name and 'displayname' in name.lower():
                                        try:
                                            display_name = data.lower()
                                            if app_name_lower in display_name:
                                                try:
                                                    install_key = winreg.OpenKey(hkey_root, subkey + '\\' + name.split()[0] if '\\' not in name else subkey + '\\' + name)
                                                    install_location, _ = winreg.QueryValueEx(install_key, 'InstallLocation')
                                                    if install_location and os.path.exists(install_location):
                                                        for exe_file in glob.glob(os.path.join(install_location, '*.exe')):
                                                            if app_name_lower in exe_file.lower():
                                                                return exe_file
                                                    winreg.CloseKey(install_key)
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                                except OSError:
                                    break
                            winreg.CloseKey(key)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"注册表搜索失败: {e}")

        return None

    def _launch_as_admin(self):
        """管理员身份启动应用"""
        app_path = self.app_data.get("path", "")
        if app_path and os.path.exists(app_path):
            try:
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(None, "runas", app_path, None, None, 1)
            except Exception as e:
                logger.debug(f"管理员启动失败: {e}")

    def _do_move_category(self, target_category):
        """执行移动分类"""
        if not self.parent_window:
            return

        current_category = self.parent_window.current_category
        if target_category == current_category:
            return

        app_path = self.app_data.get("path", "")

        apps = self.parent_window.app_config[current_category]
        for idx, app in enumerate(apps):
            if app.get("path", "") == app_path:
                del self.parent_window.app_config[current_category][idx]
                break

        self.parent_window.app_config[target_category].append(self.app_data)

        self.parent_window.category_items_cache[current_category].clear()
        self.parent_window.category_items_cache[target_category].clear()

        self.parent_window._refresh_grid(force=True)
        self.parent_window._save_config()

    def _delete_app(self):
        """删除应用"""
        if not self.parent_window:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("确认删除")
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        app_name = self.app_data.get("name", "此应用")
        label = ctk.CTkLabel(dialog, text=f"确定要删除 \"{app_name}\" 吗？", font=ctk.CTkFont(size=14))
        label.pack(pady=(30, 20))

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=10)

        def confirm_delete():
            current_category = self.parent_window.current_category
            app_path = self.app_data.get("path", "")
            apps = self.parent_window.app_config[current_category]

            target_path = os.path.normpath(app_path).lower() if app_path else ""
            target_name = self.app_data.get("name", "")

            indices_to_delete = []
            for idx, app in enumerate(apps):
                app_path_in_config = app.get("path", "")
                config_path = os.path.normpath(app_path_in_config).lower() if app_path_in_config else ""
                app_name = app.get("name", "")

                if config_path == target_path or app_name == target_name:
                    indices_to_delete.append(idx)

            for idx in reversed(indices_to_delete):
                self.parent_window.app_config[current_category].pop(idx)

            self.parent_window.category_items_cache[current_category].clear()
            self.parent_window._refresh_grid(force=True)
            self.parent_window._save_config()
            dialog.destroy()

        confirm_btn = ctk.CTkButton(
            button_frame,
            text="删除",
            width=100,
            fg_color="#e74c3c",
            hover_color="#c0392b",
            command=confirm_delete
        )
        confirm_btn.pack(side="left", padx=10)

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="取消",
            width=100,
            command=dialog.destroy
        )
        cancel_btn.pack(side="left", padx=10)

    def _clear_category(self):
        """清空当前分类"""
        if not self.parent_window:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("确认清空")
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        current_category = self.parent_window.current_category
        app_count = len(self.parent_window.app_config[current_category])
        label = ctk.CTkLabel(dialog, text=f"确定要清空 \"{current_category}\" 分类吗？\n（共 {app_count} 个应用）", font=ctk.CTkFont(size=14))
        label.pack(pady=(30, 20))

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=10)

        def confirm_clear():
            current_category = self.parent_window.current_category
            self.parent_window.app_config[current_category].clear()
            self.parent_window.category_items_cache[current_category].clear()
            self.parent_window._refresh_grid(force=True)
            self.parent_window._save_config()
            dialog.destroy()

        confirm_btn = ctk.CTkButton(
            button_frame,
            text="清空",
            width=100,
            fg_color="#e74c3c",
            hover_color="#c0392b",
            command=confirm_clear
        )
        confirm_btn.pack(side="left", padx=10)

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="取消",
            width=100,
            command=dialog.destroy
        )
        cancel_btn.pack(side="left", padx=10)

    def _change_icon(self):
        """更换图标"""
        file_path = filedialog.askopenfilename(
            title="选择图标文件",
            filetypes=[
                ("图标文件", "*.ico"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.app_data["icon_path"] = file_path
            for widget in self.winfo_children():
                widget.destroy()
            self._setup_ui()

    def _rename_app(self):
        """重命名应用"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("重命名")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2
        y = (dialog.winfo_screenheight() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        label = ctk.CTkLabel(dialog, text="输入新名称:", font=ctk.CTkFont(size=14))
        label.pack(pady=(20, 10))

        entry = ctk.CTkEntry(dialog, width=200)
        entry.insert(0, self.app_data.get("name", ""))
        entry.pack(pady=10)

        def save_rename():
            new_name = entry.get().strip()
            if new_name:
                self.app_data["name"] = new_name
                for widget in self.winfo_children():
                    widget.destroy()
                self._setup_ui()
            dialog.destroy()

        btn = ctk.CTkButton(dialog, text="确定", width=80, command=save_rename)
        btn.pack(pady=10)

    def _open_file_location(self):
        """打开文件位置"""
        app_path = self.app_data.get("path", "")
        if app_path:
            if os.path.isfile(app_path):
                os.startfile(os.path.dirname(app_path))
            elif os.path.isdir(app_path):
                os.startfile(app_path)

    def _show_properties(self):
        """显示属性"""
        import subprocess
        import ctypes
        from ctypes import wintypes

        app_path = self.app_data.get("path", "")
        if not app_path or not os.path.exists(app_path):
            return

        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "properties", app_path, None, None, 1
            )
            if result > 32:
                return
        except Exception:
            pass

        try:
            class SHELLEXECUTEINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("fMask", wintypes.ULONG),
                    ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", wintypes.LPCVOID),
                    ("lpClass", wintypes.LPCWSTR),
                    ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD),
                    ("hIconOrMonitor", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE)
                ]

            sei = SHELLEXECUTEINFO()
            sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFO)
            sei.fMask = 0x0000000C
            sei.hwnd = None
            sei.lpVerb = "properties"
            sei.lpFile = app_path
            sei.nShow = 1

            result = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
            if result:
                return
        except Exception:
            pass

        try:
            subprocess.Popen(['explorer.exe', f'/select,{app_path}'])
        except Exception:
            pass

    def _setup_ui(self, lazy_load=True):
        """设置UI"""
        initial_text = self.app_data.get("name", "App")[:1].upper()
        self.icon_label = ctk.CTkLabel(
            self,
            text=initial_text,
            width=48,
            height=48,
            fg_color=("#0078D4", "#005A9E"),
            corner_radius=8,
            font=ctk.CTkFont(size=24, weight="bold")
        )
        self.icon_label.pack(pady=(12, 4))

        name_label = ctk.CTkLabel(
            self,
            text=self.app_data.get("name", "App"),
            font=ctk.CTkFont(size=11),
            text_color=("#1A1A1A", "#E0E0E0"),
            wraplength=90
        )
        name_label.pack(pady=(0, 8))

        if lazy_load:
            self._load_icon_async()

    def _load_icon_async(self):
        """异步加载图标 - 使用线程池"""
        def extract_icon():
            app_path = self.app_data.get("path", "")
            icon_path = self.app_data.get("icon_path", None)
            original_path = self.app_data.get("original_path", None)

            if not app_path:
                return None
            try:
                return get_app_icon(app_path, icon_path, size=48, original_path=original_path)
            except Exception as e:
                logger.debug(f"图标提取失败 {app_path}: {e}")
                return None

        def update_ui(icon_img):
            if icon_img:
                try:
                    photo_img = ImageTk.PhotoImage(icon_img)
                    self.icon_label.configure(
                        text="",
                        image=photo_img,
                        fg_color="transparent"
                    )
                    self.icon_label.image = photo_img
                    self.icon_loaded = True
                except Exception as e:
                    logger.debug(f"图标UI更新失败: {e}")

        def on_done(future):
            try:
                icon_img = future.result()
                self.after(0, lambda: update_ui(icon_img))
            except Exception as e:
                logger.debug(f"图标任务异常: {e}")

        if self.parent_window and hasattr(self.parent_window, 'icon_executor'):
            future = self.parent_window.icon_executor.submit(extract_icon)
            future.add_done_callback(on_done)
        else:
            self.after_idle(lambda: update_ui(extract_icon()))
