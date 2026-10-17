# -*- coding: utf-8 -*-
"""
平台适配层（门面）：按 sys.platform 选择 Windows / Linux 后端，向上提供统一接口。

设计目标：
  - Windows 现有实现零改动——_win 后端直接委托既有模块（同一个函数对象），
    调用方经本门面调用与原先直接调用行为完全一致。
  - Linux（Kylin）提供等价实现——_linux 后端 + linux_* 子模块。
  - 调用方只 import 本模块，不直接 import 平台专有模块，从而避免在 Linux 上
    import 仅 Windows 可用的模块（如 ctypes.wintypes）而崩溃。

对外统一接口：
  get_app_icon / get_app_info / launch_app / make_install_monitor /
  scan_app_names / find_app_by_name / autostart_is_enabled / autostart_set
"""

import sys

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

if IS_WINDOWS:
    from services.platform import _win as _backend
else:
    from services.platform import _linux as _backend

# 从所选后端导出统一接口
get_app_icon = _backend.get_app_icon
get_app_info = _backend.get_app_info
launch_app = _backend.launch_app
make_install_monitor = _backend.make_install_monitor
scan_app_names = _backend.scan_app_names
find_app_by_name = _backend.find_app_by_name
autostart_is_enabled = _backend.autostart_is_enabled
autostart_set = _backend.autostart_set
