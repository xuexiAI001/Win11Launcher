# -*- coding: utf-8 -*-
"""本地搜索 Mixin：顶部搜索栏，实时过滤启动台内的本地应用，不发起任何网络请求。

设计要点：
- 纯本地：仅在启动台已收录的应用（config.app_config）中按名称/路径关键词过滤，
  绝不调用浏览器或任何在线搜索服务。
- 平台无关：Windows 与麒麟共用，不触碰 services/windows 或 services/kylin。
- 过滤范围限定在「当前分类」内（保持 current_category 语义，所有右键/拖放操作不受影响）。
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit
from PySide6.QtCore import Qt

from core import constants as C
from core.logger import get_logger

logger = get_logger()


def app_matches(app: dict, query: str) -> bool:
    """判断单个应用是否匹配本地搜索关键词（名称 + 路径，不区分大小写）。

    query 为空时匹配全部（即不过滤）。query 与文本统一小写化，调用方无需预处理。
    """
    if not query:
        return True
    q = query.lower()
    haystack = (app.get("name", "") + " " + app.get("path", "")).lower()
    return q in haystack


class SearchMixin:
    """顶部本地搜索栏：输入框（含清除按钮），输入即实时过滤当前分类应用。

    依赖 MainWindow 提供的方法/状态：
      - self._c(color_pair, dark)        主题取色（ThemeApplyMixin）
      - self.config                    配置（Config）
      - self._refresh_grid()           网格刷新（GridMixin）
      - self.status_label              底部状态栏（UiBuilderMixin）
    """

    def _setup_search(self, parent_layout):
        """在标题栏下方插入搜索栏行"""
        self._search_query = ""
        frame = QWidget()
        frame.setObjectName("searchBar")
        fl = QHBoxLayout(frame)
        fl.setContentsMargins(16, 8, 16, 4)
        fl.setSpacing(8)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索本地应用…")
        self._search_edit.setFixedHeight(32)
        self._search_edit.setClearButtonEnabled(True)  # 自带清除按钮（×）
        self._search_edit.textChanged.connect(self._on_search_text_changed)

        fl.addWidget(self._search_edit, 1)
        parent_layout.addWidget(frame)
        self._apply_search_theme()

    def _apply_search_theme(self):
        """搜索栏主题样式（跟随深浅色）"""
        bg = self._c(C.COLOR_CARD_BG)
        fg = self._c(C.COLOR_CARD_NAME)
        border = self._c(C.COLOR_INPUT_BORDER)
        self._search_edit.parent().setStyleSheet(
            f"QWidget#searchBar {{ background: transparent; }}"
            f"QWidget#searchBar QLineEdit {{"
            f" background-color: {bg}; color: {fg};"
            f" border: 1px solid {border}; border-radius: 6px;"
            f" font-family: '{C.FONT_FAMILY}'; font-size: {C.FONT_MENU_SIZE}px;"
            f" padding: 2px 8px; }}"
        )

    def _on_search_text_changed(self, text: str):
        """输入即过滤：更新查询词、刷新网格、状态栏提示结果数"""
        self._search_query = text.strip().lower()
        self._refresh_grid()
        if self._search_query:
            n = self._count_local_matches(self._search_query)
            self.status_label.setText(f"本地搜索：找到 {n} 个应用")
        else:
            self.status_label.setText("")

    def _count_local_matches(self, query: str) -> int:
        """统计当前分类下匹配的应用数"""
        apps = self.config.get_apps(self.config.current_category)
        return sum(1 for a in apps if app_matches(a, query))

    def _clear_search(self):
        """清空搜索（切换分类时调用，恢复完整视图）"""
        self._search_query = ""
        if getattr(self, "_search_edit", None) is not None:
            self._search_edit.blockSignals(True)
            self._search_edit.clear()
            self._search_edit.blockSignals(False)
        if getattr(self, "status_label", None) is not None:
            self.status_label.setText("")
