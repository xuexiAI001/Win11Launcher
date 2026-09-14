# -*- coding: utf-8 -*-
"""
图标提取模块 - 从 EXE/DLL/LNK/注册表等多种来源提取应用图标
支持7种提取方法，带磁盘缓存
"""
import os
import hashlib
import logging
import ctypes
from ctypes import wintypes
from PIL import Image

logger = logging.getLogger("Win11Launcher")

APP_NAME = "Win11Launcher"
ICON_CACHE_DIR = os.path.join(os.environ.get('APPDATA', '.'), APP_NAME, "icon_cache")

# Windows API 常量
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
IMAGE_ICON = 1
IDI_APPLICATION = 32512
GCL_HICON = -14
GCL_HICONSM = -34


def _get_icon_cache_path(app_path: str) -> str:
    """获取图标缓存文件路径（基于应用路径的MD5）"""
    path_hash = hashlib.md5(app_path.encode('utf-8')).hexdigest()
    return os.path.join(ICON_CACHE_DIR, f"{path_hash}.png")


def _is_cache_valid(app_path: str, cache_path: str) -> bool:
    """检查缓存是否有效"""
    if not os.path.exists(cache_path):
        return False
    if not os.path.exists(app_path):
        return True  # 源文件可能已删除，但图标应该保留
    try:
        app_mtime = os.path.getmtime(app_path)
        cache_mtime = os.path.getmtime(cache_path)
        return cache_mtime >= app_mtime
    except Exception:
        return False


def _load_icon_from_cache(app_path: str):
    """从缓存加载图标"""
    cache_path = _get_icon_cache_path(app_path)
    if _is_cache_valid(app_path, cache_path):
        try:
            return Image.open(cache_path).convert("RGBA")
        except Exception as e:
            logger.debug(f"加载缓存失败: {e}")
    return None


def _save_icon_to_cache(app_path: str, icon_img):
    """保存图标到缓存"""
    try:
        os.makedirs(ICON_CACHE_DIR, exist_ok=True)
        cache_path = _get_icon_cache_path(app_path)
        icon_img.save(cache_path, "PNG")
    except Exception as e:
        logger.debug(f"保存图标缓存失败: {e}")


def _is_icon_valid(img) -> bool:
    """检查图标是否有效（非全透明、尺寸合理）"""
    if img is None:
        return False
    try:
        if img.width < 8 or img.height < 8:
            return False
        # 检查是否全透明
        if img.mode == "RGBA":
            alpha = img.split()[3]
            if alpha.getextrema()[1] == 0:
                return False
        return True
    except Exception:
        return False


def _prepare_icon_for_display(img: Image.Image, target_size: int = 48) -> Image.Image:
    """预处理图标：缩放、去白底、统一尺寸"""
    if img is None:
        return None
    try:
        img = img.convert("RGBA")
        # 去白底（接近白色的像素设为透明）
        datas = img.getdata()
        new_data = []
        for item in datas:
            if item[0] > 240 and item[1] > 240 and item[2] > 240 and item[3] > 200:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        img.putdata(new_data)
        # 缩放到目标尺寸
        img = img.resize((target_size, target_size), Image.LANCZOS)
        return img
    except Exception as e:
        logger.debug(f"图标预处理失败: {e}")
        return img


def get_app_icon(app_path: str, icon_path: str = None, size: int = 48, original_path: str = None):
    """
    获取应用图标 - 依次尝试7种方法
    返回 PIL.Image 或 None
    """
    # 1. 先查缓存
    cached = _load_icon_from_cache(app_path)
    if cached and _is_icon_valid(cached):
        return _prepare_icon_for_display(cached, size)

    img = None

    # 2. 方法1: ExtractIconEx (从EXE/DLL提取)
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_method1(app_path, icon_path, size)

    # 3. 方法2: ExtractIcon (简化版)
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_method2(app_path, icon_path, size)

    # 4. 方法3: LoadImage (从文件加载图标)
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_method3(app_path, icon_path, size)

    # 5. 方法4: 从快捷方式(.lnk)提取
    if img is None or not _is_icon_valid(img):
        if original_path and original_path.lower().endswith('.lnk'):
            img = _extract_icon_from_lnk(original_path, size)
        elif app_path.lower().endswith('.lnk'):
            img = _extract_icon_from_lnk(app_path, size)

    # 6. 方法5: Shell32 SHGetFileInfo (系统图标)
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_shell32(app_path, size)

    # 7. 方法6: 从注册表查找关联图标
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_from_registry(app_path, size)

    # 8. 方法7: 从 icon_path 指定的图标文件加载
    if (img is None or not _is_icon_valid(img)) and icon_path and os.path.exists(icon_path):
        try:
            img = Image.open(icon_path).convert("RGBA")
        except Exception:
            pass

    # 保存到缓存
    if img and _is_icon_valid(img):
        prepared = _prepare_icon_for_display(img, size)
        _save_icon_to_cache(app_path, prepared)
        return prepared

    return None


