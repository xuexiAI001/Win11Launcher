# -*- coding: utf-8 -*-
"""全局搜索测试：分词、模糊匹配、相关性排序、跨分类检索、分类收窄、空态、
跨分类操作的分类归属、以及无网络守卫。

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
from ui.behaviors.search import (
    app_matches, SearchMixin, tokenize, app_score, search_apps,
)
import ui.main_window as mw_mod


def _make_window():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    mw_mod.MainWindow._setup_system_integration = lambda self: None
    mw_mod.MainWindow._setup_theme_watcher = lambda self: None
    cfg = Config()
    return mw_mod.MainWindow(cfg)


# ------------------------------------------------------------
# 无网络依赖（全局搜索仍是纯本地）
# ------------------------------------------------------------
def test_search_module_has_no_network_dependency():
    assert "webbrowser" not in search_mod.__dict__
    assert not hasattr(search_mod, "build_search_url")
    assert not hasattr(SearchMixin, "_do_search")
    assert callable(app_matches)


# ------------------------------------------------------------
# 分词 tokenize
# ------------------------------------------------------------
def test_tokenize_empty():
    assert tokenize("") == []
    assert tokenize("   ") == []


def test_tokenize_splits_by_space_and_punct():
    assert tokenize("hello world") == ["hello", "world"]
    assert tokenize("a/b;c") == ["a", "b", "c"]


def test_tokenize_lowercases_and_strips():
    assert tokenize("  NotePAD ") == ["notepad"]


def test_tokenize_cjk_kept_as_one_token():
    # 中文无空格：整段作为一个词
    assert tokenize("记事本") == ["记事本"]


# ------------------------------------------------------------
# 模糊匹配 + 多词 AND（app_matches 保持 bool 接口）
# ------------------------------------------------------------
def test_app_matches_empty_query_matches_all():
    assert app_matches({"name": "记事本", "path": "x"}, "")
    assert app_matches({}, "")


def test_app_matches_substring_fuzzy():
    assert app_matches({"name": "记事本", "path": "C:/n.exe"}, "记事")
    assert app_matches({"name": "Notepad", "path": ""}, "note")


def test_app_matches_case_insensitive():
    assert app_matches({"name": "Calculator", "path": ""}, "CALC")


def test_app_matches_by_path():
    assert app_matches({"name": "X", "path": "C:/Program Files/QQ/qq.exe"}, "qq")


def test_app_matches_multi_token_and():
    # 多个关键词需全部命中
    app = {"name": "Visual Studio Code", "path": "C:/VS Code/code.exe"}
    assert app_matches(app, "vs code")
    assert not app_matches(app, "vs chrome")  # chrome 未命中 → AND 不成立


def test_app_matches_no_match():
    assert not app_matches({"name": "记事本", "path": ""}, "浏览器")


# ------------------------------------------------------------
# 相关性打分与排序
# ------------------------------------------------------------
def test_app_score_name_beats_path():
    by_name = {"name": "QQ", "path": "C:/other/x.exe"}
    by_path = {"name": "Other", "path": "C:/qq.exe"}
    assert app_score(by_name, "qq") > app_score(by_path, "qq")


def test_app_score_prefix_beats_middle():
    prefix = {"name": "QQ音乐", "path": ""}
    middle = {"name": "音乐QQ", "path": ""}
    assert app_score(prefix, "qq") > app_score(middle, "qq")


def test_app_score_zero_when_not_matching():
    assert app_score({"name": "记事本", "path": ""}, "浏览器") == 0
    assert app_score({"name": "记事本", "path": ""}, "") == 0


# ------------------------------------------------------------
# 全局检索 search_apps（跨分类）
# ------------------------------------------------------------
def test_search_apps_is_global_across_categories():
    app_config = {
        "办公": [{"name": "Word", "path": "C:/word.exe"}],
        "影音": [{"name": "QQ音乐", "path": "C:/qqmusic.exe"}],
        "我的游戏": [{"name": "Steam", "path": "C:/steam.exe"}],
    }
    res = search_apps(app_config, "qq")
    # 命中 QQ音乐（名称）——跨分类召回，不要求它在"当前分类"
    assert [r["category"] for r in res] == ["影音"]
    assert res[0]["app"]["name"] == "QQ音乐"


def test_search_apps_returns_sorted_by_score_desc():
    app_config = {
        "A": [
            {"name": "QQ飞车", "path": ""},        # 前缀命中 → 高分
            {"name": "我的QQ", "path": ""},        # 中间命中
            {"name": "Foo", "path": "C:/qq.exe"},  # 仅路径命中 → 低分
        ],
    }
    res = search_apps(app_config, "qq")
    scores = [r["score"] for r in res]
    assert scores == sorted(scores, reverse=True)
    assert res[0]["app"]["name"] == "QQ飞车"


def test_search_apps_searches_inside_folders():
    # 文件夹内部应用也应可被搜到
    app_config = {
        "工具": [{
            "type": "folder", "name": "常用", "apps": [
                {"name": "计算器", "path": "C:/calc.exe"},
            ],
        }],
    }
    res = search_apps(app_config, "计算器")
    assert len(res) == 1
    assert res[0]["app"]["type"] == "folder"


def test_search_apps_empty_query_returns_empty():
    assert search_apps({"A": [{"name": "x"}]}, "") == []


# ------------------------------------------------------------
# UI：全局搜索 → 网格跨分类展示 + 空态 + 分类收窄
# ------------------------------------------------------------
def test_global_search_shows_cross_category_results():
    win = _make_window()
    cats = win.config.categories
    assert len(cats) >= 2
    win.config.add_app(cats[0], {"name": "目标应用甲", "path": "C:/a.exe"})
    win.config.add_app(cats[1], {"name": "目标应用乙", "path": "C:/b.exe"})
    win.config.add_app(cats[1], {"name": "无关应用", "path": "C:/c.exe"})
    # 当前分类设为 cats[0]，但搜索应能召回 cats[1] 的结果（全局）
    win.config.current_category = cats[0]

    win._on_search_text_changed("目标应用")

    assert win._search_results, "应召回到结果"
    cats_hit = {r["category"] for r in win._visible_results()}
    # 结果跨分类（cats[0] 与 cats[1] 都应有命中）
    assert cats_hit == {cats[0], cats[1]}
    assert len(win._visible_results()) == 2


def test_search_empty_state_shown_when_no_result():
    win = _make_window()
    win.config.current_category = win.config.categories[0]
    win._on_search_text_changed("绝不存在的应用名xyz")
    assert win._visible_results() == []
    # 空态已挂载到网格并显示（测试未真正 show 主窗口，
    # 故用 isHidden / parent 判定，而非依赖父可见性的 isVisible）
    assert win._empty_label.text().startswith("未找到")
    assert win._empty_label.parent() is not None
    assert not win._empty_label.isHidden()


def test_category_narrowing_filters_results_only():
    win = _make_window()
    cats = win.config.categories
    win.config.add_app(cats[0], {"name": "同名应用", "path": "C:/a.exe"})
    win.config.add_app(cats[1], {"name": "同名应用", "path": "C:/b.exe"})

    win._on_search_text_changed("同名应用")
    assert len(win._visible_results()) == 2

    # 收窄到 cats[1]：只保留该分类的结果（不重新改变匹配）
    win._on_filter_category_changed(cats[1])
    assert len(win._visible_results()) == 1
    assert win._visible_results()[0]["category"] == cats[1]
    assert "收窄" in win.status_label.text()

    # 回到全部分类恢复 2 条
    win._on_filter_category_changed(SearchMixin.ALL_CATEGORIES)
    assert len(win._visible_results()) == 2


def test_search_result_cards_remember_source_category():
    win = _make_window()
    cats = win.config.categories
    win.config.add_app(cats[1], {"name": "异类应用", "path": "C:/x.exe"})
    win.config.current_category = cats[0]
    win._on_search_text_changed("异类应用")
    cards = list(getattr(win, "_search_cards", None) or [])
    assert cards
    assert cards[0].property("source_category") == cats[1]


# ------------------------------------------------------------
# 跨分类操作的归属正确性（全局搜索的关键风险点）
# ------------------------------------------------------------
def test_move_app_uses_real_category_not_current():
    win = _make_window()
    cats = win.config.categories
    app = {"name": "待搬家应用", "path": "C:/m.exe"}
    win.config.add_app(cats[1], app)
    # 当前浏览 cats[0]，但该应用真实在 cats[1]
    win.config.current_category = cats[0]

    win._move_app_to_category(app, cats[0])
    app_names_c1 = [a.get("name") for a in win.config.get_apps(cats[1])]
    app_names_c0 = [a.get("name") for a in win.config.get_apps(cats[0])]
    assert "待搬家应用" not in app_names_c1
    assert "待搬家应用" in app_names_c0


def test_delete_app_uses_real_category_not_current():
    win = _make_window()
    cats = win.config.categories
    app = {"name": "待删应用", "path": "C:/d.exe"}
    target = cats[2] if len(cats) > 2 else cats[1]
    win.config.add_app(target, app)
    other = next(c for c in cats if c != target)
    win.config.current_category = other

    # 直接走删除的数据路径（跳过弹窗），验证源分类取自真实分类
    win.config.remove_app(win._category_of(app), app)
    assert app not in win.config.get_apps(target)
    # 另一个分类未被误删
    assert "待删应用" not in [a.get("name") for a in win.config.get_apps(other)]
