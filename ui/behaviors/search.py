# -*- coding: utf-8 -*-
"""本地全局搜索 Mixin：跨分类全量检索本机启动台应用，纯本地、无网络请求。

搜索能力（2026-10-31 从「当前分类过滤」改造为「全局检索」）：
 1. **搜索字段**：name（应用/文件夹名称，即标题）+ path（可执行路径 / Exec 命令）；
    文件夹额外检索其内部应用的 name + path，因此"藏在文件夹里的应用"也能被搜到。
 2. **模糊匹配 + 分词**：
    - 分词 tokenize()：按空白与常见分隔符（, ; | / \\ 、 ， ； ·）切词并小写化；
      中文无空格时整段作为一个词，英文/路径按分隔符成词。
    - 模糊：子串包含匹配（非全等），不区分大小写。
    - 多关键词取 **AND**：全部词命中才算匹配（更精确地收窄）。
 3. **相关性排序**（app_score）：名称命中(30+) > 路径/内部命中(5)；
    名称前缀命中额外 +20，命中位置越靠前得分越高，短名称优先。
    结果按 score 降序展示（同名按名称字母序兜底）。
 4. **无结果**：网格显示空态提示"未找到与「xxx」匹配的应用"，状态栏显示 0。
 5. **分类（标签）仅用于收窄结果**：搜索匹配阶段完全不看分类（全量跨分类召回），
    界面提供「全部分类 / 某分类」下拉，仅过滤已召回的结果，不参与搜索匹配。

平台无关：Windows 与麒麟共用；不触碰 services/windows 或 services/kylin。
兼容说明：保留 app_matches(app, query) -> bool 原有接口（内部升级为分词 AND），
新增 tokenize / app_score / search_apps 三个纯函数。
"""
from __future__ import annotations

import re
from typing import Dict, List

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QComboBox

from core import constants as C
from core.logger import get_logger

logger = get_logger()

# 分词分隔符：空白 + 常见标点（英文标点与中文标点）
_TOKEN_SPLIT = re.compile(r"[\s,;|/\\·、，；]+")


# ------------------------------------------------------------
# 纯函数层（可独立测试，无 Qt 依赖）
# ------------------------------------------------------------
def tokenize(query: str) -> List[str]:
    """分词：切分为小写关键词列表；空/纯空白返回 []。"""
    if not query or not query.strip():
        return []
    return [t for t in _TOKEN_SPLIT.split(query.strip().lower()) if t]


def search_fields(app: dict) -> tuple:
    """返回 (name, rest)：标题文本 与 其余可搜索文本（路径 + 文件夹内部应用）。"""
    name = app.get("name") or ""
    path = app.get("path") or ""
    rest = path
    if app.get("type") == "folder":
        inner = " ".join(
            (a.get("name") or "") + " " + (a.get("path") or "")
            for a in (app.get("apps") or [])
        )
        rest = (rest + " " + inner).strip() if rest else inner
    return name, rest


def app_matches(app: dict, query: str) -> bool:
    """是否命中（保留原有 bool 接口）。

    空 query 匹配全部；多关键词需全部命中（AND）；子串包含即算模糊匹配。
    """
    tokens = tokenize(query)
    if not tokens:
        return True
    name, rest = search_fields(app)
    hay = (name + " " + rest).lower()
    return all(t in hay for t in tokens)


def app_score(app: dict, query: str) -> int:
    """相关性打分；0 表示不命中（任一关键词未命中即 0）。"""
    tokens = tokenize(query)
    if not tokens:
        return 0
    name, rest = search_fields(app)
    n, r = name.lower(), rest.lower()
    score = 0
    for t in tokens:
        if t in n:
            idx = n.find(t)
            score += 30 + max(0, 10 - idx)  # 名称命中；越靠前越相关
            if n.startswith(t):
                score += 20                  # 前缀命中额外加权
        elif t in r:
            score += 5                       # 仅路径/内部命中，权重低
        else:
            return 0                         # 未命中 → AND 不成立
    if n:
        score += max(0, 20 - len(n))         # 短名称优先（更精确）
    return score


def search_apps(app_config: Dict[str, List[dict]], query: str) -> List[dict]:
    """全局检索：对所有分类全量匹配，返回按相关性降序的结果列表。

    返回结构（保持 [{...}]，展示层直接消费）：
        [{"category": str, "app": dict, "score": int}, ...]
    """
    tokens = tokenize(query)
    if not tokens:
        return []
    results = []
    for category, apps in app_config.items():
        for app in apps or []:
            s = app_score(app, query)
            if s > 0:
                results.append({"category": category, "app": app, "score": s})
    results.sort(key=lambda it: (-it["score"], (it["app"].get("name") or "").lower()))
    return results


