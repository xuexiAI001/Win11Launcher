# -*- coding: utf-8 -*-
"""数据目录解析测试：Windows 行为不变 + Linux 走 XDG。"""

import os
import sys

from core.paths import get_appdata_dir


def test_windows_branch_uses_appdata(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")
    assert get_appdata_dir() == os.path.join(r"C:\Users\test\AppData\Roaming", "Win11Launcher")


def test_windows_branch_appdata_missing_keeps_legacy_fallback(monkeypatch):
    """无 APPDATA 时保持原有相对目录回退（Windows 行为逐字节不变）"""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    assert get_appdata_dir() == os.path.join(".", "Win11Launcher")


def test_linux_branch_honors_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert get_appdata_dir() == os.path.join(str(tmp_path), "Win11Launcher")


def test_linux_branch_defaults_to_dot_config(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert get_appdata_dir() == os.path.join(os.path.expanduser("~/.config"), "Win11Launcher")


def test_constants_and_logger_use_resolver():
    """constants / logger 均从 core.paths 取目录，保持一致"""
    import core.constants as const
    import core.logger as lg
    assert const.APPDATA_DIR == get_appdata_dir()
    assert const.CONFIG_FILE == os.path.join(const.APPDATA_DIR, "launcher_config.json")
    assert const.ICON_CACHE_DIR == os.path.join(const.APPDATA_DIR, "icon_cache")
    assert lg.LOG_DIR == get_appdata_dir()
    assert lg.LOG_FILE == os.path.join(lg.LOG_DIR, "launcher.log")
