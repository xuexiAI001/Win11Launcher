# -*- coding: utf-8 -*-
"""
模块名：services.install_monitor
职责：监控开始菜单，检测新安装的应用
依赖：core.logger
"""

import os
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QObject, QTimer, Signal

from core.logger import get_logger

logger = get_logger()

# 过滤关键词（安装器/说明文件等）
SKIP_KEYWORDS = ["uninstall", "卸载", "help", "readme", "说明", "website", "官网",
                 "update", "更新", "license", "许可"]


def _get_start_menu_dirs() -> list[str]:
    """获取开始菜单程序目录"""
    dirs = []
    try:
        CSIDL_PROGRAMS = 2
        CSIDL_COMMON_PROGRAMS = 23
        buf = ctypes.create_unicode_buffer(260)
        for csidl in (CSIDL_PROGRAMS, CSIDL_COMMON_PROGRAMS):
            if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
                if buf.value and os.path.isdir(buf.value):
                    dirs.append(buf.value)
    except Exception as e:
        logger.debug(f"获取开始菜单目录失败: {e}")
    return dirs


def scan_start_menu_names() -> set[str]:
    """扫描开始菜单所有快捷方式，返回应用名称集合（不含扩展名）"""
    names = set()
    for d in _get_start_menu_dirs():
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith(".lnk"):
                    names.add(os.path.splitext(f)[0])
    return names


def find_lnk_by_name(app_name: str) -> str | None:
    """根据应用名称查找开始菜单中的 .lnk 完整路径"""
    for d in _get_start_menu_dirs():
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith(".lnk") and os.path.splitext(f)[0] == app_name:
                    return os.path.join(root, f)
    return None


class InstallMonitor(QObject):
    """新安装应用监控（定时轮询开始菜单）"""

    new_apps_found = Signal(list)  # 新应用的 lnk 路径列表

    def __init__(self, interval_ms: int = 5000):
        super().__init__()
        self.interval_ms = interval_ms
        self._known: set[str] = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._paused = False

    def start(self):
        """启动监控"""
        self._known = self._scan()
        self._timer.start(self.interval_ms)
        self._paused = False
        logger.debug(f"安装监控已启动，已知 {len(self._known)} 个应用")

    def stop(self):
        """停止监控"""
        self._timer.stop()

    def pause(self):
        """暂停监控（窗口最小化时调用，省 CPU）"""
        if self._paused:
            return
        self._paused = True
        self._timer.stop()
        logger.debug("安装监控已暂停")

    def resume(self):
        """恢复监控（窗口恢复时调用）"""
        if not self._paused:
            return
        self._paused = False
        # 重新扫描基线，避免暂停期间的新应用被漏掉或误报
        self._known = self._scan()
        self._timer.start(self.interval_ms)
        logger.debug("安装监控已恢复")

    def _scan(self) -> set[str]:
        """扫描开始菜单所有 lnk"""
        result = set()
        for d in _get_start_menu_dirs():
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        result.add(os.path.join(root, f))
        return result

    def _check(self):
        """检查新增应用"""
        current = self._scan()
        new = current - self._known
        self._known = current
        if not new:
            return
        filtered = []
        for path in new:
            name = os.path.splitext(os.path.basename(path))[0].lower()
            if any(k in name for k in SKIP_KEYWORDS):
                continue
            filtered.append(path)
        if filtered:
            logger.debug(f"检测到 {len(filtered)} 个新应用")
            self.new_apps_found.emit(filtered)
