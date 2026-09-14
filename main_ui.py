# -*- coding: utf-8 -*-
"""
Windows 11 风格软件启动台 - UI重构版
基于 CustomTkinter 5.2.1 开发
"""

import os
import sys
import json

# 高DPI设置 - 在导入任何GUI库之前设置
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception as e:
        print(f"[DEBUG] DPI setting failed: {e}")

from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageTk

# 尝试导入拖放库
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
    print("[DEBUG] tkinterdnd2 imported successfully")
except ImportError as e:
    HAS_DND = False
    print(f"[DEBUG] tkinterdnd2 import failed: {e}")

# 尝试导入全局快捷键库
try:
    from pynput import keyboard
    HAS_HOTKEY = True
    print("[DEBUG] pynput imported successfully")
except ImportError as e:
    HAS_HOTKEY = False
    print(f"[DEBUG] pynput import failed: {e}")

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

APP_NAME = "Win11Launcher"
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

def _get_start_menu_programs_path(all_users=False):
    """获取开始菜单程序文件夹路径"""
    try:
        import ctypes
        from ctypes import wintypes
        
        CSIDL_PROGRAMS = 2
        CSIDL_COMMON_PROGRAMS = 23
        
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if all_users:
            ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_COMMON_PROGRAMS, None, 0, buf)
        else:
            ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PROGRAMS, None, 0, buf)
        return buf.value
    except:
        # 回退到环境变量
        if all_users:
            return os.path.join(os.environ.get('ALLUSERSPROFILE', ''), 'Start Menu', 'Programs')
        else:
            return os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs')

def _parse_shell_link_from_start_menu(app_name: str) -> dict:
    """从开始菜单搜索应用快捷方式"""
    # 搜索用户开始菜单和公共开始菜单
    search_paths = [_get_start_menu_programs_path(False), _get_start_menu_programs_path(True)]
    
    for base_path in search_paths:
        if not os.path.exists(base_path):
            continue
            
        # 递归搜索快捷方式
        for root, dirs, files in os.walk(base_path):
            for filename in files:
                if filename.lower().endswith('.lnk'):
                    lnk_path = os.path.join(root, filename)
                    try:
                        import win32com.client
                        shell = win32com.client.Dispatch("WScript.Shell")
                        shortcut = shell.CreateShortCut(lnk_path)
                        target_path = shortcut.Targetpath
                        
                        # 检查是否匹配应用名称
                        lnk_name = Path(filename).stem
                        if (lnk_name.lower() == app_name.lower() or 
                            target_path.lower().find(app_name.lower()) != -1):
                            # 获取图标路径
                            icon_path = None
                            if shortcut.IconLocation:
                                icon_location = shortcut.IconLocation[0] if isinstance(shortcut.IconLocation, tuple) else shortcut.IconLocation
                                if icon_location and os.path.exists(icon_location):
                                    icon_path = icon_location
                            if not icon_path and target_path and os.path.exists(target_path):
                                icon_path = target_path
                                
                            return {
                                "name": lnk_name,
                                "path": target_path,
                                "original_path": lnk_path,
                                "icon_path": icon_path
                            }
                    except Exception as e:
                        continue
    return None

def _parse_application_uri(uri: str) -> dict:
    """解析应用URI（如 ms-appx:// 或 shell:::）"""
    # 处理 ms-appx:// 格式
    if uri.startswith('ms-appx://'):
        try:
            # 从注册表查找UWP应用信息
            import winreg
            app_id = uri.replace('ms-appx://', '').strip('/')
            if '!' in app_id:
                app_id = app_id.split('!')[0]
            
            # 搜索注册表中的应用信息
            reg_paths = [
                rf"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages\{app_id}",
                rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{app_id}"
            ]
            
            for reg_path in reg_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                        try:
                            display_name = winreg.QueryValueEx(key, "DisplayName")[0]
                        except:
                            display_name = app_id
                        return {
                            "name": display_name,
                            "path": uri,
                            "original_path": uri,
                            "icon_path": None
                        }
                except:
                    continue
        except:
            pass
    
    # 处理 shell::: 格式
    elif uri.startswith('shell:::'):
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            # 尝试解析shell路径
            return {
                "name": "系统应用",
                "path": uri,
                "original_path": uri,
                "icon_path": None
            }
        except:
            pass
    
    return None

def get_app_info(file_path: str) -> dict:
    """获取应用信息
    
    支持多种拖拽来源：
    1. 普通文件/快捷方式
    2. Win11开始菜单拖拽（可能包含特殊URI或路径）
    3. UWP应用（ms-appx:// 格式）
    
    无论拖拽的是快捷方式还是exe，都提取目标程序路径进行保存。
    这样只依赖程序本身，不依赖快捷方式。
    
    特别注意：完全保留拖拽文件的原始显示名称，拖拽时显示什么名字就显示什么名字。
    """
    # 清理路径（处理开始菜单拖拽可能带有的额外字符）
    original_file_path = file_path.strip()
    file_path = original_file_path
    
    # 处理特殊URI格式（从开始菜单拖拽的UWP应用等）
    if file_path.startswith('ms-appx://') or file_path.startswith('shell:::'):
        result = _parse_application_uri(file_path)
        if result:
            return result
    
    # 处理可能带有引号的路径
    if (file_path.startswith('"') and file_path.endswith('"')) or \
       (file_path.startswith("'") and file_path.endswith("'")):
        file_path = file_path[1:-1]
        original_file_path = file_path
    
    # 处理 file:// 协议路径
    if file_path.startswith('file:///'):
        import urllib.parse
        file_path = urllib.parse.unquote(file_path[8:])
        original_file_path = file_path
    
    path = Path(file_path)
    # 直接使用原始文件名（不带扩展名），不做任何修改
    name = path.stem
    icon_path = None
    target_path = None
    
    # 如果是快捷方式，尝试解析目标路径
    if file_path.lower().endswith('.lnk'):
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(file_path)
            target_path = shortcut.Targetpath
            
            # 获取图标路径（优先从目标程序提取）
            if shortcut.IconLocation:
                icon_location = shortcut.IconLocation[0] if isinstance(shortcut.IconLocation, tuple) else shortcut.IconLocation
                if icon_location and os.path.exists(icon_location):
                    icon_path = icon_location
                elif target_path and os.path.exists(target_path):
                    # 图标位置无效时，从目标程序提取
                    icon_path = target_path
            elif target_path and os.path.exists(target_path):
                icon_path = target_path
                
        except Exception as e:
            print(f"[DEBUG] Failed to parse lnk: {e}")
            # 如果无法解析，尝试从开始菜单搜索
            result = _parse_shell_link_from_start_menu(name)
            if result:
                return result
    
    # 如果目标路径存在，使用目标路径；否则使用原文件路径
    final_path = target_path if (target_path and os.path.exists(target_path)) else file_path
    
    # 如果最终路径不存在，尝试从开始菜单搜索
    if not os.path.exists(final_path):
        result = _parse_shell_link_from_start_menu(name)
        if result:
            return result
    
    return {
        "name": name,           # 完全保留原始文件名
        "path": final_path,
        "original_path": original_file_path,  # 保存原始路径（可能是快捷方式）
        "icon_path": icon_path
    }

def _get_icon_cache_path(app_path: str) -> str:
    """获取图标缓存文件路径（基于应用路径的MD5）"""
    import hashlib
    path_hash = hashlib.md5(app_path.encode('utf-8')).hexdigest()
    return os.path.join(ICON_CACHE_DIR, f"{path_hash}.png")

def _is_cache_valid(app_path: str, cache_path: str) -> bool:
    """检查缓存是否有效
    - 如果缓存文件不存在：无效
    - 如果应用文件不存在：仍使用缓存（源文件可能已删除，但图标应该保留）
    - 如果应用文件存在：应用文件修改时间晚于缓存则无效（需要重新提取）
    """
    if not os.path.exists(cache_path):
        return False
    # 如果缓存存在，无论应用文件是否存在，都认为缓存有效
    # 这样即使应用被删除，之前缓存的图标仍然可以使用
    try:
        if not os.path.exists(app_path):
            return True
        app_mtime = os.path.getmtime(app_path)
        cache_mtime = os.path.getmtime(cache_path)
        return app_mtime <= cache_mtime
    except:
        return True  # 发生异常时仍使用缓存

def _load_icon_from_cache(app_path: str) -> 'Image.Image | None':
    """从缓存加载图标"""
    cache_path = _get_icon_cache_path(app_path)
    if not os.path.exists(cache_path):
        return None
    try:
        from PIL import Image
        img = Image.open(cache_path)
        img = img.convert('RGBA')
        return img
    except Exception as e:
        print(f"[ICON CACHE] 加载缓存失败: {e}")
        return None

def _save_icon_to_cache(app_path: str, icon_img: 'Image.Image'):
    """保存图标到缓存"""
    _ensure_icon_cache_dir()
    cache_path = _get_icon_cache_path(app_path)
    try:
        icon_img.save(cache_path, 'PNG')
    except:
        pass

