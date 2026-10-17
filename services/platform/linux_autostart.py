# -*- coding: utf-8 -*-
"""Linux 开机自启动：XDG Autostart（~/.config/autostart/*.desktop）。

与 Windows 写注册表 Run 项对应，Linux 通过在用户 autostart 目录放置一个
.desktop 文件实现开机自启。
"""

import os
import shlex
import sys

from core.logger import get_logger

logger = get_logger()

DESKTOP_NAME = "win11launcher.desktop"


def _config_home() -> str:
    """配置主目录：优先 XDG_CONFIG_HOME（测试可注入），否则 ~/.config。"""
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )


def _autostart_dir() -> str:
    return os.path.join(_config_home(), "autostart")


def _desktop_path() -> str:
    return os.path.join(_autostart_dir(), DESKTOP_NAME)


def _project_root() -> str:
    # 本文件位于 services/platform/，向上三级即项目根
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _exec_command() -> str:
    """构造自启动 Exec：打包后为可执行文件本身，源码运行为 python + main.py。"""
    if getattr(sys, "frozen", False):
        return shlex.quote(sys.executable)
    main_py = os.path.join(_project_root(), "main.py")
    return f"{shlex.quote(sys.executable)} {shlex.quote(main_py)}"


def _desktop_content() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Win11Launcher\n"
        f"Exec={_exec_command()}\n"
        "Icon=win11launcher\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def is_autostart_enabled() -> bool:
    """检查是否已设置开机自启。"""
    return os.path.exists(_desktop_path())


def set_autostart(enabled: bool) -> bool:
    """设置/取消开机自启。"""
    path = _desktop_path()
    try:
        if enabled:
            os.makedirs(_autostart_dir(), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(_desktop_content())
            logger.debug("已设置开机自启（XDG autostart）")
        else:
            if os.path.exists(path):
                os.remove(path)
            logger.debug("已取消开机自启")
        return True
    except Exception as e:
        logger.warning(f"设置自启动失败: {e}")
        return False
