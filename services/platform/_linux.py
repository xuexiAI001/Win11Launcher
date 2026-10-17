# -*- coding: utf-8 -*-
"""Linux（Kylin）后端：.desktop 应用发现 + 图标主题解析 + XDG 自启动 + Exec 启动。

只在非 Windows 平台被 services.platform 导入，绝不 import Windows 专有模块。
"""

import shlex
import subprocess

from services.platform.linux_icons import get_app_icon
from services.platform.linux_apps import (
    parse_desktop_file,          # 即 get_app_info：.desktop 路径 -> 应用 dict
    LinuxInstallMonitor,
    scan_app_names,
    find_app_by_name,
)
from services.platform.linux_autostart import (
    is_autostart_enabled as autostart_is_enabled,
    set_autostart as autostart_set,
)

# get_app_info 与 Windows 语义一致：传入应用文件路径，返回标准化应用 dict
get_app_info = parse_desktop_file


def launch_app(path: str) -> None:
    """启动应用。

    Linux 下 path 为 .desktop 的 Exec 命令（已去除字段码），可能含参数，
    用 shlex 拆分后以脱离会话的子进程启动，避免随启动器退出而被回收。
    """
    try:
        argv = shlex.split(path) if isinstance(path, str) else list(path)
        if not argv:
            return
        subprocess.Popen(argv, start_new_session=True)
    except Exception as e:  # noqa: BLE001
        from core.logger import get_logger
        get_logger().warning(f"Linux 启动失败: {e}")


def make_install_monitor(*args, **kwargs):
    return LinuxInstallMonitor(*args, **kwargs)