def get_app_icon(app_path: str, icon_path: str = None, size: int = 48, original_path: str = None):
    """从应用程序提取图标 - 多种方法尝试（支持缓存）
    
    参数:
        app_path: 应用程序路径（可能是目标exe路径）
        icon_path: 图标路径（从快捷方式获取）
        size: 图标大小
        original_path: 原始文件路径（可能是快捷方式路径）
    """
    # 先尝试从缓存加载
    cached_icon = _load_icon_from_cache(app_path)
    if cached_icon:
        return _prepare_icon_for_display(cached_icon, size)

    result = None

    # 方法0: 如果提供了原始路径（快捷方式），先尝试从原始路径提取图标
    # 这很重要，因为即使目标exe不存在，快捷方式文件可能仍包含图标信息
    if original_path and original_path.lower().endswith('.lnk') and os.path.exists(original_path):
        result = _extract_icon_from_lnk(original_path, size)
        if result and _is_icon_valid(result):
            _save_icon_to_cache(app_path, result)
            return _prepare_icon_for_display(result, size)

    # 方法1: 如果提供了icon_path，先尝试从icon_path提取
    if icon_path and os.path.exists(icon_path):
        result = _extract_icon_shell32(icon_path, size)
        if result and _is_icon_valid(result):
            _save_icon_to_cache(app_path, result)
            return _prepare_icon_for_display(result, size)

    # 方法2: 使用 SHGetFileInfo (最可靠)
    if os.path.exists(app_path):
        result = _extract_icon_shell32(app_path, size)
        if result and _is_icon_valid(result):
            _save_icon_to_cache(app_path, result)
            return _prepare_icon_for_display(result, size)

    # 方法3: 使用 win32ui
    if os.path.exists(app_path):
        result = _extract_icon_method4(app_path, icon_path, size)
        if result and _is_icon_valid(result):
            _save_icon_to_cache(app_path, result)
            return _prepare_icon_for_display(result, size)

    # 方法4: 从快捷方式文件提取图标（如果app_path本身是lnk）
    if app_path.lower().endswith('.lnk') and os.path.exists(app_path):
        result = _extract_icon_from_lnk(app_path, size)
        if result and _is_icon_valid(result):
            _save_icon_to_cache(app_path, result)
            return _prepare_icon_for_display(result, size)

    # 方法5: 从注册表获取文件类型图标
    result = _extract_icon_from_registry(app_path, size)
    if result and _is_icon_valid(result):
        _save_icon_to_cache(app_path, result)
        return _prepare_icon_for_display(result, size)

    # 方法6: 使用 win32gui.LoadImage
    if os.path.exists(app_path):
        result = _extract_icon_method3(app_path, icon_path, size)
        if result and _is_icon_valid(result):
            _save_icon_to_cache(app_path, result)
            return _prepare_icon_for_display(result, size)

    # 方法7: 如果原始路径存在且不是lnk，尝试从原始路径提取
    if original_path and os.path.exists(original_path) and not original_path.lower().endswith('.lnk'):
        result = _extract_icon_shell32(original_path, size)
        if result and _is_icon_valid(result):
            _save_icon_to_cache(app_path, result)
            return _prepare_icon_for_display(result, size)

    return None


def _is_icon_valid(img) -> bool:
    """检查图标图像是否有效（有实际内容）"""
    try:
        if img is None:
            return False
        if img.mode != 'RGBA':
            return True

        pixels = list(img.getdata())
        opaque_count = sum(1 for p in pixels if p[3] > 128)
        total_pixels = len(pixels)

        return opaque_count > total_pixels * 0.1
    except:
        return False


def _prepare_icon_for_display(img: Image.Image, target_size: int = 48) -> Image.Image:
    """准备图标显示 - 使用最近邻采样保持锐利，不进行平滑缩放"""
    try:
        if img is None:
            return None

        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        original_size = img.size[0]

        if original_size != target_size:
            if original_size < target_size:
                intermediate = int(target_size * 1.5)
                img = img.resize((intermediate, intermediate), Image.Resampling.NEAREST)
                img = img.resize((target_size, target_size), Image.Resampling.NEAREST)
            else:
                img = img.resize((target_size, target_size), Image.Resampling.NEAREST)

        return img

    except Exception as e:
        print(f"[ICON DEBUG] 图标预处理失败: {e}")
        return img


