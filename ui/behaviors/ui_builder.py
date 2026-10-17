# -*- coding: utf-8 -*-
"""UI 组装 Mixin：标题栏、分类标签栏、应用网格、底部状态栏"""
import os
import sys

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QGridLayout, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon

from core import constants as C
from core.logger import get_logger

logger = get_logger()


class UiBuilderMixin:
    """主界面 UI 的组装与布局（依赖 MainWindow 提供的方法/状态）"""

    # ------------------------------------------------------------
    # UI 组装
    # ------------------------------------------------------------
    def _setup_ui(self):
        """组装主界面"""
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        self._central = central
        self._apply_window_bg()

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._setup_title_bar(layout)
        self._setup_tabs(layout)
        self._setup_grid(layout)
        self._setup_status_bar(layout)

    def _apply_window_bg(self):
        """窗口背景完全透明，让 DWM 亚克力填充

        纯亚克力方案下，Qt 不绘制任何窗口背景色，
        背景完全由 DWM 的扩展框架（亚克力）提供。
        子控件（卡片、标签栏）各自保持不透明背景。
        """
        self._central.setStyleSheet(
            f"#central {{ background: transparent; }}"
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: transparent; }}"
            f"QScrollArea > QWidget {{ background: transparent; }}"
            f"QWidget#gridContainer {{ background: transparent; }}"
        )

    def _setup_title_bar(self, parent_layout):
        """标题栏"""
        frame = QWidget()
        frame.setFixedHeight(36)
        fl = QHBoxLayout(frame)
        fl.setContentsMargins(16, 12, 16, 4)

        label = QLabel(C.WINDOW_TITLE)
        font = QFont(C.FONT_FAMILY, C.FONT_TITLE_SIZE)
        font.setBold(True)
        label.setFont(font)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"color: {self._c(C.COLOR_TITLE_TEXT)};")
        fl.addWidget(label, 1)
        self._title_label = label

        parent_layout.addWidget(frame)

    def _setup_tabs(self, parent_layout):
        """分类标签栏"""
        outer = QWidget()
        ol = QHBoxLayout(outer)
        ol.setContentsMargins(12, 8, 12, 8)
        ol.setSpacing(0)

        inner = QWidget()
        il = QHBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(C.TAB_SPACING)

        self._tab_buttons = {}
        for cat in self.config.categories:
            btn = QPushButton(cat)
            btn.setFixedSize(C.TAB_WIDTH, C.TAB_HEIGHT)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, c=cat: self._switch_category(c))
            il.addWidget(btn)
            self._tab_buttons[cat] = btn

        ol.addStretch(1)
        ol.addWidget(inner)
        ol.addStretch(1)
        parent_layout.addWidget(outer)

        self._tabs_outer = outer
        self._tabs_layout = parent_layout
        self._update_tab_styles()

    def _setup_tabs_refresh(self):
        """分类变化后重建标签栏"""
        # 移除旧标签栏
        if hasattr(self, '_tabs_outer'):
            self._tabs_outer.setParent(None)
        # 重建（插入到网格之前）
        idx = self._tabs_layout.indexOf(self.scroll)
        new_outer = QWidget()
        ol = QHBoxLayout(new_outer)
        ol.setContentsMargins(12, 8, 12, 8)
        ol.setSpacing(0)
        inner = QWidget()
        il = QHBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(C.TAB_SPACING)
        self._tab_buttons = {}
        for cat in self.config.categories:
            btn = QPushButton(cat)
            btn.setFixedSize(C.TAB_WIDTH, C.TAB_HEIGHT)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, c=cat: self._switch_category(c))
            il.addWidget(btn)
            self._tab_buttons[cat] = btn
        ol.addStretch(1)
        ol.addWidget(inner)
        ol.addStretch(1)
        self._tabs_layout.insertWidget(idx, new_outer)
        self._tabs_outer = new_outer
        self._update_tab_styles()
        self._refresh_grid()

    def _update_tab_styles(self):
        """更新分类标签配色"""
        for cat, btn in self._tab_buttons.items():
            active = (cat == self.config.current_category)
            if active:
                bg = self._c(C.COLOR_TAB_ACTIVE_BG)
                fg = self._c(C.COLOR_TAB_ACTIVE_FG)
            else:
                bg = self._c(C.COLOR_TAB_INACTIVE_BG)
                fg = self._c(C.COLOR_TAB_INACTIVE_FG)
            btn.setStyleSheet(
                f"QPushButton {{"
                f" background-color: {bg}; color: {fg};"
                f" border: none; border-radius: {C.TAB_CORNER_RADIUS}px;"
                f" font-family: '{C.FONT_FAMILY}'; font-size: {C.FONT_TAB_SIZE}px;"
                f"}}"
            )

    def _setup_grid(self, parent_layout):
        """应用网格区"""
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self.scroll.setContextMenuPolicy(Qt.CustomContextMenu)
        self.scroll.customContextMenuRequested.connect(self._on_blank_right_clicked)

        self.grid_container = QWidget()
        self.grid_container.setObjectName("gridContainer")
        self.grid_container.setStyleSheet("background: transparent;")
        self.grid_container.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid_container.customContextMenuRequested.connect(self._on_blank_right_clicked)
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(8, 10, 8, 10)
        self.grid_layout.setSpacing(C.GRID_PADDING)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.scroll.setWidget(self.grid_container)
        parent_layout.addWidget(self.scroll, 1)

        # 拖放支持
        self.setAcceptDrops(True)

    def _setup_status_bar(self, parent_layout):
        """底部状态栏（仅保留状态提示，按钮已移至右键菜单）"""
        frame = QWidget()
        fl = QHBoxLayout(frame)
        fl.setContentsMargins(16, 0, 16, 8)

        fl.addStretch(1)

        self.status_label = QLabel("")
        self.status_label.setFont(QFont(C.FONT_FAMILY, C.FONT_STATUS_SIZE))
        self.status_label.setStyleSheet(f"color: {self._c(C.COLOR_STATUS_TEXT)};")
        fl.addWidget(self.status_label)

        parent_layout.addWidget(frame)

    # ------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------
    def _switch_category(self, category: str):
        """切换分类"""
        if category == self.config.current_category:
            return
        self.config.current_category = category
        self._update_tab_styles()
        self._refresh_grid()
        logger.debug(f"切换到分类: {category}")

    # ------------------------------------------------------------
    # 窗口
    # ------------------------------------------------------------
    def _center_window(self):
        """窗口居中（考虑标题栏与边框，确保完整可见）"""
        screen = self.screen().availableGeometry()
        # 用 frameGeometry 获取含边框的完整尺寸
        frame = self.frameGeometry()
        fw = frame.width() if frame.width() > 0 else C.WINDOW_WIDTH
        fh = frame.height() if frame.height() > 0 else C.WINDOW_HEIGHT
        x = screen.x() + (screen.width() - fw) // 2
        y = screen.y() + (screen.height() - fh) // 2
        self.move(max(screen.x(), x), max(screen.y(), y))

    def _resource_path(self, rel: str) -> str:
        """资源路径（兼容打包）

        源码运行时按当前文件向上回溯到包含 main.py 的项目根目录；
        打包后使用 PyInstaller 注入的 sys._MEIPASS。
        """
        import os as _os
        if getattr(sys, '_MEIPASS', ''):
            base = sys._MEIPASS
        else:
            base = _os.path.dirname(_os.path.abspath(__file__))
            # 向上查找项目根目录（含 main.py），兼容本文件位于 ui/ 或 ui/behaviors/
            while base and not _os.path.exists(_os.path.join(base, 'main.py')):
                parent = _os.path.dirname(base)
                if parent == base:
                    break
                base = parent
        path = _os.path.join(base, rel)
        return path if _os.path.exists(path) else ""