# ============================================================
# 7种图标提取方法
# ============================================================

def _extract_icon_method1(app_path: str, icon_path: str, size: int):
    """方法1: ExtractIconEx - 从EXE/DLL提取图标"""
    try:
        if not os.path.exists(app_path):
            logger.debug("方法1: 路径不存在")
            return None

        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        # 提取大图标和小图标
        hicon_large = wintypes.HICON()
        hicon_small = wintypes.HICON()

        result = shell32.ExtractIconExW(
            ctypes.c_wchar_p(app_path),
            0,
            ctypes.byref(hicon_large),
            ctypes.byref(hicon_small),
            1
        )

        if result == 0:
            logger.debug("方法1: ExtractIconEx失败")
            return None

        hicon = hicon_large.value or hicon_small.value
        if not hicon:
            logger.debug("方法1: ExtractIconEx失败")
            return None

        logger.debug(f"方法1: 获取图标句柄成功: {hicon}")

        # 获取图标信息
        class ICONINFO(ctypes.Structure):
            _fields_ = [
                ("fIcon", wintypes.BOOL),
                ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP),
            ]

        icon_info = ICONINFO()
        if not user32.GetIconInfo(hicon, ctypes.byref(icon_info)):
            user32.DestroyIcon(hicon)
            return None

        # 获取位图信息
        class BITMAP(ctypes.Structure):
            _fields_ = [
                ("bmType", wintypes.LONG),
                ("bmWidth", wintypes.LONG),
                ("bmHeight", wintypes.LONG),
                ("bmWidthBytes", wintypes.LONG),
                ("bmPlanes", wintypes.WORD),
                ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p),
            ]

        bmp = BITMAP()
        gdi32 = ctypes.windll.gdi32
        gdi32.GetObjectW(icon_info.hbmColor, ctypes.sizeof(bmp), ctypes.byref(bmp))

        logger.debug(f"方法1: 位图信息 - 宽:{bmp.bmWidth}, 高:{bmp.bmHeight}, 位深:{bmp.bmBitsPixel}")

        if bmp.bmBitsPixel == 0:
            logger.debug("方法1: 位深为0，失败")
            user32.DestroyIcon(hicon)
            gdi32.DeleteObject(icon_info.hbmMask)
            gdi32.DeleteObject(icon_info.hbmColor)
            return None

        # 创建设备上下文
        hdc = user32.GetDC(0)
        mem_dc = gdi32.CreateCompatibleDC(hdc)
        gdi32.SelectObject(mem_dc, icon_info.hbmColor)

        # 获取像素数据
        width = bmp.bmWidth
        height = bmp.bmHeight
        bmi = ctypes.create_string_buffer(ctypes.sizeof(wintypes.BITMAPINFOHEADER) + 256 * 4)
        bmi_header = wintypes.BITMAPINFOHEADER()
        bmi_header.biSize = ctypes.sizeof(wintypes.BITMAPINFOHEADER)
        bmi_header.biWidth = width
        bmi_header.biHeight = -height  # 顶部朝下
        bmi_header.biPlanes = 1
        bmi_header.biBitCount = 32
        bmi_header.biCompression = 0  # BI_RGB
        ctypes.memmove(bmi, ctypes.byref(bmi_header), ctypes.sizeof(bmi_header))

        pixels = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(hdc, icon_info.hbmColor, 0, height, pixels, bmi, 0)

        # 转换为 PIL Image
        img = Image.frombuffer('RGBA', (width, height), pixels.raw, 'raw', 'BGRA', 0, 1)

        # 清理
        user32.ReleaseDC(0, hdc)
        gdi32.DeleteDC(mem_dc)
        gdi32.DeleteObject(icon_info.hbmMask)
        gdi32.DeleteObject(icon_info.hbmColor)
        user32.DestroyIcon(hicon)

        return img

    except Exception as e:
        logger.debug(f"方法1失败: {e}")
        return None


