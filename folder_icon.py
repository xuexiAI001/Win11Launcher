# -*- coding: utf-8 -*-
"""
文件夹预览图标生成模块
将文件夹内前4个应用图标组合成类似iOS/Android的文件夹预览图标
"""
import os
import hashlib
import logging
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger("Win11Launcher")


def _round_rect_mask(size, radius):
    """创建圆角矩形遮罩"""
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size[0]-1, size[1]-1], radius=radius, fill=255)
    return mask


def generate_folder_icon(apps, size=64, theme="light"):
    """
    生成文件夹预览图标

    Args:
        apps: 应用列表，每个应用是dict，包含path字段
        size: 图标尺寸（正方形）
        theme: 主题 "light" 或 "dark"

    Returns:
        PIL.Image 对象
    """
    try:
        from icon_extractor import get_app_icon

        # 创建画布
        canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        # 背景颜色（半透明磨砂效果）
        if theme == "dark":
            bg_color = (60, 60, 60, 200)
            border_color = (80, 80, 80, 150)
        else:
            bg_color = (240, 240, 240, 200)
            border_color = (200, 200, 200, 150)

        # 绘制圆角矩形背景
        radius = int(size * 0.22)
        draw.rounded_rectangle(
            [2, 2, size-3, size-3],
            radius=radius,
            fill=bg_color,
            outline=border_color,
            width=1
        )

        # 取前4个应用
        preview_apps = apps[:4]
        if not preview_apps:
            return canvas

        # 计算每个小图标的尺寸和位置
        padding = int(size * 0.12)
        inner_size = size - padding * 2
        icon_size = inner_size // 2 - 2
        icon_radius = int(icon_size * 0.2)

        positions = [
            (padding, padding),
            (padding + icon_size + 4, padding),
            (padding, padding + icon_size + 4),
            (padding + icon_size + 4, padding + icon_size + 4),
        ]

        for i, app in enumerate(preview_apps):
            if i >= 4:
                break
            try:
                app_path = app.get("path", "")
                if not app_path:
                    continue

                # 提取应用图标
                app_icon = get_app_icon(app_path, size=icon_size)
                if app_icon is None:
                    continue

                # 转换为RGBA
                if app_icon.mode != 'RGBA':
                    app_icon = app_icon.convert('RGBA')

                # 缩放
                app_icon = app_icon.resize((icon_size, icon_size), Image.LANCZOS)

                # 创建圆角裁剪
                mask = _round_rect_mask((icon_size, icon_size), icon_radius)
                rounded_icon = Image.new('RGBA', (icon_size, icon_size), (0, 0, 0, 0))
                rounded_icon.paste(app_icon, (0, 0), mask)

                # 粘贴到画布
                pos = positions[i]
                canvas.paste(rounded_icon, pos, rounded_icon)

            except Exception as e:
                logger.debug(f"生成文件夹图标时处理应用失败: {e}")
                continue

        return canvas

    except Exception as e:
        logger.debug(f"生成文件夹图标失败: {e}")
        return None


def get_folder_icon_cache_path(apps, size=64, theme="light"):
    """
    获取文件夹图标的缓存路径
    根据应用列表内容生成哈希，内容不变则使用缓存
    """
    try:
        # 根据应用路径列表生成哈希
        paths = sorted([app.get("path", "") for app in apps if app.get("path")])
        content = f"{size}_{theme}_" + "_".join(paths)
        hash_str = hashlib.md5(content.encode('utf-8')).hexdigest()[:16]

        cache_dir = os.path.join(os.environ.get('APPDATA', '.'), "Win11Launcher", "icon_cache")
        os.makedirs(cache_dir, exist_ok=True)

        return os.path.join(cache_dir, f"folder_{hash_str}.png")
    except Exception:
        return None


def get_cached_folder_icon(apps, size=64, theme="light"):
    """
    获取文件夹图标（优先从缓存加载，没有则生成并缓存）

    Returns:
        PIL.Image 对象或 None
    """
    cache_path = get_folder_icon_cache_path(apps, size, theme)

    # 尝试从缓存加载
    if cache_path and os.path.exists(cache_path):
        try:
            return Image.open(cache_path)
        except Exception:
            pass

    # 生成新图标
    icon = generate_folder_icon(apps, size, theme)

    # 保存到缓存
    if icon and cache_path:
        try:
            icon.save(cache_path, "PNG")
        except Exception as e:
            logger.debug(f"保存文件夹图标缓存失败: {e}")

    return icon
