# -*- coding: utf-8 -*-
"""平台适配层（门面）：按 sys.platform 选择 Windows / Kylin 后端，向上提供统一接口。

设计目标（2026-10-31 重构：物理分离）：
  - Windows 实现位于 services/windows/，Kylin（Linux）实现位于 services/kylin/，
    二者互不 import 对方平台专有模块，彻底解耦——在 Windows 上绝不会加载 Kylin 代码，
    反之亦然。新增 Kylin 专属功能只写在 services/kylin/ 下，不触碰 Windows 代码。
  - 本门面只做分发与统一接口再导出，不承载任何平台逻辑；
    调用方（ui/*、main.py）仍只 import 本模块，不受后端物理位置变化影响。

对外统一接口（各后端 __init__.py 提供同名实现）：
  get_app_icon / get_app_info / launch_app / make_install_monitor /
  scan_app_names / find_app_by_name / autostart_is_enabled / autostart_set
"""

import sys

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

if IS_WINDOWS:
    from services import windows as _backend
else:
    from services import kylin as _backend

# 从所选后端导出统一接口
get_app_icon = _backend.get_app_icon
get_app_info = _backend.get_app_info
launch_app = _backend.launch_app
make_install_monitor = _backend.make_install_monitor
scan_app_names = _backend.scan_app_names
find_app_by_name = _backend.find_app_by_name
autostart_is_enabled = _backend.autostart_is_enabled
autostart_set = _backend.autostart_set
