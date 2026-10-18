#!/usr/bin/env bash
# ============================================================
# Win11Launcher 麒麟（银河麒麟 V10 / UKUI）一键离线构建脚本
#
# 前提：已在联网机器上执行过 prepare_wheelhouse.py，并把整个项目目录
#      （含 packaging/kylin/wheelhouse）拷贝到本机。
#
# 用法：bash packaging/kylin/build_on_kylin.sh
# 产物：dist-linux/Win11Launcher/（PyInstaller onedir，可直接运行）
#      之后可执行 bash packaging/kylin/make_deb.sh 打包 .deb
#
# 说明：构建全程离线（--no-index），依赖来自 wheelhouse；
#       不影响系统 Python 环境（venv 隔离）。
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|aarch64) ;;
    *)
        echo "错误：不支持的 CPU 架构 '$ARCH'。"
        echo "  本套件覆盖 x86_64（兆芯/海光/Intel/AMD）与 aarch64（飞腾/鲲鹏）。"
        echo "  龙芯 LoongArch64 暂无 PySide6 官方预编译轮子，见 packaging/kylin/README.md。"
        exit 1
        ;;
esac

WHEELHOUSE="$PROJECT_ROOT/packaging/kylin/wheelhouse/$ARCH"
REQS="$PROJECT_ROOT/packaging/kylin/requirements-linux.txt"
VENV="$PROJECT_ROOT/packaging/kylin/.venv-build"
DIST="$PROJECT_ROOT/dist-linux"
WORK="$PROJECT_ROOT/build-linux-work"
SPEC="$SCRIPT_DIR/win11launcher.spec"

echo "==> 项目目录：$PROJECT_ROOT"
echo "==> 目标架构：$ARCH"

# ---------- 1. wheelhouse 检查 ----------
if [ ! -d "$WHEELHOUSE" ] || [ -z "$(ls -A "$WHEELHOUSE" 2>/dev/null)" ]; then
    echo "错误：wheelhouse 目录缺失或为空：$WHEELHOUSE"
    echo "  请先在联网机器（Windows 即可）上执行："
    echo "      python packaging/kylin/prepare_wheelhouse.py --arch $ARCH"
    echo "  再把整个项目目录拷贝到本机后重跑本脚本。"
    exit 1
fi
WHEEL_COUNT="$(ls "$WHEELHOUSE"/*.whl 2>/dev/null | wc -l)"
echo "==> wheelhouse：$WHEELHOUSE（$WHEEL_COUNT 个 wheel）"

# ---------- 2. Python 解释器选择与版本检查 ----------
# 麒麟 V10 自带 Python 3.8.x；优先显式找 python3.8
if command -v python3.8 >/dev/null 2>&1; then
    PYTHON=python3.8
else
    PYTHON=python3
fi
PY_VER="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "==> Python：$("$PYTHON" --version 2>&1)（$PYTHON）"

if [ "$PY_VER" != "3.8" ]; then
    echo "错误：检测到 Python $PY_VER，但 wheelhouse 是按 Python 3.8 准备的。"
    echo "  wheelhouse 中：PySide6-Essentials 6.6.3.1 支持 3.8~3.12，"
    echo "  但 Pillow 10.4.0 仅提供 cp38 轮子（最后一个支持 3.8 的 Pillow）。"
    echo "  解决办法（二选一）："
    echo "    1) 换用 python3.8：若本机装有 python3.8，重新运行本脚本会自动优先选用；"
    echo "    2) 在联网机器上重新生成 wheelhouse："
    echo "         python packaging/kylin/prepare_wheelhouse.py --python-version ${PY_VER//./}"
    echo "       并同步调整 packaging/kylin/requirements-linux.txt 中的版本锁"
    echo "       （Pillow 需换为支持 $PY_VER 的版本，PySide6 需仍带 manylinux_2_28 轮子）。"
    exit 1
fi

