# -*- coding: utf-8 -*-
"""搜索栏 Mixin：顶部常驻搜索栏，回车 / 点击「搜索」调用系统默认浏览器打开搜索引擎。

平台无关：Windows 与麒麟共用，仅依赖 webbrowser（跨平台调默认浏览器）。
UI 交互放本 Mixin，不触碰 services/windows 或 services/kylin，保持已分离架构不受影响。
"""
from __future__ import annotations

import webbrowser
from urllib.parse import quote_plus

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QComboBox, QPushButton
from PySide6.QtCore import Qt

from core import constants as C
from core.logger import get_logger

logger = get_logger()


def build_search_url(engine: str, query: str) -> str:
    """拼接搜索引擎 URL（query 会做 urlencode；未知引擎回退默认）。"""
    template = C.SEARCH_ENGINES.get(engine, C.SEARCH_ENGINES[C.DEFAULT_SEARCH_ENGINE])
    return template.format(q=quote_plus(query))


class SearchMixin:
    """顶部搜索栏：搜索引擎下拉 + 输入框 + 搜索按钮。

    依赖 MainWindow 提供的方法/状态：
      - self._c(color_pair, dark)        主题取色（ThemeApplyMixin）
      - self.config.search_engine        当前搜索引擎（Config）
      - self.status_label                底部状态栏（UiBuilderMixin，仅失败时提示用）
    """

    def _setup_search(self, parent_layout):
        """在标题栏下方插入搜索栏行"""
        frame = QWidget()
        frame.setObjectName("searchBar")
        fl = QHBoxLayout(frame)
        fl.setContentsMargins(16, 8, 16, 4)
        fl.setSpacing(8)

        # 搜索引擎下拉
        self._search_engine_combo = QComboBox()
        self._search_engine_combo.addItems(C.SEARCH_ENGINE_NAMES)
        if getattr(self, "config", None) and self.config.search_engine in C.SEARCH_ENGINE_NAMES:
            self._search_engine_combo.setCurrentText(self.config.search_engine)
        self._search_engine_combo.setFixedHeight(32)
        self._search_engine_combo.setMinimumWidth(92)
        self._search_engine_combo.currentTextChanged.connect(self._on_search_engine_changed)

        # 输入框
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索网页…")
        self._search_edit.setFixedHeight(32)
        self._search_edit.returnPressed.connect(self._do_search)

        # 搜索按钮
        self._search_btn = QPushButton("搜索")
        self._search_btn.setFixedHeight(32)
        self._search_btn.setCursor(Qt.PointingHandCursor)
        self._search_btn.clicked.connect(self._do_search)

        fl.addWidget(self._search_engine_combo)
        fl.addWidget(self._search_edit, 1)
        fl.addWidget(self._search_btn)

        self._apply_search_theme()
        parent_layout.addWidget(frame)

    def _apply_search_theme(self):
        """搜索栏主题样式（跟随深浅色）"""
        bg = self._c(C.COLOR_CARD_BG)
        fg = self._c(C.COLOR_CARD_NAME)
        border = self._c(C.COLOR_INPUT_BORDER)
        primary_bg = self._c(C.COLOR_BTN_PRIMARY_BG)
        primary_fg = self._c(C.COLOR_BTN_PRIMARY_FG)
        hover = self._c(C.COLOR_MENU_HOVER)
        self._search_engine_combo.parent().setStyleSheet(
            f"QWidget#searchBar {{ background: transparent; }}"
            f"QWidget#searchBar QLineEdit, QWidget#searchBar QComboBox {{"
            f" background-color: {bg}; color: {fg};"
            f" border: 1px solid {border}; border-radius: 6px;"
            f" font-family: '{C.FONT_FAMILY}'; font-size: {C.FONT_MENU_SIZE}px;"
            f" padding: 2px 8px; }}"
            f"QWidget#searchBar QComboBox QAbstractItemView {{ background-color: {bg};"
            f" color: {fg}; border: 1px solid {border};"
            f" selection-background-color: {hover}; }}"
            f"QWidget#searchBar QPushButton {{ background-color: {primary_bg};"
            f" color: {primary_fg}; border: none; border-radius: 6px;"
            f" padding: 4px 14px; font-family: '{C.FONT_FAMILY}';"
            f" font-size: {C.FONT_MENU_SIZE}px; }}"
            f"QWidget#searchBar QPushButton:hover {{ background-color: {hover}; }}"
        )

    def _on_search_engine_changed(self, name: str):
        """切换搜索引擎并写入配置"""
        if getattr(self, "config", None):
            self.config.search_engine = name

    def _do_search(self):
        """执行搜索：取输入框文本，调系统默认浏览器打开"""
        query = self._search_edit.text().strip()
        if not query:
            self._search_edit.setFocus()
            return
        engine = self._search_engine_combo.currentText()
        url = build_search_url(engine, query)
        logger.debug(f"打开搜索: {engine} -> {url}")
        try:
            # new=2：优先在已有浏览器标签页打开
            webbrowser.open(url, new=2)
        except Exception as e:
            logger.warning(f"打开浏览器失败: {e}")
            if hasattr(self, "status_label"):
                self.status_label.setText(f"无法打开浏览器: {e}")
