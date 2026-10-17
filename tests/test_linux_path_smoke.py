# -*- coding: utf-8 -*-
"""Linux（麒麟）路径启动冒烟：子进程内模拟 sys.platform=linux 完整构建主窗口。

为什么用子进程：sys.platform 补丁会污染同进程其他测试的平台判定，
且 Linux 分支的配置目录走 XDG，需隔离临时目录，避免写用户真实配置。

覆盖：门面分发到 Linux 后端、标题栏窗口控制按钮、主题轮询、
滚轮缩放过滤器、缩放/最大化/全屏联动。
"""
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CODE = textwrap.dedent("""
    import sys, os, tempfile
    sys.path.insert(0, {root!r})
    sys.platform = "linux"          # 必须在导入平台相关模块前打补丁
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication
    import core.config as cc
    cc.CONFIG_FILE = os.path.join(tempfile.mkdtemp(), "cfg.json")  # 隔离真实配置
    from core.config import Config
    from core import constants as C
    import ui.main_window as mw_mod

    # 隔离托盘/热键（由其他单测覆盖）
    mw_mod.MainWindow._setup_system_integration = lambda self: None

    app = QApplication(sys.argv[:1])
    cfg = Config()
    cfg.add_app("系统应用", {{"name": "火狐", "path": "firefox %u",
                            "original_path": "/usr/share/applications/firefox.desktop",
                            "icon_path": "firefox"}})
    win = mw_mod.MainWindow(cfg)

    assert (win.width(), win.height()) == (1060, 700)
    assert win._btn_maximize is not None and win._btn_fullscreen is not None
    assert win._theme_poll_timer is not None
    assert type(win._wheel_filter).__name__ == "_WheelZoomFilter"

    # 缩放联动
    win.set_zoom(1.2)
    assert (C.WINDOW_WIDTH, C.WINDOW_HEIGHT) == (1272, 840)
    assert (win.width(), win.height()) == (1272, 840)
    assert C.ICON_SIZE == 58

    # 最大化 / 全屏
    win.toggle_maximize()
    assert win.isMaximized() and win._btn_maximize.text() == "还原"
    win.toggle_fullscreen()
    assert win.isFullScreen() and win._btn_fullscreen.text() == "退出全屏"
    win.toggle_fullscreen()
    assert not win.isFullScreen()

    # 主题轮询不炸（跟随系统场景）
    win._poll_linux_theme()

    win.set_zoom(1.0)
    print("OK")
""")


def test_linux_path_startup_smoke():
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    r = subprocess.run([sys.executable, "-c", _CODE.format(root=ROOT)],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout
