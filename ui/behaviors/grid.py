# -*- coding: utf-8 -*-
"""网格 Mixin：应用卡片网格的构建、刷新与图标回调"""
from PySide6.QtCore import Qt

from core import constants as C
from core.logger import get_logger
from ui.app_card import AppCard

logger = get_logger()


class GridMixin:
    """当前分类应用网格的构建、缓存与图标加载回调"""

    # ------------------------------------------------------------
    # 网格
    # ------------------------------------------------------------
    def _clear_grid(self):
        """清空网格布局（卡片保留父级，仅隐藏，避免游离 widget 崩溃）"""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()

    def _refresh_grid(self):
        """刷新当前分类的应用网格"""
        category = self.config.current_category
        apps = self.config.get_apps(category)

        # 复用缓存
        if category not in self._card_cache:
            self._card_cache[category] = []

        self._clear_grid()
        cards = self._card_cache[category]

        # 数量变化则重建
        if len(cards) != len(apps):
            cards = []
            for app in apps:
                card = AppCard(app, self.dark)
                card.clicked.connect(self._on_card_clicked)
                card.right_clicked.connect(self._on_card_right_clicked)
                card.drag_released.connect(self._on_card_drag_released)
                cards.append(card)
            self._card_cache[category] = cards

        # 布局（固定 9 列，卡片居中）
        for i, card in enumerate(cards):
            row, col = divmod(i, C.GRID_COLUMNS)
            self.grid_layout.addWidget(card, row, col, Qt.AlignCenter)
            card.show()

        # 异步加载图标
        theme = "dark" if self.dark else "light"
        for card in cards:
            self.icon_loader.load(card.app_data, size=C.ICON_SIZE,
                                  is_folder=card.is_folder, theme=theme)

    def _on_icon_ready(self, app_data: dict, pixmap):
        """普通应用图标就绪"""
        import shiboken6
        # 主窗口卡片
        for cards in self._card_cache.values():
            for card in cards:
                if card.app_data is app_data and shiboken6.isValid(card):
                    card.set_icon(pixmap)
        # 文件夹窗口内的卡片
        for win in list(self._folder_windows.values()):
            if not shiboken6.isValid(win):
                continue
            for card in win.findChildren(AppCard):
                if card.app_data is app_data and shiboken6.isValid(card):
                    card.set_icon(pixmap)

    def _on_folder_icon_ready(self, app_data: dict, pixmap):
        """文件夹预览图就绪"""
        self._on_icon_ready(app_data, pixmap)
