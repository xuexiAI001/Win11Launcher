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

    def _effective_columns(self) -> int:
        """当前有效列数

        常规状态 = C.GRID_COLUMNS（与历史行为一致）；
        最大化/全屏时按窗口可用宽度自适应，避免大窗口下内容稀疏居中。
        """
        if not (self.isMaximized() or self.isFullScreen()):
            return C.GRID_COLUMNS
        # 可用宽 = 窗宽 - 网格容器左右边距(8+8)；列间距按 GRID_PADDING
        avail = max(1, self.width() - 16)
        per = C.ITEM_WIDTH + C.GRID_PADDING
        return max(1, min(16, int((avail + C.GRID_PADDING) // per)))

    def _refresh_grid(self):
        """刷新网格：全局搜索模式渲染跨分类结果，常规模式渲染当前分类"""
        query = getattr(self, "_search_query", "")
        if query:
            self._render_search_results(query)
            return

        # 常规模式：先清理搜索残留（临时卡片 / 空态），再渲染当前分类
        self._hide_empty_state()
        self._dispose_search_cards()

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

        # 布局（固定 9 列，卡片居中；最大化/全屏时列数自适应）
        for i, card in enumerate(cards):
            row, col = divmod(i, self._effective_columns())
            self.grid_layout.addWidget(card, row, col, Qt.AlignCenter)
            card.show()

        # 异步加载图标
        theme = "dark" if self.dark else "light"
        for card in cards:
            self.icon_loader.load(card.app_data, size=C.ICON_SIZE,
                                  is_folder=card.is_folder, theme=theme)

    # ------------------------------------------------------------
    # 全局搜索结果渲染
    # ------------------------------------------------------------
    def _dispose_search_cards(self):
        """回收上次搜索创建的临时卡片，避免隐藏 widget 无限累积。

        注意：只销毁搜索临时结果卡片，不动 _card_cache 中复用的常规卡片。
        """
        cards = getattr(self, "_search_cards", None) or []
        for card in cards:
            try:
                card.setParent(None)
                card.deleteLater()
            except Exception:
                pass
        self._search_cards = []

    def _render_search_results(self, query: str):
        """渲染全局搜索结果（跨分类平铺；无结果则显示空态）"""
        results = self._visible_results() if hasattr(self, "_visible_results") else []

        self._dispose_search_cards()
        self._clear_grid()

        if not results:
            self._show_empty_state(f"未找到与「{query}」匹配的应用")
            return
        self._hide_empty_state()

        cards = []
        for item in results:
            card = AppCard(item["app"], self.dark)
            # 记录来源分类：右键菜单的移动/删除/重命名据此定位源分类，不依赖 current_category
            card.setProperty("source_category", item["category"])
            card.setToolTip(f"分类：{item['category']}")
            card.clicked.connect(self._on_card_clicked)
            card.right_clicked.connect(self._on_card_right_clicked)
            card.drag_released.connect(self._on_card_drag_released)
            cards.append(card)
        self._search_cards = cards

        for i, card in enumerate(cards):
            row, col = divmod(i, self._effective_columns())
            self.grid_layout.addWidget(card, row, col, Qt.AlignCenter)
            card.show()

        # 异步加载图标
        theme = "dark" if self.dark else "light"
        for card in cards:
            self.icon_loader.load(card.app_data, size=C.ICON_SIZE,
                                  is_folder=card.is_folder, theme=theme)

    def _show_empty_state(self, text: str):
        """无结果空态提示"""
        from PySide6.QtWidgets import QLabel
        if getattr(self, "_empty_label", None) is None:
            self._empty_label = QLabel()
            self._empty_label.setAlignment(Qt.AlignCenter)
            self._empty_label.setWordWrap(True)
        lbl = self._empty_label
        lbl.setMinimumWidth(max(1, int(self.width() * 0.6)))
        lbl.setText(text)
        lbl.setStyleSheet(
            f"color: {self._c(C.COLOR_STATUS_TEXT)};"
            f" font-family: '{C.FONT_FAMILY}'; font-size: {C.FONT_MENU_SIZE}px;"
            f" background: transparent;"
        )
        self.grid_layout.addWidget(lbl, 0, 0, 1, self._effective_columns(),
                                   Qt.AlignCenter)
        lbl.show()

    def _hide_empty_state(self):
        """移除空态提示"""
        lbl = getattr(self, "_empty_label", None)
        if lbl is not None:
            lbl.setParent(None)
            lbl.hide()

    def _on_icon_ready(self, app_data: dict, pixmap):
        """普通应用图标就绪"""
        import shiboken6
        # 主窗口卡片
        for cards in self._card_cache.values():
            for card in cards:
                if card.app_data is app_data and shiboken6.isValid(card):
                    card.set_icon(pixmap)
        # 全局搜索结果卡片（跨分类临时卡片）
        for card in (getattr(self, "_search_cards", None) or []):
            try:
                if card.app_data is app_data and shiboken6.isValid(card):
                    card.set_icon(pixmap)
            except RuntimeError:
                continue
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
