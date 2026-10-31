# -*- coding: utf-8 -*-
"""本地搜索测试：纯函数 app_matches、网格按关键词过滤、无网络依赖、清空恢复。

说明：
- 必须在导入任何 PySide 模块前设置 QT_QPA_PLATFORM=offscreen。
- _setup_system_integration / _setup_theme_watcher 依赖系统级集成，headless 下打桩隔离。
- 关键断言：搜索为纯本地过滤，绝不 import webbrowser 或发起网络请求。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.config import Config
import ui.behaviors.search as search_mod
from ui.behaviors.search import app_matches, SearchMixin
import ui.main_window as mw_mod


def _make_window():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    mw_mod.MainWindow._setup_system_integration = lambda self: None
    mw_mod.MainWindow._setup_theme_watcher = lambda self: None
    cfg = Config()
    return mw_mod.MainWindow(cfg)


# ------------------------------------------------------------
# 无网络依赖（替换掉原来的网络搜索引擎）
# ------------------------------------------------------------
def test_search_module_has_no_network_dependency():
    # 本地搜索绝不能依赖 webbrowser 或任何在线搜索逻辑
    assert "webbrowser" not in search_mod.__dict__
    assert not hasattr(search_mod, "build_search_url")
    assert not hasattr(SearchMixin, "_do_search")
    # 核心过滤逻辑为纯函数，无副作用
    assert callable(app_matches)


# ------------------------------------------------------------
# 纯函数：app_matches
# ------------------------------------------------------------
def test_app_matches_empty_query_matches_all():
    assert app_matches({"name": "记事本", "path": "x"}, "")
    assert app_matches({}, "")


def test_app_matches_by_name():
    assert app_matches({"name": "记事本", "path": "C:/n.exe"}, "记事")
    assert app_matches({"name": "Notepad", "path": ""}, "note")


def test_app_matches_by_path():
    assert app_matches({"name": "X", "path": "C:/Program Files/QQ/qq.exe"}, "qq")


def test_app_matches_case_insensitive():
    assert app_matches({"name": "Calculator", "path": ""}, "CALC")


def test_app_matches_no_match():
    assert not app_matches({"name": "记事本", "path": ""}, "浏览器")


# ------------------------------------------------------------
# 网格过滤（限定当前分类，无网络）
# ------------------------------------------------------------
def test_grid_filters_current_category():
    win = _make_window()
    cat = win.config.current_category
    win.config.add_app(cat, {"name": "记事本", "path": "C:/n.exe"})
    win.config.add_app(cat, {"name": "计算器", "path": "C:/c.exe"})
    win.config.add_app(cat, {"name": "浏览器", "path": "C:/b.exe"})

    win._search_query = "记事"
    win._refresh_grid()

    # 网格中只应显示 1 张匹配卡片
    assert win.grid_layout.count() == 1


def test_grid_shows_all_when_query_empty():
    win = _make_window()
    cat = win.config.current_category
    win.config.add_app(cat, {"name": "A", "path": "1"})
    win.config.add_app(cat, {"name": "B", "path": "2"})

    win._search_query = ""  # 空查询不过滤
    win._refresh_grid()
    assert win.grid_layout.count() == 2


# ------------------------------------------------------------
# 搜索栏交互
# ------------------------------------------------------------
def test_search_text_changed_sets_query_and_status():
    win = _make_window()
    cat = win.config.current_category
    win.config.add_app(cat, {"name": "记事本", "path": "C:/n.exe"})

    win._on_search_text_changed("记事")
    assert win._search_query == "记事"
    assert "找到 1 个" in win.status_label.text()


def test_clear_search_restores_view():
    win = _make_window()
    win._search_query = "x"
    win._search_edit.setText("x")
    win._clear_search()
    assert win._search_query == ""
    assert win._search_edit.text() == ""


def test_switch_category_clears_search():
    win = _make_window()
    if len(win.config.categories) < 2:
        win.config.add_category("临时分类")
    cat = win.config.current_category
    other = next(c for c in win.config.categories if c != cat)
    win._search_query = "abc"
    win._search_edit.setText("abc")
    win._switch_category(other)
    assert win._search_query == ""
    assert win._search_edit.text() == ""
    assert win.config.current_category == other
