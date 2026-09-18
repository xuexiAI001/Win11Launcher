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

        # 计算目标位置：左上角对齐图标附近（从图标位置展开，非居中）
        self.update_idletasks()
        if self._anchor_x is not None and self._anchor_y is not None:
            # 窗口左上角在图标中心的左下方，从图标位置展开
            self._target_x = self._anchor_x - 5
            self._target_y = self._anchor_y
            # 屏幕边界检测
            if self._target_x < 10:
                self._target_x = 10
            if self._target_x + self._target_w > self.winfo_screenwidth() - 10:
                self._target_x = self.winfo_screenwidth() - self._target_w - 10
            if self._target_y < 10:
                self._target_y = 10
            if self._target_y + self._target_h > self.winfo_screenheight() - 10:
                self._target_y = self.winfo_screenheight() - self._target_h - 10
        else:
            self._target_x = (self.winfo_screenwidth() - 500) // 2
            self._target_y = (self.winfo_screenheight() - 400) // 2

        # 初始状态：直接设置为起始大小，内容区域固定目标大小提前布局
        if self._anchor_x is not None:
            start_w = 120
            start_h = 100
            start_x = self._anchor_x - start_w // 2
            start_y = self._anchor_y - start_h // 2
            self.geometry(f"{start_w}x{start_h}+{start_x}+{start_y}")
            self.attributes('-alpha', 0.3)
        else:
            self.geometry(f"{self._target_w}x{self._target_h}+{self._target_x}+{self._target_y}")
            self.attributes('-alpha', self._target_alpha)


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

        # 内容区域固定目标大小，动画期间不随窗口缩放重排（避免卡顿）
        self._content_frame = ctk.CTkFrame(self, fg_color="transparent", width=480, height=335)
        self._content_frame.pack(fill="both", expand=True)
        self._content_frame.pack_propagate(False)

        self.scroll_frame = ctk.CTkScrollableFrame(self._content_frame, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._render_apps()


        # 强制完成内容布局（内容区域固定大小，不依赖窗口大小）
        self.update_idletasks()
        # 关闭时从主窗口字典中移除
        self.protocol("WM_DELETE_WINDOW", self._on_close)


        # 启动展开动画
        self.after(10, self._animate_open)
    def _animate_open(self):
        """iOS风格展开动画：从图标位置放大到目标大小（丝滑版）"""
        try:
            if self._anchor_x is None:
                self.focus_force()
                self.after(100, self._ensure_on_top)
                return

            # 动画前：焦点提前设置，隐藏滚动条避免动画中状态变化触发重排
            self.focus_force()
            try:
                if hasattr(self.scroll_frame, '_scrollbar'):
                    self.scroll_frame._scrollbar.pack_forget()
            except Exception:
                pass

            # 预计算所有帧参数
            frames = 16
            delay = 10  # 每帧10ms，总时长约160ms

            start_w, start_h = 120, 100
            start_x = self._anchor_x - start_w // 2
            start_y = self._anchor_y - start_h // 2

            # 预计算每一帧的 geometry 和 alpha
            frame_data = []
            for i in range(frames):
                t = (i + 1) / frames
                # ease-out-cubic：减速更均匀，末尾不拖沓
                ease = 1 - (1 - t) ** 3

                w = int(start_w + (self._target_w - start_w) * ease)
                h = int(start_h + (self._target_h - start_h) * ease)
                x = int(start_x + (self._target_x - start_x) * ease)
                y = int(start_y + (self._target_y - start_y) * ease)
                alpha = 0.3 + (self._target_alpha - 0.3) * ease
                frame_data.append((f"{w}x{h}+{x}+{y}", alpha))

            def animate(idx):
                if not self.winfo_exists() or self._is_closing:
                    return
                if idx >= frames:
                    self.geometry(f"{self._target_w}x{self._target_h}+{self._target_x}+{self._target_y}")
                    self.attributes('-alpha', self._target_alpha)
                    # 动画结束后延迟恢复滚动条，避免最后一帧卡顿
                    self.after(50, self._restore_scrollbar)
                    self.after(100, self._ensure_on_top)
                    return

                geom, alpha = frame_data[idx]
                self.geometry(geom)
                self.attributes('-alpha', alpha)
                self.after(delay, lambda: animate(idx + 1))

            animate(0)
        except Exception as e:
            logger.debug(f"展开动画失败: {e}")
            try:
                self.geometry(f"{self._target_w}x{self._target_h}+{self._target_x}+{self._target_y}")
                self.attributes('-alpha', self._target_alpha)
                self._restore_scrollbar()
            except Exception:
                pass

    def _restore_scrollbar(self):
        """恢复滚动条显示"""
        try:
            if hasattr(self.scroll_frame, '_scrollbar'):
                sb = self.scroll_frame._scrollbar
                if not sb.winfo_ismapped():
                    sb.pack(side="right", fill="y")
        except Exception:
            pass

    def _animate_close(self, callback=None):
        """iOS风格回收动画：缩小回图标位置（丝滑版）"""
        if self._is_closing:
            return
        self._is_closing = True

        try:
            if self._anchor_x is None:
                if callback:
                    callback()
                else:
                    self.destroy()
                return

            # 回收动画开始时隐藏滚动条，避免缩放中状态变化
            try:
                if hasattr(self.scroll_frame, '_scrollbar'):
                    self.scroll_frame._scrollbar.pack_forget()
            except Exception:
                pass

            # 预计算所有帧参数
            frames = 14
            delay = 10  # 每帧10ms，总时长约140ms

            start_w = self._target_w
            start_h = self._target_h
            start_x = self._target_x
            start_y = self._target_y
            end_w, end_h = 120, 100
            end_x = self._anchor_x - end_w // 2
            end_y = self._anchor_y - end_h // 2

            # 预计算每一帧
            frame_data = []
            for i in range(frames):
                t = (i + 1) / frames
                # ease-in-quad：开始慢，结尾快
                ease = t * t

                w = int(start_w + (end_w - start_w) * ease)
                h = int(start_h + (end_h - start_h) * ease)
                x = int(start_x + (end_x - start_x) * ease)
                y = int(start_y + (end_y - start_y) * ease)
                alpha = self._target_alpha * (1 - ease)
                frame_data.append((f"{w}x{h}+{x}+{y}", max(0.1, alpha)))

            def animate(idx):
                if not self.winfo_exists():
                    return
                if idx >= frames:
                    if callback:
                        callback()
                    else:
                        self.destroy()
                    return

                geom, alpha = frame_data[idx]
                self.geometry(geom)
                self.attributes('-alpha', alpha)
                self.after(delay, lambda: animate(idx + 1))

            animate(0)
        except Exception as e:
            logger.debug(f"回收动画失败: {e}")
            if callback:
                callback()
            else:
                self.destroy()

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
        """窗口关闭时播放回收动画再销毁"""
        try:
            open_windows = getattr(self.parent_window, '_open_folder_windows', {})
            if self.folder_key in open_windows:
                del open_windows[self.folder_key]
                logger.debug(f"关闭文件夹窗口，移除引用: {self.folder_key}")
        except Exception:
            pass

        def do_destroy():
            try:
                self.destroy()
            except Exception:
                pass

        self._animate_close(do_destroy)

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
                lazy_load=True,
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
