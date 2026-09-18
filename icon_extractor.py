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

# COM GUID 结构（用于 SHGetImageList）
class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

def _make_guid(s):
    parts = s.strip('{}').split('-')
    data4 = bytes.fromhex(parts[3] + parts[4])
    return _GUID(int(parts[0], 16), int(parts[1], 16), int(parts[2], 16),
                 (ctypes.c_ubyte * 8)(*data4))

_IID_IImageList = _make_guid("{46EB5926-582E-4017-9FDF-E8998DAA0950}")

# SHGetImageList 常量
_SHGFI_SYSICONINDEX = 0x4000
_SHIL_JUMBO = 0x4  # 256x256
_ILD_TRANSPARENT = 0x00000001

_dpi_scale_cache = None

def _get_dpi_scale():
    """获取系统 DPI 缩放比例（带缓存）"""
    global _dpi_scale_cache
    if _dpi_scale_cache is not None:
        return _dpi_scale_cache
    try:
        _user32 = ctypes.windll.user32
        _user32.SetProcessDPIAware()
        hdc = _user32.GetDC(0)
        dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        _user32.ReleaseDC(0, hdc)
        _dpi_scale_cache = dpi_x / 96.0
    except Exception:
        _dpi_scale_cache = 1.0
    return _dpi_scale_cache

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
    return os.path.join(ICON_CACHE_DIR, f"{path_hash}_hd.png")


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


def _process_icon(img: Image.Image) -> Image.Image:
    """仅做白色背景透明化，不缩放（用于缓存原始大图）"""
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
        return img
    except Exception as e:
        logger.debug(f"图标处理失败: {e}")
        return img


def _prepare_icon_for_display(img: Image.Image, target_size: int = 48) -> Image.Image:
    """白色透明化 + 缩放到目标尺寸（用于显示）"""
    if img is None:
        return None
    try:
        img = _process_icon(img)
        if img.width != target_size or img.height != target_size:
            img = img.resize((target_size, target_size), Image.LANCZOS)
        return img
    except Exception as e:
        logger.debug(f"图标预处理失败: {e}")
        return img


def _hicon_to_pil(hicon, size: int = 48):
    """将HICON句柄转换为PIL Image

    使用 DrawIconEx 渲染到内存位图，兼容 32bpp Alpha 图标、PNG压缩图标和 DIB section。
    旧的 GetIconInfo+SelectObject(hbmColor) 方式对部分 DIB section 会读到全透明像素。
    """
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        # 先通过 GetIconInfo 获取图标真实尺寸（仅用于尺寸，不依赖 hbmColor）
        user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
        user32.GetIconInfo.restype = wintypes.BOOL
        icon_info = ICONINFO()
        width = height = size
        if user32.GetIconInfo(hicon, ctypes.byref(icon_info)):
            try:
                gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
                gdi32.GetObjectW.restype = ctypes.c_int
                bmp = BITMAP()
                # 优先从 hbmMask 读尺寸（mask 总是有效的 DDB），hbmColor 可能是无效 DIB 句柄
                handle_for_size = icon_info.hbmMask if icon_info.hbmMask else icon_info.hbmColor
                if handle_for_size and gdi32.GetObjectW(handle_for_size, ctypes.sizeof(bmp), ctypes.byref(bmp)) > 0:
                    if bmp.bmWidth > 0 and bmp.bmHeight > 0:
                        width = bmp.bmWidth
                        height = bmp.bmHeight if bmp.bmHeight > 0 else bmp.bmWidth
            except Exception:
                pass
            # 清理 GetIconInfo 产生的位图
            try:
                if icon_info.hbmMask:
                    gdi32.DeleteObject(icon_info.hbmMask)
            except Exception:
                pass
            try:
                if icon_info.hbmColor:
                    gdi32.DeleteObject(icon_info.hbmColor)
            except Exception:
                pass

        if width <= 0 or height <= 0:
            width = height = size

        # 用屏幕 DC 创建兼容内存 DC 和 32bpp 位图
        hdc_screen = user32.GetDC(0)
        mem_dc = gdi32.CreateCompatibleDC(hdc_screen)

        # 创建 32bpp 兼容位图
        bmi_header = BITMAPINFOHEADER()
        bmi_header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi_header.biWidth = width
        bmi_header.biHeight = -height  # top-down
        bmi_header.biPlanes = 1
        bmi_header.biBitCount = 32
        bmi_header.biCompression = 0  # BI_RGB
        bmi = ctypes.create_string_buffer(ctypes.sizeof(BITMAPINFOHEADER) + 256 * 4)
        ctypes.memmove(bmi, ctypes.byref(bmi_header), ctypes.sizeof(bmi_header))

        ppv = ctypes.c_void_p()
        hbm = gdi32.CreateDIBSection(hdc_screen, bmi, 0, ctypes.byref(ppv), None, 0)
        if not hbm:
            logger.debug("CreateDIBSection失败")
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(0, hdc_screen)
            user32.DestroyIcon(hicon)
            return None

        old_bmp = gdi32.SelectObject(mem_dc, hbm)

        # 用 DrawIconEx 将图标绘制到内存位图（DI_NORMAL = DI_IMAGE|DI_MASK）
        DI_NORMAL = 0x0003
        user32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON, ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT]
        user32.DrawIconEx.restype = wintypes.BOOL
        draw_ok = user32.DrawIconEx(mem_dc, 0, 0, hicon, width, height, 0, None, DI_NORMAL)

        # 从位图读取像素
        pixels = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
        gdi32.GetDIBits.restype = ctypes.c_int
        got = gdi32.GetDIBits(mem_dc, hbm, 0, height, pixels, bmi, 0)

        # 清理
        gdi32.SelectObject(mem_dc, old_bmp)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(0, hdc_screen)
        user32.DestroyIcon(hicon)

        if got == 0:
            logger.debug(f"GetDIBits返回0, DrawIconEx={draw_ok}")
            return None

        img = Image.frombuffer('RGBA', (width, height), pixels.raw, 'raw', 'BGRA', 0, 1)

        # 修复 Alpha 通道：DrawIconEx 绘制到 32bpp DIB 时不写 Alpha，
        # 若 Alpha 全0但 RGB 有内容，用 RGB 非零像素重建 Alpha
        try:
            r, g, b, a = img.split()
            if a.getextrema()[1] == 0:
                # 统计 RGB 非零像素
                has_content = False
                for band in (r, g, b):
                    if band.getextrema()[1] > 0:
                        has_content = True
                        break
                if has_content:
                    # RGB 相加后取阈值生成 Alpha：非黑像素不透明
                    from PIL import ImageChops
                    alpha_sum = ImageChops.add(ImageChops.add(r, g), b)
                    a = alpha_sum.point(lambda x: 255 if x > 0 else 0)
                    img = Image.merge('RGBA', (r, g, b, a))
                    logger.debug(f"已重建 Alpha 通道 ({width}x{height})")
        except Exception as e:
            logger.debug(f"Alpha 修复跳过: {e}")

        return img
    except Exception as e:
        logger.debug(f"HICON转PIL失败: {e}")
        return None


