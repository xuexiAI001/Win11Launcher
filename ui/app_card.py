# -*- coding: utf-8 -*-
"""
模块名：ui.app_card
职责：应用卡片——图标 + 名称，悬停/点击/拖拽/右键菜单
依赖：core.constants, core.logger, services.icon_loader
"""

import os

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, QPoint, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QColor, QPen, QPixmap

from core import constants as C
from core.logger import get_logger

logger = get_logger()


class AppCard(QWidget):
    """应用卡片（100×100）"""

    clicked = Signal(object)          # 单击
    right_clicked = Signal(object, QPoint)  # 右键
    drag_released = Signal(object, QPoint)  # 拖拽释放

    def __init__(self, app_data: dict, dark: bool, parent=None, in_folder: bool = False):
        super().__init__(parent)
        self.app_data = app_data
        self.dark = dark
        self.in_folder = in_folder
        self.is_folder = app_data.get("type") == "folder"

        self._hover = False
        self._pressed = False
        self._drag_start = None
        self._is_dragging = False
        self._icon_pixmap: QPixmap | None = None

        self.setFixedSize(C.ITEM_WIDTH, C.ITEM_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        # 卡片背景半透明，让底层亚克力轻微透出（轻微模糊透明观感）
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._setup_ui()

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        # 与旧版一致：图标上留白 12、下留白 4，文字底部 8
        layout.setContentsMargins(5, 12, 5, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        # 图标标签
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(C.ICON_SIZE, C.ICON_SIZE)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.icon_label, 0, Qt.AlignHCenter)

        # 名称标签
        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setFixedWidth(90)
        self.name_label.setStyleSheet(
            f"color: {C.color(C.COLOR_CARD_NAME, self.dark)}; background: transparent;"
        )
        layout.addWidget(self.name_label, 0, Qt.AlignHCenter)

        self._update_name()
        self._show_placeholder()

    def _update_name(self):
        """设置名称与自适应字号"""
        if self.is_folder:
            name = self.app_data.get("name", "文件夹")
            count = len(self.app_data.get("apps", []))
            text = f"{name}\n({count})"
            max_lines = 2
        else:
            text = self.app_data.get("name", "App")
            max_lines = 2

        # 先按最大字号算出实际行数，再按行数分档：
        # 单行/两行字号略小，三行保持原字号
        lines = self._count_lines(text, max_width=90, size=C.FONT_CARD_NAME_BASE)
        if lines >= 3:
            base = C.FONT_CARD_NAME_BASE
        else:
            base = C.FONT_CARD_NAME_BASE - 1
        size = self._fit_font_size(text, max_width=90, max_lines=max_lines,
                                   base_size=base)
        font = QFont(C.FONT_FAMILY, size)
        self.name_label.setFont(font)
        self.name_label.setText(text)

    @staticmethod
    def _count_lines(text: str, max_width: int = 90, size: int = 11) -> int:
        """按指定字号计算文本换行后的行数"""
        fm = QFontMetrics(QFont(C.FONT_FAMILY, size))
        lines = 0
        for seg in text.split("\n"):
            if not seg:
                lines += 1
                continue
            cur = ""
            seg_lines = 1
            for ch in seg:
                if fm.horizontalAdvance(cur + ch) > max_width:
                    seg_lines += 1
                    cur = ch
                else:
                    cur += ch
            lines += seg_lines
        return lines

    @staticmethod
    def _fit_font_size(text: str, max_width: int = 90, max_lines: int = 3,
                       base_size: int = C.FONT_CARD_NAME_BASE,
                       min_size: int = C.FONT_CARD_NAME_MIN) -> int:
        """计算能放下文本的最大字号"""
        for size in range(base_size, min_size - 1, -1):
            fm = QFontMetrics(QFont(C.FONT_FAMILY, size))
            lines = 0
            for seg in text.split("\n"):
                if not seg:
                    lines += 1
                    continue
                cur = ""
                seg_lines = 1
                for ch in seg:
                    if fm.horizontalAdvance(cur + ch) > max_width:
                        seg_lines += 1
                        cur = ch
                    else:
                        cur += ch
                lines += seg_lines
            if lines <= max_lines:
                return size
        return min_size

    def _show_placeholder(self):
        """显示占位（首字母 / 文件夹 emoji）"""
        if self.is_folder:
            bg = C.color(C.COLOR_ICON_FOLDER_BG, self.dark)
            self.icon_label.setText("📁")
            font = QFont(C.FONT_FAMILY, 24)
            self.icon_label.setFont(font)
            self.icon_label.setStyleSheet(
                f"background-color: {bg}; border-radius: {C.ICON_CORNER_RADIUS}px;"
            )
        else:
            bg = C.color(C.COLOR_ICON_APP_BG, self.dark)
            initial = self.app_data.get("name", "A")[:1].upper()
            self.icon_label.setText(initial)
            font = QFont(C.FONT_FAMILY, 24)
            font.setBold(True)
            self.icon_label.setFont(font)
            self.icon_label.setStyleSheet(
                f"background-color: {bg}; color: white;"
                f" border-radius: {C.ICON_CORNER_RADIUS}px;"
            )

    def set_icon(self, pixmap: QPixmap):
        """设置图标（异步加载完成后调用）"""
        if pixmap.isNull():
            return
        # 图标按 DPI 提取（如 125% 下为 60px），而 icon_label 是 48 逻辑像素。
        # 设置 devicePixelRatio 让 Qt 知道这是高分辨率图，
        # 从而 1:1 映射到逻辑尺寸，既不裁剪也不模糊。
        target = self.icon_label.width()
        if target > 0 and pixmap.width() != target:
            ratio = pixmap.width() / target
            pixmap.setDevicePixelRatio(ratio)
        self._icon_pixmap = pixmap
        self.icon_label.setText("")
        self.icon_label.setPixmap(pixmap)
        self.icon_label.setStyleSheet("background: transparent;")

    # ------------------------------------------------------------
    # 绘制（卡片背景 + 悬停边框）
    # ------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._is_dragging:
            bg = C.color(C.COLOR_CARD_DRAG_BG, self.dark)
        elif self._pressed:
            bg = C.color(C.COLOR_CARD_CLICK_BG, self.dark)
        elif self._hover:
            bg = C.color(C.COLOR_CARD_HOVER_BG, self.dark)
        else:
            bg = C.color(C.COLOR_CARD_BG, self.dark)

        rect = self.rect().adjusted(2, 2, -2, -2)

        # 半透明背景：让底层亚克力轻微透出，形成轻微模糊透明观感
        color = QColor(bg)
        color.setAlpha(C.CARD_BG_ALPHA)
        painter.setBrush(color)
        if self._hover:
            painter.setPen(QPen(QColor(C.color(C.COLOR_CARD_HOVER_BORDER, self.dark)), 2))
        else:
            painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, C.CARD_CORNER_RADIUS, C.CARD_CORNER_RADIUS)

    # ------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------
    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._drag_start = event.globalPosition().toPoint()
            self._is_dragging = False
            self.update()
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(self.app_data, event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self._drag_start is None or self.is_folder:
            return
        pos = event.globalPosition().toPoint()
        if (pos - self._drag_start).manhattanLength() > 8:
            self._is_dragging = True
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        was_dragging = self._is_dragging
        self._pressed = False
        self._is_dragging = False
        self._drag_start = None
        self.update()

        if was_dragging:
            self.drag_released.emit(self.app_data, event.globalPosition().toPoint())
        else:
            self._click_animation()
            self.clicked.emit(self.app_data)

    def _click_animation(self):
        """点击闪烁动画"""
        self._pressed = True
        self.update()
        QTimer.singleShot(50, self._anim_stage2)

    def _anim_stage2(self):
        self._pressed = False
        self._hover = True
        self.update()
        QTimer.singleShot(100, self._anim_stage3)

    def _anim_stage3(self):
        self._hover = False
        self.update()
