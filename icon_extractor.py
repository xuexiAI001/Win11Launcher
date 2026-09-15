# -*- coding: utf-8 -*-
"""
图标提取模块 - 从 EXE/DLL/LNK/注册表等多种来源提取应用图标
修复版：修复BITMAPINFOHEADER未定义、HICON类型错误、Shell32常量错误等问题
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

# 自定义 BITMAPINFOHEADER 结构体（wintypes中没有）
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]

class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]

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


def _get_icon_cache_path(app_path: str) -> str:
    path_hash = hashlib.md5(app_path.encode('utf-8')).hexdigest()
    return os.path.join(ICON_CACHE_DIR, f"{path_hash}.png")


def _is_cache_valid(app_path: str, cache_path: str) -> bool:
    if not os.path.exists(cache_path):
        return False
    if not os.path.exists(app_path):
        return True
    try:
        return os.path.getmtime(cache_path) >= os.path.getmtime(app_path)
    except Exception:
        return False


def _load_icon_from_cache(app_path: str):
    cache_path = _get_icon_cache_path(app_path)
    if _is_cache_valid(app_path, cache_path):
        try:
            return Image.open(cache_path).convert("RGBA")
        except Exception as e:
            logger.debug(f"加载缓存失败: {e}")
    return None


def _save_icon_to_cache(app_path: str, icon_img):
    try:
        os.makedirs(ICON_CACHE_DIR, exist_ok=True)
        icon_img.save(_get_icon_cache_path(app_path), "PNG")
    except Exception as e:
        logger.debug(f"保存图标缓存失败: {e}")


def _is_icon_valid(img) -> bool:
    if img is None:
        return False
    try:
        if img.width < 8 or img.height < 8:
            return False
        if img.mode == "RGBA":
            if img.split()[3].getextrema()[1] == 0:
                return False
        return True
    except Exception:
        return False


def _prepare_icon_for_display(img: Image.Image, target_size: int = 48) -> Image.Image:
    if img is None:
        return None
    try:
        img = img.convert("RGBA")
        datas = img.getdata()
        new_data = []
        for item in datas:
            if item[0] > 240 and item[1] > 240 and item[2] > 240 and item[3] > 200:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        img.putdata(new_data)
        img = img.resize((target_size, target_size), Image.LANCZOS)
        return img
    except Exception as e:
        logger.debug(f"图标预处理失败: {e}")
        return img


def _hicon_to_pil(hicon, size: int = 48):
    """将HICON句柄转换为PIL Image（核心转换函数，统一处理类型）"""
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        # 设置函数参数类型，避免OverflowError
        user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
        user32.GetIconInfo.restype = wintypes.BOOL

        icon_info = ICONINFO()
        if not user32.GetIconInfo(hicon, ctypes.byref(icon_info)):
            logger.debug("GetIconInfo失败")
            return None

        # 获取位图信息
        gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
        gdi32.GetObjectW.restype = ctypes.c_int

        bmp = BITMAP()
        gdi32.GetObjectW(icon_info.hbmColor, ctypes.sizeof(bmp), ctypes.byref(bmp))

        width = bmp.bmWidth
        height = bmp.bmHeight

        if width == 0 or height == 0 or bmp.bmBitsPixel == 0:
            logger.debug(f"位图信息无效: {width}x{height}, bpp={bmp.bmBitsPixel}")
            user32.DestroyIcon(hicon)
            gdi32.DeleteObject(icon_info.hbmMask)
            gdi32.DeleteObject(icon_info.hbmColor)
            return None

        # 创建设备上下文
        hdc = user32.GetDC(0)
        mem_dc = gdi32.CreateCompatibleDC(hdc)
        gdi32.SelectObject(mem_dc, icon_info.hbmColor)

        # 准备BITMAPINFOHEADER
        bmi_header = BITMAPINFOHEADER()
        bmi_header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi_header.biWidth = width
        bmi_header.biHeight = -height  # 顶部朝下
        bmi_header.biPlanes = 1
        bmi_header.biBitCount = 32
        bmi_header.biCompression = 0  # BI_RGB

        bmi = ctypes.create_string_buffer(ctypes.sizeof(BITMAPINFOHEADER) + 256 * 4)
        ctypes.memmove(bmi, ctypes.byref(bmi_header), ctypes.sizeof(bmi_header))

        pixels = ctypes.create_string_buffer(width * height * 4)

        gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
        gdi32.GetDIBits.restype = ctypes.c_int
        gdi32.GetDIBits(hdc, icon_info.hbmColor, 0, height, pixels, bmi, 0)

        img = Image.frombuffer('RGBA', (width, height), pixels.raw, 'raw', 'BGRA', 0, 1)

        # 清理
        user32.ReleaseDC(0, hdc)
        gdi32.DeleteDC(mem_dc)
        gdi32.DeleteObject(icon_info.hbmMask)
        gdi32.DeleteObject(icon_info.hbmColor)
        user32.DestroyIcon(hicon)

        return img
    except Exception as e:
        logger.debug(f"HICON转PIL失败: {e}")
        return None


def get_app_icon(app_path: str, icon_path: str = None, size: int = 48, original_path: str = None):
    """获取应用图标 - 依次尝试多种方法"""
    cached = _load_icon_from_cache(app_path)
    if cached and _is_icon_valid(cached):
        return _prepare_icon_for_display(cached, size)

    img = None

    # 方法1: ExtractIconEx (ctypes，最可靠)
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_method1(app_path, size)

    # 方法2: win32gui ExtractIconEx (备用)
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_method2(app_path, size)

    # 方法3: Shell32 SHGetFileInfo
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_shell32(app_path, size)

    # 方法4: 从快捷方式提取
    if img is None or not _is_icon_valid(img):
        lnk_path = original_path if original_path and original_path.lower().endswith('.lnk') else app_path
        if lnk_path.lower().endswith('.lnk'):
            img = _extract_icon_from_lnk(lnk_path, size)

    # 方法5: 从注册表查找关联图标
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_from_registry(app_path, size)

    # 方法6: 从指定图标文件加载
    if (img is None or not _is_icon_valid(img)) and icon_path and os.path.exists(icon_path):
        try:
            img = Image.open(icon_path).convert("RGBA")
        except Exception:
            pass

    if img and _is_icon_valid(img):
        prepared = _prepare_icon_for_display(img, size)
        _save_icon_to_cache(app_path, prepared)
        return prepared

    return None


def _extract_icon_method1(app_path: str, size: int):
    """方法1: ExtractIconExW - ctypes实现（已修复类型问题）"""
    try:
        if not os.path.exists(app_path):
            return None

        shell32 = ctypes.windll.shell32

        hicon_large = wintypes.HICON()
        hicon_small = wintypes.HICON()

        shell32.ExtractIconExW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), wintypes.UINT]
        shell32.ExtractIconExW.restype = ctypes.c_uint

        result = shell32.ExtractIconExW(
            app_path, 0,
            ctypes.byref(hicon_large),
            ctypes.byref(hicon_small),
            1
        )

        if result == 0:
            logger.debug("方法1: ExtractIconEx返回0")
            return None

        # 优先用大图标，用HICON对象传递（不是int）
        hicon = hicon_large if hicon_large.value else hicon_small
        if not hicon.value:
            logger.debug("方法1: 图标句柄为空")
            return None

        logger.debug(f"方法1: 获取图标句柄成功: {hicon.value}")
        return _hicon_to_pil(hicon, size)
    except Exception as e:
        logger.debug(f"方法1失败: {e}")
        return None


def _extract_icon_method2(app_path: str, size: int):
    """方法2: win32gui ExtractIconEx - pywin32实现"""
    try:
        if not os.path.exists(app_path):
            return None
        import win32gui
        icons = win32gui.ExtractIconEx(app_path, 0)
        if not icons or not icons[0]:
            logger.debug("方法2: win32gui提取失败")
            return None
        hicon = icons[0][0] if isinstance(icons[0], list) else icons[0]
        logger.debug(f"方法2: win32gui获取句柄: {hicon}")
        # 转换为ctypes HICON
        return _hicon_to_pil(wintypes.HICON(hicon), size)
    except Exception as e:
        logger.debug(f"方法2失败: {e}")
        return None


def _extract_icon_shell32(file_path: str, size: int):
    """方法3: Shell32 SHGetFileInfo - 修复常量引用"""
    try:
        if not os.path.exists(file_path):
            return None

        import win32gui
        from win32com.shell import shell, shellcon

        # 常量从shellcon获取，不是shell
        SHGFI_ICON = getattr(shellcon, 'SHGFI_ICON', 0x100)
        SHGFI_LARGEICON = getattr(shellcon, 'SHGFI_LARGEICON', 0x0)
        SHGFI_SYSICONINDEX = getattr(shellcon, 'SHGFI_SYSICONINDEX', 0x4000)

        ret, info = shell.SHGetFileInfo(
            file_path, 0,
            SHGFI_ICON | SHGFI_LARGEICON | SHGFI_SYSICONINDEX
        )

        hicon = info[0]
        if not hicon:
            logger.debug("Shell32: 图标句柄为空")
            return None

        logger.debug(f"Shell32: 获取图标句柄成功: {hicon}")
        return _hicon_to_pil(wintypes.HICON(hicon), size)
    except Exception as e:
        logger.debug(f"Shell32提取失败: {e}")
        return None


def _extract_icon_from_lnk(lnk_path: str, size: int):
    """从快捷方式(.lnk)提取图标"""
    try:
        if not os.path.exists(lnk_path):
            return None
        import pythoncom
        from win32com.shell import shell

        pythoncom.CoInitialize()
        shortcut = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None,
            pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
        )
        persist_file = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
        persist_file.Load(lnk_path, 0)

        icon_location, icon_index = shortcut.GetIconLocation()
        if icon_location and os.path.exists(icon_location):
            img = _extract_icon_method1(icon_location, size)
            if img:
                return img

        target_path = shortcut.GetPath(shell.SLGP_UNCPRIORITY)[0]
        if target_path and os.path.exists(target_path):
            return _extract_icon_method1(target_path, size)

        return None
    except Exception as e:
        logger.debug(f"LNK提取失败: {e}")
        return None


def _extract_icon_from_registry(file_path: str, size: int):
    """从注册表查找文件关联的图标"""
    try:
        import winreg
        ext = os.path.splitext(file_path)[1].lower()
        if not ext:
            return None
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext) as key:
            prog_id, _ = winreg.QueryValueEx(key, '')
        if not prog_id:
            return None
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\DefaultIcon") as key:
                icon_value, _ = winreg.QueryValueEx(key, '')
        except FileNotFoundError:
            return None
        if not icon_value:
            return None
        if ',' in icon_value:
            icon_file = icon_value.rsplit(',', 1)[0]
        else:
            icon_file = icon_value
        icon_file = os.path.expandvars(icon_file)
        if os.path.exists(icon_file):
            return _extract_icon_method1(icon_file, size)
        return None
    except Exception as e:
        logger.debug(f"注册表提取失败: {e}")
        return None