def _extract_icon_jumbo(app_path: str):
    """高清提取：通过 SHGetImageList 获取 256x256 系统图标（方案A）

    比 ExtractIconEx 的 40x40 清晰得多。失败时返回 None，由调用方回退。
    """
    try:
        if not os.path.exists(app_path):
            return None

        _shell32 = ctypes.windll.shell32

        # 获取系统图标列表索引
        class _SHFILEINFO(ctypes.Structure):
            _fields_ = [
                ("hIcon", wintypes.HICON),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName", ctypes.c_wchar * 80),
            ]
        sfi = _SHFILEINFO()
        ret = _shell32.SHGetFileInfoW(app_path, 0, ctypes.byref(sfi), ctypes.sizeof(sfi), _SHGFI_SYSICONINDEX)
        if sfi.hIcon:
            ctypes.windll.user32.DestroyIcon(sfi.hIcon)
        if ret == 0 or sfi.iIcon < 0:
            return None

        # 获取 256x256 图像列表
        _shell32.SHGetImageList.argtypes = [ctypes.c_int, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        _shell32.SHGetImageList.restype = ctypes.c_long
        ppv = ctypes.c_void_p()
        hr = _shell32.SHGetImageList(_SHIL_JUMBO, ctypes.byref(_IID_IImageList), ctypes.byref(ppv))
        if hr != 0 or not ppv.value:
            return None

        try:
            # 调用 IImageList::GetIcon（vtable index 10）
            vtbl_ptr = ctypes.cast(ppv.value, ctypes.POINTER(ctypes.c_void_p)).contents
            vtbl = ctypes.cast(vtbl_ptr, ctypes.POINTER(ctypes.c_void_p * 16)).contents
            GetIconProto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(wintypes.HICON))
            GetIcon = ctypes.cast(vtbl[10], GetIconProto)
            hicon = wintypes.HICON()
            hr2 = GetIcon(ppv.value, sfi.iIcon, _ILD_TRANSPARENT, ctypes.byref(hicon))
            if hr2 != 0 or not hicon.value:
                return None
            return _hicon_to_pil(hicon, 256)
        finally:
            # Release IImageList
            try:
                ReleaseProto = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
                Release = ctypes.cast(vtbl[2], ReleaseProto)
                Release(ppv.value)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"JUMBO高清提取失败: {e}")
        return None


def get_app_icon(app_path: str, icon_path: str = None, size: int = 48, original_path: str = None):
    """获取应用图标 - 依次尝试多种方法

    高清策略：优先用 SHGetImageList 提取 256x256 原图缓存，
    显示时按 DPI 缩放（方案A+B+C）。
    """
    # 统一规范化路径：正斜杠转反斜杠，否则 SHGetFileInfoW 无法获取系统图标索引
    if app_path:
        app_path = os.path.normpath(app_path)
    if icon_path:
        icon_path = os.path.normpath(icon_path)
    if original_path:
        original_path = os.path.normpath(original_path)

    # DPI 适配目标尺寸（方案B）
    dpi_scale = _get_dpi_scale()
    target_size = max(size, int(round(size * dpi_scale)))

    cached = _load_icon_from_cache(app_path)
    if cached and _is_icon_valid(cached):
        # 从缓存原图缩放到 DPI 适配尺寸
        return _prepare_icon_for_display(cached, target_size)

    img = None

    # 方法0: SHGetImageList 256x256 高清提取（方案A，最优先）
    if img is None or not _is_icon_valid(img):
        img = _extract_icon_jumbo(app_path)

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
        # 缓存原始大图（仅白色透明化，不缩放），显示时再按需缩放（方案C）
        raw_icon = _process_icon(img)
        _save_icon_to_cache(app_path, raw_icon)
        return _prepare_icon_for_display(raw_icon, target_size)

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
