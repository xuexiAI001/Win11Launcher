#!/usr/bin/env bash
# ============================================================
# Win11Launcher 麒麟 .deb 打包脚本
#
# 前置：已执行 build_on_kylin.sh 生成 dist-linux/Win11Launcher/
# 产物：packaging/kylin/win11launcher_<版本>_<架构>.deb
# 安装：sudo dpkg -i packaging/kylin/win11launcher_*.deb
#
# 安装布局：
#   /opt/win11launcher/                     程序本体（PyInstaller onedir）
#   /usr/bin/win11launcher                  命令行快捷方式（符号链接）
#   /usr/share/applications/win11launcher.desktop   桌面菜单入口
#   /usr/share/icons/hicolor/256x256/apps/win11launcher.png   应用图标
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST="$PROJECT_ROOT/dist-linux/Win11Launcher"

if [ ! -x "$DIST/Win11Launcher" ]; then
    echo "错误：找不到 $DIST/Win11Launcher"
    echo "  请先执行：bash packaging/kylin/build_on_kylin.sh"
    exit 1
fi

# ---------- 版本号：默认取 core/constants.py 的 APP_VERSION，可用首个参数覆盖 ----------
if [ $# -ge 1 ]; then
    VERSION="$1"
else
    VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' "$PROJECT_ROOT/core/constants.py")"
fi
[ -n "$VERSION" ] || VERSION="1.1.0"
echo "==> 版本号：$VERSION"

# ---------- dpkg 架构（amd64 / arm64） ----------
DPKG_ARCH="$(dpkg --print-architecture 2>/dev/null || true)"
if [ -z "$DPKG_ARCH" ]; then
    case "$(uname -m)" in
        x86_64)  DPKG_ARCH=amd64 ;;
        aarch64) DPKG_ARCH=arm64 ;;
        *) echo "错误：无法确定 dpkg 架构（uname -m = $(uname -m)）"; exit 1 ;;
    esac
fi
echo "==> 架构：$DPKG_ARCH"

# ---------- 组装 deb 目录树 ----------
PKGDIR="$PROJECT_ROOT/build/deb/win11launcher_${VERSION}_${DPKG_ARCH}"
rm -rf "$PKGDIR"
mkdir -p "$PKGDIR/DEBIAN" \
         "$PKGDIR/opt/win11launcher" \
         "$PKGDIR/usr/share/applications" \
         "$PKGDIR/usr/share/icons/hicolor/256x256/apps" \
         "$PKGDIR/usr/bin"
echo "==> 组装目录：$PKGDIR"

# 1. 程序本体 → /opt/win11launcher/
cp -a "$DIST/." "$PKGDIR/opt/win11launcher/"

# 2. 桌面菜单入口
install -m 644 "$SCRIPT_DIR/win11launcher.desktop" \
    "$PKGDIR/usr/share/applications/win11launcher.desktop"

# 3. 应用图标（hicolor 主题，256x256）
install -m 644 "$PROJECT_ROOT/assets/app.png" \
    "$PKGDIR/usr/share/icons/hicolor/256x256/apps/win11launcher.png"

# 4. 命令行快捷方式
ln -sf /opt/win11launcher/Win11Launcher "$PKGDIR/usr/bin/win11launcher"

# ---------- control ----------
cat > "$PKGDIR/DEBIAN/control" <<EOF
Package: win11launcher
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DPKG_ARCH
Depends: libc6, libstdc++6, libgcc-s1
Maintainer: Win11Launcher Project
Description: Windows 11 风格软件启动台（银河麒麟版）
 Qt6 离线打包版本，不依赖系统 Python 环境。
 支持 .desktop 应用发现、整体 UI 缩放（Ctrl+滚轮 / 设置滑块）、
 窗口最大化与全屏、跟随系统深浅色主题。
EOF

# ---------- postinst（刷新图标与桌面数据库，全部容错） ----------
cat > "$PKGDIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
chmod 755 "$PKGDIR/DEBIAN/postinst"

# ---------- 打包 ----------
OUT="$PROJECT_ROOT/packaging/kylin/win11launcher_${VERSION}_${DPKG_ARCH}.deb"
rm -f "$OUT"
if dpkg-deb --help 2>&1 | grep -q -- "--root-owner-group"; then
    # dpkg >= 1.19：文件属主统一为 root:root，不受构建用户影响
    dpkg-deb --build --root-owner-group "$PKGDIR" "$OUT"
else
    dpkg-deb --build "$PKGDIR" "$OUT"
fi

SIZE="$(du -h "$OUT" | cut -f1)"
cat <<EOF

============================================================
.deb 打包完成：$OUT（$SIZE）

安装：
    sudo dpkg -i $OUT
    （如有依赖提示，可执行：sudo apt-get install -f）

卸载：
    sudo dpkg -r win11launcher        # 保留配置
    sudo dpkg -P win11launcher        # 连配置一起清除

运行：
    桌面菜单搜索"Win11Launcher"，或命令行输入 win11launcher
============================================================
EOF
