# -*- coding: utf-8 -*-
"""MainWindow 重构冒烟测试：offscreen 模式下验证类可构建、方法齐全、关键路径可调用。

说明：
- 必须在导入任何 PySide 模块前设置 QT_QPA_PLATFORM=offscreen，避免连接显示器。
- _setup_system_integration / _setup_theme_watcher 依赖系统托盘/全局快捷键/原生消息，
  在 headless 下不稳定；它们内容未变，已由 import 阶段验证模块可导入，
  此处打桩隔离，只验证被拆分到各 Mixin 的 UI / 网格 / 主题逻辑。
"""
import os
import sys

# 必须在导入任何 PySide 模块前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.config import Config
import ui.main_window as mw_mod


def test_mainwindow_construction_and_key_paths():
    app = QApplication.instance() or QApplication(sys.argv[:1])

    # 隔离与平台/线程相关的系统级集成（内容未变，单独由 import 验证）
    mw_mod.MainWindow._setup_system_integration = lambda self: None
    mw_mod.MainWindow._setup_theme_watcher = lambda self: None

    cfg = Config()
    cfg.add_app("系统应用", {"name": "测试应用", "path": "C:/Windows/notepad.exe"})

    win = mw_mod.MainWindow(cfg)

    # 关键方法必须存在（来自各 Mixin）
    expected = [
        # ui_builder
        "_setup_ui", "_apply_window_bg", "_setup_title_bar", "_setup_tabs",
        "_setup_tabs_refresh", "_update_tab_styles", "_setup_grid", "_setup_status_bar",
        "_center_window", "_resource_path", "_switch_category",
        # grid
        "_clear_grid", "_refresh_grid", "_on_icon_ready", "_on_folder_icon_ready",
        # cards
        "_on_card_clicked", "_open_folder", "_on_card_right_clicked", "_on_card_drag_released",
        # app_ops
        "_launch_app", "_launch_as_admin", "_move_app_to_category", "_move_app_to_folder",
        "_create_folder_with_app", "_change_icon", "_rename_app", "_delete_app", "_clear_category",
        "_open_file_location", "_show_properties", "_rename_folder", "_delete_folder",
        "_on_add_app", "_open_settings", "register_dialog", "_unregister_dialog", "show_message",
        # context_menus
        "_on_blank_right_clicked", "_new_folder", "_create_new_file",
        # dragdrop
        "dragEnterEvent", "dragMoveEvent", "dropEvent",
        # window_events
        "closeEvent", "changeEvent",
        # theme_watcher
        "_setup_theme_watcher", "_on_show_request", "_show_from_tray",
        "_on_system_theme_changed", "_apply_system_theme",
        # system_integration
        "_setup_system_integration", "_on_hotkey", "_on_new_apps", "_force_quit",
        # theme
        "_resolve_dark", "_c", "_apply_effects", "preview_alpha", "preview_theme",
        "restore_preview_theme", "commit_preview_theme", "apply_theme",
    ]
    missing = [m for m in expected if not hasattr(win, m)]
    assert not missing, f"缺失方法: {missing}"

    # 关键路径可调用（不依赖真实窗口特效/托盘）
    win._switch_category("系统应用")
    win._update_tab_styles()
    win._refresh_grid()
    win.apply_theme()
    win.show_message("冒烟测试")

    # 资源路径解析（源码模式下应回退到项目根目录）
    rp = win._resource_path("assets/app.ico")
    assert isinstance(rp, str)

    print(f"MainWindow 重构冒烟测试通过：类可构建，{len(expected)} 个方法齐全，关键路径可调用")
