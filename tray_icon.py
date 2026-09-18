# -*- coding: utf-8 -*-
"""
系统托盘模块 - 关闭最小化到托盘、托盘菜单、点击唤起
"""
import os
import logging
import threading
from PIL import Image, ImageDraw

logger = logging.getLogger("Win11Launcher")


def _load_tray_font(size):
    """加载托盘图标字体，优先使用 Windows 系统字体"""
    from PIL import ImageFont
    font_candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",      # Win11 默认 Segoe UI
        r"C:\Windows\Fonts\segoeuib.ttf",     # Segoe UI Bold
        r"C:\Windows\Fonts\arial.ttf",        # Arial
        r"C:\Windows\Fonts\arialbd.ttf",      # Arial Bold
    ]
    for font_path in font_candidates:
        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        except Exception:
            continue
    # 回退到默认字体
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def create_tray_icon_image():
    """生成托盘图标（Win11风格：蓝色圆角背景 + 白色L字母）"""
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 蓝色圆角背景
    margin = 4
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=12,
        fill=(0, 120, 212, 255)  # Win11 蓝色
    )

    # 白色 L 字母（使用系统字体，居中显示）
    font = _load_tray_font(36)
    text = "L"
    # 计算文字居中位置
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (size - text_w) // 2 - bbox[0]
        text_y = (size - text_h) // 2 - bbox[1] - 2
    except Exception:
        text_x, text_y = 20, 10
    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    return img


class TrayManager:
    """系统托盘管理器"""

    def __init__(self, app_window):
        self.app = app_window
        self.tray_icon = None
        self._tray_thread = None
        self._running = False

    def start(self):
        """在后台线程启动托盘"""
        try:
            import pystray

            # 优先使用本地图标文件
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "app.ico")
            if os.path.exists(icon_path):
                icon_image = Image.open(icon_path)
            else:
                icon_image = create_tray_icon_image()

            menu = pystray.Menu(
                pystray.MenuItem("显示/隐藏", self._on_toggle, default=True),
                pystray.MenuItem("退出", self._on_quit)
            )

            self.tray_icon = pystray.Icon(
                "Win11Launcher",
                icon_image,
                "Win11 启动台",
                menu
            )

            self._running = True
            self._tray_thread = threading.Thread(
                target=self.tray_icon.run,
                daemon=True
            )
            self._tray_thread.start()
            logger.debug("系统托盘已启动")
        except Exception as e:
            logger.debug(f"系统托盘启动失败: {e}")

    def _on_toggle(self, icon, item):
        """托盘菜单：显示/隐藏"""
        try:
            self.app.after(0, self._toggle_window)
        except Exception:
            pass

    def _toggle_window(self):
        """在主线程切换窗口可见性"""
        try:
            if self.app.state() == 'withdrawn' or not self.app.winfo_viewable():
                self.app.deiconify()
                self.app.lift()
                self.app.focus_force()
                logger.debug("托盘唤起窗口")
            else:
                self.app.withdraw()
                logger.debug("托盘隐藏窗口")
        except Exception as e:
            logger.debug(f"托盘切换窗口失败: {e}")

    def _on_quit(self, icon, item):
        """托盘菜单：退出程序"""
        try:
            self.app.after(0, self._quit_app)
        except Exception:
            pass

    def _quit_app(self):
        """在主线程退出程序"""
        try:
            self._running = False
            if self.tray_icon:
                self.tray_icon.stop()
            self.app._force_quit()
        except Exception as e:
            logger.debug(f"托盘退出失败: {e}")

    def stop(self):
        """停止托盘"""
        try:
            self._running = False
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