# ---------- 3. 创建/复用 venv（隔离安装，不污染系统 Python） ----------
# venv_healthy：解释器存在且 pip 可用。
# 背景：麒麟最小化安装缺 ensurepip 组件时，`python -m venv` 先建目录、
#       后跑 ensurepip 才失败，留下"没有 pip 的残骸 venv"；若不做检查
#       直接复用，后续 pip install 必报 "No module named pip"。
venv_healthy() {
    [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -m pip --version >/dev/null 2>&1
}

# venv_bootstrap_pip：ensurepip 缺失时的兜底——先 --without-pip 建环境，
# 再用本地 get-pip.py + pip wheel 离线引导安装 pip。
# 全程无需 root、无需 apt、无需联网（适配离线麒麟机器）。
venv_bootstrap_pip() {
    local tools="$SCRIPT_DIR/tools"
    ls "$tools"/pip-*.whl >/dev/null 2>&1 || return 1
    [ -f "$tools/get-pip.py" ] || return 1
    "$PYTHON" -m venv --without-pip "$VENV" || return 1
    "$VENV/bin/python" "$tools/get-pip.py" --no-index --find-links="$tools" || return 1
    venv_healthy
}

if [ -d "$VENV" ] && ! venv_healthy; then
    echo "==> 已存在的虚拟环境不可用（缺少 pip 或已损坏），自动删除重建：$VENV"
    rm -rf "$VENV"
fi

if [ ! -d "$VENV" ]; then
    echo "==> 创建虚拟环境：$VENV"
    if ! "$PYTHON" -m venv "$VENV" || ! venv_healthy; then
        # ensurepip 缺失（麒麟最小化安装常见）：清理残骸，切换离线引导模式
        rm -rf "$VENV"
        echo "==> ensurepip 不可用，切换离线引导模式（--without-pip + get-pip，无需 apt/root）"
        if venv_bootstrap_pip; then
            echo "==> pip 引导成功：$("$VENV/bin/python" -m pip --version 2>&1 | head -1)"
        else
            rm -rf "$VENV"
            echo "错误：venv 创建与离线引导均失败。请检查："
            echo "  1) packaging/kylin/tools/ 下是否有 get-pip.py 和 pip-*.whl（需随项目一起拷贝）"
            echo "  2) 或有软件源时安装 venv 组件："
            echo "        sudo apt-get update && sudo apt-get install python3.8-venv python3-pip"
            echo "     （若提示无法定位软件包，换用：sudo apt-get install python3-3.8-venv）"
            echo "然后重跑本脚本。"
            exit 1
        fi
    fi
else
    echo "==> 复用已存在的虚拟环境：$VENV"
fi

# ---------- 4. 离线安装依赖闭包 ----------
echo "==> 离线安装依赖（--no-index --find-links wheelhouse --no-deps）"
"$VENV/bin/python" -m pip install --disable-pip-version-check \
    --no-index --find-links="$WHEELHOUSE" --no-deps \
    -r "$REQS"

# ---------- 5. 导入冒烟测试 ----------
echo "==> 依赖导入冒烟测试"
"$VENV/bin/python" - <<'PYEOF'
import sys
import PySide6
import PIL
from PIL import Image, ImageDraw
print("    PySide6 %s / Pillow %s / Python %s" % (
    PySide6.__version__, PIL.__version__, sys.version.split()[0]))
try:
    import pynput.keyboard  # noqa: F401
    print("    pynput 可用（X11 全局快捷键）")
except Exception as e:  # noqa: BLE001
    print("    pynput 不可用（%s）——全局快捷键将禁用，其余功能不受影响" % e)
PYEOF

# ---------- 6. PyInstaller 打包 ----------
echo "==> PyInstaller 打包（onedir）"
rm -rf "$DIST" "$WORK"
"$VENV/bin/pyinstaller" --noconfirm --clean \
    --distpath "$DIST" --workpath "$WORK" \
    "$SPEC"

# ---------- 7. 产物校验 ----------
BIN="$DIST/Win11Launcher/Win11Launcher"
echo "==> 校验产物"
[ -x "$BIN" ] || { echo "错误：未找到可执行文件 $BIN"; exit 1; }
echo "    可执行文件：$BIN"
if find "$DIST/Win11Launcher" -name "libqxcb.so" -print -quit | grep -q .; then
    echo "    Qt xcb 平台插件：存在（X11 会话可正常启动）"
else
    echo "    警告：未找到 libqxcb.so，X11 会话可能无法启动（请检查 PyInstaller 版本兼容性）"
fi
DU_SIZE="$(du -sh "$DIST/Win11Launcher" 2>/dev/null | cut -f1 || echo '?')"
echo "    打包体积：$DU_SIZE"

# ---------- 8. 无头冒烟运行（offscreen，5 秒后自动结束） ----------
echo "==> 无头冒烟运行（QT_QPA_PLATFORM=offscreen，5 秒）"
SMOKE_HOME="$(mktemp -d)"
set +e
XDG_CONFIG_HOME="$SMOKE_HOME" QT_QPA_PLATFORM=offscreen timeout 5 "$BIN"
RC=$?
set -e
rm -rf "$SMOKE_HOME"
if [ "$RC" -ne 0 ] && [ "$RC" -ne 124 ]; then
    echo "错误：冒烟运行失败（退出码 $RC）。请把上面日志反馈给开发者。"
    exit 1
fi
echo "    冒烟运行通过（退出码 $RC：0=自行退出，124=超时终止，均为正常）"

# ---------- 9. 完成 ----------
cat <<EOF

============================================================
构建完成！

产物目录：$DIST/Win11Launcher/
直接运行测试：
    $BIN

打包 .deb（安装到 /opt + 桌面菜单入口）：
    bash packaging/kylin/make_deb.sh
    sudo dpkg -i $(ls "$PROJECT_ROOT"/packaging/kylin/*.deb 2>/dev/null | head -1 || echo 'packaging/kylin/win11launcher_*.deb')
============================================================
EOF
