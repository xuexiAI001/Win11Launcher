# -*- coding: utf-8 -*-
"""平台适配层测试：门面分发 + Windows 委托一致性 + Linux 纯逻辑单测。

Linux 侧 .desktop 解析 / 图标主题解析 / XDG 自启动均为纯 Python 文件与路径逻辑，
可在任意 OS（含本机 Windows）直接运行，无需麒麟环境。
"""

import sys

import pytest
from PIL import Image

import services.platform as platform
from services.platform import IS_WINDOWS, IS_LINUX

from services.platform.linux_apps import (
    clean_exec, parse_desktop_file, scan_apps, scan_app_names, find_app_by_name,
)
from services.platform.linux_icons import resolve_icon_file, get_app_icon
from services.platform import linux_autostart


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------- 门面与平台判定 ----------

def test_platform_flags_match_sys():
    assert IS_WINDOWS == (sys.platform == "win32")
    assert IS_LINUX == sys.platform.startswith("linux")


def test_facade_exposes_unified_api():
    for name in ("get_app_icon", "get_app_info", "launch_app",
                 "make_install_monitor", "scan_app_names", "find_app_by_name",
                 "autostart_is_enabled", "autostart_set"):
        assert hasattr(platform, name), name


@pytest.mark.skipif(not IS_WINDOWS, reason="Windows 委托一致性仅在 Windows 上验证")
def test_windows_backend_delegates_to_existing_modules():
    """证明 Windows 路径零改动：门面导出的就是既有模块的同一个函数对象。"""
    import services.icon_extractor as ie
    import services.app_info as ai
    import services.install_monitor as im
    assert platform.get_app_icon is ie.get_app_icon
    assert platform.get_app_info is ai.get_app_info
    assert isinstance(platform.scan_app_names(), set)
    m = platform.make_install_monitor()
    assert isinstance(m, im.InstallMonitor)
    assert hasattr(m, "new_apps_found")


# ---------- Linux: clean_exec ----------

def test_clean_exec_strips_field_codes():
    assert clean_exec("/usr/bin/foo %U") == "/usr/bin/foo"
    assert clean_exec("env A=1 /usr/bin/bar %f %i") == "env A=1 /usr/bin/bar"
    assert clean_exec("  /bin/x   %u  ") == "/bin/x"
    assert clean_exec("") == ""


# ---------- Linux: parse_desktop_file ----------

def test_parse_desktop_file_basic(tmp_path):
    p = tmp_path / "foo.desktop"
    _write(p, "[Desktop Entry]\nType=Application\nName=Foo App\n"
              "Exec=/usr/bin/foo %U\nIcon=foo\nCategories=Utility;\n")
    info = parse_desktop_file(str(p))
    assert info["name"] == "Foo App"
    assert info["path"] == "/usr/bin/foo"
    assert info["original_path"] == str(p)
    assert info["icon_path"] == "foo"


@pytest.mark.parametrize("extra", ["NoDisplay=true", "Hidden=true"])
def test_parse_desktop_file_skips_hidden(tmp_path, extra):
    p = tmp_path / "h.desktop"
    _write(p, f"[Desktop Entry]\nType=Application\nName=X\nExec=/bin/true\n{extra}\n")
    assert parse_desktop_file(str(p)) is None


def test_parse_desktop_file_skips_non_application(tmp_path):
    p = tmp_path / "link.desktop"
    _write(p, "[Desktop Entry]\nType=Link\nName=Web\nURL=http://x\n")
    assert parse_desktop_file(str(p)) is None


def test_parse_desktop_file_requires_name(tmp_path):
    p = tmp_path / "noname.desktop"
    _write(p, "[Desktop Entry]\nType=Application\nExec=/bin/true\n")
    assert parse_desktop_file(str(p)) is None


# ---------- Linux: scan_apps / find ----------

