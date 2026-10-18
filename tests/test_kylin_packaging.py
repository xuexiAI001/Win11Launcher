# -*- coding: utf-8 -*-
"""麒麟离线打包套件（packaging/kylin/）的结构完整性守卫。

套件要在离线的麒麟机器上运行，本地无法端到端验证；这些测试至少保证：
  - 套件文件齐全、未被误删；
  - requirements-linux.txt 每行都是合法依赖声明且无重复；
  - win11launcher.desktop 关键键齐全，Exec/Icon 与 make_deb.sh 的安装布局一致；
  - 两个 shell 脚本通过 bash -n 语法检查（有 bash 时才跑）。
"""

import re
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KIT = PROJECT_ROOT / "packaging" / "kylin"

REQUIRED_FILES = [
    "README.md",
    "requirements-linux.txt",
    "prepare_wheelhouse.py",
    "build_on_kylin.sh",
    "make_deb.sh",
    "win11launcher.spec",
    "win11launcher.desktop",
]

# 与 make_deb.sh 的安装布局保持一致
EXPECTED_EXEC = "/opt/win11launcher/Win11Launcher"
EXPECTED_ICON = "win11launcher"  # hicolor 主题名 → /usr/share/icons/hicolor/256x256/apps/win11launcher.png


def test_kit_files_exist():
    missing = [f for f in REQUIRED_FILES if not (KIT / f).is_file()]
    assert not missing, f"打包套件缺少文件：{missing}"


def test_requirements_linux_is_valid_and_unique():
    reqs = KIT / "requirements-linux.txt"
    seen = {}
    pattern = re.compile(r"^([A-Za-z0-9._-]+)\s*==\s*([A-Za-z0-9._-]+)\s*(#.*)?$")
    for lineno, raw in enumerate(reqs.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = pattern.match(line)
        assert m, f"{reqs.name}:{lineno} 不是合法的 'name==version' 声明：{line!r}"
        name = m.group(1).lower().replace("_", "-")
        assert name not in seen, f"{reqs.name}:{lineno} 重复依赖 {name}（首次出现在第 {seen[name]} 行）"
        seen[name] = lineno
    # 关键依赖必须在位（版本锁的核心结论）
    for must in ["pyside6-essentials", "shiboken6", "pillow", "pynput", "python-xlib", "pyinstaller"]:
        assert must in seen, f"{reqs.name} 缺少关键依赖 {must}"
    # PySide6 必须锁 6.6.x（6.7+ 不支持 Python 3.8；6.10+ 无 manylinux_2_28 轮子）
    text = reqs.read_text(encoding="utf-8")
    assert "PySide6-Essentials==6.6.3.1" in text
    assert "shiboken6==6.6.3.1" in text


def test_desktop_entry_contract():
    entry = KIT / "win11launcher.desktop"
    text = entry.read_text(encoding="utf-8")
    keys = dict(
        line.split("=", 1)
        for line in text.splitlines()
        if "=" in line and not line.startswith("[")
    )
    for required in ("Type", "Name", "Exec", "Icon", "Terminal", "Categories"):
        assert required in keys, f"desktop 入口缺少键 {required}"
    assert keys["Type"] == "Application"
    assert keys["Exec"].strip() == EXPECTED_EXEC, "Exec 必须与 make_deb.sh 的 /opt 安装路径一致"
    assert keys["Icon"].strip() == EXPECTED_ICON
    assert keys["Terminal"].strip().lower() == "false"
    # 图标文件必须存在（make_deb.sh 会安装它）
    assert (PROJECT_ROOT / "assets" / "app.png").is_file(), "缺少 assets/app.png（deb 图标）"


def test_spec_mentions_linux_essentials():
    spec = (KIT / "win11launcher.spec").read_text(encoding="utf-8")
    # pynput 的 X11 后端与 keysymdef 分组是动态 import，必须在 hiddenimports 中
    for must in ("pynput.keyboard._xorg", "Xlib.keysymdef.xkb", "PySide6.QtSvg",
                 "PySide6.QtNetwork", "services.platform._linux"):
        assert must in spec, f"spec hiddenimports 缺少 {must}"
    assert "numpy" in spec, "spec 应排除 numpy（Linux 不需要）"


def test_build_script_guards_venv_health():
    """回归守卫：venv 复用前必须做 pip 健康检查，不可用必须清理残骸。

    背景（麒麟真机实测）：最小化安装缺 ensurepip 组件时，`python -m venv`
    会留下"没有 pip 的残骸 venv"；脚本若直接复用，后续安装必报
    "No module named pip"（2026-10-18 用户实测踩坑）。
    """
    text = (KIT / "build_on_kylin.sh").read_text(encoding="utf-8")
    # 复用/创建后都要验证 pip 可用
    assert "venv_healthy" in text, "build_on_kylin.sh 缺少 venv_healthy 健康检查"
    assert "-m pip --version" in text, "健康检查必须实际执行 pip --version"
    # 两条失败路径都要清理残骸目录（复用前发现不健康 + 创建失败）
    assert text.count('rm -rf "$VENV"') >= 2, \
        "venv 不可用时必须清理残骸目录（复用前 + 创建失败各一处）"
    # apt 提示要覆盖麒麟/Ubuntu 两种 venv 包命名
    assert "python3.8-venv" in text and "python3-3.8-venv" in text


def test_shell_scripts_syntax():
    bash = shutil.which("bash")
    if not bash:
        import pytest
        pytest.skip("当前环境没有 bash，跳过 shell 语法检查")
    for name in ("build_on_kylin.sh", "make_deb.sh"):
        proc = subprocess.run(
            [bash, "-n", str(KIT / name)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"{name} bash -n 失败：\n{proc.stderr}"


def test_version_constant_matches_deb_default():
    """make_deb.sh 用 sed 从 core/constants.py 提取 APP_VERSION，验证提取得动。"""
    constants = (PROJECT_ROOT / "core" / "constants.py").read_text(encoding="utf-8")
    m = re.search(r'^APP_VERSION = "([^"]+)"', constants, re.M)
    assert m, "core/constants.py 缺少 APP_VERSION"
    sed = shutil.which("sed")
    if sed:
        proc = subprocess.run(
            [sed, "-n", 's/^APP_VERSION = "\\(.*\\)"$/\\1/p', str(PROJECT_ROOT / "core" / "constants.py")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        assert proc.stdout.strip() == m.group(1), "sed 提取版本与常量不一致"
