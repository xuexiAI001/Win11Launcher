# -*- coding: utf-8 -*-
"""
应用信息解析模块 - 从拖拽文件/快捷方式/URI中提取应用信息
支持普通EXE、快捷方式(.lnk)、UWP应用(ms-appx://)、系统shell路径
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger("Win11Launcher")


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
    except Exception:
        if all_users:
            return os.path.join(os.environ.get('ALLUSERSPROFILE', ''), 'Start Menu', 'Programs')
        else:
            return os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs')


def _parse_shell_link_from_start_menu(app_name: str) -> dict:
    """从开始菜单搜索应用快捷方式"""
    search_paths = [_get_start_menu_programs_path(False), _get_start_menu_programs_path(True)]

    for base_path in search_paths:
        if not os.path.exists(base_path):
            continue

        for root, dirs, files in os.walk(base_path):
            for filename in files:
                if filename.lower().endswith('.lnk'):
                    lnk_path = os.path.join(root, filename)
                    try:
                        import win32com.client
                        shell = win32com.client.Dispatch("WScript.Shell")
                        shortcut = shell.CreateShortCut(lnk_path)
                        target_path = shortcut.Targetpath

                        lnk_name = Path(filename).stem
                        if (lnk_name.lower() == app_name.lower() or
                                target_path.lower().find(app_name.lower()) != -1):
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
                    except Exception:
                        continue
    return None


def _parse_application_uri(uri: str) -> dict:
    """解析应用URI（如 ms-appx:// 或 shell:::）"""
    if uri.startswith('ms-appx://'):
        try:
            import winreg
            app_id = uri.replace('ms-appx://', '').strip('/')
            if '!' in app_id:
                app_id = app_id.split('!')[0]

            reg_paths = [
                rf"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages\{app_id}",
                rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{app_id}"
            ]

            for reg_path in reg_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                        try:
                            display_name = winreg.QueryValueEx(key, "DisplayName")[0]
                        except Exception:
                            display_name = app_id
                        return {
                            "name": display_name,
                            "path": uri,
                            "original_path": uri,
                            "icon_path": None
                        }
                except Exception:
                    continue
        except Exception:
            pass

    elif uri.startswith('shell:::'):
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            return {
                "name": "系统应用",
                "path": uri,
                "original_path": uri,
                "icon_path": None
            }
        except Exception:
            pass

    return None


def get_app_info(file_path: str) -> dict:
    """获取应用信息

    支持多种拖拽来源：
    1. 普通文件/快捷方式
    2. Win11开始菜单拖拽（可能包含特殊URI或路径）
    3. UWP应用（ms-appx:// 格式）

    无论拖拽的是快捷方式还是exe，都提取目标程序路径进行保存。
    特别注意：完全保留拖拽文件的原始显示名称。
    """
    original_file_path = file_path.strip()
    file_path = original_file_path

    # 处理特殊URI格式
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

            if shortcut.IconLocation:
                icon_location = shortcut.IconLocation[0] if isinstance(shortcut.IconLocation, tuple) else shortcut.IconLocation
                if icon_location and os.path.exists(icon_location):
                    icon_path = icon_location
                elif target_path and os.path.exists(target_path):
                    icon_path = target_path
            elif target_path and os.path.exists(target_path):
                icon_path = target_path

        except Exception as e:
            logger.debug(f"Failed to parse lnk: {e}")
            result = _parse_shell_link_from_start_menu(name)
            if result:
                return result

    final_path = target_path if (target_path and os.path.exists(target_path)) else file_path

    if not os.path.exists(final_path):
        result = _parse_shell_link_from_start_menu(name)
        if result:
            return result

    return {
        "name": name,
        "path": final_path,
        "original_path": original_file_path,
        "icon_path": icon_path
    }
