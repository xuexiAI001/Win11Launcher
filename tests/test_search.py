# -*- coding: utf-8 -*-
"""搜索引擎测试：build_search_url 编码/回退、搜索栏控件、回车/按钮调浏览器、引擎切换持久化。

说明：
- 必须在导入任何 PySide 模块前设置 QT_QPA_PLATFORM=offscreen。
- _setup_system_integration / _setup_theme_watcher 依赖系统级集成，headless 下打桩隔离。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit, QComboBox, QPushButton
from unittest.mock import patch

from core.config import Config
import ui.behaviors.search as search_mod
from ui.behaviors.search import build_search_url
from core import constants as C
import ui.main_window as mw_mod


def _make_window():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    mw_mod.MainWindow._setup_system_integration = lambda self: None
    mw_mod.MainWindow._setup_theme_watcher = lambda self: None
    cfg = Config()
    return mw_mod.MainWindow(cfg)


# ------------------------------------------------------------
# 纯函数：build_search_url
# ------------------------------------------------------------
def test_build_search_url_baidu():
    url = build_search_url("百度", "hello world")
    assert url == "https://www.baidu.com/s?wd=hello+world"


def test_build_search_url_bing_encodes_cjk():
    url = build_search_url("必应", "python 编程")
    assert url.startswith("https://www.bing.com/search?q=")
    assert "python" in url
    # 中文应被 percent-encode，不应原样出现
    assert "编程" not in url
    assert "%" in url


def test_build_search_url_unknown_engine_falls_back():
    url = build_search_url("不存在的引擎", "x")
    assert url == "https://www.baidu.com/s?wd=x"


def test_build_search_url_empty_query():
    url = build_search_url("谷歌", "")
    assert url == "https://www.google.com/search?q="


# ------------------------------------------------------------
# 搜索栏 UI 与交互
# ------------------------------------------------------------
def test_search_bar_widgets_present():
    win = _make_window()
    assert isinstance(win._search_edit, QLineEdit)
    assert isinstance(win._search_engine_combo, QComboBox)
    assert isinstance(win._search_btn, QPushButton)
    # 下拉包含全部引擎
    items = [win._search_engine_combo.itemText(i) for i in range(win._search_engine_combo.count())]
    assert items == C.SEARCH_ENGINE_NAMES
    # 默认选中百度
    assert win._search_engine_combo.currentText() == C.DEFAULT_SEARCH_ENGINE


def test_search_opens_browser_on_button():
    win = _make_window()
    win._search_edit.setText("测试 搜索")
    with patch.object(search_mod.webbrowser, "open") as mock_open:
        win._search_btn.clicked.emit()
    assert mock_open.called
    called_url = mock_open.call_args[0][0]
    assert called_url.startswith("https://www.baidu.com/s?wd=")
    assert "%" in called_url  # 中文已编码


def test_search_opens_browser_on_return_pressed():
    win = _make_window()
    win._search_edit.setText("pytest")
    with patch.object(search_mod.webbrowser, "open") as mock_open:
        # 模拟回车：直接调用槽
        win._do_search()
    assert mock_open.called
    assert mock_open.call_args[0][0] == "https://www.baidu.com/s?wd=pytest"


def test_search_empty_query_does_not_open_browser():
    win = _make_window()
    win._search_edit.setText("   ")
    with patch.object(search_mod.webbrowser, "open") as mock_open:
        win._do_search()
    assert not mock_open.called


def test_search_engine_switch_persists_to_config():
    win = _make_window()
    win._search_engine_combo.setCurrentText("必应")
    assert win.config.search_engine == "必应"
    # 再次搜索应使用新引擎
    win._search_edit.setText("x")
    with patch.object(search_mod.webbrowser, "open") as mock_open:
        win._do_search()
    assert mock_open.call_args[0][0].startswith("https://www.bing.com/search?q=")