def _extract_icon_method1(app_path: str, icon_path: str, size: int):
    """方法1: 使用 ctypes 调用 Windows API"""
    try:
        import ctypes
        from ctypes import wintypes
        from PIL import Image
        
        # 检查路径
        if not os.path.exists(app_path):
            print(f"[ICON DEBUG] 方法1: 路径不存在")
            return None
        
        path = icon_path if (icon_path and os.path.exists(icon_path)) else app_path
        
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        
        # 提取图标
        hicon = wintypes.HICON()
        result = user32.ExtractIconExW(path, 0, ctypes.byref(hicon), None, 1)
        
        if result == 0 or not hicon.value:
            print(f"[ICON DEBUG] 方法1: ExtractIconEx失败")
            return None
        
        print(f"[ICON DEBUG] 方法1: 获取图标句柄成功: {hicon.value}")
        
        # 创建位图
        hdc = user32.GetDC(0)
        hbmp = gdi32.CreateCompatibleBitmap(hdc, size, size)
        hdcMem = gdi32.CreateCompatibleDC(hdc)
        gdi32.SelectObject(hdcMem, hbmp)
        
        # 绘制图标
        user32.DrawIconEx(hdcMem, 0, 0, hicon, size, size, 0, None, 0x0003)
        
        # 获取位图信息
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)
            ]
        
        bmp_info = BITMAPINFOHEADER()
        bmp_info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        gdi32.GetDIBits(hdcMem, hbmp, 0, size, None, ctypes.byref(bmp_info), 0)
        
        print(f"[ICON DEBUG] 方法1: 位图信息 - 宽:{bmp_info.biWidth}, 高:{bmp_info.biHeight}, 位深:{bmp_info.biBitCount}")
        
        if bmp_info.biBitCount == 0:
            print(f"[ICON DEBUG] 方法1: 位深为0，失败")
            return None
        
        # 计算缓冲区大小
        bytes_per_pixel = bmp_info.biBitCount // 8
        stride = (bmp_info.biWidth * bytes_per_pixel + 3) // 4 * 4
        buffer_size = stride * bmp_info.biHeight
        
        # 获取位图数据
        bmp_buffer = ctypes.create_string_buffer(buffer_size)
        gdi32.GetDIBits(hdcMem, hbmp, 0, size, ctypes.byref(bmp_buffer), ctypes.byref(bmp_info), 0)
        
        # 创建PIL图像
        img = Image.frombuffer("BGRA", (bmp_info.biWidth, bmp_info.biHeight), 
                             bmp_buffer, "raw", "BGRA", stride, 1)
        
        # 清理资源
        gdi32.DeleteDC(hdcMem)
        gdi32.DeleteObject(hbmp)
        user32.ReleaseDC(0, hdc)
        user32.DestroyIcon(hicon)
        
        return img
        
    except Exception as e:
        print(f"[ICON DEBUG] 方法1失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _extract_icon_method2(app_path: str, icon_path: str, size: int):
    """方法2: 使用 win32gui + PIL"""
    try:
        from PIL import Image
        import win32gui
        import win32con
        import win32api
        
        if not os.path.exists(app_path):
            return None
        
        path = icon_path if (icon_path and os.path.exists(icon_path)) else app_path
        
        # 使用 win32gui.ExtractIcon
        hicon = win32gui.ExtractIcon(0, path, 0)
        if not hicon:
            print(f"[ICON DEBUG] 方法2: ExtractIcon失败")
            return None
        
        print(f"[ICON DEBUG] 方法2: 获取图标句柄成功: {hicon}")
        
        # 创建DC和位图
        hdc = win32gui.GetDC(0)
        hbmp = win32gui.CreateCompatibleBitmap(hdc, size, size)
        hdcMem = win32gui.CreateCompatibleDC(hdc)
        win32gui.SelectObject(hdcMem, hbmp)
        
        # 绘制图标
        win32gui.DrawIconEx(hdcMem, 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)
        
        # 获取位图信息
        bmpinfo = win32gui.GetObject(hbmp)
        
        # 使用 ctypes 获取位图数据
        import ctypes
        gdi32 = ctypes.windll.gdi32
        
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)
            ]
        
        bmp_info = BITMAPINFOHEADER()
        bmp_info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        gdi32.GetDIBits(hdcMem, hbmp, 0, size, None, ctypes.byref(bmp_info), 0)
        
        bytes_per_pixel = bmp_info.biBitCount // 8
        stride = (bmp_info.biWidth * bytes_per_pixel + 3) // 4 * 4
        buffer_size = stride * bmp_info.biHeight
        
        bmp_buffer = ctypes.create_string_buffer(buffer_size)
        gdi32.GetDIBits(hdcMem, hbmp, 0, size, ctypes.byref(bmp_buffer), ctypes.byref(bmp_info), 0)
        
        img = Image.frombuffer("BGRA", (bmp_info.biWidth, bmp_info.biHeight), 
                             bmp_buffer, "raw", "BGRA", stride, 1)
        
        win32gui.DeleteDC(hdcMem)
        win32gui.DeleteObject(hbmp)
        win32gui.ReleaseDC(0, hdc)
        win32gui.DestroyIcon(hicon)
        
        return img
        
    except Exception as e:
        print(f"[ICON DEBUG] 方法2失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _extract_icon_method3(app_path: str, icon_path: str, size: int):
    """方法3: 使用 win32gui.LoadImage"""
    try:
        from PIL import Image
        import win32gui
        import win32con
        
        if not os.path.exists(app_path):
            return None
        
        path = icon_path if (icon_path and os.path.exists(icon_path)) else app_path
        
        # 使用 LoadImage 加载图标
        LR_LOADFROMFILE = 0x00000010
        LR_SHARED = 0x00008000
        
        hicon = win32gui.LoadImage(
            0,
            path,
            win32con.IMAGE_ICON,
            size,
            size,
            LR_LOADFROMFILE | LR_SHARED
        )
        
        if not hicon:
            print(f"[ICON DEBUG] 方法3: LoadImage失败")
            return None
        
        print(f"[ICON DEBUG] 方法3: LoadImage成功: {hicon}")
        
        # 创建DC和位图
        hdc = win32gui.GetDC(0)
        hbmp = win32gui.CreateCompatibleBitmap(hdc, size, size)
        hdcMem = win32gui.CreateCompatibleDC(hdc)
        win32gui.SelectObject(hdcMem, hbmp)
        
        # 绘制图标
        win32gui.DrawIconEx(hdcMem, 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)
        
        # 使用 ctypes 获取位图数据
        import ctypes
        gdi32 = ctypes.windll.gdi32
        
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)
            ]
        
        bmp_info = BITMAPINFOHEADER()
        bmp_info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        gdi32.GetDIBits(hdcMem, hbmp, 0, size, None, ctypes.byref(bmp_info), 0)
        
        bytes_per_pixel = bmp_info.biBitCount // 8
        stride = (bmp_info.biWidth * bytes_per_pixel + 3) // 4 * 4
        buffer_size = stride * bmp_info.biHeight
        
        bmp_buffer = ctypes.create_string_buffer(buffer_size)
        gdi32.GetDIBits(hdcMem, hbmp, 0, size, ctypes.byref(bmp_buffer), ctypes.byref(bmp_info), 0)
        
        img = Image.frombuffer("BGRA", (bmp_info.biWidth, bmp_info.biHeight), 
                             bmp_buffer, "raw", "BGRA", stride, 1)
        
        win32gui.DeleteDC(hdcMem)
        win32gui.DeleteObject(hbmp)
        win32gui.ReleaseDC(0, hdc)
        
        return img
        
    except Exception as e:
        print(f"[ICON DEBUG] 方法3失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _extract_icon_method4(app_path: str, icon_path: str, size: int):
    """方法4: 使用 win32ui"""
    try:
        from PIL import Image
        import win32ui
        import win32gui
        import win32con
        
        if not os.path.exists(app_path):
            return None
        
        path = icon_path if (icon_path and os.path.exists(icon_path)) else app_path
        
        # 使用 win32ui 加载图标
        hicon = win32gui.ExtractIcon(0, path, 0)
        if not hicon:
            return None
        
        # 创建设备上下文
        dc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        mem_dc = dc.CreateCompatibleDC()
        
        # 创建位图
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(dc, size, size)
        mem_dc.SelectObject(bmp)
        
        # 绘制图标
        win32gui.DrawIconEx(mem_dc.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)
        
        # 获取位图数据
        bmp_info = bmp.GetInfo()
        bmp_str = bmp.GetBitmapBits(True)
        
        # 创建PIL图像
        img = Image.frombuffer(
            "RGBA",
            (bmp_info['bmWidth'], bmp_info['bmHeight']),
            bmp_str,
            "raw",
            "BGRA",
            bmp_info['bmWidthBytes'],
            1
        )
        
        # 清理资源
        win32gui.DestroyIcon(hicon)
        
        return img
        
    except Exception as e:
        return None


def _extract_icon_from_lnk(lnk_path: str, size: int):
    """从快捷方式文件提取图标"""
    try:
        from win32com.client import Dispatch
        from PIL import Image
        import win32ui
        import win32gui
        import win32con
        
        # 解析快捷方式
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(lnk_path)
        
        # 获取图标路径和索引
        icon_location = shortcut.IconLocation
        icon_path = None
        icon_index = 0
        
        if icon_location and icon_location != '':
            if ',' in icon_location:
                icon_path, icon_index = icon_location.rsplit(',', 1)
                icon_index = int(icon_index)
            else:
                icon_path = icon_location
                icon_index = 0
        else:
            # 如果IconLocation为空，尝试从目标路径提取图标
            target_path = shortcut.Targetpath
            if target_path and os.path.exists(target_path):
                icon_path = target_path
                icon_index = 0
        
        # 如果还是没有图标路径，返回None
        if not icon_path:
            return None
        
        # 提取图标
        hicon = win32gui.ExtractIcon(0, icon_path, icon_index)
        if not hicon:
            return None
        
        # 创建设备上下文
        dc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        mem_dc = dc.CreateCompatibleDC()
        
        # 创建位图
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(dc, size, size)
        mem_dc.SelectObject(bmp)
        
        # 绘制图标
        win32gui.DrawIconEx(mem_dc.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)
        
        # 获取位图数据
        bmp_info = bmp.GetInfo()
        bmp_str = bmp.GetBitmapBits(True)
        
        # 创建PIL图像
        img = Image.frombuffer(
            "RGBA",
            (bmp_info['bmWidth'], bmp_info['bmHeight']),
            bmp_str,
            "raw",
            "BGRA",
            bmp_info['bmWidthBytes'],
            1
        )
        
        # 清理资源
        win32gui.DestroyIcon(hicon)
        
        return img
        
    except Exception as e:
        print(f"[ICON DEBUG] LNK提取失败: {e}")
        return None


def _extract_icon_shell32(file_path: str, size: int):
    """使用 shell32 SHGetFileInfo 提取图标"""
    try:
        import ctypes
        from ctypes import wintypes
        from PIL import Image
        import win32ui
        import win32gui
        import win32con

        if not os.path.exists(file_path):
            print(f"[ICON DEBUG] Shell32: 文件不存在")
            return None

        SHGFI_ICON = 0x000000100
        SHGFI_LARGEICON = 0x000000000

        class SHFILEINFO(ctypes.Structure):
            _fields_ = [
                ("hIcon", wintypes.HICON),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", ctypes.c_uint32),
                ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName", ctypes.c_wchar * 80)
            ]

        shfi = SHFILEINFO()
        shell32 = ctypes.windll.shell32

        result = shell32.SHGetFileInfoW(
            file_path,
            0,
            ctypes.byref(shfi),
            ctypes.sizeof(shfi),
            SHGFI_ICON | SHGFI_LARGEICON
        )

        if result == 0 or not shfi.hIcon:
            print(f"[ICON DEBUG] Shell32: 获取图标句柄失败")
            return None

        hicon = shfi.hIcon
        print(f"[ICON DEBUG] Shell32: 获取图标句柄成功")

        dc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        mem_dc = dc.CreateCompatibleDC()

        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(dc, size, size)
        mem_dc.SelectObject(bmp)

        win32gui.DrawIconEx(mem_dc.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)

        bmp_info = bmp.GetInfo()
        bmp_str = bmp.GetBitmapBits(True)

        img = Image.frombuffer(
            "RGBA",
            (bmp_info['bmWidth'], bmp_info['bmHeight']),
            bmp_str,
            "raw",
            "BGRA",
            bmp_info['bmWidthBytes'],
            1
        )

        win32gui.DestroyIcon(hicon)

        return img

    except Exception as e:
        print(f"[ICON DEBUG] Shell32提取失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _extract_icon_from_registry(file_path: str, size: int):
    """从注册表获取文件类型图标"""
    try:
        import winreg
        import os
        
        # 获取文件扩展名
        _, ext = os.path.splitext(file_path)
        if not ext:
            return None
        
        # 从注册表查找图标
        try:
            # 首先查找 HKEY_CURRENT_USER
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\{ext}\\UserChoice") as key:
                prog_id, _ = winreg.QueryValueEx(key, 'ProgId')
        except:
            prog_id = None
        
        if not prog_id:
            try:
                # 查找 HKEY_CLASSES_ROOT
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext) as key:
                    prog_id, _ = winreg.QueryValueEx(key, '')
            except:
                return None
        
        if not prog_id:
            return None
        
        # 获取图标路径
        try:
            icon_path = None
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\DefaultIcon") as key:
                icon_path, _ = winreg.QueryValueEx(key, '')
        except:
            pass
        
        if not icon_path:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command") as key:
                    cmd, _ = winreg.QueryValueEx(key, '')
                    # 从命令行提取路径
                    if cmd.startswith('"'):
                        icon_path = cmd[1:cmd.index('"', 1)]
                    else:
                        icon_path = cmd.split()[0]
            except:
                return None
        
        if not icon_path or not os.path.exists(icon_path):
            return None
        
        # 解析图标路径和索引
        icon_index = 0
        if ',' in icon_path:
            parts = icon_path.rsplit(',', 1)
            if len(parts) == 2:
                icon_path = parts[0]
                try:
                    icon_index = int(parts[1])
                except:
                    icon_index = 0
        
        # 提取图标
        from PIL import Image
        import win32ui
        import win32gui
        import win32con
        
        hicon = win32gui.ExtractIcon(0, icon_path, icon_index)
        if not hicon:
            return None
        
        dc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        mem_dc = dc.CreateCompatibleDC()
        
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(dc, size, size)
        mem_dc.SelectObject(bmp)
        
        win32gui.DrawIconEx(mem_dc.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, win32con.DI_NORMAL)
        
        bmp_info = bmp.GetInfo()
        bmp_str = bmp.GetBitmapBits(True)
        
        img = Image.frombuffer(
            "RGBA",
            (bmp_info['bmWidth'], bmp_info['bmHeight']),
            bmp_str,
            "raw",
            "BGRA",
            bmp_info['bmWidthBytes'],
            1
        )
        
        win32gui.DestroyIcon(hicon)
        
        return img
        
    except Exception as e:
        print(f"[ICON DEBUG] 注册表提取失败: {e}")
        return None

# ============================================================
# 拖放接收区域
# ============================================================
class DropZone(ctk.CTkFrame):
    """拖放接收区域"""
    
    def __init__(self, parent, drop_callback):
        super().__init__(
            parent,
            fg_color=("#EFEFEF", "#1A1A1A"),
            corner_radius=8,
            border_width=2,
            border_color=("#0078D4", "#0078D4")
        )
        self.drop_callback = drop_callback
        
        # 设置布局
        self.pack_propagate(False)
        
        # 添加提示文字
        self.label = ctk.CTkLabel(
            self,
            text="拖拽文件到这里添加应用",
            font=ctk.CTkFont(size=14),
            text_color=("#666666", "#666666")
        )
        self.label.pack(expand=True)

# ============================================================
# 主窗口类
# ============================================================
class LauncherWindow(TkinterDnD.Tk if HAS_DND else ctk.CTk):
    """启动台主窗口"""

    def __init__(self):
        if HAS_DND:
            print("[DEBUG] Using TkinterDnD.Tk")
            TkinterDnD.Tk.__init__(self)
            self._use_tkdnd = True
        else:
            print("[DEBUG] Using ctk.CTk (no DnD)")
            super().__init__()
            self._use_tkdnd = False

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
        # 加载保存的配置
        self._load_config()

        # 缓存：按分类保存AppGridItem列表
        self.category_items_cache = {cat: [] for cat in self.categories}

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

        # 设置任务栏图标（让无边框窗口在任务栏显示）
        self._setup_taskbar_icon()

        # 监听窗口大小变化 - 使用防抖
        self._resize_timer_id = None
        self._is_initialized = False
        self._current_cols = 4
        self.bind("<Configure>", self._on_window_resize)

        # 初始化完成后设置标志
        self.after(500, self._mark_initialized)

    def _setup_glass_effect(self):
        """设置Windows 11亚克力磨砂效果和窗口圆角"""
        try:
            # 先设置基础透明度（使用保存的值或默认值）
            alpha = self.alpha_var.get() if hasattr(self, 'alpha_var') else 0.96
            self.attributes('-alpha', alpha)
            
            # 设置Windows 11原生亚克力效果（仅Windows）
            if sys.platform == "win32":
                self._setup_acrylic_effect()
            
            print("[DEBUG] 亚克力磨砂效果已启用")
            
        except Exception as e:
            print(f"[DEBUG] 亚克力磨砂效果设置失败: {e}")
    
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
                print("[DEBUG] 亚克力效果设置成功 (SYSTEMBACKDROP_TYPE)")
            else:
                print("[DEBUG] 亚克力效果设置失败，尝试备用方案")
                self._setup_dwm_blur()

        except Exception as e:
            print(f"[DEBUG] DWM亚克力效果失败: {e}")
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
            print("[DEBUG] DWM模糊备用方案已应用")
            
        except Exception as e:
            print(f"[DEBUG] DWM模糊备用方案失败: {e}")

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
                        print(f"[DEBUG] 注册表检测主题: {'深色' if is_dark_mode else '浅色'}")
            
            except Exception as reg_e:
                print(f"[DEBUG] 注册表检测失败: {reg_e}")
                is_dark_mode = (ctk.get_appearance_mode() == "dark")
            
            theme_name = "深色" if is_dark_mode else "浅色"
            print(f"[DEBUG] ========== 开始设置{theme_name}标题栏 ==========")
            
            # ========== 获取正确的窗口句柄 ==========
            self.update_idletasks()
            
            hwnd = self.winfo_id()
            print(f"[DEBUG] winfo_id() = {hwnd}")
            
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            
            # 获取顶层窗口句柄（关键！）
            GetAncestor = user32.GetAncestor
            GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
            GetAncestor.restype = wintypes.HWND
            
            GA_ROOT = 2
            root_hwnd = GetAncestor(hwnd, GA_ROOT)
            if root_hwnd:
                print(f"[DEBUG] GetAncestor(GA_ROOT) = {root_hwnd}")
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
                print(f"[DEBUG] 方法1 DWMWA_USE_IMMERSIVE_DARK_MODE: result={result}, {theme_name}")
            except Exception as e:
                print(f"[DEBUG] 方法1失败: {e}")
            
            # ========== 方法2: SetPropW 设置 UseImmersiveDarkModeColors ==========
            try:
                SetPropW = user32.SetPropW
                SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
                SetPropW.restype = wintypes.BOOL
                
                # 设置窗口属性（1=深色，0=浅色）
                result = SetPropW(hwnd, "UseImmersiveDarkModeColors", wintypes.HANDLE(1 if is_dark_mode else 0))
                print(f"[DEBUG] 方法2 SetPropW(UseImmersiveDarkModeColors): result={result}, {theme_name}")
            except Exception as e:
                print(f"[DEBUG] 方法2失败: {e}")
            
            # ========== 方法3: AllowDarkModeForWindow ==========
            try:
                uxtheme = ctypes.WinDLL('uxtheme', use_last_error=True)
                AllowDarkModeForWindow = uxtheme[133]
                AllowDarkModeForWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
                AllowDarkModeForWindow.restype = wintypes.BOOL
                
                result = AllowDarkModeForWindow(hwnd, True)
                print(f"[DEBUG] 方法3 AllowDarkModeForWindow: result={result}")
            except Exception as e:
                print(f"[DEBUG] 方法3失败: {e}")
            
            # ========== 方法4: FlushDarkMode ==========
            try:
                uxtheme = ctypes.WinDLL('uxtheme', use_last_error=True)
                FlushDarkMode = uxtheme[136]
                FlushDarkMode.argtypes = []
                FlushDarkMode.restype = wintypes.BOOL
                
                result = FlushDarkMode()
                print(f"[DEBUG] 方法4 FlushDarkMode: result={result}")
            except Exception as e:
                print(f"[DEBUG] 方法4失败: {e}")
            
            # ========== 方法5: 刷新非客户区 ==========
            try:
                WM_NCACTIVATE = 0x0086
                WM_NCPAINT = 0x0085
                
                user32.SendMessageW(hwnd, WM_NCACTIVATE, 0, 0)
                user32.SendMessageW(hwnd, WM_NCACTIVATE, 1, 0)
                user32.SendMessageW(hwnd, WM_NCPAINT, 1, 0)
                print("[DEBUG] 方法5 刷新非客户区: 完成")
            except Exception as e:
                print(f"[DEBUG] 方法5失败: {e}")
            
            # ========== 方法6: 强制重绘 ==========
            try:
                SWP_FRAMECHANGED = 0x0020
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                
                user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
                print("[DEBUG] 方法6 强制重绘: 完成")
            except Exception as e:
                print(f"[DEBUG] 方法6失败: {e}")
            
            print(f"[DEBUG] ========== {theme_name}标题栏设置完成 ==========")
            
        except Exception as e:
            print(f"[DEBUG] 设置标题栏颜色失败: {e}")


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
                                print(f"[DEBUG] 注册表检测系统主题: {'深色' if is_dark_mode else '浅色'}")
                    except Exception as reg_e:
                        print(f"[DEBUG] 注册表检测系统主题失败: {reg_e}")
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
                                print(f"[DEBUG] 注册表检测系统主题: {'深色' if is_dark_mode else '浅色'}")
                    except Exception as reg_e:
                        print(f"[DEBUG] 注册表检测系统主题失败: {reg_e}")
            
            appearance_mode = user_choice if user_choice else ctk.get_appearance_mode()
            print(f"[DEBUG] appearance_mode={appearance_mode}, is_dark_mode={is_dark_mode}")
            
            theme_name = "深色" if is_dark_mode else "浅色"
            print(f"[DEBUG] 主题切换：设置{theme_name}标题栏 (模式={appearance_mode})")
            
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
                print(f"[DEBUG] DWMWA_USE_IMMERSIVE_DARK_MODE: result={result}, {theme_name}")
            except Exception as e:
                print(f"[DEBUG] DWMWA_USE_IMMERSIVE_DARK_MODE失败: {e}")
            
            # 方法2: SetPropW
            try:
                SetPropW = user32.SetPropW
                SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
                SetPropW.restype = wintypes.BOOL
                result = SetPropW(hwnd, "UseImmersiveDarkModeColors", wintypes.HANDLE(1 if is_dark_mode else 0))
                print(f"[DEBUG] SetPropW: result={result}, {theme_name}")
            except Exception as e:
                print(f"[DEBUG] SetPropW失败: {e}")
            
            # 方法3: 设置标题栏背景颜色 (DWMWA_CAPTION_COLOR = 35)
            try:
                caption_color = (bg_color_rgb[2] << 16) | (bg_color_rgb[1] << 8) | bg_color_rgb[0]
                color_value = ctypes.c_int(caption_color)
                result = DwmSetWindowAttribute(hwnd, 35, byref(color_value), sizeof(color_value))
                print(f"[DEBUG] DWMWA_CAPTION_COLOR: result={result}, color=#{caption_color:06X} ({theme_name})")
            except Exception as e:
                print(f"[DEBUG] DWMWA_CAPTION_COLOR失败: {e}")
            
            # 方法4: 设置边框颜色 (DWMWA_BORDER_COLOR = 34)
            try:
                border_color_value = ctypes.c_int(caption_color)
                result = DwmSetWindowAttribute(hwnd, 34, byref(border_color_value), sizeof(border_color_value))
                print(f"[DEBUG] DWMWA_BORDER_COLOR: result={result}, color=#{caption_color:06X}")
            except Exception as e:
                print(f"[DEBUG] DWMWA_BORDER_COLOR失败: {e}")
            
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
            
            print(f"[DEBUG] {theme_name}标题栏设置完成（原生标题栏）")
            
        except Exception as e:
            print(f"[DEBUG] 更新标题栏颜色失败: {e}")

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
                print("[DEBUG] 窗口圆角设置成功")
            else:
                print(f"[DEBUG] 窗口圆角设置失败: {result}")
                
        except Exception as e:
            print(f"[DEBUG] 设置窗口圆角失败: {e}")

    def _minimize_window(self):
        """最小化无边框窗口"""
        try:
            # 对于无边框窗口，使用withdraw隐藏，然后使用deiconify恢复
            self.withdraw()
            # 保存窗口位置以便恢复
            self._last_geometry = self.geometry()
            print("[DEBUG] 窗口已最小化")
        except Exception as e:
            print(f"[DEBUG] 最小化窗口失败: {e}")

    def _toggle_visibility(self):
        """切换窗口可见性"""
        try:
            if self.state() == 'normal' or self.winfo_viewable():
                # 使用iconify()最小化到任务栏，而不是withdraw()
                self.iconify()
                print("[DEBUG] 窗口已最小化到任务栏")
            else:
                # 恢复窗口
                self.deiconify()
                self.lift()
                self.focus_force()
                print("[DEBUG] 窗口已显示")
        except Exception as e:
            print(f"[DEBUG] 切换窗口可见性失败: {e}")

    def _setup_global_hotkey(self):
        """设置全局快捷键"""
        if not HAS_HOTKEY:
            print("[DEBUG] 全局快捷键不可用（需安装pynput）")
            return
        
        try:
            # 解析快捷键 Ctrl+Shift+L
            self._hotkey_listener = keyboard.GlobalHotKeys({
                '<ctrl>+<shift>+l': self._toggle_visibility
            })
            self._hotkey_listener.start()
            print("[DEBUG] 全局快捷键 Ctrl+Shift+L 已注册")
        except Exception as e:
            print(f"[DEBUG] 设置全局快捷键失败: {e}")

    def _set_window_icon(self):
        """设置窗口图标"""
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "app.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
                print(f"[DEBUG] 窗口图标设置成功: {icon_path}")
            else:
                print(f"[DEBUG] 窗口图标文件不存在: {icon_path}")
        except Exception as e:
            print(f"[DEBUG] 设置窗口图标失败: {e}")

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
                print("[DEBUG] 任务栏图标设置成功")
            else:
                print("[DEBUG] 任务栏图标设置失败")
                
        except Exception as e:
            print(f"[DEBUG] 设置任务栏图标失败: {e}")

    def _detect_system_theme(self):
        """检测Windows系统主题并设置应用主题"""
        try:
            if sys.platform != "win32":
                print("[DEBUG] 非Windows系统，使用默认主题")
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
                print("[DEBUG] 无法读取注册表，使用默认主题")
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
                print("[DEBUG] 无法读取主题值，使用默认主题")
                ctk.set_appearance_mode("system")
                return
            
            # 0 = 深色主题, 1 = 浅色主题
            if value.value == 0:
                print("[DEBUG] 检测到系统深色主题")
                ctk.set_appearance_mode("dark")
            else:
                print("[DEBUG] 检测到系统浅色主题")
                ctk.set_appearance_mode("light")
                
        except Exception as e:
            print(f"[DEBUG] 检测系统主题失败: {e}")
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
            print(f"[DEBUG] 早期设置{theme_name}标题栏...")
            
            # 强制更新窗口
            self.update()
            
            # 获取窗口句柄 - 尝试多种方法
            hwnd = self.winfo_id()
            print(f"[DEBUG] winfo_id() = {hwnd}")
            
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
                print(f"[DEBUG] GetAncestor(GA_ROOT) = {root_hwnd}")
                hwnd = root_hwnd
            
            # 也尝试GetParent链
            parent_hwnd = GetParent(hwnd)
            if parent_hwnd:
                print(f"[DEBUG] GetParent = {parent_hwnd}")
                # 继续向上查找
                temp = parent_hwnd
                while temp:
                    next_parent = GetParent(temp)
                    if not next_parent:
                        break
                    temp = next_parent
                if temp:
                    print(f"[DEBUG] 顶层父窗口 = {temp}")
                    hwnd = temp
            
            # ========== 方法1: 使用win32api ==========
            try:
                import win32gui
                import win32api
                import win32con
                
                # 尝试使用win32api设置窗口属性
                style = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)
                print(f"[DEBUG] 方法1 win32api.GetWindowLong: style={style}")
                
                # 尝试使用win32gui的SetProp
                ctypes.windll.user32.SetPropW(hwnd, "UseImmersiveDarkModeColors", 1 if is_dark_mode else 0)
                print(f"[DEBUG] 方法1 ctypes.SetPropW: {'深色' if is_dark_mode else '浅色'}")
            except ImportError:
                print("[DEBUG] 方法1 win32api不可用")
            except Exception as e:
                print(f"[DEBUG] 方法1失败: {e}")
            
            # ========== 方法2: SetPropW ==========
            try:
                SetPropW = user32.SetPropW
                SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
                SetPropW.restype = wintypes.BOOL
                result = SetPropW(hwnd, "UseImmersiveDarkModeColors", wintypes.HANDLE(1 if is_dark_mode else 0))
                print(f"[DEBUG] 方法2 SetPropW: result={result}, {'深色' if is_dark_mode else '浅色'}")
            except Exception as e:
                print(f"[DEBUG] 方法2失败: {e}")
            
            # ========== 方法3: DWMWA_USE_IMMERSIVE_DARK_MODE ==========
            try:
                DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
                DwmSetWindowAttribute.argtypes = [wintypes.HWND, ctypes.c_uint, c_void_p, ctypes.c_uint]
                DwmSetWindowAttribute.restype = wintypes.HRESULT
                
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dark_value = ctypes.c_int(1 if is_dark_mode else 0)
                result = DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(dark_value), sizeof(dark_value))
                print(f"[DEBUG] 方法3 DWMWA_USE_IMMERSIVE_DARK_MODE: result={result}, {'深色' if is_dark_mode else '浅色'}")
            except Exception as e:
                print(f"[DEBUG] 方法3失败: {e}")
            
            # ========== 方法4: DWMWA_MICA_EFFECT (Win11) ==========
            try:
                DWMWA_MICA_EFFECT = 38
                mica_value = ctypes.c_int(1 if is_dark_mode else 0)
                result = DwmSetWindowAttribute(hwnd, DWMWA_MICA_EFFECT, byref(mica_value), sizeof(mica_value))
                print(f"[DEBUG] 方法4 DWMWA_MICA_EFFECT: result={result}, {'深色' if is_dark_mode else '浅色'}")
            except Exception as e:
                print(f"[DEBUG] 方法4失败: {e}")
            
            # ========== 方法5: DWMWA_SYSTEMBACKDROP_TYPE (Win11 22H2) ==========
            try:
                DWMWA_SYSTEMBACKDROP_TYPE = 38
                # 2 = Mica Dark, 3 = Mica Light
                backdrop_value = ctypes.c_int(2 if is_dark_mode else 3)
                result = DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, byref(backdrop_value), sizeof(backdrop_value))
                print(f"[DEBUG] 方法5 DWMWA_SYSTEMBACKDROP_TYPE: result={result}, {'深色Mica' if is_dark_mode else '浅色Mica'}")
            except Exception as e:
                print(f"[DEBUG] 方法5失败: {e}")
            
            # ========== 方法6: 强制刷新窗口 ==========
            try:
                SWP_FRAMECHANGED = 0x0020
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                
                user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
                print("[DEBUG] 方法6 强制刷新: 完成")
            except Exception as e:
                print(f"[DEBUG] 方法6失败: {e}")
            
        except Exception as e:
            print(f"[DEBUG] 早期深色标题栏设置失败: {e}")

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
                print(f"[DEBUG] DWMWA_CAPTION_COLOR: result={result}, color=#{caption_color:06X} ({theme_name})")
                
                # 设置边框颜色 (DWMWA_BORDER_COLOR = 34)
                border_color_value = ctypes.c_int(caption_color)
                result2 = DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border_color_value), sizeof(border_color_value))
                
            except Exception as e:
                print(f"[DEBUG] 设置DWM标题栏颜色失败: {e}")
            
            print(f"[DEBUG] 窗口背景设置为透明，标题栏颜色已同步 ({theme_name}主题)")
        except Exception as e:
            print(f"[DEBUG] 设置窗口背景色失败: {e}")
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
                print("[DEBUG] 标题栏颜色设置成功（深色）")
            else:
                print(f"[DEBUG] 标题栏颜色设置失败: {result}")
                
        except Exception as e:
            print(f"[DEBUG] 设置标题栏颜色失败: {e}")

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
                print("[DEBUG] 标题栏颜色设置成功（浅色）")
            else:
                print(f"[DEBUG] 标题栏颜色设置失败: {result}")
                
        except Exception as e:
            print(f"[DEBUG] 设置标题栏颜色失败: {e}")

    def _show_settings(self):
        """显示设置对话框"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("设置")
        dialog.geometry("500x500")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # 居中
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() - 500) // 2
        y = (dialog.winfo_screenheight() - 500) // 2
        dialog.geometry(f"500x500+{x}+{y}")

        # 标题
        title_label = ctk.CTkLabel(
            dialog,
            text="设置",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=20)

        # 快捷键设置
        hotkey_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        hotkey_frame.pack(fill="x", padx=30, pady=10)

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

        # 主题设置
        theme_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        theme_frame.pack(fill="x", padx=30, pady=10)

        theme_label = ctk.CTkLabel(
            theme_frame,
            text="主题颜色：",
            font=ctk.CTkFont(size=14)
        )
        theme_label.pack(side="left", pady=10)

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
        alpha_frame.pack(fill="x", padx=30, pady=10)

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
        autostart_frame.pack(fill="x", padx=30, pady=10)

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
        cat_btn_frame.pack(fill="x", padx=30, pady=(15, 5))

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
        save_btn.pack(pady=20)

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
        cancel_btn.pack(pady=10)

    def _change_theme(self, choice):
        """更改主题（带平滑过渡效果）"""
        print(f"[DEBUG] ========== 主题切换开始 ==========")
        print(f"[DEBUG] 用户选择: {choice}")
        
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
        print(f"[DEBUG] ctk模式: {new_mode}")
        
        ctk.set_appearance_mode(new_mode)
        print(f"[DEBUG] ctk.get_appearance_mode() = {ctk.get_appearance_mode()}")
        
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
        
        print(f"[DEBUG] ========== 主题切换完成 ==========")

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
            print(f"[DEBUG] 检查自启动失败: {e}")
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
                print(f"[DEBUG] 设置开机自启动: {cmd}")
            else:
                # 取消自启动
                try:
                    winreg.DeleteValue(key, "Win11Launchpad")
                    print(f"[DEBUG] 取消开机自启动")
                except WindowsError:
                    pass
            
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[DEBUG] 设置自启动失败: {e}")

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
                        print(f"[DEBUG] 透明度已加载: {alpha_value}")
                    print(f"[DEBUG] 配置已从 {CONFIG_FILE} 加载")
            else:
                print(f"[DEBUG] 配置文件 {CONFIG_FILE} 不存在，使用默认配置")
        except Exception as e:
            print(f"[DEBUG] 加载配置失败: {e}")

    def _save_config(self):
        """保存配置到文件"""
        try:
            _ensure_config_dir()
            # 确保 alpha_var 已初始化
            if not hasattr(self, 'alpha_var'):
                self.alpha_var = ctk.DoubleVar(value=0.96)
            data = {
                "app_config": self.app_config,
                "categories": self.categories,
                "alpha": self.alpha_var.get()
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[DEBUG] 配置已保存到 {CONFIG_FILE}")
        except Exception as e:
            print(f"[DEBUG] 保存配置失败: {e}")

    def _save_settings(self, dialog):
        """保存设置"""
        # 保存快捷键
        new_hotkey = self.hotkey_var.get()
        print(f"[DEBUG] 保存快捷键: {new_hotkey}")

        # 保存主题
        theme_map = {"浅色": "light", "深色": "dark", "跟随系统": "system"}
        ctk.set_appearance_mode(theme_map.get(self.theme_var.get(), "system"))
        
        # 同步更新标题栏颜色
        self._update_titlebar_color_from_ctk()

        # 保存透明度
        self.attributes('-alpha', self.alpha_var.get())

        # 保存开机自启动
        self._set_autostart(self.autostart_var.get())

        self._show_message("设置已保存")
        dialog.destroy()

    def _show_category_manager(self):
        """弹出独立的分类管理对话框"""
        cat_dialog = ctk.CTkToplevel(self)
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
        print(f"[CATEGORY] 添加分类: {new_name}")

    def _delete_category_from_settings(self, cat_name):
        """从设置界面删除分类"""
        app_count = len(self.app_config.get(cat_name, []))

        # 确认对话框
        confirm = ctk.CTkToplevel(self)
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
            print(f"[CATEGORY] 删除分类: {cat_name}")

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
            print(f"[CATEGORY] 重命名: {old_name} -> {new_name}")

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
            print("[DEBUG] Setting up drop target")
            self.update_idletasks()
            
            # 在根窗口注册拖放
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_drop)
            print("[DEBUG] Drop target registered on root window")
            
            # 在主frame上注册
            if hasattr(self.main_frame, 'drop_target_register'):
                self.main_frame.drop_target_register(DND_FILES)
                self.main_frame.dnd_bind('<<Drop>>', self._on_drop)
                print("[DEBUG] Drop target registered on main_frame")
            
            # 在滚动框架上注册
            if hasattr(self.scroll_frame, 'drop_target_register'):
                self.scroll_frame.drop_target_register(DND_FILES)
                self.scroll_frame.dnd_bind('<<Drop>>', self._on_drop)
                print("[DEBUG] Drop target registered on scroll_frame")
            
            # 在网格框架上注册
            if hasattr(self.grid_frame, 'drop_target_register'):
                self.grid_frame.drop_target_register(DND_FILES)
                self.grid_frame.dnd_bind('<<Drop>>', self._on_drop)
                print("[DEBUG] Drop target registered on grid_frame")
            
            # 在拖放区域上注册
            if hasattr(self.drop_zone, 'drop_target_register'):
                self.drop_zone.drop_target_register(DND_FILES)
                self.drop_zone.dnd_bind('<<Drop>>', self._on_drop)
                print("[DEBUG] Drop target registered on drop_zone")
            
            self._show_message("拖拽功能已启用")
            
        except Exception as e:
            print(f"[DEBUG] DnD setup failed: {e}")
            import traceback
            traceback.print_exc()
            self._show_message(f"拖拽设置失败: {str(e)}")

    def _on_drop(self, event):
        """处理拖放事件 (tkinterdnd2)"""
        print(f"[DEBUG] Drop event received: {event}")
        try:
            # 获取拖放的文件路径
            file_paths = self.tk.splitlist(event.data)
            print(f"[DEBUG] Dropped files: {file_paths}")
            
            # 处理文件
            self._handle_dropped_files(file_paths)
                
        except Exception as e:
            print(f"[DEBUG] Drop handler error: {e}")
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
                    print(f"[ADD] 添加应用: {app_info['name']} -> {app_info['path']}")
            
            except Exception as e:
                print(f"[DEBUG] 处理文件失败 {file_path}: {e}")
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
        """切换分类"""
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

        self._refresh_grid(force=True)

    def _refresh_grid(self, force=False):
        """刷新应用网格 - 使用缓存提升性能"""
        # print(f"="*60)
        # print(f"[GRID DEBUG] 开始刷新网格, force={force}")
        
        try:
            grid_width = self.grid_frame.winfo_width()
            if grid_width <= 0:
                grid_width = 600
            new_cols = 9
        except Exception as e:
            new_cols = 4
        
        self._current_cols = new_cols
        # print(f"[GRID DEBUG] 列数: {new_cols}")
        
        # 先隐藏所有分类的项目
        # print(f"[GRID DEBUG] 隐藏所有分类的项目")
        for cat, items in self.category_items_cache.items():
            # print(f"[GRID DEBUG]   分类 {cat}: {len(items)} 个项目")
            for item in items:
                item.grid_remove()
        
        # 额外清理：直接遍历grid_frame的所有子组件，确保所有旧项目都被隐藏
        # 防止缓存被清空但组件仍然存在的问题
        child_count = 0
        for child in self.grid_frame.winfo_children():
            try:
                child.grid_remove()
                child_count += 1
            except:
                pass
        # print(f"[GRID DEBUG] 额外清理了 {child_count} 个grid_frame子组件")
        
        # 移除拖放区域（如果存在）
        if hasattr(self, 'drop_zone') and self.drop_zone.winfo_exists():
            # print(f"[GRID DEBUG] 销毁拖放区域")
            self.drop_zone.destroy()
        apps = self.app_config.get(self.current_category, [])
        cached_items = self.category_items_cache[self.current_category]
        # print(f"[GRID DEBUG] 当前分类 '{self.current_category}'")
        # print(f"[GRID DEBUG] 配置中的应用数量: {len(apps)}")
        # print(f"[GRID DEBUG] 配置中的应用: {[a.get('name') for a in apps]}")
        # print(f"[GRID DEBUG] 缓存中的项目数量: {len(cached_items)}")

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
            # print(f"[DEBUG] Recreating items for '{self.current_category}'")
            # print(f"[DEBUG] Apps list: {[app.get('name') for app in apps]}")
            
            # 销毁旧的缓存项目
            # print(f"[DEBUG] Destroying {len(cached_items)} cached items")
            for item in cached_items:
                item.destroy()
            cached_items.clear()
            # print(f"[DEBUG] Cache cleared, now has {len(cached_items)} items")
            
            # 创建新的
            # print(f"[DEBUG] Creating {len(apps)} new items")
            for idx, app in enumerate(apps):
                item = AppGridItem(
                    self.grid_frame,
                    app_data=app,
                    parent_window=self
                )
                cached_items.append(item)
                # print(f"[DEBUG] Created item {idx}: {app.get('name')}")
            
            # print(f"[DEBUG] Final cache size: {len(cached_items)}")
        
        # 重新布局和显示当前分类
        # print(f"[GRID DEBUG] 开始布局项目，共 {len(cached_items)} 个")
        for idx, item in enumerate(cached_items):
            app_name = item.app_data.get('name', '未知')
            # print(f"[GRID DEBUG]   布局项目 {idx}: {app_name}")
            item.grid(row=row, column=col, padx=8, pady=8)
            col += 1
            if col >= self._current_cols:
                col = 0
                row += 1
        # print(f"[GRID DEBUG] 布局完成")
        # print(f"="*60)

    def _mark_initialized(self):
        """标记初始化完成"""
        self._is_initialized = True
        print("[DEBUG] Window initialized, resize events enabled")

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
        print(f"[DEBUG] Status message: {msg}")
        self.status_label.configure(text=msg)
        self.after(3000, lambda: self.status_label.configure(text=""))


# ============================================================
# 应用网格项类
# ============================================================
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
        
        # 防止frame收缩
        self.pack_propagate(False)

        self._setup_ui(lazy_load=lazy_load)
        
        # 绑定鼠标事件
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
        """鼠标左键点击启动应用 - 添加点击动画"""
        app_path = self.app_data.get("path", "")
        if app_path and os.path.exists(app_path):
            try:
                # 点击动画效果
                self._click_animation()
                
                print(f"[DEBUG] 启动应用: {app_path}")
                os.startfile(app_path)
            except Exception as e:
                print(f"[DEBUG] 启动失败: {e}")

    def _click_animation(self):
        """点击动画 - 闪烁效果"""
        # 第一阶段：深色
        self.configure(fg_color=("#D0D0D0", "#4D4D4D"))
        self.after(50, lambda: self._animate_stage2())

    def _animate_stage2(self):
        """第二阶段：恢复到高亮"""
        self.configure(fg_color=("#F0F8FF", "#3D3D3D"))
        self.after(100, lambda: self._animate_stage3())

    def _animate_stage3(self):
        """第三阶段：根据悬浮状态决定"""
        if self.hover:
            self.configure(fg_color=("#F0F8FF", "#3D3D3D"))
        else:
            self.configure(fg_color=("#FFFFFF", "#2D2D2D"))

    def _on_right_click(self, event):
        """右键点击 - 显示上下文菜单"""
        self._show_context_menu(event.x_root, event.y_root)

    def _show_context_menu(self, x, y):
        """显示右键菜单 - 1:1 复刻 Win11 原生行为"""
        import customtkinter as ctk
        
        # 获取当前主题模式
        appearance_mode = ctk.get_appearance_mode()

        # 根据主题设置颜色 - Win11 风格
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

        # 获取主窗口引用
        root = self.winfo_toplevel()

        # 强制关闭所有已存在的菜单窗口
        def close_all_menus():
            # 关闭所有已知的菜单
            if hasattr(root, '_global_context_menus'):
                for menu_win in root._global_context_menus[:]:
                    try:
                        if menu_win.winfo_exists():
                            menu_win.destroy()
                    except:
                        pass
                root._global_context_menus.clear()
            
            # 关闭二级菜单
            if hasattr(root, '_current_submenu') and root._current_submenu:
                try:
                    if root._current_submenu.winfo_exists():
                        root._current_submenu.destroy()
                except:
                    pass
                root._current_submenu = None
            
            # 取消所有计时器
            for attr in ['_open_submenu_timer', '_close_submenu_timer', '_hover_timer']:
                if hasattr(root, attr):
                    timer = getattr(root, attr)
                    if timer:
                        try:
                            root.after_cancel(timer)
                        except:
                            pass
                        setattr(root, attr, None)

        # 立即执行清理
        close_all_menus()

        # 创建自定义右键菜单窗口
        menu_window = ctk.CTkToplevel(self)
        menu_window.overrideredirect(True)
        menu_window.attributes("-topmost", True)
        menu_window.attributes("-transparentcolor", "#000001")
        menu_window.attributes("-alpha", 0.95)

        # 注册到全局菜单列表
        if not hasattr(root, '_global_context_menus'):
            root._global_context_menus = []
        root._global_context_menus.append(menu_window)

        # 设置菜单内容框架
        menu_frame = ctk.CTkFrame(menu_window, fg_color=bg_color, corner_radius=8)
        menu_frame.pack(fill="both", expand=True, padx=3, pady=3)

        # 二级菜单引用
        submenu = None

        # ============================================
        # Win11 原生二级菜单逻辑
        # ============================================

        # 关闭二级菜单
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

        # 创建并显示二级菜单
        def create_submenu():
            nonlocal submenu
            if submenu and submenu.winfo_exists():
                return

            submenu = ctk.CTkToplevel(self)
            submenu.overrideredirect(True)
            submenu.attributes("-topmost", True)
            
            submenu_height = len(self.parent_window.categories)*28 + 8
            submenu_x = x + 165
            submenu_y = y + 50
            
            # 检查是否超出屏幕底部，如果是则向上偏移
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

            # 二级菜单鼠标事件 - Win11 行为
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

        # 移动分类按钮鼠标事件 - 严格 Win11 120ms 延迟
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

        # 添加菜单项的辅助函数
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

        # 添加菜单项
        add_menu_item("启动", self._launch_app)
        add_menu_item("管理员身份启动", self._launch_as_admin)
        add_menu_item("", None, is_separator=True)

        # 移动分类按钮 - 带箭头
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

        # 设置固定菜单大小
        width = 130
        height = 295
        
        # 检查是否需要向上偏移：菜单超出屏幕底部，或者点击位置在窗口底部区域
        screen_height = menu_window.winfo_screenheight()
        window_bottom = self.winfo_toplevel().winfo_y() + self.winfo_toplevel().winfo_height()
        
        # 如果菜单会超出屏幕底部，或者点击位置在窗口底部区域（底部150像素内），则向上偏移
        if y + height > screen_height or (window_bottom - y < 250):
            y = y - height - 60
        
        menu_window.geometry(f"{width}x{height}+{x}+{y}")

        # ESC键关闭
        def on_esc(event):
            close_submenu()
            if menu_window.winfo_exists():
                menu_window.destroy()

        root.bind("<Escape>", on_esc, add=True)

        # 点击外部关闭菜单
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

        # 菜单销毁时清理
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
        
        # 方法1：直接启动
        if app_path and os.path.exists(app_path):
            os.startfile(app_path)
            return
        
        # 方法2：如果直接路径失效，从原始路径（可能是快捷方式）重新解析目标路径
        original_path = self.app_data.get("original_path")
        if original_path and os.path.exists(original_path):
            try:
                import win32com.client
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortCut(original_path)
                target_path = shortcut.Targetpath
                if target_path and os.path.exists(target_path):
                    print(f"[DEBUG] 原始路径失效，从快捷方式解析新路径: {target_path}")
                    os.startfile(target_path)
                    return
            except Exception as e:
                print(f"[DEBUG] 从快捷方式解析目标路径失败: {e}")
        
        # 方法3：如果路径失效，通过程序名称搜索常见安装目录
        app_name = self.app_data.get("name", "")
        if app_name:
            found_path = self._search_app_in_common_paths(app_name)
            if found_path:
                print(f"[DEBUG] 在常见目录中找到程序: {found_path}")
                os.startfile(found_path)
                return
        
        # 方法4：都无法启动，显示提示
        if app_path:
            if hasattr(self.parent_window, '_show_message'):
                self.parent_window._show_message(f"程序不存在: {os.path.basename(app_path)}")
    
    def _search_app_in_common_paths(self, app_name: str) -> str:
        """在常见安装目录中搜索程序"""
        import glob
        
        # 搜索目录
        search_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), '*', app_name + '.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), '*', app_name + '.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', 'C:\\Users\\' + os.environ.get('USERNAME', '') + '\\AppData\\Local'), 'Programs', '*', app_name + '.exe'),
        ]
        
        for pattern in search_paths:
            try:
                matches = glob.glob(pattern, recursive=True)
                if matches:
                    # 返回找到的第一个
                    for match in matches:
                        if os.path.exists(match):
                            return match
            except Exception as e:
                print(f"[DEBUG] 搜索目录失败 {pattern}: {e}")
        
        # 搜索注册表中的 Uninstall 键
        try:
            import winreg
            app_name_lower = app_name.lower()
            
            # 搜索 HKEY_LOCAL_MACHINE 和 HKEY_CURRENT_USER 的 Uninstall 键
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
                                        # 检查DisplayName是否包含程序名称
                                        try:
                                            display_name = data.lower()
                                            if app_name_lower in display_name:
                                                # 尝试获取InstallLocation
                                                try:
                                                    install_key = winreg.OpenKey(hkey_root, subkey + '\\' + name.split()[0] if '\\' not in name else subkey + '\\' + name)
                                                    install_location, _ = winreg.QueryValueEx(install_key, 'InstallLocation')
                                                    if install_location and os.path.exists(install_location):
                                                        # 在InstallLocation中搜索exe
                                                        for exe_file in glob.glob(os.path.join(install_location, '*.exe')):
                                                            if app_name_lower in exe_file.lower():
                                                                return exe_file
                                                    winreg.CloseKey(install_key)
                                                except:
                                                    pass
                                        except:
                                            pass
                                except OSError:
                                    break
                            winreg.CloseKey(key)
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] 注册表搜索失败: {e}")
        
        return None

    def _launch_as_admin(self):
        """管理员身份启动应用"""
        app_path = self.app_data.get("path", "")
        if app_path and os.path.exists(app_path):
            try:
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(None, "runas", app_path, None, None, 1)
            except Exception as e:
                print(f"[DEBUG] 管理员启动失败: {e}")

    def _do_move_category(self, target_category):
        """执行移动分类"""
        if not self.parent_window:
            return
        
        current_category = self.parent_window.current_category
        if target_category == current_category:
            return
        
        # 使用应用路径作为唯一标识（解决对象引用问题）
        app_path = self.app_data.get("path", "")
        
        # 从当前分类移除
        apps = self.parent_window.app_config[current_category]
        for idx, app in enumerate(apps):
            if app.get("path", "") == app_path:
                del self.parent_window.app_config[current_category][idx]
                break
        
        # 添加到目标分类
        self.parent_window.app_config[target_category].append(self.app_data)
        
        # 清除缓存
        self.parent_window.category_items_cache[current_category].clear()
        self.parent_window.category_items_cache[target_category].clear()

        # 刷新显示
        self.parent_window._refresh_grid(force=True)
        self.parent_window._save_config()

    def _delete_app(self):
        """删除应用"""
        print(f"[DELETE DEBUG] ===== _delete_app 方法被调用 ======")
        print(f"[DELETE DEBUG] parent_window: {self.parent_window}")
        print(f"[DELETE DEBUG] app_data: {self.app_data}")
        
        if not self.parent_window:
            print(f"[DELETE DEBUG] parent_window 为空，返回")
            return
        
        # 创建确认对话框
        dialog = ctk.CTkToplevel(self)
        dialog.title("确认删除")
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # 居中显示对话框
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
            
            # 使用应用路径作为唯一标识来查找和删除（解决对象引用问题）
            app_path = self.app_data.get("path", "")
            apps = self.parent_window.app_config[current_category]
            
            print(f"="*60)
            print(f"[DELETE DEBUG] 开始删除流程")
            print(f"[DELETE DEBUG] 当前分类: {current_category}")
            print(f"[DELETE DEBUG] 目标应用路径: '{app_path}'")
            print(f"[DELETE DEBUG] 目标应用名称: '{self.app_data.get('name', '')}'")
            print(f"[DELETE DEBUG] 删除前应用数量: {len(apps)}")
            print(f"[DELETE DEBUG] 删除前配置中的应用: {[a.get('name') for a in apps]}")
            print(f"[DELETE DEBUG] 删除前缓存数量: {len(self.parent_window.category_items_cache[current_category])}")
            
            # 查找并删除匹配的应用（使用规范化路径比较）
            deleted = False
            target_path = os.path.normpath(app_path).lower() if app_path else ""
            target_name = self.app_data.get("name", "")
            
            # 创建索引列表，避免删除时索引错乱
            indices_to_delete = []
            for idx, app in enumerate(apps):
                app_path_in_config = app.get("path", "")
                config_path = os.path.normpath(app_path_in_config).lower() if app_path_in_config else ""
                app_name = app.get("name", "")
                
                if config_path == target_path or app_name == target_name:
                    indices_to_delete.append(idx)
                    print(f"[DEBUG] 找到匹配应用: 索引 {idx}, 应用名: {app_name}")
            
            # 从后向前删除，避免索引错乱
            for idx in reversed(indices_to_delete):
                deleted_app = self.parent_window.app_config[current_category].pop(idx)
                deleted = True
                print(f"[DEBUG] 成功删除应用: {deleted_app.get('name')}")
            
            print(f"[DELETE DEBUG] 删除后应用数量: {len(self.parent_window.app_config[current_category])}")
            print(f"[DELETE DEBUG] 删除后配置中的应用: {[a.get('name') for a in self.parent_window.app_config[current_category]]}")
            
            if not deleted:
                print(f"[DELETE DEBUG] ⚠️ 未找到匹配的应用")
            else:
                print(f"[DELETE DEBUG] ✅ 删除成功")
            
            # 清除缓存
            print(f"[DELETE DEBUG] 清除缓存前: {len(self.parent_window.category_items_cache[current_category])}")
            self.parent_window.category_items_cache[current_category].clear()
            print(f"[DELETE DEBUG] 清除缓存后: {len(self.parent_window.category_items_cache[current_category])}")
            
            # 刷新显示
            print(f"[DELETE DEBUG] 开始刷新网格...")
            self.parent_window._refresh_grid(force=True)
            self.parent_window._save_config()
            print(f"[DELETE DEBUG] 刷新完成")
            print(f"="*60)
            dialog.destroy()
        
        def on_confirm_click():
            print(f"[DELETE DEBUG] 删除按钮被点击!")
            confirm_delete()
        
        confirm_btn = ctk.CTkButton(
            button_frame,
            text="删除",
            width=100,
            fg_color="#e74c3c",
            hover_color="#c0392b",
            command=on_confirm_click
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
            # 重新设置UI
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
        
        # 居中显示对话框
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
                # 重新设置UI
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
        """显示属性 - 尝试多种方法确保兼容性"""
        import os
        import subprocess
        import ctypes
        from ctypes import wintypes
        
        app_path = self.app_data.get("path", "")
        
        if not app_path or not os.path.exists(app_path):
            return
        
        # 方法1: 直接使用 ShellExecuteW 的 properties 动词
        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "properties", app_path, None, None, 1
            )
            if result > 32:
                return
        except:
            pass
        
        # 方法2: 使用 ShellExecuteExW 带 SEE_MASK_INVOKEIDLIST
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
            sei.fMask = 0x0000000C  # SEE_MASK_INVOKEIDLIST | SEE_MASK_FLAG_NO_UI
            sei.hwnd = None
            sei.lpVerb = "properties"
            sei.lpFile = app_path
            sei.nShow = 1
            
            result = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
            if result:
                return
        except:
            pass
        
        # 方法3: 使用 explorer /select 打开文件所在位置（备选方案）
        try:
            subprocess.Popen(['explorer.exe', f'/select,{app_path}'])
        except:
            pass

    def _setup_ui(self, lazy_load=True):
        """设置UI"""
        # 首先显示字母占位符
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

        # 如果启用延迟加载，在后台异步加载真实图标
        if lazy_load:
            self._load_icon_async()

    def _load_icon_async(self):
        """异步加载图标"""
        def load_icon():
            app_path = self.app_data.get("path", "")
            icon_path = self.app_data.get("icon_path", None)
            original_path = self.app_data.get("original_path", None)
            
            if app_path:
                # 传递original_path参数，以便从原始快捷方式提取图标
                icon_img = get_app_icon(app_path, icon_path, size=48, original_path=original_path)
                if icon_img:
                    photo_img = ImageTk.PhotoImage(icon_img)
                    self.icon_label.configure(
                        text="",
                        image=photo_img,
                        fg_color="transparent"
                    )
                    self.icon_label.image = photo_img
                    self.icon_loaded = True
        
        # 使用 after() 在主循环空闲时执行，不阻塞UI
        self.after_idle(load_icon)


# ============================================================
# 入口
# ============================================================
def main():
    print("[DEBUG] Starting Win11 Launchpad...")
    app = LauncherWindow()
    print("[DEBUG] App created, entering mainloop...")
    app.mainloop()


if __name__ == "__main__":
    main()
