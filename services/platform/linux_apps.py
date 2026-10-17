# -*- coding: utf-8 -*-
"""Linux 应用发现：解析 freedesktop .desktop 文件。

与 Windows 扫开始菜单 .lnk 对应，Linux 通过扫描各应用目录下的 .desktop 文件
枚举已安装应用。.desktop 解析为纯逻辑（不依赖具体目录），便于单元测试。

产出的应用 dict 与 Windows 版结构一致，可直接进入既有数据模型：
    {"name", "path", "original_path", "icon_path"}
其中：
    name          = [Desktop Entry] 的 Name
    path          = Exec 命令（已去除字段码，可供启动）
    original_path = .desktop 文件路径
    icon_path     = Icon= 值（图标名或绝对路径）
"""

import os

from PySide6.QtCore import QObject, QTimer, Signal

from core.logger import get_logger

logger = get_logger()

# 应用目录：用户级优先（可覆盖系统级同名应用）
DEFAULT_APP_DIRS = [
    os.path.expanduser("~/.local/share/applications"),
    "/usr/local/share/applications",
    "/usr/share/applications",
    "/var/lib/snapd/desktop/applications",
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
]

# 与 Windows 版一致的过滤关键词（安装器/说明等不入库）
SKIP_KEYWORDS = ["uninstall", "卸载", "help", "readme", "说明", "website", "官网",
                 "update", "更新", "license", "许可"]

# .desktop Exec 字段码，启动时需去除
_FIELD_CODES = ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N",
                "%i", "%c", "%k", "%v", "%m")


def clean_exec(exec_str: str) -> str:
    """去除 Exec 中的字段码并规整空白。"""
    if not exec_str:
        return ""
    s = exec_str
    for code in _FIELD_CODES:
        s = s.replace(code, "")
    return " ".join(s.split())


def parse_desktop_file(path: str):
    """解析单个 .desktop 文件，返回标准化应用 dict；非应用/隐藏则返回 None。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        logger.debug(f"读取 .desktop 失败 {path}: {e}")
        return None

    in_entry = False
    data = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_entry = (line == "[Desktop Entry]")
            continue
        if not in_entry or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key not in data:  # 只取首个 Desktop Entry 组的键
            data[key] = val.strip()

    if data.get("Type") != "Application":
        return None
    if data.get("NoDisplay", "").lower() == "true":
        return None
    if data.get("Hidden", "").lower() == "true":
        return None

    name = data.get("Name")
    if not name:
        return None

    return {
        "name": name,
        "path": clean_exec(data.get("Exec", "")),
        "original_path": path,
        "icon_path": data.get("Icon") or None,
    }


def scan_apps(app_dirs=None):
    """扫描所有应用目录，返回应用 dict 列表（按 name 去重，用户级优先）。"""
    dirs = list(app_dirs) if app_dirs is not None else list(DEFAULT_APP_DIRS)
    seen = set()
    result = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if not f.lower().endswith(".desktop"):
                    continue
                info = parse_desktop_file(os.path.join(root, f))
                if not info:
                    continue
                if info["name"] in seen:
                    continue
                seen.add(info["name"])
                result.append(info)
    return result


def scan_app_names(app_dirs=None):
    return {a["name"] for a in scan_apps(app_dirs)}


def find_app_by_name(name, app_dirs=None):
    """按名称查找应用，返回其 .desktop 路径（original_path）；找不到返回 None。"""
    for a in scan_apps(app_dirs):
        if a["name"] == name:
            return a["original_path"]
    return None


class LinuxInstallMonitor(QObject):
    """新安装应用监控（定时轮询 .desktop 目录）——接口与 Windows InstallMonitor 一致。"""

    new_apps_found = Signal(list)  # 新应用的 .desktop 路径列表

    def __init__(self, interval_ms: int = 5000):
        super().__init__()
        self.interval_ms = interval_ms
        self._known: set = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._paused = False

    def start(self):
        self._known = self._scan()
        self._timer.start(self.interval_ms)
        self._paused = False
        logger.debug(f"Linux 安装监控已启动，已知 {len(self._known)} 个应用")

    def stop(self):
        self._timer.stop()

    def pause(self):
        if self._paused:
            return
        self._paused = True
        self._timer.stop()
        logger.debug("Linux 安装监控已暂停")

    def resume(self):
        if not self._paused:
            return
        self._paused = False
        self._known = self._scan()
        self._timer.start(self.interval_ms)
        logger.debug("Linux 安装监控已恢复")

    def _scan(self) -> set:
        return {a["original_path"] for a in scan_apps()}

    def _check(self):
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
