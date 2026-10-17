# -*- coding: utf-8 -*-
"""
模块名：ui.main_window
职责：主窗口——组合各行为 Mixin，对外接口与重构前完全一致
依赖：core.constants, core.config, core.logger, services.icon_loader,
      ui.behaviors.*（各职责 Mixin）

重构说明：
    原 MainWindow 约 1082 行、职责混杂。现按职责拆分为 ui/behaviors/ 下的
    多个 Mixin（主题监听 / 系统集成 / 主题应用 / UI 组装 / 网格 / 卡片交互 /
    应用操作 / 右键菜单 / 拖放 / 窗口事件），本文件只负责组合它们。
    构造方式 `MainWindow(config)` 与方法名保持不变，对外部调用方透明。
"""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QMainWindow
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, Signal

from core import constants as C
from core.config import Config
from core.logger import get_logger
from services.icon_loader import IconLoader

from ui.behaviors.theme_watcher import ThemeWatcherMixin
from ui.behaviors.system_integration import SystemIntegrationMixin
from ui.behaviors.theme import ThemeApplyMixin
from ui.behaviors.ui_builder import UiBuilderMixin
from ui.behaviors.grid import GridMixin
from ui.behaviors.cards import CardActionsMixin
from ui.behaviors.app_ops import AppOpsMixin
from ui.behaviors.context_menus import ContextMenuMixin
from ui.behaviors.dragdrop import DragDropMixin
from ui.behaviors.window_events import WindowEventsMixin
from ui.behaviors.zoom import ZoomMixin

logger = get_logger()


class MainWindow(
    QMainWindow,
    UiBuilderMixin,
    ThemeApplyMixin,
    ThemeWatcherMixin,
    SystemIntegrationMixin,
    GridMixin,
    CardActionsMixin,
    AppOpsMixin,
    ContextMenuMixin,
    DragDropMixin,
    WindowEventsMixin,
    ZoomMixin,
):
    """主窗口：组合多个行为 Mixin，保持对外接口（构造方式、方法名）完全不变"""

    # 全局快捷键信号：pynput 监听线程 emit，主线程槽执行
    _hotkey_signal = Signal()

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        # 界面缩放：必须在任何尺寸/字号读取与 _setup_ui 之前应用
        C.set_scale(self.config.ui_scale)
        self.dark = self._resolve_dark()

        self.setWindowTitle(C.WINDOW_TITLE)
        self.setFixedSize(C.WINDOW_WIDTH, C.WINDOW_HEIGHT)
        # 纯亚克力背景方案：
        # WA_TranslucentBackground 让 Qt 不绘制窗口背景，
        # 配合 DwmExtendFrameIntoClientArea 让 DWM 用亚克力填充整个客户区，
        # 从而得到纯粹的桌面模糊背景（无叠加色）。
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._center_window()

        # 图标
        icon_path = self._resource_path("assets/app.ico")
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        # 图标异步加载器
        self.icon_loader = IconLoader(max_workers=4)
        self.icon_loader.icon_ready.connect(self._on_icon_ready)
        self.icon_loader.folder_icon_ready.connect(self._on_folder_icon_ready)

        # 卡片缓存：{分类: [AppCard]}
        self._card_cache: dict[str, list] = {}
        # 已打开的文件夹窗口：{key: FolderWindow}
        self._folder_windows: dict[str, object] = {}
        # 已打开的模态弹窗（设置/分类管理等），主题变化时需同步刷新
        self._open_dialogs: list = []

        self._setup_ui()
        self._apply_effects()
        self._refresh_grid()
        self._setup_system_integration()
        self._setup_theme_watcher()
        self._setup_zoom()
