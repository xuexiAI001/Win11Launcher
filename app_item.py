# -*- coding: utf-8 -*-
"""
应用网格项组件 - 单个应用卡片的UI和交互
包含：点击启动、右键菜单（移动分类/更换图标/重命名/删除等）、异步图标加载
"""
import os
import logging
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
from PIL import ImageTk
from icon_extractor import get_app_icon
from folder_window import FolderWindow

logger = logging.getLogger("Win11Launcher")


def _enable_menu_shadow(menu_win):
    """给无边框菜单窗口添加 Windows DWM 阴影并移除边框"""
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = ctypes.windll.user32.GetParent(menu_win.winfo_id())

        # 移除窗口边框样式
        GWL_STYLE = -16
        WS_BORDER = 0x00800000
        WS_THICKFRAME = 0x00040000
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        style &= ~WS_BORDER
        style &= ~WS_THICKFRAME
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        # 启用 DWM 阴影
        DWMWA_DROPSHADOW = 2
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_DROPSHADOW,
            ctypes.byref(val), ctypes.sizeof(val)
        )
    except Exception as e:
        logger.debug(f"设置菜单阴影失败: {e}")


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
        self.is_folder = app_data.get("type") == "folder"
        self._drag_start = None  # 拖拽起始位置
        self._is_dragging = False

        self.pack_propagate(False)
        self._setup_ui(lazy_load=lazy_load)

        self.bind("<Button-1>", self._on_click)
        self.icon_label.bind("<Button-1>", self._on_click)
        # 拖拽支持
        self.bind("<ButtonPress-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_motion)
        self.bind("<ButtonRelease-1>", self._on_drag_release)
        self.icon_label.bind("<ButtonPress-1>", self._on_drag_start)
        self.icon_label.bind("<B1-Motion>", self._on_drag_motion)
        self.icon_label.bind("<ButtonRelease-1>", self._on_drag_release)
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
        """鼠标左键点击 - 文件夹打开窗口，应用启动"""
        if self._is_dragging:
            self._is_dragging = False
            return
        if self.is_folder:
            self._open_folder()
            return
        app_path = self.app_data.get("path", "")
        if app_path and os.path.exists(app_path):
            try:
                self._click_animation()
                logger.debug(f"启动应用: {app_path}")
                os.startfile(app_path)
            except Exception as e:
                logger.debug(f"启动失败: {e}")

    def _on_drag_start(self, event):
        """记录拖拽起始位置"""
        self._drag_start = (event.x_root, event.y_root)
        self._is_dragging = False

    def _on_drag_motion(self, event):
        """拖拽移动：超过阈值进入拖拽模式"""
        if self._drag_start is None or self.is_folder:
            return
        dx = abs(event.x_root - self._drag_start[0])
        dy = abs(event.y_root - self._drag_start[1])
        if dx > 8 or dy > 8:
            self._is_dragging = True
            # 拖拽视觉反馈
            self.configure(fg_color=("#0078D4", "#005A9E"))

    def _on_drag_release(self, event):
        """拖拽释放：检测是否在文件夹上"""
        if not self._is_dragging:
            self._drag_start = None
            return

        self._is_dragging = False
        self._drag_start = None
        self.configure(fg_color=("#FFFFFF", "#2D2D2D"))

        # 查找释放位置下的文件夹卡片
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
            target = widget
            while target:
                if hasattr(target, 'is_folder') and getattr(target, 'is_folder', False):
                    # 移动到文件夹
                    folder_name = target.app_data.get("name")
                    if folder_name and self.parent_window:
                        self.parent_window._move_app_to_folder(self.app_data, folder_name)
                    return
                target = getattr(target, 'master', None)
        except Exception as e:
            logger.debug(f"拖拽释放检测失败: {e}")

    def _open_folder(self):
        """打开文件夹窗口 - 单例模式，同一文件夹只打开一个"""
        try:
            folder_key = f"{self.parent_window.current_category}_{self.app_data.get('name')}"
            open_windows = getattr(self.parent_window, '_open_folder_windows', {})

            # 检查是否已打开
            if folder_key in open_windows:
                win = open_windows[folder_key]
                try:
                    if win.winfo_exists():
                        win.deiconify()
                        win.lift()
                        win.focus_force()
                        logger.debug(f"文件夹已打开，聚焦: {folder_key}")
                        return
                except Exception:
                    pass
                # 窗口已销毁，移除旧引用
                del open_windows[folder_key]

            # 创建新窗口
            win = FolderWindow(
                self.parent_window,
                self.app_data,
                folder_key,
                on_changed=lambda: self.parent_window._refresh_grid(force=True)
            )
            open_windows[folder_key] = win
            logger.debug(f"打开文件夹窗口: {folder_key}")
        except Exception as e:
            logger.debug(f"打开文件夹失败: {e}")

    def _create_and_move_to_folder(self):
        """新建文件夹并将当前应用移入"""
        if not self.parent_window:
            return
        dialog = ctk.CTkToplevel(self)
        dialog.title("新建文件夹")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 300) // 2
        y = (dialog.winfo_screenheight() - 150) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dialog, text="文件夹名称:", font=ctk.CTkFont(size=14)).pack(pady=(20, 10))
        entry = ctk.CTkEntry(dialog, width=200)
        entry.insert(0, f"文件夹{len(self.parent_window._get_folders()) + 1}")
        entry.pack(pady=10)

        def confirm():
            name = entry.get().strip()
            if name:
                self.parent_window._create_folder(name)
                self.parent_window._move_app_to_folder(self.app_data, name)
            dialog.destroy()

        ctk.CTkButton(dialog, text="确定", width=80, command=confirm).pack(pady=10)



    def _show_folder_menu(self, x, y):
        """文件夹右键菜单"""
        appearance_mode = ctk.get_appearance_mode()
        if appearance_mode == "Dark":
            bg_color = "#323232"
            fg_color = "#FFFFFF"
            hover_color = "#3D3D3D"
            separator_color = "#3C3C3C"
        else:
            bg_color = "#FFFFFF"
            fg_color = "#1A1A1A"
            hover_color = "#E8F0FE"
            separator_color = "#E5E5E5"

        root = self.winfo_toplevel()

        # 关闭其他已打开的菜单
        if hasattr(root, '_global_context_menus'):
            for menu_win in root._global_context_menus[:]:
                try:
                    if menu_win.winfo_exists():
                        menu_win.destroy()
                except Exception:
                    pass
            root._global_context_menus.clear()

        menu_window = tk.Toplevel(self)
        menu_window.overrideredirect(True)
        menu_window.attributes("-topmost", True)
        menu_window.config(bg="#000001")
        menu_window.attributes("-transparentcolor", "#000001")

        if not hasattr(root, '_global_context_menus'):
            root._global_context_menus = []
        root._global_context_menus.append(menu_window)

        menu_frame = ctk.CTkFrame(menu_window, fg_color=bg_color, corner_radius=8)
        menu_frame.pack(fill="both", expand=True, padx=0, pady=0)

        def add_item(label, command, icon=""):
            display_text = f"  {icon}  {label}" if icon else f"    {label}"
            btn = ctk.CTkButton(
                menu_frame,
                text=display_text,
                fg_color="transparent",
                hover_color=hover_color,
                text_color=fg_color,
                command=lambda: (command(), menu_window.destroy()),
                anchor="w",
                height=32,
                corner_radius=4,
                font=ctk.CTkFont(size=13)
            )
            btn.pack(fill="x", padx=4, pady=1)

        def add_sep():
            sep = ctk.CTkFrame(menu_frame, height=1, fg_color=separator_color)
            sep.pack(fill="x", padx=12, pady=5)

        add_item("打开", self._open_folder, icon="▶")
        add_item("重命名", self._rename_folder, icon="✎")
        add_sep()
        add_item("删除文件夹", self._delete_folder, icon="✕")

        width = 130
        height = 3 * 34 + 11 + 16

        # 屏幕边界检测
        screen_w = menu_window.winfo_screenwidth()
        screen_h = menu_window.winfo_screenheight()
        if x + width > screen_w:
            x = screen_w - width - 5
        if y + height > screen_h:
            y = y - height - 10

        menu_window.geometry(f"{width}x{height}+{x}+{y}")
        menu_window.update_idletasks()
        _enable_menu_shadow(menu_window)

        def on_esc(event):
            if menu_window.winfo_exists():
                menu_window.destroy()

        def on_click_outside(event):
            if menu_window.winfo_exists():
                mx, my = event.x_root, event.y_root
                wx, wy = menu_window.winfo_rootx(), menu_window.winfo_rooty()
                ww, wh = menu_window.winfo_width(), menu_window.winfo_height()
                if not (wx <= mx < wx + ww and wy <= my < wy + wh):
                    menu_window.destroy()

        def on_destroy():
            try:
                root.unbind("<Escape>", on_esc)
            except Exception:
                pass
            try:
                root.unbind("<Button-1>", on_click_outside)
            except Exception:
                pass
            if hasattr(root, '_global_context_menus') and menu_window in root._global_context_menus:
                root._global_context_menus.remove(menu_window)

        root.bind("<Escape>", on_esc, add=True)
        root.bind("<Button-1>", on_click_outside, add=True)
        menu_window.protocol("WM_DELETE_WINDOW", on_destroy)
        menu_window.bind("<Destroy>", lambda e: on_destroy())

    def _rename_folder(self):
        """重命名文件夹"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("重命名文件夹")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 300) // 2
        y = (dialog.winfo_screenheight() - 150) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dialog, text="输入新名称:", font=ctk.CTkFont(size=14)).pack(pady=(20, 10))
        entry = ctk.CTkEntry(dialog, width=200)
        entry.insert(0, self.app_data.get("name", ""))
        entry.pack(pady=10)

        def save():
            new_name = entry.get().strip()
            if new_name:
                self.app_data["name"] = new_name
                self.parent_window._save_config()
                self.parent_window._refresh_grid(force=True)
            dialog.destroy()

        ctk.CTkButton(dialog, text="确定", width=80, command=save).pack(pady=10)

    def _delete_folder(self):
        """删除文件夹（应用移回主分类）"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("确认删除")
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 350) // 2
        y = (dialog.winfo_screenheight() - 180) // 2
        dialog.geometry(f"+{x}+{y}")

        name = self.app_data.get("name", "此文件夹")
        count = len(self.app_data.get("apps", []))
        ctk.CTkLabel(
            dialog,
            text=f'删除文件夹 "{name}"？\n（{count}个应用将移回主分类）',
            font=ctk.CTkFont(size=14),
            justify="center"
        ).pack(pady=(30, 20))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)

        def confirm():
            current_cat = self.parent_window.current_category
            # 文件夹内应用移回主分类
            for app in self.app_data.get("apps", []):
                self.parent_window.app_config[current_cat].append(app)
            # 移除文件夹
            apps_list = self.parent_window.app_config[current_cat]
            target_name = self.app_data.get("name")
            for i, item in enumerate(apps_list):
                if item.get("type") == "folder" and item.get("name") == target_name:
                    del apps_list[i]
                    break
            self.parent_window._save_config()
            self.parent_window._refresh_grid(force=True)
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="删除", width=100, fg_color="#e74c3c",
                       hover_color="#c0392b", command=confirm).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="取消", width=100, command=dialog.destroy).pack(side="left", padx=10)


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
        # 文件夹显示专用菜单
        if self.is_folder:
            self._show_folder_menu(x, y)
            return



        if appearance_mode == "Dark":
            bg_color = "#323232"
            fg_color = "#FFFFFF"
            hover_color = "#3D3D3D"
            separator_color = "#3C3C3C"
        else:
            bg_color = "#FFFFFF"
            fg_color = "#1A1A1A"
            hover_color = "#E8F0FE"
            separator_color = "#E5E5E5"

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
            # 清理分类子菜单
            if hasattr(root, '_current_submenu') and root._current_submenu:
                try:
                    if root._current_submenu.winfo_exists():
                        root._current_submenu.destroy()
                except Exception:
                    pass
                root._current_submenu = None
            # 清理文件夹子菜单
            if hasattr(root, '_current_folder_submenu') and root._current_folder_submenu:
                try:
                    if root._current_folder_submenu.winfo_exists():
                        root._current_folder_submenu.destroy()
                except Exception:
                    pass
                root._current_folder_submenu = None
            for attr in ['_open_submenu_timer', '_close_submenu_timer', '_hover_timer',
                         '_open_folder_timer', '_close_folder_timer']:
                if hasattr(root, attr):
                    timer = getattr(root, attr)
                    if timer:
                        try:
                            root.after_cancel(timer)
                        except Exception:
                            pass
                        setattr(root, attr, None)

        close_all_menus()

        menu_window = tk.Toplevel(self)
        menu_window.overrideredirect(True)
        menu_window.attributes("-topmost", True)
        menu_window.config(bg="#000001")
        menu_window.attributes("-transparentcolor", "#000001")

        if not hasattr(root, '_global_context_menus'):
            root._global_context_menus = []
        root._global_context_menus.append(menu_window)

        menu_frame = ctk.CTkFrame(menu_window, fg_color=bg_color, corner_radius=8)
        menu_frame.pack(fill="both", expand=True, padx=0, pady=0)

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
            set_move_arrow("›")

        def create_submenu():
            nonlocal submenu
            if submenu and submenu.winfo_exists():
                return

            submenu = tk.Toplevel(self)
            submenu.overrideredirect(True)
            submenu.attributes("-topmost", True)
            submenu.config(bg="#000001")
            submenu.attributes("-transparentcolor", "#000001")

            submenu_height = len(self.parent_window.categories) * 34 + 8
            submenu_x = x + 155
            submenu_y = y + 40

            screen_height = submenu.winfo_screenheight()
            if submenu_y + submenu_height > screen_height:
                submenu_y = submenu_y - submenu_height - 50

            submenu.geometry(f"120x{submenu_height}+{submenu_x}+{submenu_y}")
            submenu.update_idletasks()
            _enable_menu_shadow(submenu)

            submenu_frame = ctk.CTkFrame(submenu, fg_color=bg_color, corner_radius=8)
            submenu_frame.pack(fill="both", expand=True, padx=0, pady=0)

            for cat in self.parent_window.categories:
                btn = ctk.CTkButton(
                    submenu_frame,
                    text="    " + cat,
                    fg_color="transparent",
                    hover_color=hover_color,
                    text_color=fg_color,
                    command=lambda c=cat: (self._do_move_category(c), menu_window.destroy()),
                    anchor="w",
                    height=32,
                    corner_radius=4,
                    font=ctk.CTkFont(size=13)
                )
                btn.pack(fill="x", padx=4, pady=1)

            root._current_submenu = submenu
            set_move_arrow("⌄")

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

        def add_menu_item(label, command, icon="", is_separator=False):
            if is_separator:
                sep = ctk.CTkFrame(menu_frame, height=1, fg_color=separator_color)
                sep.pack(fill="x", padx=12, pady=5)
            else:
                display_text = f"  {icon}  {label}" if icon else f"    {label}"
                btn = ctk.CTkButton(
                    menu_frame,
                    text=display_text,
                    fg_color="transparent",
                    hover_color=hover_color,
                    text_color=fg_color,
                    command=lambda: (command(), menu_window.destroy()),
                    anchor="w",
                    height=32,
                    corner_radius=4,
                    font=ctk.CTkFont(size=13)
                )
                btn.pack(fill="x", padx=4, pady=1)

        add_menu_item("启动", self._launch_app, icon="▶")
        add_menu_item("管理员身份启动", self._launch_as_admin, icon="⬆")
        add_menu_item("", None, is_separator=True)

        move_btn = ctk.CTkButton(
            menu_frame,
            text="  ⇄  移动分类            ›",
            fg_color="transparent",
            hover_color=hover_color,
            text_color=fg_color,
            anchor="w",
            height=32,
            corner_radius=4,
            font=ctk.CTkFont(size=13)
        )
        move_btn.pack(fill="x", padx=4, pady=1)
        move_btn.bind("<Enter>", on_move_btn_enter)
        move_btn.bind("<Leave>", on_move_btn_leave)

        def set_move_arrow(arrow):
            move_btn.configure(text=f"  ⇄  移动分类            {arrow}")

        # 移动到文件夹 - 二级菜单
        folder_submenu = None

        def close_folder_submenu():
            nonlocal folder_submenu
            if hasattr(root, '_open_folder_timer') and root._open_folder_timer:
                root.after_cancel(root._open_folder_timer)
                root._open_folder_timer = None
            if hasattr(root, '_close_folder_timer') and root._close_folder_timer:
                root.after_cancel(root._close_folder_timer)
                root._close_folder_timer = None
            if folder_submenu and folder_submenu.winfo_exists():
                folder_submenu.destroy()
            folder_submenu = None
            root._current_folder_submenu = None
            set_folder_arrow("›")

        def create_folder_submenu():
            nonlocal folder_submenu
            if folder_submenu and folder_submenu.winfo_exists():
                return
            folder_submenu = tk.Toplevel(self)
            folder_submenu.overrideredirect(True)
            folder_submenu.attributes("-topmost", True)
            folder_submenu.config(bg="#000001")
            folder_submenu.attributes("-transparentcolor", "#000001")

            folders = self.parent_window._get_folders() if self.parent_window else []
            submenu_height = (len(folders) + 2) * 34 + 11
            submenu_x = x + 155
            submenu_y = y + 75
            screen_h = folder_submenu.winfo_screenheight()
            if submenu_y + submenu_height > screen_h:
                submenu_y = submenu_y - submenu_height - 80
            folder_submenu.geometry(f"140x{submenu_height}+{submenu_x}+{submenu_y}")
            folder_submenu.update_idletasks()
            _enable_menu_shadow(folder_submenu)

            sf_frame = ctk.CTkFrame(folder_submenu, fg_color=bg_color, corner_radius=8)
            sf_frame.pack(fill="both", expand=True, padx=0, pady=0)

            for folder in folders:
                fname = folder.get("name", "")
                btn = ctk.CTkButton(
                    sf_frame, text="    " + fname, fg_color="transparent",
                    hover_color=hover_color, text_color=fg_color,
                    command=lambda f=fname: (self.parent_window._move_app_to_folder(self.app_data, f), menu_window.destroy()),
                    anchor="w", height=32, corner_radius=4, font=ctk.CTkFont(size=13)
                )
                btn.pack(fill="x", padx=4, pady=1)

            # 分隔线
            ctk.CTkFrame(sf_frame, height=1, fg_color=separator_color).pack(fill="x", padx=12, pady=5)

            # 新建文件夹
            ctk.CTkButton(
                sf_frame, text="    新建文件夹...", fg_color="transparent",
                hover_color=hover_color, text_color=fg_color,
                command=lambda: (self._create_and_move_to_folder(), menu_window.destroy()),
                anchor="w", height=32, corner_radius=4, font=ctk.CTkFont(size=13)
            ).pack(fill="x", padx=4, pady=1)

            root._current_folder_submenu = folder_submenu
            set_folder_arrow("⌄")

            # 文件夹子菜单鼠标事件
            def on_fsub_enter(event):
                if hasattr(root, '_close_folder_timer') and root._close_folder_timer:
                    root.after_cancel(root._close_folder_timer)
                    root._close_folder_timer = None

            def on_fsub_leave(event):
                if hasattr(root, '_open_folder_timer') and root._open_folder_timer:
                    root.after_cancel(root._open_folder_timer)
                    root._open_folder_timer = None
                if hasattr(root, '_close_folder_timer') and root._close_folder_timer:
                    root.after_cancel(root._close_folder_timer)
                root._close_folder_timer = root.after(120, close_folder_submenu)

            folder_submenu.bind("<Enter>", on_fsub_enter)
            folder_submenu.bind("<Leave>", on_fsub_leave)

        def on_folder_btn_enter(event):
            close_submenu()  # 关闭分类子菜单
            if hasattr(root, '_close_folder_timer') and root._close_folder_timer:
                root.after_cancel(root._close_folder_timer)
                root._close_folder_timer = None
            if hasattr(root, '_open_folder_timer') and root._open_folder_timer:
                root.after_cancel(root._open_folder_timer)
            root._open_folder_timer = root.after(120, create_folder_submenu)

        def on_folder_btn_leave(event):
            if hasattr(root, '_open_folder_timer') and root._open_folder_timer:
                root.after_cancel(root._open_folder_timer)
                root._open_folder_timer = None
            if hasattr(root, '_close_folder_timer') and root._close_folder_timer:
                root.after_cancel(root._close_folder_timer)
            root._close_folder_timer = root.after(120, close_folder_submenu)

        folder_btn = ctk.CTkButton(
            menu_frame,
            text="  →  移动到文件夹        ›",
            fg_color="transparent",
            hover_color=hover_color,
            text_color=fg_color,
            anchor="w",
            height=32,
            corner_radius=4,
            font=ctk.CTkFont(size=13)
        )
        folder_btn.pack(fill="x", padx=4, pady=1)
        folder_btn.bind("<Enter>", on_folder_btn_enter)
        folder_btn.bind("<Leave>", on_folder_btn_leave)

        def set_folder_arrow(arrow):
            folder_btn.configure(text=f"  →  移动到文件夹        {arrow}")

        add_menu_item("", None, is_separator=True)
        add_menu_item("更换图标", self._change_icon, icon="◉")
        add_menu_item("重命名", self._rename_app, icon="✎")
        add_menu_item("", None, is_separator=True)
        add_menu_item("删除应用", self._delete_app, icon="✕")
        add_menu_item("清空当前分类", self._clear_category, icon="⊘")
        add_menu_item("", None, is_separator=True)
        add_menu_item("打开文件位置", self._open_file_location, icon="⊞")
        add_menu_item("属性", self._show_properties, icon="ⓘ")

        width = 170
        # 动态计算高度：11个菜单项(32px+2px pady) + 3个分隔线(1px+10px pady) + 上下边距(留足余量)
        height = 11 * 34 + 3 * 11 + 24

        screen_height = menu_window.winfo_screenheight()
        # 如果菜单底部超出屏幕，往上翻
        if y + height > screen_height - 10:
            y = max(10, y - height - 20)

        menu_window.geometry(f"{width}x{height}+{x}+{y}")
        menu_window.update_idletasks()
        _enable_menu_shadow(menu_window)

        def on_esc(event):
            close_submenu()
            close_folder_submenu()
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

                in_folder_submenu = False
                if folder_submenu and folder_submenu.winfo_exists():
                    fx, fy = folder_submenu.winfo_rootx(), folder_submenu.winfo_rooty()
                    fw, fh = folder_submenu.winfo_width(), folder_submenu.winfo_height()
                    in_folder_submenu = fx <= mx < fx + fw and fy <= my < fy + fh

                if not in_menu and not in_submenu and not in_folder_submenu:
                    close_submenu()
                    close_folder_submenu()
                    menu_window.destroy()

        root.bind("<Button-1>", on_click_outside, add=True)

        def on_destroy():
            close_submenu()
            close_folder_submenu()
            try:
                root.unbind("<Escape>", on_esc)
            except Exception:
                pass
            try:
                root.unbind("<Button-1>", on_click_outside)
            except Exception:
                pass
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
        if self.is_folder:
            # 文件夹：显示文件夹图标 + 名称 + 应用数量
            self.icon_label = ctk.CTkLabel(
                self,
                text="\U0001F4C1",  # 📁 文件夹emoji
                width=48,
                height=48,
                fg_color=("#FFB900", "#D29200"),
                corner_radius=8,
                font=ctk.CTkFont(size=24)
            )
            self.icon_label.pack(pady=(12, 4))

            app_count = len(self.app_data.get("apps", []))
            name_label = ctk.CTkLabel(
                self,
                text=f"{self.app_data.get('name', '文件夹')}\n({app_count})",
                font=ctk.CTkFont(size=11),
                text_color=("#1A1A1A", "#E0E0E0"),
                wraplength=90,
                justify="center"
            )
            name_label.pack(pady=(0, 8))
            return

        # 普通应用
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