def _extract_icon_method2(app_path: str, icon_path: str, size: int):
    """方法2: ExtractIcon - 简化版图标提取"""
    try:
        if not os.path.exists(app_path):
            logger.debug("方法2: 路径不存在")
            return None

        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        hicon = shell32.ExtractIconW(0, ctypes.c_wchar_p(app_path), 0)
        if hicon == 0 or hicon == 1:
            logger.debug("方法2: ExtractIcon失败")
            return None

        logger.debug(f"方法2: 获取图标句柄成功: {hicon}")

        # 用 PIL 的 ImageWin 或手动转换
        import win32gui
        import win32ui
        import win32con

        # 获取图标尺寸
        icon_info = win32gui.GetIconInfo(hicon)
        bmp_color = icon_info[3]
        bmp_info = win32gui.GetObject(bmp_color)
        width = bmp_info[2]
        height = bmp_info[3]

        # 创建设备上下文
        hdc = win32gui.GetDC(0)
        mem_dc = win32ui.CreateDCFromHandle(hdc)
        compatible_dc = mem_dc.CreateCompatibleDC()
        compatible_dc.SelectObject(bmp_color)

        # 获取像素
        bmi = {'bitCount': 32, 'width': width, 'height': -height, 'planes': 1}
        pixels = win32gui.GetDIBits(hdc, bmp_color, 0, height, None, bmi, win32con.DIB_RGB_COLORS)

        img = Image.frombuffer('RGBA', (width, height), pixels, 'raw', 'BGRA', 0, 1)

        # 清理
        compatible_dc.DeleteDC()
        mem_dc.DeleteDC()
        win32gui.ReleaseDC(0, hdc)
        win32gui.DestroyIcon(hicon)

        return img

    except Exception as e:
        logger.debug(f"方法2失败: {e}")
        return None


def _extract_icon_method3(app_path: str, icon_path: str, size: int):
    """方法3: LoadImage - 从文件加载图标"""
    try:
        if not os.path.exists(app_path):
            logger.debug("方法3: 路径不存在")
            return None

        user32 = ctypes.windll.user32

        hicon = user32.LoadImageW(
            0,
            ctypes.c_wchar_p(app_path),
            IMAGE_ICON,
            size, size,
            LR_LOADFROMFILE | LR_DEFAULTSIZE
        )

        if not hicon:
            logger.debug("方法3: LoadImage失败")
            return None

        logger.debug(f"方法3: LoadImage成功: {hicon}")

        import win32gui
        import win32ui
        import win32con

        icon_info = win32gui.GetIconInfo(hicon)
        bmp_color = icon_info[3]
        bmp_info = win32gui.GetObject(bmp_color)
        width = bmp_info[2]
        height = bmp_info[3]

        hdc = win32gui.GetDC(0)
        mem_dc = win32ui.CreateDCFromHandle(hdc)
        compatible_dc = mem_dc.CreateCompatibleDC()
        compatible_dc.SelectObject(bmp_color)

        bmi = {'bitCount': 32, 'width': width, 'height': -height, 'planes': 1}
        pixels = win32gui.GetDIBits(hdc, bmp_color, 0, height, None, bmi, win32con.DIB_RGB_COLORS)

        img = Image.frombuffer('RGBA', (width, height), pixels, 'raw', 'BGRA', 0, 1)

        compatible_dc.DeleteDC()
        mem_dc.DeleteDC()
        win32gui.ReleaseDC(0, hdc)
        win32gui.DestroyIcon(hicon)

        return img

    except Exception as e:
        logger.debug(f"方法3失败: {e}")
        return None


