# -*- coding: utf-8 -*-
"""Linux 图标解析：按 freedesktop 图标主题规范，由 .desktop 的 Icon= 值定位图标文件。

Linux 应用不在可执行文件内嵌图标，而是在 .desktop 的 Icon= 字段给出：
  - 绝对路径（直接使用），或
  - 图标名（通常无扩展名），需在图标主题目录树中按 主题/尺寸/格式 查找。

说明：多数现代应用图标为 SVG。PIL 无法直接打开 SVG，故 SVG 经 Qt 渲染
（QSvgRenderer 优先，qsvg 图片插件回退）转为 PIL Image 后走同一缩放管线；
位图（.png/.xpm）直接走 PIL。两条路径均不引入额外第三方依赖。
"""

import os

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from core.logger import get_logger

logger = get_logger()

# 标准图标根目录（测试可通过参数注入覆盖）
DEFAULT_ICON_ROOTS = [
    "/usr/share/icons",
    "/usr/share/pixmaps",
    "/var/lib/flatpak/exports/share/icons",
    os.path.expanduser("~/.icons"),
    os.path.expanduser("~/.local/share/icons"),
]

_ALL_EXTS = (".png", ".svg", ".xpm")


def _icon_roots(icon_roots=None):
    roots = list(icon_roots) if icon_roots is not None else list(DEFAULT_ICON_ROOTS)
    for base in os.environ.get("XDG_DATA_DIRS", "/usr/share").split(":"):
        if base:
            p = os.path.join(base, "icons")
            if p not in roots:
                roots.append(p)
    return roots


def resolve_icon_file(icon, size=48, theme=None, icon_roots=None):
    """把 .desktop 的 Icon= 值解析为磁盘上的图标文件路径；找不到返回 None。

    Args:
        icon: Icon= 值（绝对路径或图标名）
        size: 期望尺寸，用于匹配 主题/<size>x<size>/ 子目录
        theme: 当前图标主题名（优先），回退 hicolor
        icon_roots: 图标根目录列表（测试注入用）
    """
    if not icon:
        return None
    icon = icon.strip()
    if os.path.isabs(icon):
        return icon if os.path.exists(icon) else None

    # 名称已带受支持扩展名则不再追加
    if os.path.splitext(icon)[1].lower() in _ALL_EXTS:
        exts = [""]
    else:
        exts = list(_ALL_EXTS)

    roots = _icon_roots(icon_roots)
    themes = [theme, "hicolor"] if theme else ["hicolor"]
    size_dir = "%dx%d" % (size, size)
    fallback = None
    for root in roots:
        # pixmaps 为扁平目录：直接存放 名称.扩展名
        if root.endswith("pixmaps"):
            for ext in exts:
                cand = os.path.join(root, icon + ext)
                if os.path.exists(cand):
                    return cand
        for th in themes:
            base = os.path.join(root, th) if th else root
            if not os.path.isdir(base):
                continue
            # 主题目录结构为 主题/<尺寸>/<上下文>/图标，逐层遍历查找，
            # 优先返回位于目标尺寸目录下的文件，否则回退首个匹配。
            for dirpath, _, files in os.walk(base):
                for ext in exts:
                    if (icon + ext) in files:
                        cand = os.path.join(dirpath, icon + ext)
                        if size_dir in dirpath.split(os.sep):
                            return cand
                        if fallback is None:
                            fallback = cand
    return fallback


def _qimage_to_pil(qimg: QImage):
    """QImage → PIL Image（RGBA）。

    处理 Qt 行填充（bytesPerLine 可能大于 width*4），逐行紧密拷贝。
    """
    if qimg.isNull():
        return None
    qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    bpl = qimg.bytesPerLine()
    buf = bytes(qimg.bits())
    if bpl != w * 4:
        buf = b"".join(buf[y * bpl:y * bpl + w * 4] for y in range(h))
    try:
        return Image.frombytes("RGBA", (w, h), buf)
    except Exception as e:
        logger.debug(f"QImage 转 PIL 失败: {e}")
        return None


def _render_svg(path: str, size: int):
    """把 SVG 渲染为 PIL Image。

    优先用 QSvgRenderer 按目标尺寸直接渲染（矢量清晰，不受固有尺寸影响）；
    wheel 自带 qsvg 图片格式插件，QImage 直接加载作为回退路径。
    两条路径都不引入额外第三方依赖。
    """
    try:
        from PySide6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(path)
        if renderer.isValid():
            qimg = QImage(size, size, QImage.Format_ARGB32)
            qimg.fill(Qt.GlobalColor.transparent)
            painter = QPainter(qimg)
            renderer.render(painter)
            painter.end()
            img = _qimage_to_pil(qimg)
            if img is not None:
                # 全透明渲染（如内容为空的 <svg/>）等同无图标，
                # 返回 None 让上层显示默认图标，而不是一张空白
                if img.getextrema()[3][1] == 0:
                    return None
                return img
    except Exception as e:
        logger.debug(f"QSvgRenderer 渲染失败 {path}: {e}")
    try:
        img = _qimage_to_pil(QImage(path))
        if img is not None:
            if img.getextrema()[3][1] == 0:
                return None
            return img
    except Exception as e:
        logger.debug(f"QImage 加载 SVG 失败 {path}: {e}")
    return None


def _prepare(img, size):
    """保持宽高比缩放到目标尺寸，居中放置在透明画布上。"""
    try:
        img = img.convert("RGBA")
        if img.width != size or img.height != size:
            scale = min(size / img.width, size / img.height)
            nw = max(1, int(round(img.width * scale)))
            nh = max(1, int(round(img.height * scale)))
            img = img.resize((nw, nh), Image.LANCZOS)
            if nw != size or nh != size:
                canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                canvas.paste(img, ((size - nw) // 2, (size - nh) // 2), img)
                img = canvas
        return img
    except Exception as e:
        logger.debug(f"图标缩放失败: {e}")
        return img


def get_app_icon(app_path, icon_path=None, size=48, original_path=None):
    """获取应用图标——与 Windows 版签名一致，返回 PIL.Image 或 None。

    Linux 下图标信息来自 icon_path（即 .desktop 的 Icon= 值），app_path 忽略。
    位图（png/xpm）走 PIL；SVG 经 Qt 渲染后再转 PIL，接口对上层保持不变。
    """
    icon = icon_path or app_path
    f = resolve_icon_file(icon, size)
    if not f:
        return None
    if f.lower().endswith(".svg"):
        img = _render_svg(f, size)
        if img is not None:
            return _prepare(img, size)
        return None
    try:
        img = Image.open(f)
        return _prepare(img, size)
    except Exception as e:
        logger.debug(f"加载图标失败 {f}: {e}")
        return None