def test_scan_apps_and_find(tmp_path):
    d = tmp_path / "applications"
    d.mkdir()
    _write(d / "a.desktop", "[Desktop Entry]\nType=Application\nName=Alpha\nExec=/bin/alpha\nIcon=alpha\n")
    _write(d / "b.desktop", "[Desktop Entry]\nType=Application\nName=Beta\nExec=/bin/beta\n")
    assert scan_app_names([str(d)]) == {"Alpha", "Beta"}
    assert find_app_by_name("Alpha", [str(d)]) == str(d / "a.desktop")
    assert find_app_by_name("Missing", [str(d)]) is None


def test_scan_apps_dedup_by_name(tmp_path):
    user = tmp_path / "user"
    sys_dir = tmp_path / "sys"
    user.mkdir()
    sys_dir.mkdir()
    _write(user / "x.desktop", "[Desktop Entry]\nType=Application\nName=Dup\nExec=/bin/user\n")
    _write(sys_dir / "x.desktop", "[Desktop Entry]\nType=Application\nName=Dup\nExec=/bin/sys\n")
    apps = scan_apps([str(user), str(sys_dir)])
    assert len(apps) == 1
    assert apps[0]["path"] == "/bin/user"  # 用户级优先


# ---------- Linux: 图标主题解析 ----------

def test_resolve_icon_absolute_passthrough(tmp_path):
    f = tmp_path / "abs.png"
    Image.new("RGBA", (8, 8)).save(f)
    assert resolve_icon_file(str(f), icon_roots=[]) == str(f)


def test_resolve_icon_by_name_in_theme(tmp_path):
    root = tmp_path / "icons"
    (root / "hicolor" / "48x48" / "apps").mkdir(parents=True)
    target = root / "hicolor" / "48x48" / "apps" / "gedit.png"
    Image.new("RGBA", (48, 48)).save(target)
    got = resolve_icon_file("gedit", size=48, theme="hicolor", icon_roots=[str(root)])
    assert got == str(target)


def test_resolve_icon_pixmaps_flat(tmp_path):
    root = tmp_path / "pixmaps"
    root.mkdir()
    Image.new("RGBA", (8, 8)).save(root / "flat.png")
    got = resolve_icon_file("flat", icon_roots=[str(root)])
    assert got == str(root / "flat.png")


def test_resolve_icon_missing_returns_none(tmp_path):
    assert resolve_icon_file("nope", icon_roots=[str(tmp_path)]) is None


def test_get_app_icon_loads_png(tmp_path, monkeypatch):
    root = tmp_path / "icons"
    (root / "hicolor" / "48x48" / "apps").mkdir(parents=True)
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(root / "hicolor" / "48x48" / "apps" / "app.png")
    monkeypatch.setattr("services.platform.linux_icons.DEFAULT_ICON_ROOTS", [str(root)])
    monkeypatch.delenv("XDG_DATA_DIRS", raising=False)
    img = get_app_icon("", icon_path="app", size=48)
    assert img is not None and img.size == (48, 48)


def test_get_app_icon_svg_returns_none(tmp_path, monkeypatch):
    root = tmp_path / "icons"
    (root / "hicolor" / "48x48" / "apps").mkdir(parents=True)
    (root / "hicolor" / "48x48" / "apps" / "vec.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr("services.platform.linux_icons.DEFAULT_ICON_ROOTS", [str(root)])
    monkeypatch.delenv("XDG_DATA_DIRS", raising=False)
    assert get_app_icon("", icon_path="vec", size=48) is None


# ---------- Linux: XDG 自启动 ----------

def test_linux_autostart_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    dfile = tmp_path / "autostart" / "win11launcher.desktop"
    assert linux_autostart.is_autostart_enabled() is False
    assert linux_autostart.set_autostart(True) is True
    assert dfile.exists()
    content = dfile.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content and "Type=Application" in content
    assert linux_autostart.is_autostart_enabled() is True
    assert linux_autostart.set_autostart(False) is True
    assert not dfile.exists()
    assert linux_autostart.is_autostart_enabled() is False


# ---------- Linux: launch_app 容错 ----------

def test_linux_launch_app_tolerates_bad_input():
    from services.platform import _linux
    _linux.launch_app("")                       # 空命令：直接返回
    _linux.launch_app("/nonexistent/bin %U")    # 不存在：内部捕获，不向外抛