def _extract_icon_method4(app_path: str, icon_path: str, size: int):
    """方法4: 从指定图标文件加载（.ico/.png/.bmp）"""
    try:
        if icon_path and os.path.exists(icon_path):
            img = Image.open(icon_path)
            return img.convert("RGBA")
        return None
    except Exception as e:
        logger.debug(f"方法4失败: {e}")
        return None


def _extract_icon_from_lnk(lnk_path: str, size: int):
    """从快捷方式(.lnk)提取图标"""
    try:
        if not os.path.exists(lnk_path):
            return None

        import pythoncom
        from win32com.shell import shell, shellcon

        pythoncom.CoInitialize()
        shortcut = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink
        )
        persist_file = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
        persist_file.Load(lnk_path, 0)

        # 获取图标位置
        icon_location, icon_index = shortcut.GetIconLocation()
        if icon_location and os.path.exists(icon_location):
            img = _extract_icon_method1(icon_location, None, size)
            if img:
                return img

        # 获取目标路径，从目标提取
        target_path = shortcut.GetPath(shell.SLGP_UNCPRIORITY)[0]
        if target_path and os.path.exists(target_path):
            return _extract_icon_method1(target_path, None, size)

        return None

    except Exception as e:
        logger.debug(f"LNK提取失败: {e}")
        return None


def _extract_icon_shell32(file_path: str, size: int):
    """方法5: Shell32 SHGetFileInfo - 获取系统关联图标"""
    try:
        if not os.path.exists(file_path):
            logger.debug("Shell32: 文件不存在")
            return None

        import win32gui
        import win32ui
        import win32con
        from win32com.shell import shell, shellcon

        SHGFI_ICON = 0x000000100
        SHGFI_LARGEICON = 0x000000000
        SHGFI_SYSICONINDEX = 0x000004000

        ret, info = shell.SHGetFileInfo(
            file_path,
            0,
            shell.SHGFI_ICON | shell.SHGFI_LARGEICON | shell.SHGFI_SYSICONINDEX
        )

        hicon = info[0]
        if not hicon:
            logger.debug("Shell32: 获取图标句柄失败")
            return None

        logger.debug("Shell32: 获取图标句柄成功")

        icon_info = win32gui.GetIconInfo(hicon)
        bmp_color = icon_info[3]
        bmp_info = win32gui.GetObject(bmp_color)
        width = bmp_info[2]
        height = bmp_info[3]

        hdc = win32gui.GetDC(0)
        mem_dc = win32ui.CreateDCFromHandle(hdc)
        compatible_dc = mem_dc.CreateCompatibleDC()
        compatible_dc.SelectObject(bmp_color)

        bmi = {'bitCount': 32, 'width': width, 'height': -height, 'planes': 1}
        pixels = win32gui.GetDIBits(hdc, bmp_color, 0, height, None, bmi, win32con.DIB_RGB_COLORS)

        img = Image.frombuffer('RGBA', (width, height), pixels, 'raw', 'BGRA', 0, 1)

        compatible_dc.DeleteDC()
        mem_dc.DeleteDC()
        win32gui.ReleaseDC(0, hdc)
        win32gui.DestroyIcon(hicon)

        return img

    except Exception as e:
        logger.debug(f"Shell32提取失败: {e}")
        return None


def _extract_icon_from_registry(file_path: str, size: int):
    """方法6: 从注册表查找文件关联的图标"""
    try:
        import winreg

        ext = os.path.splitext(file_path)[1].lower()
        if not ext:
            return None

        # 查找文件关联
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext) as key:
            prog_id, _ = winreg.QueryValueEx(key, '')

        if not prog_id:
            return None

        # 查找默认图标
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\DefaultIcon") as key:
                icon_value, _ = winreg.QueryValueEx(key, '')
        except FileNotFoundError:
            return None

        if not icon_value:
            return None

        # 解析图标路径和索引
        if ',' in icon_value:
            icon_file, icon_index = icon_value.rsplit(',', 1)
        else:
            icon_file = icon_value
            icon_index = '0'

        # 展开环境变量
        icon_file = os.path.expandvars(icon_file)

        if os.path.exists(icon_file):
            return _extract_icon_method1(icon_file, None, size)

        return None

    except Exception as e:
        logger.debug(f"注册表提取失败: {e}")
        return None
