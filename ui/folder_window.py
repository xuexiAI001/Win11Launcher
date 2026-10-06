# -*- coding: utf-8 -*-
"""
模块名：ui.folder_window
职责：文件夹内容弹窗——500×400，4 列网格
依赖：core.constants, core.logger, ui.app_card, ui.window_effects
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QGridLayout, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from core import constants as C
from core.logger import get_logger
from ui.app_card import AppCard
from ui import window_effects

logger = get_logger()


class FolderWindow(QWidget):
    """文件夹内容弹窗"""

    def __init__(self, main_window, folder_data: dict, dark: bool):
        super().__init__(None)
        self.main_window = main_window
        self.folder_data = folder_data
        self.dark = dark

        self.setWindowTitle(folder_data.get("name", "文件夹"))
        self.setFixedSize(C.FOLDER_WINDOW_WIDTH, C.FOLDER_WINDOW_HEIGHT)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self._center_window()

        self._setup_ui()
        self._apply_effects()
        self._render_apps()

    def _c(self, pair) -> str:
        return C.color(pair, self.dark)

    def _center_window(self):
        screen = self.screen().availableGeometry()
        x = (screen.width() - C.FOLDER_WINDOW_WIDTH) // 2
        y = (screen.height() - C.FOLDER_WINDOW_HEIGHT) // 2
        self.move(x, y)

    def _apply_effects(self):
        window_effects.apply_acrylic(self, self.main_window.config.alpha)
        window_effects.set_round_corner(self)
        window_effects.set_titlebar_color(self, self.dark)

    def apply_theme(self):
        """主题切换后刷新本窗口"""
        self.dark = self.main_window.dark
        self.setStyleSheet(f"background-color: {self._c(C.COLOR_FOLDER_BG)};")
        self.title_label.setStyleSheet(f"color: {self._c(C.COLOR_TITLE_TEXT)};")
        self._render_apps()
        window_effects.set_titlebar_color(self, self.dark)
        window_effects.apply_acrylic(self, self.main_window.config.alpha)
        self.update()

    def _setup_ui(self):
        self.setStyleSheet(
            f"background-color: {self._c(C.COLOR_FOLDER_BG)};"
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: transparent; }}"
            f"QScrollArea > QWidget {{ background: transparent; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # 标题栏
        title_frame = QWidget()
        title_frame.setFixedHeight(40)
        tl = QHBoxLayout(title_frame)
        tl.setContentsMargins(10, 0, 10, 0)
        name = self.folder_data.get("name", "文件夹")
        count = len(self.folder_data.get("apps", []))
        self.title_label = QLabel(f"{name}  ({count} 个应用)")
        font = QFont(C.FONT_FAMILY, C.FONT_FOLDER_TITLE_SIZE)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet(f"color: {self._c(C.COLOR_TITLE_TEXT)};")
        tl.addWidget(self.title_label)
        tl.addStretch(1)
        layout.addWidget(title_frame)

        # 滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(10, 5, 10, 5)
        self.grid_layout.setSpacing(C.GRID_PADDING)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll, 1)

    def _render_apps(self):
        """渲染文件夹内应用"""
        # 移除旧卡片：从布局摘除并显式销毁，避免游离 widget 与异步回调冲突
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        apps = self.folder_data.get("apps", [])
        if not apps:
            empty = QLabel("文件夹为空\n从主界面右键应用可移动到这里")
            empty.setAlignment(Qt.AlignCenter)
            empty.setFont(QFont(C.FONT_FAMILY, 13))
            empty.setStyleSheet(f"color: {self._c(C.COLOR_EMPTY_TEXT)};")
            self.grid_layout.addWidget(empty, 0, 0, 1, C.FOLDER_GRID_COLUMNS)
            return

        theme = "dark" if self.dark else "light"
        for i, app in enumerate(apps):
            card = AppCard(app, self.dark, in_folder=True)
            card.clicked.connect(self._on_card_clicked)
            card.right_clicked.connect(self._on_card_right_clicked)
            row, col = divmod(i, C.FOLDER_GRID_COLUMNS)
            self.grid_layout.addWidget(card, row, col)
            self.main_window.icon_loader.load(app, size=C.ICON_SIZE,
                                              is_folder=False, theme=theme)

    def _on_card_clicked(self, app_data: dict):
        """文件夹内点击应用"""
        path = app_data.get("path", "")
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                logger.warning(f"启动失败: {e}")

    def _on_card_right_clicked(self, app_data: dict, pos):
        """文件夹内右键：移出文件夹"""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        from ui.context_menu import menu_style
        menu = QMenu(self)
        menu.setStyleSheet(menu_style(self.dark))
        act = QAction("移出文件夹", menu)
        act.triggered.connect(lambda: self._remove_app(app_data))
        menu.addAction(act)
        menu.exec(pos)

    def _remove_app(self, app_data: dict):
        """从文件夹移出到主分类"""
        apps = self.folder_data.get("apps", [])
        if app_data in apps:
            apps.remove(app_data)
        self.main_window.config.add_app(self.main_window.config.current_category, app_data)
        self.main_window.config.save()
        self.main_window._card_cache.pop(self.main_window.config.current_category, None)
        self.main_window._refresh_grid()
        self._render_apps()
        self._update_title()

    def _update_title(self):
        """更新标题计数"""
        name = self.folder_data.get("name", "文件夹")
        count = len(self.folder_data.get("apps", []))
        self.title_label.setText(f"{name}  ({count} 个应用)")
