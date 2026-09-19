# -*- coding: utf-8 -*-
"""
Windows 11 风格软件启动台 - UI重构版
基于 CustomTkinter 5.2.1 开发
"""

import os
import sys
import json
import concurrent.futures
import logging
from logging.handlers import RotatingFileHandler

# 日志系统 - 必须在所有使用 logger 的代码之前初始化
APP_NAME = "Win11Launcher"
LOG_DIR = os.path.join(os.environ.get('APPDATA', '.'), APP_NAME)
LOG_FILE = os.path.join(LOG_DIR, 'launcher.log')

def _setup_logger():
    """配置日志系统：文件输出 + 轮转，打包后仍可记录"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception:
        pass
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(handler)
    return logger

logger = _setup_logger()


# 高DPI设置 - 在导入任何GUI库之前设置
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception as e:
        logger.debug(f"DPI setting failed: {e}")

from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
from window_effects import apply_acrylic
from PIL import Image, ImageTk
from icon_extractor import get_app_icon
from app_info import get_app_info
from drop_zone import DropZone
from app_item import AppGridItem, _enable_menu_shadow
from tray_icon import TrayManager
from folder_window import FolderWindow

# 尝试导入拖放库
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
    logger.debug("tkinterdnd2 imported successfully")
except ImportError as e:
    HAS_DND = False
    logger.debug(f"tkinterdnd2 import failed: {e}")

# 尝试导入全局快捷键库
try:
    from pynput import keyboard
    HAS_HOTKEY = True
    logger.debug("pynput imported successfully")
except ImportError as e:
    HAS_HOTKEY = False
    logger.debug(f"pynput import failed: {e}")

# ============================================================
# 全局配置
# ============================================================
DEFAULT_CATEGORIES = ["系统应用", "办公软件", "社交软件", "影音视频", "语言编程", "我的游戏"]
CATEGORIES = DEFAULT_CATEGORIES  # 兼容别名，运行时使用 self.categories
WINDOW_WIDTH = 1350
WINDOW_HEIGHT = 850
ICON_SIZE = 48
ITEM_WIDTH = 116  # 卡片宽度（包含间距）
GRID_PADDING = 120  # 网格区域的额外边距补偿（增加以避免卡片被遮挡）

# 主题配置
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

CONFIG_FILE = os.path.join(os.environ.get('APPDATA', '.'), APP_NAME, "launcher_config.json")
ICON_CACHE_DIR = os.path.join(os.environ.get('APPDATA', '.'), APP_NAME, "icon_cache")


def _ensure_config_dir():
    """确保配置目录存在"""
    config_dir = os.path.dirname(CONFIG_FILE)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)

def _ensure_icon_cache_dir():
    """确保图标缓存目录存在"""
    if not os.path.exists(ICON_CACHE_DIR):
        os.makedirs(ICON_CACHE_DIR, exist_ok=True)

# ============================================================
# 工具函数
# ============================================================
# ============================================================
# 主窗口类
# ============================================================
class LauncherWindow(TkinterDnD.Tk if HAS_DND else ctk.CTk):
    """启动台主窗口"""

    def __init__(self):
        if HAS_DND:
            logger.debug("Using TkinterDnD.Tk")
            TkinterDnD.Tk.__init__(self)
            self._use_tkdnd = True
        else:
            logger.debug("Using ctk.CTk (no DnD)")
            super().__init__()
            self._use_tkdnd = False

        # 用户原始主题选择（用于持久化，区分"跟随系统"和实际解析结果）
        self._user_theme_choice = "跟随系统"
        # 先检测系统主题并设置
        self._detect_system_theme()

        # 窗口属性 - 使用Win11原生标题栏
        self.title("Win11 Launchpad")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)
        # 使用原生标题栏（不设置overrideredirect或设置为False）
        
        # 设置窗口图标（用于任务栏显示）
        self._set_window_icon()
        
        # 立即设置深色标题栏（在窗口显示之前）
        self._setup_dark_titlebar_early()

        # 设置窗口背景色以匹配主题
        self._set_window_bg_color()

        # 居中显示
        self._center_window()

        # 数据
        self.categories = list(DEFAULT_CATEGORIES)
        self.current_category = self.categories[0]
        self.app_config = {cat: [] for cat in self.categories}
        self.alpha_var = ctk.DoubleVar(value=0.96)
        # 缓存必须在_load_config之前初始化
        self.category_items_cache = {cat: [] for cat in self.categories}
        self._open_folder_windows = {}  # 已打开的文件夹窗口
        # 加载保存的配置
        self._load_config()

        # 图标提取线程池（限制并发数，避免大量线程抢CPU）
        self.icon_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="icon-loader"
        )

        # 初始化UI
        self._setup_ui()

        # 设置拖放目标（必须在设置alpha之前）
        if HAS_DND:
            self._setup_drop_target()
        else:
            self._show_message("拖拽功能不可用（需安装tkinterdnd2）")

        # 显示已加载的应用（拖放目标设置之后调用）
        self._refresh_grid(force=True)

        # 设置毛玻璃效果（在UI和拖放设置之后调用）
        self.after(300, self._setup_glass_effect)

        # 设置标题栏颜色与系统主题一致
        self.after(350, self._setup_titlebar_color)
        # 设置全局快捷键
        self._setup_global_hotkey()
        # 系统托盘
        self._tray_manager = TrayManager(self)
        self._tray_manager.start()
        self._minimize_to_tray = True  # 关闭时最小化到托盘


        # 设置任务栏图标（让无边框窗口在任务栏显示）
        self._setup_taskbar_icon()

        # 监听窗口大小变化 - 使用防抖
        self._resize_timer_id = None
        self._is_initialized = False
        self._current_cols = 4
        self._previous_category = None  # 上一个分类，用于快速切换
        self.bind("<Configure>", self._on_window_resize)

        # 初始化完成后设置标志
        self.after(500, self._mark_initialized)

        # 延迟3秒启动新安装应用监控
        self._install_monitor_running = False
        self._known_installed_apps = set()
        self._notified_installs = set()
        self.after(3000, self._start_install_monitor)

        # 窗口关闭时清理线程池
        self._original_destroy = self.destroy
        self.destroy = self._on_destroy
        # 关键：绑定关闭按钮到自定义处理（最小化到托盘或退出）
        self.protocol("WM_DELETE_WINDOW", self._on_destroy)

    def _on_destroy(self):
        """窗口关闭：默认最小化到托盘，而非退出"""
        if getattr(self, '_minimize_to_tray', True):
            try:
                self.withdraw()
                logger.debug("窗口已最小化到托盘")
            except Exception as e:
                logger.debug(f"最小化到托盘失败: {e}")
                self._force_quit()
        else:
            self._force_quit()

    def _force_quit(self):
        """真正退出程序"""
        try:
            self._install_monitor_running = False
            if hasattr(self, '_tray_manager'):
                self._tray_manager.stop()
            if hasattr(self, 'icon_executor'):
                self.icon_executor.shutdown(wait=False, cancel_futures=True)
            if hasattr(self, '_hotkey_listener'):
                self._hotkey_listener.stop()
        except Exception:
            pass
        self._original_destroy()

    def _setup_glass_effect(self):
        """设置Windows 11亚克力磨砂效果和窗口圆角"""
        try:
            # 先设置基础透明度（使用保存的值或默认值）
            alpha = self.alpha_var.get() if hasattr(self, 'alpha_var') else 0.96
            self.attributes('-alpha', alpha)
            
            # 设置Windows 11原生亚克力效果（仅Windows）
            if sys.platform == "win32":
                self._setup_acrylic_effect()
            
            logger.debug("亚克力磨砂效果已启用")
            
        except Exception as e:
            logger.debug(f"亚克力磨砂效果设置失败: {e}")
    
    def _setup_acrylic_effect(self):
        """使用Windows DWM API设置亚克力效果（不影响原生标题栏按钮）"""
        try:
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

            # 方法1: 使用 DWMWA_SYSTEMBACKDROP_TYPE (Windows 11 推荐方式)
            # 2 = DWMSBT_ACRYLIC (亚克力效果)
            # 这种方式不会干扰原生标题栏按钮
            backdrop_type = ctypes.c_int(2)
            result = DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type))

            if result == 0:
                logger.debug("亚克力效果设置成功 (SYSTEMBACKDROP_TYPE)")
            else:
                logger.debug("亚克力效果设置失败，尝试备用方案")
                self._setup_dwm_blur()

        except Exception as e:
            logger.debug(f"DWM亚克力效果失败: {e}")
            pass
    
    def _setup_dwm_blur(self):
        """使用DWM模糊效果作为备用方案"""
        try:
            import ctypes
            from ctypes import wintypes
            
            DWMWA_BORDER_COLOR = 34
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36
            
            hwnd = self.winfo_id()
            color = ctypes.c_uint(0x00000000)
            
            DwmSetWindowAttribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            DwmSetWindowAttribute.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_uint),
                ctypes.c_uint
            ]
            
            # 设置边框颜色为透明
            DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.pointer(color), ctypes.sizeof(color))
            logger.debug("DWM模糊备用方案已应用")
            
        except Exception as e:
            logger.debug(f"DWM模糊备用方案失败: {e}")

    def _setup_titlebar_color(self):
        """设置标题栏颜色（支持深色和浅色主题）"""
        try:
            import ctypes
            from ctypes import wintypes, c_void_p, c_int, POINTER, byref, sizeof, c_wchar_p
            
            # ========== 检测系统主题 ==========
            is_dark_mode = False
            try:
                HKEY_CURRENT_USER = 0x80000001
                KEY_READ = 0x20019
                
                advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
                hkey = wintypes.HKEY()
                
                result = advapi32.RegOpenKeyExW(
                    HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    0,
                    KEY_READ,
                    byref(hkey)
                )
                
                if result == 0:
                    value = wintypes.DWORD()
                    value_size = ctypes.sizeof(value)
                    result = advapi32.RegQueryValueExW(
                        hkey,
                        "AppsUseLightTheme",
                        None,
                        None,
                        byref(value),
                        byref(ctypes.c_ulong(value_size))
                    )
                    
                    advapi32.RegCloseKey(hkey)
                    
                    if result == 0:
                        is_dark_mode = (value.value == 0)
                        logger.debug(f"注册表检测主题: {'深色' if is_dark_mode else '浅色'}")
            
            except Exception as reg_e:
                logger.debug(f"注册表检测失败: {reg_e}")
                is_dark_mode = (ctk.get_appearance_mode() == "dark")
            
            theme_name = "深色" if is_dark_mode else "浅色"
            logger.debug(f"========== 开始设置{theme_name}标题栏 ==========")
            
            # ========== 获取正确的窗口句柄 ==========
            self.update_idletasks()
            
            hwnd = self.winfo_id()
            logger.debug(f"winfo_id() = {hwnd}")
            
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            
            # 获取顶层窗口句柄（关键！）
            GetAncestor = user32.GetAncestor
            GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
            GetAncestor.restype = wintypes.HWND
            
            GA_ROOT = 2
            root_hwnd = GetAncestor(hwnd, GA_ROOT)
            if root_hwnd:
                logger.debug(f"GetAncestor(GA_ROOT) = {root_hwnd}")
                hwnd = root_hwnd
            
            # ========== 方法1: DWMWA_USE_IMMERSIVE_DARK_MODE (Win11) ==========
            try:
                DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
                DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, c_void_p, ctypes.c_uint]
                DwmSetWindowAttribute.restype = wintypes.HRESULT
                
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dark_value = ctypes.c_int(1 if is_dark_mode else 0)
                result = DwmSetWindowAttribute(
                    hwnd, 
                    DWMWA_USE_IMMERSIVE_DARK_MODE, 
                    byref(dark_value), 
                    sizeof(dark_value)
                )
                logger.debug(f"方法1 DWMWA_USE_IMMERSIVE_DARK_MODE: result={result}, {theme_name}")
            except Exception as e:
                logger.debug(f"方法1失败: {e}")
            
            # ========== 方法2: SetPropW 设置 UseImmersiveDarkModeColors ==========
            try:
                SetPropW = user32.SetPropW
                SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
                SetPropW.restype = wintypes.BOOL
                
                # 设置窗口属性（1=深色，0=浅色）
                result = SetPropW(hwnd, "UseImmersiveDarkModeColors", wintypes.HANDLE(1 if is_dark_mode else 0))
                logger.debug(f"方法2 SetPropW(UseImmersiveDarkModeColors): result={result}, {theme_name}")
            except Exception as e:
                logger.debug(f"方法2失败: {e}")
            
            # ========== 方法3: AllowDarkModeForWindow ==========
            try:
                uxtheme = ctypes.WinDLL('uxtheme', use_last_error=True)
                AllowDarkModeForWindow = uxtheme[133]
                AllowDarkModeForWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
                AllowDarkModeForWindow.restype = wintypes.BOOL
                
                result = AllowDarkModeForWindow(hwnd, True)
                logger.debug(f"方法3 AllowDarkModeForWindow: result={result}")
            except Exception as e:
                logger.debug(f"方法3失败: {e}")
            
            # ========== 方法4: FlushDarkMode ==========
            try:
                uxtheme = ctypes.WinDLL('uxtheme', use_last_error=True)
                FlushDarkMode = uxtheme[136]
                FlushDarkMode.argtypes = []
                FlushDarkMode.restype = wintypes.BOOL
                
                result = FlushDarkMode()
                logger.debug(f"方法4 FlushDarkMode: result={result}")
            except Exception as e:
                logger.debug(f"方法4失败: {e}")
            
            # ========== 方法5: 刷新非客户区 ==========
            try:
                WM_NCACTIVATE = 0x0086
                WM_NCPAINT = 0x0085
                
                user32.SendMessageW(hwnd, WM_NCACTIVATE, 0, 0)
                user32.SendMessageW(hwnd, WM_NCACTIVATE, 1, 0)
                user32.SendMessageW(hwnd, WM_NCPAINT, 1, 0)
                logger.debug("方法5 刷新非客户区: 完成")
            except Exception as e:
                logger.debug(f"方法5失败: {e}")
            
            # ========== 方法6: 强制重绘 ==========
            try:
                SWP_FRAMECHANGED = 0x0020
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                
                user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
                logger.debug("方法6 强制重绘: 完成")
            except Exception as e:
                logger.debug(f"方法6失败: {e}")
            
            logger.debug(f"========== {theme_name}标题栏设置完成 ==========")
            
        except Exception as e:
            logger.debug(f"设置标题栏颜色失败: {e}")


    def _update_titlebar_color_from_ctk(self, user_choice=None):
        """根据ctk设置更新标题栏颜色
        
        Args:
            user_choice: 用户选择的主题（"浅色"、"深色"、"跟随系统"），用于判断是否需要从注册表检测
        """
        try:
            import ctypes
            from ctypes import wintypes, c_void_p, byref, sizeof, c_int
            
            # 判断是否为深色模式
            is_dark_mode = False
            
            # 优先使用用户选择来判断
            if user_choice:
                if user_choice == "深色":
                    is_dark_mode = True
                elif user_choice == "跟随系统":
                    # 从注册表检测实际系统主题
                    try:
                        HKEY_CURRENT_USER = 0x80000001
                        KEY_READ = 0x20019
                        
                        advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
                        hkey = wintypes.HKEY()
                        
                        result = advapi32.RegOpenKeyExW(
                            HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                            0,
                            KEY_READ,
                            byref(hkey)
                        )
                        
                        if result == 0:
                            value = wintypes.DWORD()
                            value_size = ctypes.sizeof(value)
                            result = advapi32.RegQueryValueExW(
                                hkey,
                                "AppsUseLightTheme",
                                None,
                                None,
                                byref(value),
                                byref(ctypes.c_ulong(value_size))
                            )
                            
                            advapi32.RegCloseKey(hkey)
                            
                            if result == 0:
                                is_dark_mode = (value.value == 0)
                                logger.debug(f"注册表检测系统主题: {'深色' if is_dark_mode else '浅色'}")
                    except Exception as reg_e:
                        logger.debug(f"注册表检测系统主题失败: {reg_e}")
                # 浅色模式不需要特殊处理，is_dark_mode 保持 False
            else:
                # 没有用户选择时，从ctk获取当前主题设置
                appearance_mode = ctk.get_appearance_mode()
                
                if appearance_mode.lower() == "dark":
                    is_dark_mode = True
                elif appearance_mode.lower() == "system":
                    # 跟随系统时，从注册表检测实际系统主题
                    try:
                        HKEY_CURRENT_USER = 0x80000001
                        KEY_READ = 0x20019
                        
                        advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
                        hkey = wintypes.HKEY()
                        
                        result = advapi32.RegOpenKeyExW(
                            HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                            0,
                            KEY_READ,
                            byref(hkey)
                        )
                        
                        if result == 0:
                            value = wintypes.DWORD()
                            value_size = ctypes.sizeof(value)
                            result = advapi32.RegQueryValueExW(
                                hkey,
                                "AppsUseLightTheme",
                                None,
                                None,
                                byref(value),
                                byref(ctypes.c_ulong(value_size))
                            )
                            
                            advapi32.RegCloseKey(hkey)
                            
                            if result == 0:
                                is_dark_mode = (value.value == 0)
                                logger.debug(f"注册表检测系统主题: {'深色' if is_dark_mode else '浅色'}")
                    except Exception as reg_e:
                        logger.debug(f"注册表检测系统主题失败: {reg_e}")
            
            appearance_mode = user_choice if user_choice else ctk.get_appearance_mode()
            logger.debug(f"appearance_mode={appearance_mode}, is_dark_mode={is_dark_mode}")
            
            theme_name = "深色" if is_dark_mode else "浅色"
            logger.debug(f"主题切换：设置{theme_name}标题栏 (模式={appearance_mode})")
            
            # 定义与主框架一致的颜色
            if is_dark_mode:
                bg_color_rgb = (31, 31, 31)  # #1F1F1F
            else:
                bg_color_rgb = (243, 243, 243)  # #F3F3F3
            
            # 获取窗口句柄
            self.update_idletasks()
            hwnd = self.winfo_id()
            
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            
            # 获取顶层窗口句柄
            GetAncestor = user32.GetAncestor
            GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
            GetAncestor.restype = wintypes.HWND
            
            GA_ROOT = 2
            root_hwnd = GetAncestor(hwnd, GA_ROOT)
            if root_hwnd:
                hwnd = root_hwnd
            
            DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
            DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, c_void_p, ctypes.c_uint]
            DwmSetWindowAttribute.restype = wintypes.HRESULT
            
            # 方法1: DWMWA_USE_IMMERSIVE_DARK_MODE（原生标题栏深色模式）
            try:
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dark_value = ctypes.c_int(1 if is_dark_mode else 0)
                result = DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(dark_value), sizeof(dark_value))
                logger.debug(f"DWMWA_USE_IMMERSIVE_DARK_MODE: result={result}, {theme_name}")
            except Exception as e:
                logger.debug(f"DWMWA_USE_IMMERSIVE_DARK_MODE失败: {e}")
            
            # 方法2: SetPropW
            try:
                SetPropW = user32.SetPropW
                SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
                SetPropW.restype = wintypes.BOOL
                result = SetPropW(hwnd, "UseImmersiveDarkModeColors", wintypes.HANDLE(1 if is_dark_mode else 0))
                logger.debug(f"SetPropW: result={result}, {theme_name}")
            except Exception as e:
                logger.debug(f"SetPropW失败: {e}")
            
            # 方法3: 设置标题栏背景颜色 (DWMWA_CAPTION_COLOR = 35)
            try:
                caption_color = (bg_color_rgb[2] << 16) | (bg_color_rgb[1] << 8) | bg_color_rgb[0]
                color_value = ctypes.c_int(caption_color)
                result = DwmSetWindowAttribute(hwnd, 35, byref(color_value), sizeof(color_value))
                logger.debug(f"DWMWA_CAPTION_COLOR: result={result}, color=#{caption_color:06X} ({theme_name})")
            except Exception as e:
                logger.debug(f"DWMWA_CAPTION_COLOR失败: {e}")
            
            # 方法4: 设置边框颜色 (DWMWA_BORDER_COLOR = 34)
            try:
                border_color_value = ctypes.c_int(caption_color)
                result = DwmSetWindowAttribute(hwnd, 34, byref(border_color_value), sizeof(border_color_value))
                logger.debug(f"DWMWA_BORDER_COLOR: result={result}, color=#{caption_color:06X}")
            except Exception as e:
                logger.debug(f"DWMWA_BORDER_COLOR失败: {e}")
            
            # 强制刷新窗口
            SWP_FRAMECHANGED = 0x0020
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
            
            # 额外刷新：发送WM_THEMECHANGED消息
            WM_THEMECHANGED = 0x031A
            user32.SendMessageW(hwnd, WM_THEMECHANGED, 0, 0)
            
            # 强制重绘非客户区
            WM_NCPAINT = 0x0085
            user32.SendMessageW(hwnd, WM_NCPAINT, 1, 0)
            
            logger.debug(f"{theme_name}标题栏设置完成（原生标题栏）")
            
        except Exception as e:
            logger.debug(f"更新标题栏颜色失败: {e}")

    def _setup_window_corner_radius(self):
        """使用Windows DWM API设置窗口圆角"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # DWMWA_WINDOW_CORNER_PREFERENCE
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            
            # DWMWCP_ROUND = 2, DWMWCP_ROUNDSMALL = 1
            DWMWCP_ROUND = 2
            
            DwmSetWindowAttribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            DwmSetWindowAttribute.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.c_uint
            ]
            DwmSetWindowAttribute.restype = wintypes.HRESULT
            
            hwnd = self.winfo_id()
            corner_preference = ctypes.c_int(DWMWCP_ROUND)
            
            result = DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(corner_preference),
                ctypes.sizeof(corner_preference)
            )
            
            if result == 0:
                logger.debug("窗口圆角设置成功")
            else:
                logger.debug(f"窗口圆角设置失败: {result}")
                
        except Exception as e:
            logger.debug(f"设置窗口圆角失败: {e}")

    def _minimize_window(self):
        """最小化无边框窗口"""
        try:
            # 对于无边框窗口，使用withdraw隐藏，然后使用deiconify恢复
            self.withdraw()
            # 保存窗口位置以便恢复
            self._last_geometry = self.geometry()
            logger.debug("窗口已最小化")
        except Exception as e:
            logger.debug(f"最小化窗口失败: {e}")

    def _toggle_visibility(self):
        """切换窗口可见性"""
        try:
            if self.state() == 'normal' or self.winfo_viewable():
                # 使用iconify()最小化到任务栏，而不是withdraw()
                self.iconify()
                logger.debug("窗口已最小化到任务栏")
            else:
                # 恢复窗口
                self.deiconify()
                self.lift()
                self.focus_force()
                logger.debug("窗口已显示")
        except Exception as e:
            logger.debug(f"切换窗口可见性失败: {e}")

    def _setup_global_hotkey(self):
        """设置全局快捷键 - 支持自定义"""
        if not HAS_HOTKEY:
            logger.debug("全局快捷键不可用（需安装pynput）")
            return

        # 停止旧的监听器
        if hasattr(self, '_hotkey_listener') and self._hotkey_listener:
            self._hotkey_listener.stop()

        # 从配置读取快捷键，默认 Ctrl+Shift+L
        hotkey_str = getattr(self, 'hotkey_var', None)
        if hotkey_str:
            hotkey_str = hotkey_str.get()
        if not hotkey_str:
            hotkey_str = "Ctrl+Shift+L"

        # 转换为 pynput 格式：Ctrl+Shift+L -> <ctrl>+<shift>+l
        pynput_key = self._convert_hotkey_format(hotkey_str)

        try:
            self._hotkey_listener = keyboard.GlobalHotKeys({
                pynput_key: self._toggle_visibility
            })
            self._hotkey_listener.start()
            logger.debug(f"全局快捷键 {hotkey_str} 已注册")
        except Exception as e:
            logger.debug(f"设置全局快捷键失败: {e}")

    def _convert_hotkey_format(self, hotkey_str):
        """将 Ctrl+Shift+L 格式转换为 pynput 的 <ctrl>+<shift>+l 格式"""
        parts = hotkey_str.lower().replace(' ', '').split('+')
        converted = []
        for part in parts:
            if part in ('ctrl', 'alt', 'shift', 'win', 'cmd'):
                converted.append(f'<{part}>')
            else:
                converted.append(part)
        return '+'.join(converted)

    def _set_window_icon(self):
        """设置窗口图标"""
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "app.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
                logger.debug(f"窗口图标设置成功: {icon_path}")
            else:
                logger.debug(f"窗口图标文件不存在: {icon_path}")
        except Exception as e:
            logger.debug(f"设置窗口图标失败: {e}")

    def _setup_taskbar_icon(self):
        """设置任务栏图标 - 让无边框窗口在任务栏显示"""
        try:
            if sys.platform != "win32":
                return
            
            import ctypes
            from ctypes import wintypes
            
            # 获取窗口句柄
            hwnd = self.winfo_id()
            
            # 设置窗口扩展样式，让无边框窗口在任务栏显示
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            
            user32 = ctypes.windll.user32
            
            # 使用 c_longlong 代替 LONG_PTR
            user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.GetWindowLongPtrW.restype = ctypes.c_longlong
            
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
            user32.SetWindowLongPtrW.restype = ctypes.c_longlong
            
            # 获取当前扩展样式
            ex_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            
            # 添加 WS_EX_APPWINDOW 样式，移除 WS_EX_TOOLWINDOW 样式
            ex_style = ex_style | WS_EX_APPWINDOW
            ex_style = ex_style & ~WS_EX_TOOLWINDOW
            
            # 设置新的扩展样式
            result = user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style)
            
            if result != 0:
                logger.debug("任务栏图标设置成功")
            else:
                logger.debug("任务栏图标设置失败")
                
        except Exception as e:
            logger.debug(f"设置任务栏图标失败: {e}")

    def _detect_system_theme(self):
        """检测Windows系统主题并设置应用主题"""
        try:
            if sys.platform != "win32":
                logger.debug("非Windows系统，使用默认主题")
                ctk.set_appearance_mode("system")
                return
            
            import ctypes
            from ctypes import wintypes
            
            # 读取Windows注册表获取主题设置
            HKEY_CURRENT_USER = 0x80000001
            KEY_READ = 0x20019
            
            # 打开注册表键
            advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
            
            hkey = wintypes.HKEY()
            result = advapi32.RegOpenKeyExW(
                HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                0,
                KEY_READ,
                ctypes.byref(hkey)
            )
            
            if result != 0:
                logger.debug("无法读取注册表，使用默认主题")
                ctk.set_appearance_mode("system")
                return
            
            # 读取AppsUseLightTheme值
            value = wintypes.DWORD()
            value_size = ctypes.sizeof(value)
            result = advapi32.RegQueryValueExW(
                hkey,
                "AppsUseLightTheme",
                None,
                None,
                ctypes.byref(value),
                ctypes.byref(ctypes.c_ulong(value_size))
            )
            
            advapi32.RegCloseKey(hkey)
            
            if result != 0:
                logger.debug("无法读取主题值，使用默认主题")
                ctk.set_appearance_mode("system")
                return
            
            # 0 = 深色主题, 1 = 浅色主题
            if value.value == 0:
                logger.debug("检测到系统深色主题")
                ctk.set_appearance_mode("dark")
            else:
                logger.debug("检测到系统浅色主题")
                ctk.set_appearance_mode("light")
                
        except Exception as e:
            logger.debug(f"检测系统主题失败: {e}")
            ctk.set_appearance_mode("system")

    def _setup_dark_titlebar_early(self):
        """在窗口创建后立即设置标题栏颜色（深色/浅色）"""
        try:
            import ctypes
            from ctypes import wintypes, c_void_p, byref, sizeof
            
            # 检测系统主题
            is_dark_mode = False
            try:
                HKEY_CURRENT_USER = 0x80000001
                KEY_READ = 0x20019
                
                advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
                hkey = wintypes.HKEY()
                
                result = advapi32.RegOpenKeyExW(
                    HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    0,
                    KEY_READ,
                    byref(hkey)
                )
                
                if result == 0:
                    value = wintypes.DWORD()
                    value_size = ctypes.sizeof(value)
                    result = advapi32.RegQueryValueExW(
                        hkey,
                        "AppsUseLightTheme",
                        None,
                        None,
                        byref(value),
                        byref(ctypes.c_ulong(value_size))
                    )
                    
                    advapi32.RegCloseKey(hkey)
                    
                    if result == 0:
                        is_dark_mode = (value.value == 0)
            except:
                is_dark_mode = (ctk.get_appearance_mode() == "dark")
            
            theme_name = "深色" if is_dark_mode else "浅色"
            logger.debug(f"早期设置{theme_name}标题栏...")
            
            # 强制更新窗口
            self.update()
            
            # 获取窗口句柄 - 尝试多种方法
            hwnd = self.winfo_id()
            logger.debug(f"winfo_id() = {hwnd}")
            
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            
            # 获取顶层窗口句柄
            GetParent = user32.GetParent
            GetParent.argtypes = [wintypes.HWND]
            GetParent.restype = wintypes.HWND
            
            GetAncestor = user32.GetAncestor
            GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
            GetAncestor.restype = wintypes.HWND
            
            GA_ROOT = 2
            root_hwnd = GetAncestor(hwnd, GA_ROOT)
            if root_hwnd:
                logger.debug(f"GetAncestor(GA_ROOT) = {root_hwnd}")
                hwnd = root_hwnd
            
            # 也尝试GetParent链
            parent_hwnd = GetParent(hwnd)
            if parent_hwnd:
                logger.debug(f"GetParent = {parent_hwnd}")
                # 继续向上查找
                temp = parent_hwnd
                while temp:
                    next_parent = GetParent(temp)
                    if not next_parent:
                        break
                    temp = next_parent
                if temp:
                    logger.debug(f"顶层父窗口 = {temp}")
                    hwnd = temp
            
            # ========== 方法1: 使用win32api ==========
            try:
                import win32gui
                import win32api
                import win32con
                
                # 尝试使用win32api设置窗口属性
                style = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)
                logger.debug(f"方法1 win32api.GetWindowLong: style={style}")
                
                # 尝试使用win32gui的SetProp
                ctypes.windll.user32.SetPropW(hwnd, "UseImmersiveDarkModeColors", 1 if is_dark_mode else 0)
                logger.debug(f"方法1 ctypes.SetPropW: {'深色' if is_dark_mode else '浅色'}")
            except ImportError:
                logger.debug("方法1 win32api不可用")
            except Exception as e:
                logger.debug(f"方法1失败: {e}")
            
            # ========== 方法2: SetPropW ==========
            try:
                SetPropW = user32.SetPropW
                SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
                SetPropW.restype = wintypes.BOOL
                result = SetPropW(hwnd, "UseImmersiveDarkModeColors", wintypes.HANDLE(1 if is_dark_mode else 0))
                logger.debug(f"方法2 SetPropW: result={result}, {'深色' if is_dark_mode else '浅色'}")
            except Exception as e:
                logger.debug(f"方法2失败: {e}")
            
            # ========== 方法3: DWMWA_USE_IMMERSIVE_DARK_MODE ==========
            try:
                DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
                DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, c_void_p, ctypes.c_uint]
                DwmSetWindowAttribute.restype = wintypes.HRESULT
                
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dark_value = ctypes.c_int(1 if is_dark_mode else 0)
                result = DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(dark_value), sizeof(dark_value))
                logger.debug(f"方法3 DWMWA_USE_IMMERSIVE_DARK_MODE: result={result}, {'深色' if is_dark_mode else '浅色'}")
            except Exception as e:
                logger.debug(f"方法3失败: {e}")
            
            # ========== 方法4: DWMWA_MICA_EFFECT (Win11) ==========
            try:
                DWMWA_MICA_EFFECT = 38
                mica_value = ctypes.c_int(1 if is_dark_mode else 0)
                result = DwmSetWindowAttribute(hwnd, DWMWA_MICA_EFFECT, byref(mica_value), sizeof(mica_value))
                logger.debug(f"方法4 DWMWA_MICA_EFFECT: result={result}, {'深色' if is_dark_mode else '浅色'}")
            except Exception as e:
                logger.debug(f"方法4失败: {e}")
            
            # ========== 方法5: DWMWA_SYSTEMBACKDROP_TYPE (Win11 22H2) ==========
            try:
                DWMWA_SYSTEMBACKDROP_TYPE = 38
                # 2 = Mica Dark, 3 = Mica Light
                backdrop_value = ctypes.c_int(2 if is_dark_mode else 3)
                result = DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, byref(backdrop_value), sizeof(backdrop_value))
                logger.debug(f"方法5 DWMWA_SYSTEMBACKDROP_TYPE: result={result}, {'深色Mica' if is_dark_mode else '浅色Mica'}")
            except Exception as e:
                logger.debug(f"方法5失败: {e}")
            
            # ========== 方法6: 强制刷新窗口 ==========
            try:
                SWP_FRAMECHANGED = 0x0020
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                
                user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
                logger.debug("方法6 强制刷新: 完成")
            except Exception as e:
                logger.debug(f"方法6失败: {e}")
            
        except Exception as e:
            logger.debug(f"早期深色标题栏设置失败: {e}")

    def _set_window_bg_color(self):
        """设置窗口背景色并同步标题栏颜色"""
        try:
            import ctypes
            from ctypes import wintypes, byref, c_int, sizeof
            
            # 检测系统主题
            is_dark_mode = (ctk.get_appearance_mode().lower() == "dark")
            
            try:
                HKEY_CURRENT_USER = 0x80000001
                KEY_READ = 0x20019
                
                advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
                hkey = wintypes.HKEY()
                
                result = advapi32.RegOpenKeyExW(
                    HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    0,
                    KEY_READ,
                    byref(hkey)
                )
                
                if result == 0:
                    value = wintypes.DWORD()
                    value_size = ctypes.sizeof(value)
                    result = advapi32.RegQueryValueExW(
                        hkey,
                        "AppsUseLightTheme",
                        None,
                        None,
                        byref(value),
                        byref(ctypes.c_ulong(value_size))
                    )
                    
                    advapi32.RegCloseKey(hkey)
                    
                    if result == 0:
                        is_dark_mode = (value.value == 0)
            except:
                pass
            
            theme_name = "深色" if is_dark_mode else "浅色"
            
            # 定义与主框架一致的颜色
            if is_dark_mode:
                bg_color_rgb = (31, 31, 31)  # #1F1F1F
            else:
                bg_color_rgb = (243, 243, 243)  # #F3F3F3
            
            # 使用主题背景色而不是透明色，避免干扰标题栏按钮
            self.configure(bg=('#F3F3F3', '#1F1F1F')[is_dark_mode])
            
            # 同步DWM标题栏颜色（消除分割线）
            try:
                dwmapi = ctypes.windll.dwmapi
                user32 = ctypes.windll.user32
                
                # 获取顶层窗口句柄
                self.update_idletasks()
                hwnd = self.winfo_id()
                
                GetAncestor = user32.GetAncestor
                GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
                GetAncestor.restype = wintypes.HWND
                
                root_hwnd = GetAncestor(hwnd, 2)  # GA_ROOT
                if root_hwnd:
                    hwnd = root_hwnd
                
                DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
                DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.POINTER(ctypes.c_int), ctypes.c_uint]
                DwmSetWindowAttribute.restype = wintypes.HRESULT
                
                # 设置标题栏背景颜色 (DWMWA_CAPTION_COLOR = 35)
                caption_color = (bg_color_rgb[2] << 16) | (bg_color_rgb[1] << 8) | bg_color_rgb[0]
                color_value = ctypes.c_int(caption_color)
                result = DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color_value), sizeof(color_value))
                logger.debug(f"DWMWA_CAPTION_COLOR: result={result}, color=#{caption_color:06X} ({theme_name})")
                
                # 设置边框颜色 (DWMWA_BORDER_COLOR = 34)
                border_color_value = ctypes.c_int(caption_color)
                result2 = DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border_color_value), sizeof(border_color_value))
                
            except Exception as e:
                logger.debug(f"设置DWM标题栏颜色失败: {e}")
            
            logger.debug(f"窗口背景设置为透明，标题栏颜色已同步 ({theme_name}主题)")
        except Exception as e:
            logger.debug(f"设置窗口背景色失败: {e}")
            is_dark_mode = (ctk.get_appearance_mode().lower() == "dark")
            if is_dark_mode:
                self.configure(bg="#1F1F1F")
            else:
                self.configure(bg="#F3F3F3")
        self.update_idletasks()

    def _set_title_bar_color_dark(self):
        """设置标题栏为深色主题"""
        try:
            if sys.platform != "win32":
                return
            
            import ctypes
            from ctypes import wintypes
            
            # DWMWA_COLORIZATION_COLOR
            DWMWA_COLORIZATION_COLOR = 3
            
            DwmSetWindowAttribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            DwmSetWindowAttribute.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_uint),
                ctypes.c_uint
            ]
            DwmSetWindowAttribute.restype = wintypes.HRESULT
            
            hwnd = self.winfo_id()
            color = ctypes.c_uint(0x1F1F1F)  # 深色主题颜色
            
            result = DwmSetWindowAttribute(
                hwnd,
                DWMWA_COLORIZATION_COLOR,
                ctypes.byref(color),
                ctypes.sizeof(color)
            )
            
            if result == 0:
                logger.debug("标题栏颜色设置成功（深色）")
            else:
                logger.debug(f"标题栏颜色设置失败: {result}")
                
        except Exception as e:
            logger.debug(f"设置标题栏颜色失败: {e}")

    def _set_title_bar_color_light(self):
        """设置标题栏为浅色主题"""
        try:
            if sys.platform != "win32":
                return
            
            import ctypes
            from ctypes import wintypes
            
            DWMWA_COLORIZATION_COLOR = 3
            
            DwmSetWindowAttribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            DwmSetWindowAttribute.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_uint),
                ctypes.c_uint
            ]
            DwmSetWindowAttribute.restype = wintypes.HRESULT
            
            hwnd = self.winfo_id()
            color = ctypes.c_uint(0xF3F3F3)  # 浅色主题颜色
            
            result = DwmSetWindowAttribute(
                hwnd,
                DWMWA_COLORIZATION_COLOR,
                ctypes.byref(color),
                ctypes.sizeof(color)
            )
            
            if result == 0:
                logger.debug("标题栏颜色设置成功（浅色）")
            else:
                logger.debug(f"标题栏颜色设置失败: {result}")
                
        except Exception as e:
            logger.debug(f"设置标题栏颜色失败: {e}")

    def _show_settings(self):
        """显示设置对话框"""
        dialog = ctk.CTkToplevel(self)
        apply_acrylic(dialog, parent=self)
        dialog.title("设置")
        dialog.geometry("500x560")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # 居中
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 500) // 2
        y = (dialog.winfo_screenheight() - 560) // 2
        dialog.geometry(f"500x560+{x}+{y}")

        # 标题
        title_label = ctk.CTkLabel(
            dialog,
            text="设置",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=15)

        # 快捷键设置
        hotkey_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        hotkey_frame.pack(fill="x", padx=30, pady=5)

        hotkey_label = ctk.CTkLabel(
            hotkey_frame,
            text="启动快捷键：",
            font=ctk.CTkFont(size=14)
        )
        hotkey_label.pack(side="left")

        self.hotkey_var = ctk.StringVar(value="Ctrl+Shift+L")

        hotkey_entry = ctk.CTkEntry(
            hotkey_frame,
            textvariable=self.hotkey_var,
            width=150,
            height=32
        )
        hotkey_entry.pack(side="left", padx=10)


        # 关闭时最小化到托盘
        tray_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        tray_frame.pack(fill="x", padx=30, pady=5)

        ctk.CTkLabel(
            tray_frame,
            text="关闭时最小化到托盘",
            font=ctk.CTkFont(size=13)
        ).pack(side="left")

        self.tray_var = ctk.BooleanVar(value=getattr(self, '_minimize_to_tray', True))
        ctk.CTkSwitch(
            tray_frame,
            text="",
            variable=self.tray_var,
            width=40
        ).pack(side="right")

        # 主题设置
        theme_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        theme_frame.pack(fill="x", padx=30, pady=5)

        theme_label = ctk.CTkLabel(
            theme_frame,
            text="主题颜色：",
            font=ctk.CTkFont(size=14)
        )
        theme_label.pack(side="left")

        # 将ctk返回的英文主题转换为中文
        appearance_mode = ctk.get_appearance_mode()
        theme_map_reverse = {"Light": "浅色", "Dark": "深色", "System": "跟随系统"}
        current_theme = theme_map_reverse.get(appearance_mode, "跟随系统")
        self.theme_var = ctk.StringVar(value=current_theme)

        theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            values=["浅色", "深色", "跟随系统"],
            variable=self.theme_var,
            width=120,
            height=32,
            command=self._change_theme
        )
        theme_menu.pack(side="left", padx=10)

        # 透明度设置
        alpha_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        alpha_frame.pack(fill="x", padx=30, pady=5)

        alpha_label = ctk.CTkLabel(
            alpha_frame,
            text="窗口透明度：",
            font=ctk.CTkFont(size=14)
        )
        alpha_label.pack(side="left")

        # 如果已有保存的值则使用，否则使用默认值0.96
        if not hasattr(self, 'alpha_var') or self.alpha_var.get() == 0:
            self.alpha_var = ctk.DoubleVar(value=0.96)

        alpha_slider = ctk.CTkSlider(
            alpha_frame,
            from_=0.5,
            to=1.0,
            variable=self.alpha_var,
            width=200,
            command=self._change_alpha
        )
        alpha_slider.pack(side="left", padx=10)

        self.alpha_value_label = ctk.CTkLabel(
            alpha_frame,
            text=f"{int(self.alpha_var.get() * 100)}%",
            font=ctk.CTkFont(size=12)
        )
        self.alpha_value_label.pack(side="left")

        # 开机自启动设置
        autostart_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        autostart_frame.pack(fill="x", padx=30, pady=5)

        autostart_label = ctk.CTkLabel(
            autostart_frame,
            text="开机自启动：",
            font=ctk.CTkFont(size=14)
        )
        autostart_label.pack(side="left")

        self.autostart_var = ctk.BooleanVar(value=self._check_autostart())
        
        autostart_switch = ctk.CTkSwitch(
            autostart_frame,
            variable=self.autostart_var,
            text=""
        )
        autostart_switch.pack(side="left", padx=10)

        # 分类管理按钮（点击弹出独立窗口）
        cat_btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        cat_btn_frame.pack(fill="x", padx=30, pady=(10, 5))

        ctk.CTkButton(
            cat_btn_frame,
            text="管理分类...",
            width=440,
            height=36,
            corner_radius=8,
            fg_color=("#E8E8E8", "#2D2D2D"),
            text_color=("#1A1A1A", "#E0E0E0"),
            command=self._show_category_manager
        ).pack()

        # 配置导入导出
        ie_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        ie_frame.pack(fill="x", padx=30, pady=(5, 5))

        ctk.CTkButton(
            ie_frame,
            text="导出配置",
            width=200,
            height=32,
            corner_radius=8,
            fg_color=("#E8E8E8", "#2D2D2D"),
            text_color=("#1A1A1A", "#E0E0E0"),
            command=self._export_config
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            ie_frame,
            text="导入配置",
            width=200,
            height=32,
            corner_radius=8,
            fg_color=("#E8E8E8", "#2D2D2D"),
            text_color=("#1A1A1A", "#E0E0E0"),
            command=self._import_config
        ).pack(side="left")


        # 查看已扫描应用
        scan_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        scan_frame.pack(fill="x", padx=30, pady=(5, 5))

        ctk.CTkButton(
            scan_frame,
            text="查看已扫描应用（开始菜单）",
            width=440,
            height=32,
            corner_radius=8,
            fg_color=("#E8E8E8", "#2D2D2D"),
            text_color=("#1A1A1A", "#E0E0E0"),
            command=self._show_scanned_apps
        ).pack()


        # 保存按钮
        save_btn = ctk.CTkButton(
            dialog,
            text="保存设置",
            width=120,
            height=36,
            corner_radius=8,
            fg_color=("#0078D4", "#005A9E"),
            command=lambda: self._save_settings(dialog)
        )
        save_btn.pack(pady=15)

        # 取消按钮
        cancel_btn = ctk.CTkButton(
            dialog,
            text="取消",
            width=120,
            height=36,
            corner_radius=8,
            fg_color=("#E8E8E8", "#2D2D2D"),
            text_color=("#1A1A1A", "#E0E0E0"),
            command=dialog.destroy
        )
        cancel_btn.pack(pady=5)

    def _change_theme(self, choice):
        """更改主题（带平滑过渡效果）"""
        logger.debug(f"========== 主题切换开始 ==========")
        logger.debug(f"用户选择: {choice}")
        self._user_theme_choice = choice
        
        # 保存原始透明度
        original_alpha = self.attributes('-alpha')
        
        # 同步淡出动画
        for i in range(10, 0, -1):
            alpha = original_alpha * (i / 10)
            self.attributes('-alpha', alpha)
            self.update_idletasks()
        
        # 切换主题
        theme_map = {"浅色": "light", "深色": "dark", "跟随系统": "system"}
        new_mode = theme_map.get(choice, "system")
        logger.debug(f"ctk模式: {new_mode}")
        
        ctk.set_appearance_mode(new_mode)
        logger.debug(f"ctk.get_appearance_mode() = {ctk.get_appearance_mode()}")

        # 关闭已打开的右键菜单（避免颜色不一致）
        try:
            if hasattr(self, '_global_context_menus'):
                for menu_win in self._global_context_menus[:]:
                    try:
                        if menu_win.winfo_exists():
                            menu_win.destroy()
                    except Exception:
                        pass
                self._global_context_menus.clear()
            if hasattr(self, '_current_submenu') and self._current_submenu:
                try:
                    if self._current_submenu.winfo_exists():
                        self._current_submenu.destroy()
                except Exception:
                    pass
                self._current_submenu = None
        except Exception:
            pass

        # 重新加载当前分类所有文件夹卡片的图标（主题相关）
        try:
            items = self.category_items_cache.get(self.current_category, [])
            for item in items:
                try:
                    if getattr(item, 'is_folder', False) and hasattr(item, '_load_folder_icon_async'):
                        item.after(50, item._load_folder_icon_async)
                except Exception:
                    pass
        except Exception:
            pass

        # 更新已打开的文件夹窗口主题
        try:
            for win in list(self._open_folder_windows.values()):
                try:
                    if win.winfo_exists() and hasattr(win, 'update_theme'):
                        win.update_theme()
                except Exception:
                    pass
        except Exception:
            pass

        # 同步更新窗口背景色
        self._set_window_bg_color()

        # 更新标题栏颜色（传递用户选择，用于判断是否跟随系统）
        self._update_titlebar_color_from_ctk(user_choice=choice)

        # 强制刷新整个窗口
        self.update()
        self.main_frame.update()
        
        # 同步淡入动画
        for i in range(1, 11):
            alpha = original_alpha * (i / 10)
            self.attributes('-alpha', alpha)
            self.update_idletasks()
        
        logger.debug(f"========== 主题切换完成 ==========")

    def _change_alpha(self, value):
        """更改透明度"""
        self.alpha_value_label.configure(text=f"{int(value * 100)}%")
        self.attributes('-alpha', value)
        self._save_config()

    def _check_autostart(self):
        """检查是否已设置开机自启动"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, "Win11Launchpad")
                return True
            except WindowsError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"检查自启动失败: {e}")
            return False

    def _set_autostart(self, enabled):
        """设置或取消开机自启动"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            
            if enabled:
                # 设置自启动
                exe_path = sys.executable
                script_path = os.path.abspath(sys.argv[0])
                cmd = f'"{exe_path}" "{script_path}"'
                winreg.SetValueEx(key, "Win11Launchpad", 0, winreg.REG_SZ, cmd)
                logger.debug(f"设置开机自启动: {cmd}")
            else:
                # 取消自启动
                try:
                    winreg.DeleteValue(key, "Win11Launchpad")
                    logger.debug(f"取消开机自启动")
                except WindowsError:
                    pass
            
            winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"设置自启动失败: {e}")

    def _load_config(self):
        """从文件加载配置"""
        try:
            _ensure_config_dir()
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    loaded_config = data.get("app_config", {})
                    # 加载自定义分类列表
                    if "categories" in data and isinstance(data["categories"], list):
                        self.categories = data["categories"]
                        # 确保 app_config 和 cache 包含所有分类
                        for cat in self.categories:
                            if cat not in self.app_config:
                                self.app_config[cat] = []
                            if cat not in self.category_items_cache:
                                self.category_items_cache[cat] = []
                        # 确保当前分类有效
                        if self.current_category not in self.categories:
                            self.current_category = self.categories[0]
                    for cat in self.categories:
                        if cat in loaded_config and isinstance(loaded_config[cat], list):
                            self.app_config[cat] = loaded_config[cat]
                    # 加载透明度设置
                    if "alpha" in data:
                        alpha_value = float(data["alpha"])
                        self.alpha_var.set(alpha_value)
                        self.attributes('-alpha', alpha_value)
                        logger.debug(f"透明度已加载: {alpha_value}")
                    # 加载主题设置并应用
                    if "theme" in data:
                        saved_theme = data["theme"]
                        self._user_theme_choice = saved_theme
                        theme_map = {"浅色": "light", "深色": "dark", "跟随系统": "system"}
                        ctk.set_appearance_mode(theme_map.get(saved_theme, "system"))
                        logger.debug(f"主题已加载: {saved_theme}")
                    logger.debug(f"配置已从 {CONFIG_FILE} 加载")
            else:
                logger.debug(f"配置文件 {CONFIG_FILE} 不存在，使用默认配置")
        except Exception as e:
            logger.debug(f"加载配置失败: {e}")

    def _save_config(self):
        """保存配置到文件 - 原子写入，避免中断导致配置损坏"""
        try:
            _ensure_config_dir()
            # 确保 alpha_var 已初始化
            if not hasattr(self, 'alpha_var'):
                self.alpha_var = ctk.DoubleVar(value=0.96)
            # 保存用户原始主题选择（区分"跟随系统"和实际解析结果）
            data = {
                "app_config": self.app_config,
                "categories": self.categories,
                "alpha": self.alpha_var.get(),
                "theme": getattr(self, '_user_theme_choice', '跟随系统')
            }
            # 先写入临时文件
            tmp_path = CONFIG_FILE + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # 原子替换（Windows 上 os.replace 是原子操作）
            os.replace(tmp_path, CONFIG_FILE)
            # 保留一份备份
            try:
                import shutil
                shutil.copy2(CONFIG_FILE, CONFIG_FILE + '.bak')
            except Exception:
                pass
            logger.debug(f"配置已保存到 {CONFIG_FILE}")
        except Exception as e:
            logger.debug(f"保存配置失败: {e}")

    def _save_settings(self, dialog):
        """保存设置"""
        # 保存快捷键
        new_hotkey = self.hotkey_var.get()

        # 保存托盘设置
        if hasattr(self, 'tray_var'):
            self._minimize_to_tray = self.tray_var.get()

        # 重新注册快捷键
        self._setup_global_hotkey()
        logger.debug(f"保存快捷键: {new_hotkey}")

        # 主题已在选择时通过 _change_theme 即时切换，这里只持久化到配置
        # 保存透明度
        self.attributes('-alpha', self.alpha_var.get())

        # 保存开机自启动
        self._set_autostart(self.autostart_var.get())

        # 保存配置到文件（包括主题、透明度等）
        self._save_config()
        self._show_message("设置已保存")
        dialog.destroy()


    def _export_config(self):
        """导出配置到文件"""
        try:
            from tkinter import filedialog
            file_path = filedialog.asksaveasfilename(
                title="导出配置",
                defaultextension=".json",
                filetypes=[("配置文件", "*.json"), ("所有文件", "*.*")],
                initialfile="win11launcher_config.json"
            )
            if not file_path:
                return

            data = {
                "app_config": self.app_config,
                "categories": self.categories,
                "alpha": self.alpha_var.get() if hasattr(self, 'alpha_var') else 0.96,
                "version": "1.0",
                "export_time": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                import json
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"配置已导出到: {file_path}")
            self._show_message(f"配置已导出到:\n{file_path}")
        except Exception as e:
            logger.debug(f"导出配置失败: {e}")
            self._show_message("导出配置失败")

    def _import_config(self):
        """从文件导入配置"""
        try:
            from tkinter import filedialog
            file_path = filedialog.askopenfilename(
                title="导入配置",
                filetypes=[("配置文件", "*.json"), ("所有文件", "*.*")]
            )
            if not file_path:
                return

            import json
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 确认对话框
            confirm = ctk.CTkToplevel(self)
            apply_acrylic(confirm, parent=self)
            confirm.title("确认导入")
            confirm.geometry("380x200")
            confirm.resizable(False, False)
            confirm.transient(self)
            confirm.grab_set()
            confirm.update_idletasks()
            x = (confirm.winfo_screenwidth() - 380) // 2
            y = (confirm.winfo_screenheight() - 200) // 2
            confirm.geometry(f"+{x}+{y}")

            ctk.CTkLabel(
                confirm,
                text="导入配置将覆盖当前所有应用和分类设置，\n确定要继续吗？",
                font=ctk.CTkFont(size=13),
                justify="center"
            ).pack(pady=(30, 20))

            btn_frame = ctk.CTkFrame(confirm, fg_color="transparent")
            btn_frame.pack(pady=10)

            def do_import():
                try:
                    # 加载分类
                    if "categories" in data and isinstance(data["categories"], list):
                        self.categories = data["categories"]
                        self.current_category = self.categories[0]

                    # 加载应用配置
                    if "app_config" in data:
                        self.app_config = data["app_config"]

                    # 加载透明度
                    if "alpha" in data and hasattr(self, 'alpha_var'):
                        alpha_val = float(data["alpha"])
                        self.alpha_var.set(alpha_val)
                        self.attributes('-alpha', alpha_val)

                    # 重建缓存
                    self.category_items_cache = {cat: [] for cat in self.categories}

                    # 保存并刷新
                    self._save_config()
                    self._refresh_grid(force=True)
                    # 重建分类Tab
                    self._setup_tabs()

                    logger.debug(f"配置已从 {file_path} 导入")
                    self._show_message("配置导入成功")
                except Exception as e:
                    logger.debug(f"导入配置失败: {e}")
                    self._show_message("导入配置失败，文件格式可能不正确")
                confirm.destroy()

            ctk.CTkButton(
                btn_frame, text="导入", width=100,
                fg_color="#0078D4", command=do_import
            ).pack(side="left", padx=10)
            ctk.CTkButton(
                btn_frame, text="取消", width=100,
                fg_color=("#E8E8E8", "#2D2D2D"),
                text_color=("#1A1A1A", "#E0E0E0"),
                command=confirm.destroy
            ).pack(side="left", padx=10)

        except Exception as e:
            logger.debug(f"导入配置失败: {e}")
            self._show_message("导入配置失败")

    def _show_category_manager(self):
        """弹出独立的分类管理对话框"""
        cat_dialog = ctk.CTkToplevel(self)
        apply_acrylic(cat_dialog, parent=self)
        cat_dialog.title("分类管理")
        cat_dialog.geometry("460x440")
        cat_dialog.resizable(False, False)
        cat_dialog.transient(self)
        cat_dialog.grab_set()
        cat_dialog.update_idletasks()
        cx = (cat_dialog.winfo_screenwidth() - 460) // 2
        cy = (cat_dialog.winfo_screenheight() - 440) // 2
        cat_dialog.geometry(f"460x440+{cx}+{cy}")

        ctk.CTkLabel(
            cat_dialog,
            text="分类管理",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(15, 8))

        # 分类列表容器（可滚动）
        cat_list_frame = ctk.CTkScrollableFrame(
            cat_dialog,
            width=400,
            height=260,
            fg_color=("#F5F5F5", "#2A2A2A"),
            corner_radius=8
        )
        cat_list_frame.pack(fill="x", padx=20, pady=(0, 10))
        cat_list_frame._scrollbar.configure(width=0)

        self._cat_list_frame = cat_list_frame
        self._cat_dialog = cat_dialog
        self._render_category_list()

        # 添加分类输入区
        add_frame = ctk.CTkFrame(cat_dialog, fg_color="transparent")
        add_frame.pack(fill="x", padx=20, pady=(0, 10))

        self._new_cat_var = ctk.StringVar()
        entry = ctk.CTkEntry(
            add_frame,
            placeholder_text="输入新分类名称...",
            textvariable=self._new_cat_var,
            height=32,
            corner_radius=8
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        entry.bind("<Return>", lambda e: self._add_category_from_settings())

        ctk.CTkButton(
            add_frame,
            text="+ 添加",
            width=70,
            height=32,
            corner_radius=8,
            fg_color=("#0078D4", "#005A9E"),
            command=self._add_category_from_settings
        ).pack(side="left")

        # 关闭按钮
        ctk.CTkButton(
            cat_dialog,
            text="关闭",
            width=100,
            height=32,
            corner_radius=8,
            fg_color=("#E8E8E8", "#2D2D2D"),
            text_color=("#1A1A1A", "#E0E0E0"),
            command=cat_dialog.destroy
        ).pack(pady=(5, 10))

    def _render_category_list(self):
        """渲染设置界面中的分类列表"""
        # 清空现有内容
        for child in self._cat_list_frame.winfo_children():
            child.destroy()

        for idx, cat in enumerate(self.categories):
            row_frame = ctk.CTkFrame(
                self._cat_list_frame,
                fg_color="transparent"
            )
            row_frame.pack(fill="x", pady=2)

            app_count = len(self.app_config.get(cat, []))
            name_label = ctk.CTkLabel(
                row_frame,
                text=f"  {cat}  ({app_count}个应用)",
                font=ctk.CTkFont(size=13),
                anchor="w",
                width=220
            )
            name_label.pack(side="left", padx=(8, 0))

            # 重命名按钮
            rename_btn = ctk.CTkButton(
                row_frame,
                text="重命名",
                width=60,
                height=26,
                corner_radius=6,
                fg_color=("#E8E8E8", "#2D2D2D"),
                text_color=("#1A1A1A", "#E0E0E0"),
                command=lambda c=cat: self._rename_category_from_settings(c)
            )
            rename_btn.pack(side="right", padx=(4, 8))

            # 删除按钮（第一个默认分类不允许删除）
            if idx > 0:
                del_btn = ctk.CTkButton(
                    row_frame,
                    text="删除",
                    width=50,
                    height=26,
                    corner_radius=6,
                    fg_color=("#E81123", "#C42B1C"),
                    command=lambda c=cat: self._delete_category_from_settings(c)
                )
                del_btn.pack(side="right", padx=(4, 0))
            else:
                ctk.CTkLabel(
                    row_frame,
                    text="默认",
                    font=ctk.CTkFont(size=11),
                    text_color=("#999999", "#777777"),
                    width=50
                ).pack(side="right", padx=(4, 0))

    def _add_category_from_settings(self):
        """从设置界面添加新分类"""
        new_name = self._new_cat_var.get().strip()
        if not new_name:
            self._show_message("请输入分类名称")
            return
        if new_name in self.categories:
            self._show_message(f"分类 '{new_name}' 已存在")
            return

        # 添加分类
        self.categories.append(new_name)
        self.app_config[new_name] = []
        self.category_items_cache[new_name] = []

        # 保存配置
        self._save_config()

        # 刷新UI
        self._render_category_list()
        self._setup_tabs()
        self._new_cat_var.set("")

        self._show_message(f"已添加分类 '{new_name}'")
        logger.info(f"添加分类: {new_name}")

    def _delete_category_from_settings(self, cat_name):
        """从设置界面删除分类"""
        app_count = len(self.app_config.get(cat_name, []))

        # 确认对话框
        confirm = ctk.CTkToplevel(self)
        apply_acrylic(confirm, parent=self)
        confirm.title("确认删除")
        confirm.geometry("360x180")
        confirm.resizable(False, False)
        confirm.transient(self)
        confirm.grab_set()
        confirm.update_idletasks()
        cx = (confirm.winfo_screenwidth() - 360) // 2
        cy = (confirm.winfo_screenheight() - 180) // 2
        confirm.geometry(f"360x180+{cx}+{cy}")

        msg = f"确定删除分类 '{cat_name}' 吗？"
        if app_count > 0:
            msg += f"\n该分类下有 {app_count} 个应用，将一并删除。"

        ctk.CTkLabel(
            confirm,
            text=msg,
            font=ctk.CTkFont(size=13),
            justify="center"
        ).pack(pady=25)

        btn_frame = ctk.CTkFrame(confirm, fg_color="transparent")
        btn_frame.pack()

        def do_delete():
            # 从列表移除
            self.categories.remove(cat_name)
            # 移除配置和缓存
            if cat_name in self.app_config:
                del self.app_config[cat_name]
            if cat_name in self.category_items_cache:
                for item in self.category_items_cache[cat_name]:
                    try:
                        item.destroy()
                    except Exception:
                        pass
                del self.category_items_cache[cat_name]
            # 如果当前分类被删除，切换到第一个
            if self.current_category == cat_name:
                self.current_category = self.categories[0]

            self._save_config()
            self._render_category_list()
            self._setup_tabs()
            self._refresh_grid(force=True)
            confirm.destroy()
            self._show_message(f"已删除分类 '{cat_name}'")
            logger.info(f"删除分类: {cat_name}")

        ctk.CTkButton(
            btn_frame,
            text="确定删除",
            width=90,
            height=30,
            corner_radius=6,
            fg_color=("#E81123", "#C42B1C"),
            command=do_delete
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="取消",
            width=90,
            height=30,
            corner_radius=6,
            fg_color=("#E8E8E8", "#2D2D2D"),
            text_color=("#1A1A1A", "#E0E0E0"),
            command=confirm.destroy
        ).pack(side="left", padx=10)

    def _rename_category_from_settings(self, old_name):
        """从设置界面重命名分类"""
        rename_dlg = ctk.CTkToplevel(self)
        apply_acrylic(rename_dlg, parent=self)
        rename_dlg.title("重命名分类")
        rename_dlg.geometry("340x160")
        rename_dlg.resizable(False, False)
        rename_dlg.transient(self)
        rename_dlg.grab_set()
        rename_dlg.update_idletasks()
        cx = (rename_dlg.winfo_screenwidth() - 340) // 2
        cy = (rename_dlg.winfo_screenheight() - 160) // 2
        rename_dlg.geometry(f"340x160+{cx}+{cy}")

        ctk.CTkLabel(
            rename_dlg,
            text=f"将 '{old_name}' 重命名为：",
            font=ctk.CTkFont(size=13)
        ).pack(pady=(20, 8))

        new_name_var = ctk.StringVar(value=old_name)
        entry = ctk.CTkEntry(
            rename_dlg,
            textvariable=new_name_var,
            width=260,
            height=32,
            corner_radius=8
        )
        entry.pack(pady=(0, 10))
        entry.select_range(0, 'end')
        entry.focus_set()

        def do_rename():
            new_name = new_name_var.get().strip()
            if not new_name:
                return
            if new_name == old_name:
                rename_dlg.destroy()
                return
            if new_name in self.categories:
                self._show_message(f"分类 '{new_name}' 已存在")
                return

            # 更新分类列表
            idx = self.categories.index(old_name)
            self.categories[idx] = new_name

            # 更新 app_config 的 key
            if old_name in self.app_config:
                self.app_config[new_name] = self.app_config.pop(old_name)

            # 更新 cache 的 key
            if old_name in self.category_items_cache:
                self.category_items_cache[new_name] = self.category_items_cache.pop(old_name)

            # 更新当前分类
            if self.current_category == old_name:
                self.current_category = new_name

            self._save_config()
            self._render_category_list()
            self._setup_tabs()
            self._refresh_grid(force=True)
            rename_dlg.destroy()
            self._show_message(f"已重命名为 '{new_name}'")
            logger.info(f"重命名: {old_name} -> {new_name}")

        entry.bind("<Return>", lambda e: do_rename())

        btn_frame = ctk.CTkFrame(rename_dlg, fg_color="transparent")
        btn_frame.pack()

        ctk.CTkButton(
            btn_frame,
            text="确定",
            width=80,
            height=30,
            corner_radius=6,
            fg_color=("#0078D4", "#005A9E"),
            command=do_rename
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame,
            text="取消",
            width=80,
            height=30,
            corner_radius=6,
            fg_color=("#E8E8E8", "#2D2D2D"),
            text_color=("#1A1A1A", "#E0E0E0"),
            command=rename_dlg.destroy
        ).pack(side="left", padx=8)

    def _center_window(self):
        """窗口居中"""
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - WINDOW_WIDTH) // 2
        y = (screen_h - WINDOW_HEIGHT) // 2
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    def _setup_ui(self):
        """设置UI"""
        # 主容器 - 与原生标题栏融为一体，无边框无圆角
        self.main_frame = ctk.CTkFrame(
            self,
            fg_color=("#F3F3F3", "#1F1F1F"),
            corner_radius=0,
            border_width=0
        )
        self.main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # 标题栏
        self._setup_title_bar()

        # 标签页
        self._setup_tabs()

        # 应用网格/拖放区域
        self._setup_app_grid()

        # 底部按钮
        self._setup_bottom_bar()

    def _setup_title_bar(self):
        """标题区域 - 居中显示标题（原生标题栏模式）"""
        title_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="transparent",
            height=36
        )
        title_frame.pack(fill="x", padx=16, pady=(12, 4))
        
        # 标题 - 居中显示
        title_label = ctk.CTkLabel(
            title_frame,
            text="Win11 Launchpad",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=("#1A1A1A", "#E0E0E0")
        )
        title_label.pack(expand=True)

    def _start_move(self, event):
        """开始拖拽窗口"""
        self._x = event.x
        self._y = event.y

    def _on_move(self, event):
        """拖拽窗口"""
        if hasattr(self, '_x') and hasattr(self, '_y'):
            deltax = event.x - self._x
            deltay = event.y - self._y
            x = self.winfo_x() + deltax
            y = self.winfo_y() + deltay
            self.geometry(f"+{x}+{y}")

    def _setup_tabs(self):
        """分类标签页 - 居中显示（支持重复调用重建）"""
        # 销毁旧的Tab框架（如果存在）
        if hasattr(self, '_tabs_frame') and self._tabs_frame.winfo_exists():
            self._tabs_frame.destroy()

        self._tabs_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="transparent"
        )
        self._tabs_frame.pack(fill="x", padx=12, pady=8)

        # 创建内部容器用于居中按钮
        self._tabs_inner = ctk.CTkFrame(
            self._tabs_frame,
            fg_color="transparent"
        )
        self._tabs_inner.pack(side="top", anchor="center")

        self.tab_buttons = {}
        for cat in self.categories:
            btn = ctk.CTkButton(
                self._tabs_inner,
                text=cat,
                width=100,
                height=36,
                corner_radius=8,
                fg_color=("#0078D4", "#005A9E") if cat == self.current_category else ("#E8E8E8", "#2D2D2D"),
                text_color=("white", "white") if cat == self.current_category else ("gray10", "gray90"),
                hover=False,
                command=lambda c=cat: self._switch_category(c)
            )
            btn.pack(side="left", padx=4)
            self.tab_buttons[cat] = btn

    def _setup_app_grid(self):
        """应用网格/拖放区域"""
        scroll_frame = ctk.CTkScrollableFrame(
            self.main_frame,
            fg_color="transparent",
            corner_radius=0
        )
        scroll_frame.pack(fill="both", expand=True, padx=12, pady=8)
        
        # 隐藏滚动条
        scroll_frame._scrollbar.configure(width=0)
        scroll_frame._scrollbar.grid_forget()

        self.grid_frame = ctk.CTkFrame(
            scroll_frame,
            fg_color="transparent"
        )
        self.grid_frame.pack(fill="both", expand=True)
        # 空白处右键菜单：用 add="+" 绑定所有层级，不覆盖原有事件
        def _bind_right(widget):
            try:
                widget.bind("<Button-3>", self._show_grid_context_menu, add="+")
            except Exception:
                pass
        _bind_right(self.grid_frame)
        _bind_right(scroll_frame)
        _bind_right(self.main_frame)
        try:
            _bind_right(scroll_frame._canvas)
        except Exception:
            pass
        try:
            _bind_right(scroll_frame._parent_frame)
        except Exception:
            pass
        # 给主窗口也绑定（最可靠，确保所有空白区域都能触发）
        self.bind("<Button-3>", self._show_grid_context_menu, add="+")


        # 创建拖放区域（初始显示）
        self.drop_zone = DropZone(self.grid_frame, self._handle_dropped_files)
        self.drop_zone.pack(fill="both", expand=True, pady=20)
        
        self.scroll_frame = scroll_frame
        self.app_items = []

    def _setup_bottom_bar(self):
        """底部按钮栏"""
        bottom_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="transparent"
        )
        bottom_frame.pack(fill="x", padx=16, pady=(0, 8))

        add_btn = ctk.CTkButton(
            bottom_frame,
            text="+ 添加应用",
            width=120,
            height=32,
            corner_radius=8,
            fg_color=("#0078D4", "#005A9E"),
            command=self._on_add_app
        )
        add_btn.pack(side="left")

        settings_btn = ctk.CTkButton(
            bottom_frame,
            text="⚙ 设置",
            width=80,
            height=32,
            corner_radius=8,
            fg_color=("#E8E8E8", "#2D2D2D"),
            text_color=("#1A1A1A", "#E0E0E0"),
            command=self._show_settings
        )
        settings_btn.pack(side="right")

        self.status_label = ctk.CTkLabel(
            bottom_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=("#666666", "#888888")
        )
        self.status_label.pack(side="right", padx=(0, 10))

    def _setup_drop_target(self):
        """设置拖放目标 (tkinterdnd2方式)"""
        try:
            logger.debug("Setting up drop target")
            self.update_idletasks()
            
            # 在根窗口注册拖放
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_drop)
            logger.debug("Drop target registered on root window")
            
            # 在主frame上注册
            if hasattr(self.main_frame, 'drop_target_register'):
                self.main_frame.drop_target_register(DND_FILES)
                self.main_frame.dnd_bind('<<Drop>>', self._on_drop)
                logger.debug("Drop target registered on main_frame")
            
            # 在滚动框架上注册
            if hasattr(self.scroll_frame, 'drop_target_register'):
                self.scroll_frame.drop_target_register(DND_FILES)
                self.scroll_frame.dnd_bind('<<Drop>>', self._on_drop)
                logger.debug("Drop target registered on scroll_frame")
            
            # 在网格框架上注册
            if hasattr(self.grid_frame, 'drop_target_register'):
                self.grid_frame.drop_target_register(DND_FILES)
                self.grid_frame.dnd_bind('<<Drop>>', self._on_drop)
                logger.debug("Drop target registered on grid_frame")
            
            # 在拖放区域上注册
            if hasattr(self.drop_zone, 'drop_target_register'):
                self.drop_zone.drop_target_register(DND_FILES)
                self.drop_zone.dnd_bind('<<Drop>>', self._on_drop)
                logger.debug("Drop target registered on drop_zone")
            
            self._show_message("拖拽功能已启用")
            
        except Exception as e:
            logger.debug(f"DnD setup failed: {e}")
            import traceback
            traceback.print_exc()
            self._show_message(f"拖拽设置失败: {str(e)}")

    def _on_drop(self, event):
        """处理拖放事件 (tkinterdnd2)"""
        logger.debug(f"Drop event received: {event}")
        try:
            # 获取拖放的文件路径
            file_paths = self.tk.splitlist(event.data)
            logger.debug(f"Dropped files: {file_paths}")
            
            # 处理文件
            self._handle_dropped_files(file_paths)
                
        except Exception as e:
            logger.debug(f"Drop handler error: {e}")
            import traceback
            traceback.print_exc()
            self._show_message(f"拖放失败: {str(e)}")

    def _handle_dropped_files(self, file_paths):
        """处理拖放的文件
        
        支持从以下来源拖拽：
        1. 桌面快捷方式
        2. Win11开始菜单（可能包含URI或特殊路径）
        3. 文件资源管理器中的exe文件
        """
        added_count = 0
        skipped_count = 0
        invalid_count = 0
        
        for file_path in file_paths:
            # 跳过目录
            if os.path.isdir(file_path):
                skipped_count += 1
                continue
            
            try:
                # 获取应用信息（支持多种格式）
                app_info = get_app_info(file_path)
                
                # 验证应用信息是否有效
                if not app_info or not app_info.get("path"):
                    invalid_count += 1
                    continue
                
                # 检查是否已存在
                exists = False
                for app in self.app_config.get(self.current_category, []):
                    if app.get("path") == app_info["path"]:
                        exists = True
                        skipped_count += 1
                        break
                
                if not exists:
                    self.app_config[self.current_category].append(app_info)
                    added_count += 1
                    logger.info(f"添加应用: {app_info['name']} -> {app_info['path']}")
                    # 如果是从桌面拖入的启动程序文件，删除桌面原文件
                    self._delete_desktop_source_if_program(file_path)
            
            except Exception as e:
                logger.debug(f"处理文件失败 {file_path}: {e}")
                invalid_count += 1
        
        if added_count > 0:
            self.category_items_cache[self.current_category].clear()
            self._refresh_grid(force=True)
            self._save_config()
            self._show_message(f"成功添加 {added_count} 个应用")
        elif invalid_count > 0:
            self._show_message(f"有 {invalid_count} 个项目无法识别或添加")
        else:
            self._show_message("未添加新应用（已存在或无效）")


    def _delete_desktop_source_if_program(self, file_path):
        """如果拖入的文件来自桌面且是启动程序文件，则删除桌面原文件"""
        try:
            # 获取桌面路径（Windows桌面文件夹实际名称始终是Desktop）
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.exists(desktop_path):
                # 兼容中文系统的桌面文件夹
                desktop_path = os.path.join(os.path.expanduser("~"), "桌面")

            file_path_abs = os.path.abspath(file_path)
            desktop_path_abs = os.path.abspath(desktop_path)

            # 不在桌面则不处理
            if not file_path_abs.startswith(desktop_path_abs):
                return

            # 只删除启动程序文件
            program_exts = {'.exe', '.lnk', '.bat', '.cmd', '.com', '.msi', '.appref-ms'}
            file_ext = os.path.splitext(file_path_abs)[1].lower()
            if file_ext not in program_exts:
                return

            # 删除原文件
            if os.path.exists(file_path_abs):
                os.remove(file_path_abs)
                logger.info(f"已删除桌面原文件: {file_path_abs}")
        except Exception as e:
            logger.debug(f"删除桌面原文件失败: {e}")

    def _start_install_monitor(self):
        """启动新安装应用监控（事件驱动，ReadDirectoryChangesW）"""
        try:
            self._known_installed_apps = self._scan_start_menu_apps()
            self._install_monitor_running = True
            logger.debug(f"安装监控已启动（事件驱动），已知应用数: {len(self._known_installed_apps)}")

            import threading
            t = threading.Thread(target=self._fs_monitor_loop, daemon=True)
            t.start()
        except Exception as e:
            logger.debug(f"启动安装监控失败: {e}")

    def _fs_monitor_loop(self):
        """文件系统监控循环 - 使用ReadDirectoryChangesW，事件驱动零占用"""
        try:
            import win32file
            import win32con

            start_menu_paths = [
                os.path.join(os.environ.get('PROGRAMDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
                os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
            ]

            # 为每个开始菜单目录创建监控句柄
            handles = []
            for sm_path in start_menu_paths:
                if os.path.exists(sm_path):
                    hDir = win32file.CreateFile(
                        sm_path,
                        win32con.GENERIC_READ,
                        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
                        None,
                        win32con.OPEN_EXISTING,
                        win32con.FILE_FLAG_BACKUP_SEMANTICS | win32con.FILE_FLAG_OVERLAPPED,
                        None
                    )
                    handles.append((hDir, sm_path))

            if not handles:
                logger.debug("无可用的开始菜单目录，监控未启动")
                return

            while self._install_monitor_running:
                for hDir, sm_path in handles:
                    if not self._install_monitor_running:
                        break
                    try:
                        # 阻塞等待文件变化（零CPU占用）
                        results = win32file.ReadDirectoryChangesW(
                            hDir,
                            8192,
                            True,  # 监控子目录
                            win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_DIR_NAME,
                            None,
                            None
                        )
                        # 检测到变化，延迟2秒等待文件写入完成，然后检查新应用
                        has_new_lnk = any(
                            action in (1, 5) and filename.lower().endswith('.lnk')
                            for action, filename in results
                        )
                        if has_new_lnk:
                            import time
                            time.sleep(2)  # 等待快捷方式写入完成
                            self.after(0, self._check_new_installs)
                    except Exception as e:
                        if self._install_monitor_running:
                            logger.debug(f"目录监控异常: {e}")
                            import time
                            time.sleep(5)

            # 清理句柄
            for hDir, _ in handles:
                try:
                    win32file.CloseHandle(hDir)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"文件监控循环失败: {e}")

    def _scan_start_menu_apps(self):
        """扫描开始菜单中的所有快捷方式，返回应用名称集合"""
        apps = set()
        try:
            start_menu_paths = [
                os.path.join(os.environ.get('PROGRAMDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
                os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
            ]
            for sm_path in start_menu_paths:
                if not os.path.exists(sm_path):
                    continue
                for root, dirs, files in os.walk(sm_path):
                    for f in files:
                        if f.lower().endswith('.lnk'):
                            apps.add(os.path.splitext(f)[0])
        except Exception as e:
            logger.debug(f"扫描开始菜单失败: {e}")
        return apps

    def _check_new_installs(self):
        """检查是否有新安装的应用"""
        try:
            current_apps = self._scan_start_menu_apps()
            if not self._known_installed_apps:
                self._known_installed_apps = current_apps
                return
            new_apps = current_apps - self._known_installed_apps
            self._known_installed_apps = current_apps
            for app_name in new_apps:
                if app_name in self._notified_installs:
                    continue
                skip_keywords = ['uninstall', 'help', 'readme', 'url', '卸载', '帮助', '文档', '网址', '说明']
                if any(kw in app_name.lower() for kw in skip_keywords):
                    continue
                self.after(0, lambda name=app_name: self._show_new_app_dialog(name))
                self._notified_installs.add(app_name)
                logger.debug(f"检测到新安装应用: {app_name}")
        except Exception as e:
            logger.debug(f"检查新安装失败: {e}")

    def _show_new_app_dialog(self, app_name):
        """显示新安装应用提示对话框"""
        try:
            dialog = ctk.CTkToplevel(self)
            apply_acrylic(dialog, parent=self)
            dialog.title("发现新应用")
            dialog.geometry("380x280")
            dialog.resizable(False, False)
            dialog.transient(self)
            dialog.grab_set()
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() - 380) // 2
            y = (dialog.winfo_screenheight() - 280) // 2
            dialog.geometry(f"380x280+{x}+{y}")

            ctk.CTkLabel(dialog, text="发现新安装的应用", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 5))
            ctk.CTkLabel(dialog, text=app_name, font=ctk.CTkFont(size=14)).pack(pady=(0, 15))
            ctk.CTkLabel(dialog, text="选择要添加到的分类：", font=ctk.CTkFont(size=13)).pack(pady=(0, 10))

            selected_cat = ctk.StringVar(value=self.categories[0])
            ctk.CTkOptionMenu(dialog, values=self.categories, variable=selected_cat, width=200, height=32).pack(pady=(0, 20))

            def on_add():
                cat = selected_cat.get()
                lnk_path = self._find_lnk_by_name(app_name)
                if lnk_path:
                    from app_info import get_app_info
                    app_info = get_app_info(lnk_path)
                    if app_info and app_info.get("path"):
                        exists = any(a.get("path") == app_info["path"] for a in self.app_config.get(cat, []))
                        if not exists:
                            self.app_config[cat].append(app_info)
                            self.category_items_cache[cat].clear()
                            self._save_config()
                            if cat == self.current_category:
                                self._refresh_grid(force=True)
                            self._show_message(f"已添加「{app_name}」到「{cat}」")
                        else:
                            self._show_message(f"「{app_name}」已在「{cat}」中")
                    else:
                        self._show_message("无法解析应用信息")
                else:
                    self._show_message("未找到应用快捷方式")
                dialog.destroy()

            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_frame.pack(pady=10)
            ctk.CTkButton(btn_frame, text="添加", width=100, height=32, fg_color=("#0078D4", "#005A9E"), command=on_add).pack(side="left", padx=10)
            ctk.CTkButton(btn_frame, text="忽略", width=100, height=32, fg_color=("#E8E8E8", "#2D2D2D"), text_color=("#1A1A1A", "#E0E0E0"), command=dialog.destroy).pack(side="left", padx=10)
        except Exception as e:
            logger.debug(f"显示新应用对话框失败: {e}")

    def _find_lnk_by_name(self, app_name):
        """根据应用名称查找开始菜单中的.lnk文件路径"""
        try:
            start_menu_paths = [
                os.path.join(os.environ.get('PROGRAMDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
                os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
            ]
            for sm_path in start_menu_paths:
                if not os.path.exists(sm_path):
                    continue
                for root, dirs, files in os.walk(sm_path):
                    for f in files:
                        if f.lower().endswith('.lnk') and os.path.splitext(f)[0] == app_name:
                            return os.path.join(root, f)
        except Exception as e:
            logger.debug(f"查找快捷方式失败: {e}")
        return None

    def _show_scanned_apps(self):
        """显示已扫描的开始菜单应用列表（带复选框批量添加）"""
        try:
            from PIL import ImageTk
            from app_info import get_app_info
            from icon_extractor import get_app_icon

            apps = sorted(getattr(self, '_known_installed_apps', set()))
            if not apps:
                apps = sorted(self._scan_start_menu_apps())

            # 构建「应用名 -> 所在位置列表」映射（含文件夹内应用，位置格式：分类/文件夹）
            added_map = {}
            for cat, cat_apps in self.app_config.items():
                for app in cat_apps:
                    if app.get("type") == "folder":
                        folder_name = app.get("name", "")
                        for sub in app.get("apps", []):
                            nm = sub.get("name", "")
                            if nm:
                                added_map.setdefault(nm, []).append(f"{cat}/{folder_name}")
                    else:
                        nm = app.get("name", "")
                        if nm:
                            added_map.setdefault(nm, []).append(cat)
            added_count = sum(1 for nm in apps if nm in added_map)

            dlg = ctk.CTkToplevel(self)
            apply_acrylic(dlg, parent=self)
            dlg.title(f"已扫描应用（共 {len(apps)} 个）")
            dlg.geometry("440x600")
            dlg.resizable(False, False)
            dlg.transient(self)
            dlg.grab_set()
            dlg.update_idletasks()
            x = (dlg.winfo_screenwidth() - 440) // 2
            y = (dlg.winfo_screenheight() - 600) // 2
            dlg.geometry(f"440x600+{x}+{y}")

            # 顶部信息
            top_frame = ctk.CTkFrame(dlg, fg_color="transparent")
            top_frame.pack(fill="x", padx=15, pady=(10, 5))

            count_label = ctk.CTkLabel(top_frame, text=f"共 {len(apps)} 个 · 已添加 {added_count} 个 · 已选中 0 个", font=ctk.CTkFont(size=13, weight="bold"))
            count_label.pack(side="left")

            # 全选/取消全选
            btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
            btn_frame.pack(fill="x", padx=15, pady=(0, 5))

            checkbox_vars = {}
            item_frames = {}

            def update_count():
                selected = sum(1 for v in checkbox_vars.values() if v.get())
                count_label.configure(text=f"共 {len(apps)} 个 · 已添加 {added_count} 个 · 已选中 {selected} 个")
                add_btn.configure(state="normal" if selected > 0 else "disabled")

            def select_all():
                for v in checkbox_vars.values():
                    v.set(True)
                update_count()

            def deselect_all():
                for v in checkbox_vars.values():
                    v.set(False)
                update_count()

            ctk.CTkButton(btn_frame, text="全选", width=80, height=28, fg_color=("#E8E8E8", "#2D2D2D"), text_color=("#1A1A1A", "#E0E0E0"), command=select_all).pack(side="left", padx=(0, 8))
            ctk.CTkButton(btn_frame, text="取消全选", width=80, height=28, fg_color=("#E8E8E8", "#2D2D2D"), text_color=("#1A1A1A", "#E0E0E0"), command=deselect_all).pack(side="left")

            # 可滚动列表
            scroll_frame = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
            scroll_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

            icon_refs = []

            def load_icon_async(app_name, icon_label):
                try:
                    lnk_path = self._find_lnk_by_name(app_name)
                    if not lnk_path:
                        return
                    app_info = get_app_info(lnk_path)
                    if not app_info or not app_info.get("path"):
                        return
                    icon_img = get_app_icon(app_info["path"], size=24)
                    if icon_img:
                        photo = ImageTk.PhotoImage(icon_img)
                        icon_refs.append(photo)
                        self.after(0, lambda: icon_label.configure(image=photo, text=""))
                except Exception as e:
                    logger.debug(f"加载应用图标失败 {app_name}: {e}")

            for idx, app_name in enumerate(apps, 1):
                item = ctk.CTkFrame(scroll_frame, fg_color="transparent", height=32)
                item.pack(fill="x", pady=1)

                var = ctk.BooleanVar(value=False)
                checkbox_vars[app_name] = var

                cb = ctk.CTkCheckBox(item, text="", variable=var, width=20, height=20, command=update_count)
                cb.pack(side="left", padx=(5, 5))

                icon_label = ctk.CTkLabel(item, text="", width=28, height=28)
                icon_label.pack(side="left", padx=(0, 5))

                ctk.CTkLabel(item, text=f"{idx:3d}.  {app_name}", font=ctk.CTkFont(size=12), anchor="w").pack(side="left", padx=2)

                # 已添加标记：显示所在分类/文件夹，允许跨分类继续添加（复选框不禁用）
                locations = added_map.get(app_name, [])
                if locations:
                    loc_text = "已添加 · " + "、".join(locations[:3])
                    if len(locations) > 3:
                        loc_text += f" 等{len(locations)}处"
                    ctk.CTkLabel(
                        item, text=loc_text,
                        font=ctk.CTkFont(size=10),
                        text_color=("#107C10", "#6CCB6C"),
                        anchor="e"
                    ).pack(side="right", padx=(0, 8))

                if hasattr(self, 'icon_executor'):
                    self.icon_executor.submit(load_icon_async, app_name, icon_label)

            # 底部分类选择和添加按钮
            bottom_frame = ctk.CTkFrame(dlg, fg_color="transparent")
            bottom_frame.pack(fill="x", padx=15, pady=(0, 10))

            ctk.CTkLabel(bottom_frame, text="添加到分类：", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))

            selected_cat = ctk.StringVar(value=self.categories[0])
            cat_menu = ctk.CTkOptionMenu(bottom_frame, values=self.categories, variable=selected_cat, width=120, height=30)
            cat_menu.pack(side="left", padx=(0, 10))

            def batch_add():
                selected_apps = [name for name, v in checkbox_vars.items() if v.get()]
                if not selected_apps:
                    return

                cat = selected_cat.get()
                added = 0
                skipped = 0

                for app_name in selected_apps:
                    lnk_path = self._find_lnk_by_name(app_name)
                    if not lnk_path:
                        skipped += 1
                        continue
                    app_info = get_app_info(lnk_path)
                    if not app_info or not app_info.get("path"):
                        skipped += 1
                        continue
                    # 检查是否已存在
                    exists = any(a.get("path") == app_info["path"] for a in self.app_config.get(cat, []))
                    if exists:
                        skipped += 1
                        continue
                    self.app_config[cat].append(app_info)
                    added += 1

                self.category_items_cache[cat].clear()
                self._save_config()
                if cat == self.current_category:
                    self._refresh_grid(force=True)

                self._show_message(f"成功添加 {added} 个，跳过 {skipped} 个已存在")
                dlg.destroy()

            add_btn = ctk.CTkButton(bottom_frame, text="添加选中", width=100, height=30, fg_color=("#0078D4", "#005A9E"), state="disabled", command=batch_add)
            add_btn.pack(side="left")

            ctk.CTkButton(bottom_frame, text="关闭", width=80, height=30, fg_color=("#E8E8E8", "#2D2D2D"), text_color=("#1A1A1A", "#E0E0E0"), command=dlg.destroy).pack(side="left", padx=(8, 0))

            # 保存到文件
            try:
                list_file = os.path.join(os.environ.get('APPDATA', '.'), "Win11Launcher", "scanned_apps.txt")
                with open(list_file, 'w', encoding='utf-8') as f:
                    f.write(f"开始菜单已扫描应用列表（共 {len(apps)} 个）\n")
                    f.write("=" * 50 + "\n\n")
                    for idx, app_name in enumerate(apps, 1):
                        f.write(f"{idx:3d}. {app_name}\n")
            except Exception as e:
                logger.debug(f"保存应用列表失败: {e}")

        except Exception as e:
            logger.debug(f"显示已扫描应用失败: {e}")

    def _get_folders(self, category=None):
        """获取指定分类的文件夹列表"""
        if category is None:
            category = self.current_category
        apps = self.app_config.get(category, [])
        return [a for a in apps if a.get("type") == "folder"]

    def _create_folder(self, name=None):
        """在当前分类创建新文件夹"""
        if name is None:
            name = f"新建文件夹{len(self._get_folders()) + 1}"
        folder = {
            "type": "folder",
            "name": name,
            "apps": []
        }
        self.app_config[self.current_category].append(folder)
        self._save_config()
        self._refresh_grid(force=True)
        logger.debug(f"创建文件夹: {name}")
        return folder


    def _show_grid_context_menu(self, event):
        """空白处右键菜单：新建文件夹 - Win11风格自定义菜单"""
        # 只在点击空白区域时触发（不是点击应用卡片）
        widget = event.widget
        parent = widget
        while parent:
            if hasattr(parent, 'app_data'):
                return  # 点击的是应用卡片，不显示此菜单
            parent = getattr(parent, '_parent', None) or getattr(parent, 'master', None)
            if parent is None or parent == self.grid_frame:
                break

        x, y = event.x_root, event.y_root

        # 关闭其他已打开的菜单
        if hasattr(self, '_global_context_menus'):
            for menu_win in self._global_context_menus[:]:
                try:
                    if menu_win.winfo_exists():
                        menu_win.destroy()
                except Exception:
                    pass
            self._global_context_menus.clear()

        appearance_mode = ctk.get_appearance_mode()
        if appearance_mode == "Dark":
            bg_color = "#323232"
            fg_color = "#FFFFFF"
            hover_color = "#3D3D3D"
        else:
            bg_color = "#FFFFFF"
            fg_color = "#1A1A1A"
            hover_color = "#E8F0FE"

        menu_window = tk.Toplevel(self)
        menu_window.overrideredirect(True)
        menu_window.attributes("-topmost", True)
        menu_window.config(bg="#000001")
        menu_window.attributes("-transparentcolor", "#000001")

        if not hasattr(self, '_global_context_menus'):
            self._global_context_menus = []
        self._global_context_menus.append(menu_window)

        menu_frame = ctk.CTkFrame(menu_window, fg_color=bg_color, corner_radius=8,
                                  border_width=1, border_color=("#E0D8D0", "#454545"))
        menu_frame.pack(fill="both", expand=True, padx=0, pady=4)

        new_submenu = None
        def close_new_submenu():
            nonlocal new_submenu
            for attr in ['_new_sub_open_timer', '_new_sub_close_timer']:
                if hasattr(self, attr) and getattr(self, attr):
                    self.after_cancel(getattr(self, attr))
                    setattr(self, attr, None)
            if new_submenu and new_submenu.winfo_exists():
                new_submenu.destroy()
            new_submenu = None
            try:
                if new_btn.winfo_exists():
                    new_btn.configure(text="  ➕  新建                  ›")
            except Exception:
                pass

        def create_new_submenu():
            nonlocal new_submenu
            if new_submenu and new_submenu.winfo_exists():
                return
            new_submenu = tk.Toplevel(self)
            new_submenu.overrideredirect(True)
            new_submenu.attributes("-topmost", True)
            new_submenu.config(bg="#000001")
            new_submenu.attributes("-transparentcolor", "#000001")
            items = [("📁","文件夹","folder"),("📄","文本文档","txt"),("📘","Word 文档","docx"),
                     ("📊","Excel 工作表","xlsx"),("📙","PowerPoint 演示","pptx")]
            ns_x, ns_y = x + 165, y
            sf = ctk.CTkFrame(new_submenu, fg_color=bg_color, corner_radius=8, border_width=1, border_color=("#E0D8D0","#454545"))
            sf.pack(fill="both", expand=True, padx=0, pady=2)
            for icon, label, ft in items:
                ctk.CTkButton(sf, text=f"  {icon}  {label}", fg_color="transparent", hover_color=hover_color,
                    text_color=fg_color, anchor="w", height=32, corner_radius=4, font=ctk.CTkFont(size=13),
                    command=lambda f=ft: (close_new_submenu(), menu_window.destroy(), self._create_new_file(f))
                ).pack(fill="x", padx=4, pady=0)
            new_submenu.update_idletasks()
            nh = sf.winfo_reqheight() + 4
            if ns_y + nh > new_submenu.winfo_screenheight():
                ns_y = new_submenu.winfo_screenheight() - nh - 10
            new_submenu.geometry(f"180x{nh}+{ns_x}+{ns_y}")
            new_submenu.update_idletasks()
            _enable_menu_shadow(new_submenu)
            try:
                new_btn.configure(text="  ➕  新建                  ⌄")
            except Exception:
                pass
            def _enter(e):
                if hasattr(self,'_new_sub_close_timer') and self._new_sub_close_timer:
                    self.after_cancel(self._new_sub_close_timer); self._new_sub_close_timer=None
            def _leave(e):
                if hasattr(self,'_new_sub_open_timer') and self._new_sub_open_timer:
                    self.after_cancel(self._new_sub_open_timer); self._new_sub_open_timer=None
                self._new_sub_close_timer = self.after(120, close_new_submenu)
            new_submenu.bind("<Enter>", _enter)
            new_submenu.bind("<Leave>", _leave)

        def _btn_enter(e):
            if hasattr(self,'_new_sub_close_timer') and self._new_sub_close_timer:
                self.after_cancel(self._new_sub_close_timer); self._new_sub_close_timer=None
            self._new_sub_open_timer = self.after(120, create_new_submenu)
        def _btn_leave(e):
            if hasattr(self,'_new_sub_open_timer') and self._new_sub_open_timer:
                self.after_cancel(self._new_sub_open_timer); self._new_sub_open_timer=None
            self._new_sub_close_timer = self.after(120, close_new_submenu)

        new_btn = ctk.CTkButton(menu_frame, text="  ➕  新建                  ›", fg_color="transparent",
            hover_color=hover_color, text_color=fg_color, anchor="w", height=32, corner_radius=4, font=ctk.CTkFont(size=13))
        new_btn.pack(fill="x", padx=4, pady=1)
        new_btn.bind("<Enter>", _btn_enter)
        new_btn.bind("<Leave>", _btn_leave)

        width = 170

        # 先更新布局，获取实际渲染高度
        menu_window.update_idletasks()
        actual_height = menu_frame.winfo_reqheight() + 8

        # 屏幕边界检测
        screen_w = menu_window.winfo_screenwidth()
        screen_h = menu_window.winfo_screenheight()
        if x + width > screen_w:
            x = screen_w - width - 5
        if y + actual_height > screen_h:
            y = y - actual_height - 10

        menu_window.geometry(f"{width}x{actual_height}+{x}+{y}")
        menu_window.update_idletasks()
        _enable_menu_shadow(menu_window)

        def on_esc(event):
            close_new_submenu()
            if menu_window.winfo_exists():
                menu_window.destroy()

        def on_click_outside(event):
            if menu_window.winfo_exists():
                mx, my = event.x_root, event.y_root
                wx, wy = menu_window.winfo_rootx(), menu_window.winfo_rooty()
                ww, wh = menu_window.winfo_width(), menu_window.winfo_height()
                in_menu = wx <= mx < wx + ww and wy <= my < wy + wh
                in_sub = False
                if new_submenu and new_submenu.winfo_exists():
                    sx, sy = new_submenu.winfo_rootx(), new_submenu.winfo_rooty()
                    sw, sh = new_submenu.winfo_width(), new_submenu.winfo_height()
                    in_sub = sx <= mx < sx + sw and sy <= my < sy + sh
                if not in_menu and not in_sub:
                    close_new_submenu()
                    menu_window.destroy()

        def on_destroy():
            try:
                self.unbind("<Escape>", on_esc)
            except Exception:
                pass
            try:
                self.unbind("<Button-1>", on_click_outside)
            except Exception:
                pass
            if hasattr(self, '_global_context_menus') and menu_window in self._global_context_menus:
                self._global_context_menus.remove(menu_window)

        self.bind("<Escape>", on_esc, add=True)
        self.bind("<Button-1>", on_click_outside, add=True)
        menu_window.protocol("WM_DELETE_WINDOW", on_destroy)
        menu_window.bind("<Destroy>", lambda e: on_destroy())

    def _create_folder_with_dialog(self):
        """对话框创建文件夹"""
        dialog = ctk.CTkToplevel(self)
        apply_acrylic(dialog, parent=self)
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
        entry.insert(0, f"文件夹{len(self._get_folders()) + 1}")
        entry.pack(pady=10)
        entry.focus_set()

        def confirm():
            name = entry.get().strip()
            if name:
                self._create_folder(name)
            dialog.destroy()

        entry.bind("<Return>", lambda e: confirm())
        ctk.CTkButton(dialog, text="确定", width=80, command=confirm).pack(pady=10)

    def _create_new_file(self, file_type):
        """新建文件并添加到当前分类 file_type: folder/txt/docx/xlsx/pptx"""
        import time
        if file_type == "folder":
            self._create_folder_with_dialog()
            return
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        type_map = {"txt": ("文本文档", ".txt"), "docx": ("Word 文档", ".docx"),
                    "xlsx": ("Excel 工作表", ".xlsx"), "pptx": ("PowerPoint 演示文稿", ".pptx")}
        if file_type not in type_map:
            return
        name, ext = type_map[file_type]
        base_name = f"新建{name}{timestamp}"
        file_path = os.path.join(desktop, base_name + ext)
        n = 1
        while os.path.exists(file_path):
            file_path = os.path.join(desktop, f"{base_name}({n}){ext}")
            n += 1
        try:
            if file_type == "txt":
                open(file_path, 'w', encoding='utf-8').close()
            else:
                ok = False
                try:
                    import win32com.client
                    pm = {"docx": "Word.Application", "xlsx": "Excel.Application", "pptx": "PowerPoint.Application"}
                    ap = win32com.client.Dispatch(pm[file_type])
                    ap.Visible = False
                    if file_type == "docx":
                        d = ap.Documents.Add(); d.SaveAs(file_path); d.Close()
                    elif file_type == "xlsx":
                        w = ap.Workbooks.Add(); w.SaveAs(file_path); w.Close()
                    else:
                        p = ap.Presentations.Add(); p.SaveAs(file_path); p.Close()
                    ap.Quit(); ok = True
                except Exception:
                    pass
                if not ok:
                    open(file_path, 'wb').close()
        except Exception as e:
            logger.debug(f"新建文件失败: {e}")
            self._show_message(f"新建{name}失败")
            return
        self.app_config[self.current_category].append({"name": base_name, "path": file_path, "icon_path": None, "original_path": None})
        self._save_config()
        self._refresh_grid(force=True)
        self._show_message(f"已新建{name}并添加到启动台")

    def _move_app_to_folder(self, app_data, folder_name):
        """将应用移动到指定文件夹"""
        category = self.current_category
        apps = self.app_config.get(category, [])

        # 从主列表移除
        app_path = app_data.get("path", "")
        removed = None
        for i, app in enumerate(apps):
            if app.get("type") != "folder" and app.get("path", "") == app_path:
                removed = apps.pop(i)
                break

        if not removed:
            return

        # 添加到文件夹
        for app in apps:
            if app.get("type") == "folder" and app.get("name") == folder_name:
                app["apps"].append(removed)
                break

        self._save_config()
        self._refresh_grid(force=True)
        logger.debug(f"应用 {removed.get('name')} 移动到文件夹 {folder_name}")

    def _on_add_app(self):
        """通过文件对话框添加应用（智能浏览Program Files目录）"""
        # 优先浏览 Program Files 目录，让用户更容易找到已安装的程序
        initial_dir = os.environ.get('PROGRAMFILES', 'C:\\Program Files')

        files = filedialog.askopenfilenames(
            title="选择应用程序（建议选择 exe 程序，添加后更稳定）",
            initialdir=initial_dir,
            filetypes=[
                ("可执行文件", "*.exe"),
                ("快捷方式", "*.lnk"),
                ("所有文件", "*.*"),
                ("批处理文件", "*.bat"),
                ("PowerShell脚本", "*.ps1")
            ]
        )

        if files:
            self._handle_dropped_files(files)

    def _switch_category(self, category: str):
        """切换分类 - 复用缓存，不重建卡片"""
        if category == self.current_category:
            return
        self._previous_category = self.current_category
        self.current_category = category

        for cat, btn in self.tab_buttons.items():
            if cat == category:
                btn.configure(
                    fg_color=("#0078D4", "#005A9E"),
                    text_color=("white", "white")
                )
            else:
                btn.configure(
                    fg_color=("#E8E8E8", "#2D2D2D"),
                    text_color=("gray10", "gray90")
                )

        self._refresh_grid(force=False)

    def _refresh_grid(self, force=False):
        """刷新应用网格 - 使用缓存提升性能"""
        
        try:
            grid_width = self.grid_frame.winfo_width()
            if grid_width <= 0:
                grid_width = 600
            new_cols = 9
        except Exception as e:
            new_cols = 4
        
        self._current_cols = new_cols
        
        # 只隐藏上一个分类的项目（快速切换），首次加载或force时隐藏全部分类
        if not force and self._previous_category and self._previous_category != self.current_category:
            prev_items = self.category_items_cache.get(self._previous_category, [])
            for item in prev_items:
                try:
                    item.grid_remove()
                except:
                    pass
        else:
            # 隐藏所有分类的项目
            for cat, items in self.category_items_cache.items():
                for item in items:
                    try:
                        item.grid_remove()
                    except:
                        pass
            # 额外清理grid_frame子组件
            for child in self.grid_frame.winfo_children():
                try:
                    child.grid_remove()
                except:
                    pass
        
        # 移除拖放区域（如果存在）
        if hasattr(self, 'drop_zone') and self.drop_zone.winfo_exists():
            self.drop_zone.destroy()
        apps = self.app_config.get(self.current_category, [])
        cached_items = self.category_items_cache[self.current_category]

        if len(apps) == 0:
            # 如果没有应用，显示拖放区域
            # 先清理所有使用grid管理的子组件
            for child in self.grid_frame.winfo_children():
                child.grid_remove()
            
            self.drop_zone = DropZone(self.grid_frame, self._handle_dropped_files)
            self.drop_zone.pack(fill="both", expand=True, pady=20)
            return

        col = 0
        row = 0
        
        # 检查缓存是否有效
        needs_recreate = False
        if force or len(cached_items) != len(apps):
            needs_recreate = True
        else:
            # 检查缓存的app数据是否匹配
            for cached_item, app in zip(cached_items, apps):
                if cached_item.app_data.get("path") != app.get("path"):
                    needs_recreate = True
                    break
        
        if needs_recreate:
            
            # 销毁旧的缓存项目
            for item in cached_items:
                item.destroy()
            cached_items.clear()
            
            # 创建新的
            for idx, app in enumerate(apps):
                item = AppGridItem(
                    self.grid_frame,
                    app_data=app,
                    parent_window=self
                )
                cached_items.append(item)
            
        
        # 重新布局和显示当前分类
        for idx, item in enumerate(cached_items):
            app_name = item.app_data.get('name', '未知')
            item.grid(row=row, column=col, padx=8, pady=8)
            col += 1
            if col >= self._current_cols:
                col = 0
                row += 1

    def _mark_initialized(self):
        """标记初始化完成"""
        self._is_initialized = True
        logger.debug("Window initialized, resize events enabled")

    def _on_window_resize(self, event):
        """窗口大小变化时刷新网格（带防抖）"""
        # 初始化完成后才响应窗口大小变化
        if not self._is_initialized:
            return
            
        if event.width > 100 and event.height > 100:  # 过滤初始小尺寸事件
            # 取消之前的定时器
            if self._resize_timer_id is not None:
                self.after_cancel(self._resize_timer_id)
            # 设置新的定时器（200ms防抖）
            self._resize_timer_id = self.after(200, self._refresh_grid)

    def _show_message(self, msg: str):
        """显示消息"""
        logger.debug(f"Status message: {msg}")
        self.status_label.configure(text=msg)
        self.after(3000, lambda: self.status_label.configure(text=""))


# ============================================================
# 入口
# ============================================================
def main():
    logger.debug("Starting Win11 Launchpad...")
    app = LauncherWindow()
    logger.debug("App created, entering mainloop...")
    app.mainloop()


if __name__ == "__main__":
    main()
