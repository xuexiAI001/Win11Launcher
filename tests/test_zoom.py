# -*- coding: utf-8 -*-
"""界面缩放测试：常量重算、窗口尺寸、Ctrl+滚轮、边界夹取、列数自适应。

offscreen 环境运行；默认缩放 1.0 时窗口尺寸/常量与历史版本一致。
"""
import os
import sys

# 必须在导入任何 PySide 模块前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QPoint
from PySide6.QtGui import QWheelEvent

from core import constants as C
from core.config import Config
import ui.main_window as mw_mod


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv[:1])


@pytest.fixture()
def window(app, tmp_path, monkeypatch):
    # 隔离系统级集成（托盘/热键/原生消息），只测缩放逻辑
    monkeypatch.setattr(mw_mod.MainWindow, "_setup_system_integration", lambda self: None)
    monkeypatch.setattr(mw_mod.MainWindow, "_setup_theme_watcher", lambda self: None)
    # 隔离真实配置文件（每个用例独立临时目录）
    monkeypatch.setattr("core.config.CONFIG_FILE", str(tmp_path / "cfg.json"))
    cfg = Config()
    cfg.load()
    win = mw_mod.MainWindow(cfg)
    yield win
    win.close()


def test_default_scale_matches_legacy_sizes(window):
    """默认 1.0：窗口与常量与历史版本逐像素一致"""
    assert C.get_scale() == 1.0
    assert (window.width(), window.height()) == (1060, 700)
    assert (C.ICON_SIZE, C.ITEM_WIDTH, C.ITEM_HEIGHT) == (48, 100, 100)
    assert (C.FONT_TITLE_SIZE, C.TITLEBAR_HEIGHT) == (18, 36)


def test_set_zoom_rescales_constants_and_window(window):
    window.set_zoom(1.3)
    assert C.get_scale() == 1.3
    assert (C.WINDOW_WIDTH, C.WINDOW_HEIGHT) == (1378, 910)
    assert (window.width(), window.height()) == (1378, 910)
    assert (C.ICON_SIZE, C.ITEM_WIDTH, C.ITEM_HEIGHT) == (62, 130, 130)
    assert window.config.ui_scale == 1.3  # 已持久化到配置


def test_set_zoom_clamps_to_range(window):
    window.set_zoom(9.9)
    assert C.get_scale() == C.UI_SCALE_MAX == 1.6
    window.set_zoom(0.01)
    assert C.get_scale() == C.UI_SCALE_MIN == 0.8


def test_adjust_zoom_steps(window):
    window.set_zoom(1.0)
    window.adjust_zoom(C.UI_SCALE_STEP)
    assert C.get_scale() == pytest.approx(1.1)
    window.adjust_zoom(-C.UI_SCALE_STEP)
    assert C.get_scale() == pytest.approx(1.0)


def _wheel(app, widget, dy, modifiers):
    pos = QPointF(5, 5)
    ev = QWheelEvent(pos, widget.mapToGlobal(pos).toPoint(),
                     QPoint(0, 0), QPoint(0, dy),
                     Qt.NoButton, modifiers, Qt.NoScrollPhase, False)
    app.sendEvent(widget, ev)


def test_ctrl_wheel_zooms(app, window):
    window.set_zoom(1.0)
    _wheel(app, window.scroll.viewport(), 120, Qt.ControlModifier)
    assert C.get_scale() == pytest.approx(1.1)
    _wheel(app, window.scroll.viewport(), -120, Qt.ControlModifier)
    assert C.get_scale() == pytest.approx(1.0)


def test_wheel_without_ctrl_does_not_zoom(app, window):
    window.set_zoom(1.0)
    _wheel(app, window.scroll.viewport(), 120, Qt.NoModifier)
    assert C.get_scale() == 1.0


def test_effective_columns_fixed_in_normal_state(window):
    """常规状态列数固定 9（与历史行为一致）"""
    assert window._effective_columns() == C.GRID_COLUMNS == 9


def test_effective_columns_expands_when_maximized(window, monkeypatch):
    """最大化时列数按窗口宽度自适应"""
    window.set_zoom(1.0)
    monkeypatch.setattr(type(window), "isMaximized", lambda self: True)
    monkeypatch.setattr(type(window), "isFullScreen", lambda self: False)
    # 默认窗宽 1060：9 列刚好放得下（9*100+8*16=1024 ≤ 1044）
    assert window._effective_columns() == 9
    # 宽窗 → 更多列（上限 16）
    monkeypatch.setattr(type(window), "width", lambda self: 2000)
    assert window._effective_columns() == 16
    # 窄窗 → 更少列
    monkeypatch.setattr(type(window), "width", lambda self: 500)
    assert window._effective_columns() == 4


def test_zoom_rebuilds_cards_with_new_size(window):
    """缩放后卡片按新尺寸重建"""
    window.config.add_app("系统应用", {"name": "缩放测试", "path": "C:/x.exe"})
    window.set_zoom(1.0)
    window._refresh_grid()
    card = window._card_cache["系统应用"][0]
    assert (card.width(), card.height()) == (C.ITEM_WIDTH, C.ITEM_HEIGHT) == (100, 100)
    window.set_zoom(1.5)
    card = window._card_cache["系统应用"][0]
    assert (card.width(), card.height()) == (C.ITEM_WIDTH, C.ITEM_HEIGHT) == (150, 150)