# ------------------------------------------------------------
# UI Mixin
# ------------------------------------------------------------
class SearchMixin:
    """顶部全局搜索栏：输入框（含清除按钮）+ 分类收窄下拉 + 实时检索。

    依赖 MainWindow 提供的方法/状态：
      - self._c(color_pair, dark)        主题取色（ThemeApplyMixin）
      - self.config                    配置（Config）
      - self._refresh_grid()           网格刷新（GridMixin）
      - self.status_label              底部状态栏（UiBuilderMixin）
    """

    ALL_CATEGORIES = "全部分类"

    def _setup_search(self, parent_layout):
        """在标题栏下方插入搜索栏行"""
        self._search_query = ""
        self._search_results = []
        self._search_filter_category = ""

        frame = QWidget()
        frame.setObjectName("searchBar")
        fl = QHBoxLayout(frame)
        fl.setContentsMargins(16, 8, 16, 4)
        fl.setSpacing(8)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索本地应用（全局）…")
        self._search_edit.setFixedHeight(32)
        self._search_edit.setClearButtonEnabled(True)  # 自带清除按钮（×）
        self._search_edit.textChanged.connect(self._on_search_text_changed)

        # 分类收窄下拉：仅用于收窄已召回的结果，不参与搜索匹配
        self._search_cat_combo = QComboBox()
        self._search_cat_combo.setFixedHeight(32)
        self._search_cat_combo.setMinimumWidth(110)
        self._search_cat_combo.currentTextChanged.connect(self._on_filter_category_changed)
        self._refresh_search_categories()

        fl.addWidget(self._search_edit, 1)
        fl.addWidget(self._search_cat_combo)
        parent_layout.addWidget(frame)
        self._apply_search_theme()

    def _apply_search_theme(self):
        """搜索栏主题样式（跟随深浅色）

        搜索框与分类下拉统一圆角半径，视觉风格匹配；下拉原本的方形箭头区改为
        右侧圆角 + CSS 三角形箭头，避免突兀的"方块"。
        """
        radius = 10  # 统一圆角半径（输入框与下拉一致）
        bg = self._c(C.COLOR_CARD_BG)
        fg = self._c(C.COLOR_CARD_NAME)
        border = self._c(C.COLOR_INPUT_BORDER)
        self._search_edit.parent().setStyleSheet(
            f"QWidget#searchBar {{ background: transparent; }}"
            f"QWidget#searchBar QLineEdit, QWidget#searchBar QComboBox {{"
            f" background-color: {bg}; color: {fg};"
            f" border: 1px solid {border}; border-radius: {radius}px;"
            f" font-family: '{C.FONT_FAMILY}'; font-size: {C.FONT_MENU_SIZE}px;"
            f" padding: 2px 8px; }}"
            # 下拉区：右侧圆角、去掉分隔竖线，避免方形箭头块
            f"QWidget#searchBar QComboBox::drop-down {{"
            f" subcontrol-origin: padding; subcontrol-position: top right;"
            f" width: 24px; border-left-width: 0px;"
            f" border-top-right-radius: {radius}px;"
            f" border-bottom-right-radius: {radius}px;"
            f" background: transparent; }}"
            # 用 CSS 三角形替代默认方块箭头
            f"QWidget#searchBar QComboBox::down-arrow {{"
            f" image: none; width: 0px; height: 0px;"
            f" border-left: 4px solid transparent;"
            f" border-right: 4px solid transparent;"
            f" border-top: 5px solid {fg}; margin-right: 6px; }}"
            f"QWidget#searchBar QComboBox QAbstractItemView {{"
            f" background-color: {bg}; color: {fg};"
            f" border: 1px solid {border}; border-radius: {radius}px; }}"
        )

    def _refresh_search_categories(self):
        """分类增删后同步收窄下拉（只影响收窄，不影响匹配逻辑）"""
        combo = getattr(self, "_search_cat_combo", None)
        if combo is None:
            return
        current = getattr(self, "_search_filter_category", "")
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self.ALL_CATEGORIES)
        for cat in self.config.categories:
            combo.addItem(cat)
        if current and current in self.config.categories:
            combo.setCurrentText(current)
        else:
            combo.setCurrentText(self.ALL_CATEGORIES)
            self._search_filter_category = ""
        combo.blockSignals(False)

    # ------------------------------------------------------------
    # 检索流程
    # ------------------------------------------------------------
    def _on_search_text_changed(self, text: str):
        """输入即检索：全量匹配 → 应用分类收窄 → 刷新网格 → 更新状态栏"""
        self._search_query = text.strip()
        self._run_search()
        self._refresh_grid()
        self._update_search_status()

    def _run_search(self):
        """执行全局检索（跨所有分类，全量，不涉及网络）"""
        if not getattr(self, "_search_query", ""):
            self._search_results = []
            return
        self._search_results = search_apps(self.config.app_config, self._search_query)

    def _visible_results(self) -> List[dict]:
        """当前展示的结果：已召回结果经「分类收窄」过滤后的子集"""
        results = getattr(self, "_search_results", None) or []
        filt = getattr(self, "_search_filter_category", "")
        if not filt:
            return list(results)
        return [r for r in results if r["category"] == filt]

    def _on_filter_category_changed(self, text: str):
        """切换收窄分类：仅重新过滤结果，不重新匹配"""
        self._search_filter_category = (
            "" if (not text or text == self.ALL_CATEGORIES) else text
        )
        self._refresh_grid()
        self._update_search_status()

    def _update_search_status(self):
        """状态栏展示结果数（含收窄标记）"""
        if not getattr(self, "_search_query", ""):
            self.status_label.setText("")
            return
        n = len(self._visible_results())
        extra = (f"（已按分类 {self._search_filter_category} 收窄）"
                 if self._search_filter_category else "")
        self.status_label.setText(f"本地搜索：找到 {n} 个应用{extra}")

    def _clear_search(self):
        """清空搜索（切换分类 / 退出搜索时调用，恢复完整视图）"""
        self._search_query = ""
        self._search_results = []
        self._search_filter_category = ""
        edit = getattr(self, "_search_edit", None)
        if edit is not None:
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        combo = getattr(self, "_search_cat_combo", None)
        if combo is not None:
            combo.blockSignals(True)
            combo.setCurrentText(self.ALL_CATEGORIES)
            combo.blockSignals(False)
        if getattr(self, "status_label", None) is not None:
            self.status_label.setText("")
