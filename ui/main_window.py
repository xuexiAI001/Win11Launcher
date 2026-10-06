# -*- coding: utf-8 -*-
"""
模块名：ui.main_window
职责：主窗口——组装标题栏、分类标签栏、应用网格、底部按钮栏
依赖：core.constants, core.config, core.logger, ui.window_effects
"""

import os
import sys
import time
import ctypes

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QGridLayout, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, QAbstractNativeEventFilter, QEvent
from PySide6.QtGui import QFont, QIcon

from core import constants as C
from core.config import Config
from core.logger import get_logger
from ui import window_effects
from ui.app_card import AppCard
from services.icon_loader import IconLoader

logger = get_logger()

# Windows 消息：系统设置变化（含主题切换）
WM_SETTINGCHANGE = 0x001A
# 自定义消息：新实例请求唤起已有窗口（WM_APP + 1）
WM_LAUNCHER_SHOW = 0x8000 + 1


class _MSG(ctypes.Structure):
    """Windows MSG 结构（64 位下 hwnd/wParam/lParam 均为 8 字节）"""
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_void_p),
        ("lParam", ctypes.c_void_p),
    ]


class _ThemeChangeFilter(QAbstractNativeEventFilter):
    """监听 Windows 原生消息

    1. WM_SETTINGCHANGE + "ImmersiveColorSet"：系统主题变化
    2. WM_LAUNCHER_SHOW：新实例请求唤起已有窗口（单实例唤起）
    """

    def __init__(self, theme_callback, show_callback):
        super().__init__()
        self._theme_callback = theme_callback
        self._show_callback = show_callback

    def nativeEventFilter(self, event_type, message):
        try:
            if event_type == b"windows_generic_MSG":
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
                if msg.message == WM_SETTINGCHANGE:
                    lparam = msg.lParam
                    if lparam:
                        name = ctypes.c_wchar_p(lparam).value or ""
                        if name == "ImmersiveColorSet":
                            self._theme_callback()
                elif msg.message == WM_LAUNCHER_SHOW:
                    self._show_callback()
        except Exception as e:
            logger.debug(f"原生消息监听异常: {e}")
        return False, 0


class MainWindow(QMainWindow):
    """主窗口"""

    # 全局快捷键信号：pynput 监听线程 emit，主线程槽执行
    _hotkey_signal = Signal()

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
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
        self._card_cache: dict[str, list[AppCard]] = {}
        # 已打开的文件夹窗口：{key: FolderWindow}
        self._folder_windows: dict[str, object] = {}
        # 已打开的模态弹窗（设置/分类管理等），主题变化时需同步刷新
        self._open_dialogs: list = []

        self._setup_ui()
        self._apply_effects()
        self._refresh_grid()
        self._setup_system_integration()
        self._setup_theme_watcher()

    # ------------------------------------------------------------
    # 系统主题监听
    # ------------------------------------------------------------
    def _setup_theme_watcher(self):
        """监听系统主题变化 + 单实例唤起请求"""
        if sys.platform != "win32":
            return
        try:
            from PySide6.QtWidgets import QApplication
            self._theme_filter = _ThemeChangeFilter(
                self._on_system_theme_changed, self._on_show_request
            )
            QApplication.instance().installNativeEventFilter(self._theme_filter)
            logger.debug("系统主题变化监听已安装")
        except Exception as e:
            logger.debug(f"安装主题监听失败: {e}")

    def _on_show_request(self):
        """收到新实例的唤起请求（原生事件线程，需投递到主线程）"""
        # 防抖：同一消息可能被 Qt 投递两次，短时间内只处理一次
        now = time.monotonic()
        if now - getattr(self, '_last_show_req', 0) < 0.3:
            return
        self._last_show_req = now
        QTimer.singleShot(0, self._show_from_tray)

    def _show_from_tray(self):
        """从最小化状态恢复窗口（触发 Windows 原生还原动画）"""
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        logger.debug("已响应唤起请求，显示窗口")

    def _on_system_theme_changed(self):
        """系统主题变化回调（原生事件线程，需投递到主线程）"""
        # 仅"跟随系统"时才响应
        if self.config.theme != C.THEME_SYSTEM:
            return
        # 用 QTimer 投递到主线程执行，避免在原生事件回调里操作 UI
        QTimer.singleShot(0, self._apply_system_theme)

    def _apply_system_theme(self):
        """重新解析系统主题并应用"""
        new_dark = self._resolve_dark()
        if new_dark == self.dark:
            return
        logger.debug(f"检测到系统主题变化，切换为{'深色' if new_dark else '浅色'}")
        self.apply_theme()

    # ------------------------------------------------------------
    # 系统集成
    # ------------------------------------------------------------
    def _setup_system_integration(self):
        """托盘、全局快捷键、安装监控"""
        # 托盘
        from ui.tray import TrayManager
        self.tray = TrayManager(self)
        self.tray.start()

        # 全局快捷键
        from services.hotkey import HotkeyManager
        hotkey = self.config.__dict__.get("hotkey", C.DEFAULT_HOTKEY)
        # pynput 回调运行在监听线程，必须经信号投递到主线程再操作 GUI
        self._hotkey_signal.connect(self._on_hotkey, Qt.QueuedConnection)
        self.hotkey_mgr = HotkeyManager(self._hotkey_signal.emit)
        self.hotkey_mgr.start(hotkey)

        # 安装监控
        from services.install_monitor import InstallMonitor
        self.install_monitor = InstallMonitor()
        self.install_monitor.new_apps_found.connect(self._on_new_apps)
        QTimer.singleShot(3000, self.install_monitor.start)

    def _on_hotkey(self):
        """全局快捷键触发：切换窗口显示"""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _on_new_apps(self, paths: list):
        """检测到新安装应用"""
        from PySide6.QtWidgets import QMessageBox
        names = [os.path.splitext(os.path.basename(p))[0] for p in paths]
        ret = QMessageBox.question(
            self, "发现新应用",
            "检测到新安装的应用:\n" + "\n".join(names[:10]) +
            ("\n..." if len(names) > 10 else "") +
            f"\n\n是否添加到「{self.config.current_category}」？",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        from services.app_info import get_app_info
        added = 0
        for p in paths:
            info = get_app_info(p)
            if self.config.add_app(self.config.current_category, info):
                added += 1
        if added:
            self.config.save()
            self._card_cache.pop(self.config.current_category, None)
            self._refresh_grid()
            self.show_message(f"已添加 {added} 个新应用")

    def _force_quit(self):
        """强制退出程序"""
        # 标记正在退出，避免 close() 再次触发 closeEvent 造成递归
        self._quitting = True
        try:
            if hasattr(self, 'hotkey_mgr'):
                self.hotkey_mgr.stop()
            if hasattr(self, 'install_monitor'):
                self.install_monitor.stop()
            if hasattr(self, 'tray'):
                self.tray.stop()
            if hasattr(self, 'icon_loader'):
                self.icon_loader.shutdown()
        except Exception:
            pass
        from PySide6.QtWidgets import QApplication
        # 先关闭窗口，再退出应用，确保进程真正结束
        self.close()
        QApplication.quit()

    # ------------------------------------------------------------
    # 主题
    # ------------------------------------------------------------
    def _resolve_dark(self) -> bool:
        """解析当前是否深色模式"""
        theme = self.config.theme
        if theme == C.THEME_DARK:
            return True
        if theme == C.THEME_LIGHT:
            return False
        # 跟随系统
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
        except Exception:
            return False

    def _c(self, pair) -> str:
        """取当前主题下的颜色"""
        return C.color(pair, self.dark)

    # ------------------------------------------------------------
    # 窗口
    # ------------------------------------------------------------
    def _center_window(self):
        """窗口居中（考虑标题栏与边框，确保完整可见）"""
        screen = self.screen().availableGeometry()
        # 用 frameGeometry 获取含边框的完整尺寸
        frame = self.frameGeometry()
        fw = frame.width() if frame.width() > 0 else C.WINDOW_WIDTH
        fh = frame.height() if frame.height() > 0 else C.WINDOW_HEIGHT
        x = screen.x() + (screen.width() - fw) // 2
        y = screen.y() + (screen.height() - fh) // 2
        self.move(max(screen.x(), x), max(screen.y(), y))

    def _resource_path(self, rel: str) -> str:
        """资源路径（兼容打包）"""
        import os, sys
        base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(base, rel)
        return path if os.path.exists(path) else ""

    def _apply_effects(self):
        """应用亚克力、圆角、标题栏着色"""
        window_effects.apply_acrylic(self, self.config.alpha)
        window_effects.extend_frame_into_client(self)
        window_effects.set_round_corner(self)
        window_effects.set_titlebar_color(self, self.dark)

    def preview_alpha(self, alpha: int):
        """预览透明度（不写配置）"""
        window_effects.apply_acrylic(self, alpha)

    def preview_theme(self, theme: str):
        """预览主题（临时改 config.theme，不写配置）

        首次预览时记录原始主题，供取消时恢复。
        """
        if not hasattr(self, '_preview_old_theme'):
            self._preview_old_theme = self.config.theme
        self.config.theme = theme
        self.apply_theme()

    def restore_preview_theme(self):
        """取消预览：恢复原始主题"""
        if hasattr(self, '_preview_old_theme'):
            self.config.theme = self._preview_old_theme
            del self._preview_old_theme
            self.apply_theme()

    def commit_preview_theme(self):
        """确认预览：丢弃记录的原始主题（保留当前值）"""
        if hasattr(self, '_preview_old_theme'):
            del self._preview_old_theme

    def apply_theme(self):
        """主题切换后立即生效：刷新窗口背景、标题栏、标签、卡片、弹窗"""
        # 重新解析主题（支持"跟随系统"）
        self.dark = self._resolve_dark()

        # 窗口背景
        self._apply_window_bg()
        # 标题栏文字
        if hasattr(self, '_title_label'):
            self._title_label.setStyleSheet(f"color: {self._c(C.COLOR_TITLE_TEXT)};")
        # 分类标签
        self._update_tab_styles()
        # 状态文字
        if hasattr(self, 'status_label'):
            self.status_label.setStyleSheet(f"color: {self._c(C.COLOR_STATUS_TEXT)};")

        # 卡片：清缓存重建（图标需按新主题重新提取）
        self._card_cache.clear()
        self._refresh_grid()

        # 已打开的文件夹窗口
        for win in list(self._folder_windows.values()):
            try:
                import shiboken6
                if shiboken6.isValid(win) and hasattr(win, 'apply_theme'):
                    win.apply_theme()
            except Exception as e:
                logger.debug(f"刷新文件夹窗口主题失败: {e}")

        # 已打开的模态弹窗（设置/分类管理/已扫描应用）
        for dlg in list(self._open_dialogs):
            try:
                import shiboken6
                if shiboken6.isValid(dlg) and hasattr(dlg, 'apply_theme'):
                    dlg.apply_theme()
            except Exception as e:
                logger.debug(f"刷新弹窗主题失败: {e}")

        # 托盘菜单
        if hasattr(self, 'tray') and self.tray is not None:
            try:
                self.tray.apply_theme()
            except Exception as e:
                logger.debug(f"刷新托盘菜单主题失败: {e}")

        # 标题栏颜色 + 亚克力
        window_effects.set_titlebar_color(self, self.dark)
        window_effects.apply_acrylic(self, self.config.alpha)
        window_effects.extend_frame_into_client(self)
        # WA_NoSystemBackground 下需强制重绘，否则背景色不刷新
        self._central.update()
        self._central.repaint()
        self.update()
        self.repaint()

    # ------------------------------------------------------------
    # UI 组装
    # ------------------------------------------------------------
    def _setup_ui(self):
        """组装主界面"""
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        self._central = central
        self._apply_window_bg()

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._setup_title_bar(layout)
        self._setup_tabs(layout)
        self._setup_grid(layout)
        self._setup_status_bar(layout)

    def _apply_window_bg(self):
        """窗口背景完全透明，让 DWM 亚克力填充

        纯亚克力方案下，Qt 不绘制任何窗口背景色，
        背景完全由 DWM 的扩展框架（亚克力）提供。
        子控件（卡片、标签栏）各自保持不透明背景。
        """
        self._central.setStyleSheet(
            f"#central {{ background: transparent; }}"
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: transparent; }}"
            f"QScrollArea > QWidget {{ background: transparent; }}"
            f"QWidget#gridContainer {{ background: transparent; }}"
        )

    def _setup_title_bar(self, parent_layout):
        """标题栏"""
        frame = QWidget()
        frame.setFixedHeight(36)
        fl = QHBoxLayout(frame)
        fl.setContentsMargins(16, 12, 16, 4)

        label = QLabel(C.WINDOW_TITLE)
        font = QFont(C.FONT_FAMILY, C.FONT_TITLE_SIZE)
        font.setBold(True)
        label.setFont(font)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"color: {self._c(C.COLOR_TITLE_TEXT)};")
        fl.addWidget(label, 1)
        self._title_label = label

        parent_layout.addWidget(frame)

    def _setup_tabs(self, parent_layout):
        """分类标签栏"""
        outer = QWidget()
        ol = QHBoxLayout(outer)
        ol.setContentsMargins(12, 8, 12, 8)
        ol.setSpacing(0)

        inner = QWidget()
        il = QHBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(C.TAB_SPACING)

        self._tab_buttons = {}
        for cat in self.config.categories:
            btn = QPushButton(cat)
            btn.setFixedSize(C.TAB_WIDTH, C.TAB_HEIGHT)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, c=cat: self._switch_category(c))
            il.addWidget(btn)
            self._tab_buttons[cat] = btn

        ol.addStretch(1)
        ol.addWidget(inner)
        ol.addStretch(1)
        parent_layout.addWidget(outer)

        self._tabs_outer = outer
        self._tabs_layout = parent_layout
        self._update_tab_styles()

    def _setup_tabs_refresh(self):
        """分类变化后重建标签栏"""
        # 移除旧标签栏
        if hasattr(self, '_tabs_outer'):
            self._tabs_outer.setParent(None)
        # 重建（插入到网格之前）
        idx = self._tabs_layout.indexOf(self.scroll)
        new_outer = QWidget()
        ol = QHBoxLayout(new_outer)
        ol.setContentsMargins(12, 8, 12, 8)
        ol.setSpacing(0)
        inner = QWidget()
        il = QHBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(C.TAB_SPACING)
        self._tab_buttons = {}
        for cat in self.config.categories:
            btn = QPushButton(cat)
            btn.setFixedSize(C.TAB_WIDTH, C.TAB_HEIGHT)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, c=cat: self._switch_category(c))
            il.addWidget(btn)
            self._tab_buttons[cat] = btn
        ol.addStretch(1)
        ol.addWidget(inner)
        ol.addStretch(1)
        self._tabs_layout.insertWidget(idx, new_outer)
        self._tabs_outer = new_outer
        self._update_tab_styles()
        self._refresh_grid()

    def _update_tab_styles(self):
        """更新分类标签配色"""
        for cat, btn in self._tab_buttons.items():
            active = (cat == self.config.current_category)
            if active:
                bg = self._c(C.COLOR_TAB_ACTIVE_BG)
                fg = self._c(C.COLOR_TAB_ACTIVE_FG)
            else:
                bg = self._c(C.COLOR_TAB_INACTIVE_BG)
                fg = self._c(C.COLOR_TAB_INACTIVE_FG)
            btn.setStyleSheet(
                f"QPushButton {{"
                f" background-color: {bg}; color: {fg};"
                f" border: none; border-radius: {C.TAB_CORNER_RADIUS}px;"
                f" font-family: '{C.FONT_FAMILY}'; font-size: {C.FONT_TAB_SIZE}px;"
                f"}}"
            )

    def _setup_grid(self, parent_layout):
        """应用网格区"""
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self.scroll.setContextMenuPolicy(Qt.CustomContextMenu)
        self.scroll.customContextMenuRequested.connect(self._on_blank_right_clicked)

        self.grid_container = QWidget()
        self.grid_container.setObjectName("gridContainer")
        self.grid_container.setStyleSheet("background: transparent;")
        self.grid_container.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid_container.customContextMenuRequested.connect(self._on_blank_right_clicked)
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(8, 10, 8, 10)
        self.grid_layout.setSpacing(C.GRID_PADDING)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.scroll.setWidget(self.grid_container)
        parent_layout.addWidget(self.scroll, 1)

        # 拖放支持
        self.setAcceptDrops(True)

    def _setup_status_bar(self, parent_layout):
        """底部状态栏（仅保留状态提示，按钮已移至右键菜单）"""
        frame = QWidget()
        fl = QHBoxLayout(frame)
        fl.setContentsMargins(16, 0, 16, 8)

        fl.addStretch(1)

        self.status_label = QLabel("")
        self.status_label.setFont(QFont(C.FONT_FAMILY, C.FONT_STATUS_SIZE))
        self.status_label.setStyleSheet(f"color: {self._c(C.COLOR_STATUS_TEXT)};")
        fl.addWidget(self.status_label)

        parent_layout.addWidget(frame)

    # ------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------
    def _switch_category(self, category: str):
        """切换分类"""
        if category == self.config.current_category:
            return
        self.config.current_category = category
        self._update_tab_styles()
        self._refresh_grid()
        logger.debug(f"切换到分类: {category}")

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

    def _refresh_grid(self):
        """刷新当前分类的应用网格"""
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

        # 布局（固定 9 列，卡片居中）
        for i, card in enumerate(cards):
            row, col = divmod(i, C.GRID_COLUMNS)
            self.grid_layout.addWidget(card, row, col, Qt.AlignCenter)
            card.show()

        # 异步加载图标
        theme = "dark" if self.dark else "light"
        for card in cards:
            self.icon_loader.load(card.app_data, size=C.ICON_SIZE,
                                  is_folder=card.is_folder, theme=theme)

    def _on_icon_ready(self, app_data: dict, pixmap):
        """普通应用图标就绪"""
        import shiboken6
        # 主窗口卡片
        for cards in self._card_cache.values():
            for card in cards:
                if card.app_data is app_data and shiboken6.isValid(card):
                    card.set_icon(pixmap)
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

    # ------------------------------------------------------------
    # 卡片交互
    # ------------------------------------------------------------
    def _on_card_clicked(self, app_data: dict):
        """单击卡片：启动应用或打开文件夹"""
        if app_data.get("type") == "folder":
            self._open_folder(app_data)
            return
        path = app_data.get("path", "")
        if path and os.path.exists(path):
            try:
                os.startfile(path)
                logger.debug(f"启动应用: {path}")
            except Exception as e:
                logger.warning(f"启动失败 {path}: {e}")
                self.show_message(f"启动失败: {app_data.get('name')}")
        else:
            self.show_message(f"文件不存在: {app_data.get('name')}")

    def _open_folder(self, folder_data: dict):
        """打开文件夹弹窗（单例）"""
        from ui.folder_window import FolderWindow
        key = f"{self.config.current_category}_{folder_data.get('name')}"
        win = self._folder_windows.get(key)
        if win is not None:
            try:
                win.show()
                win.raise_()
                win.activateWindow()
                return
            except RuntimeError:
                self._folder_windows.pop(key, None)

        win = FolderWindow(self, folder_data, self.dark)
        self._folder_windows[key] = win
        win.show()
        logger.debug(f"打开文件夹: {folder_data.get('name')}")

    def _on_card_right_clicked(self, app_data: dict, pos):
        """右键卡片：弹出菜单"""
        from ui import context_menu
        handlers = {
            "launch": self._launch_app,
            "launch_admin": self._launch_as_admin,
            "categories": self.config.categories,
            "move_category": self._move_app_to_category,
            "folders": self.config.get_folders(self.config.current_category),
            "move_to_folder": self._move_app_to_folder,
            "create_folder": self._create_folder_with_app,
            "in_folder": False,
            "change_icon": self._change_icon,
            "rename": self._rename_app,
            "delete_app": self._delete_app,
            "clear_category": self._clear_category,
            "open_location": self._open_file_location,
            "properties": self._show_properties,
            "settings": self._open_settings,
        }
        if app_data.get("type") == "folder":
            menu = context_menu.build_folder_menu(self, app_data, self.dark, {
                "open_folder": self._open_folder,
                "rename_folder": self._rename_folder,
                "delete_folder": self._delete_folder,
            })
        else:
            menu = context_menu.build_app_menu(self, app_data, self.dark, handlers)
        menu.exec(pos)

    def _on_card_drag_released(self, app_data: dict, pos):
        """拖拽释放：检测是否落在文件夹卡片上"""
        target = self.childAt(self.mapFromGlobal(pos))
        if isinstance(target, AppCard) and target.is_folder:
            self._move_app_to_folder(app_data, target.app_data)
            logger.debug(f"移动 {app_data.get('name')} 到文件夹 {target.app_data.get('name')}")

    # ------------------------------------------------------------
    # 应用操作
    # ------------------------------------------------------------
    def _launch_app(self, app_data: dict):
        """启动应用"""
        path = app_data.get("path", "")
        if path and os.path.exists(path):
            try:
                os.startfile(path)
                logger.debug(f"启动应用: {path}")
            except Exception as e:
                logger.warning(f"启动失败 {path}: {e}")
                self.show_message(f"启动失败: {app_data.get('name')}")
        else:
            self.show_message(f"文件不存在: {app_data.get('name')}")

    def _launch_as_admin(self, app_data: dict):
        """管理员身份启动"""
        path = app_data.get("path", "")
        if not path:
            return
        try:
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(None, "runas", path, None, None, 1)
            logger.debug(f"管理员启动: {path}")
        except Exception as e:
            logger.warning(f"管理员启动失败: {e}")
            self.show_message("管理员启动失败")

    def _move_app_to_category(self, app_data: dict, category: str):
        """移动应用到其他分类"""
        cur = self.config.current_category
        if category == cur:
            return
        self.config.remove_app(cur, app_data)
        self.config.add_app(category, app_data)
        self.config.save()
        self._card_cache.pop(cur, None)
        self._refresh_grid()
        self.show_message(f"已移动到 {category}")

    def _move_app_to_folder(self, app_data: dict, folder: dict):
        """移动应用到文件夹"""
        cur = self.config.current_category
        self.config.remove_app(cur, app_data)
        folder.setdefault("apps", []).append(app_data)
        self.config.save()
        self._card_cache.pop(cur, None)
        self._refresh_grid()
        self.show_message(f"已移动到 {folder.get('name')}")

    def _create_folder_with_app(self, app_data: dict):
        """新建文件夹并移入应用"""
        from PySide6.QtWidgets import QInputDialog
        folders = self.config.get_folders(self.config.current_category)
        default = f"文件夹{len(folders) + 1}"
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称:", text=default)
        if not ok or not name.strip():
            return
        folder = {"type": "folder", "name": name.strip(), "apps": []}
        cur = self.config.current_category
        self.config.remove_app(cur, app_data)
        folder["apps"].append(app_data)
        self.config.app_config.setdefault(cur, []).append(folder)
        self.config.save()
        self._card_cache.pop(cur, None)
        self._refresh_grid()
        self.show_message(f"已创建文件夹 {name}")

    def _change_icon(self, app_data: dict):
        """更换图标"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "选择图标", "", "图标文件 (*.ico *.png)")
        if not path:
            return
        app_data["icon_path"] = path
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message("图标已更换")

    def _rename_app(self, app_data: dict):
        """重命名应用"""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=app_data.get("name", ""))
        if not ok or not name.strip():
            return
        app_data["name"] = name.strip()
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message("已重命名")

    def _delete_app(self, app_data: dict):
        """删除应用"""
        from PySide6.QtWidgets import QMessageBox
        ret = QMessageBox.question(
            self, "删除应用",
            f"确定要删除「{app_data.get('name')}」吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        self.config.remove_app(self.config.current_category, app_data)
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message("已删除")

    def _clear_category(self):
        """清空当前分类"""
        from PySide6.QtWidgets import QMessageBox
        cat = self.config.current_category
        ret = QMessageBox.question(
            self, "清空分类",
            f"确定要清空「{cat}」的所有应用吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        self.config.app_config[cat] = []
        self.config.save()
        self._card_cache.pop(cat, None)
        self._refresh_grid()
        self.show_message("已清空")

    def _open_file_location(self, app_data: dict):
        """打开文件位置"""
        path = app_data.get("path", "")
        if not path:
            return
        try:
            if os.path.isdir(path):
                os.startfile(path)
            else:
                import subprocess
                subprocess.Popen(f'explorer /select,"{path}"')
        except Exception as e:
            logger.warning(f"打开位置失败: {e}")

    def _show_properties(self, app_data: dict):
        """显示属性"""
        path = app_data.get("path", "")
        if not path:
            return
        try:
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(None, "properties", path, None, None, 1)
        except Exception as e:
            logger.warning(f"显示属性失败: {e}")

    def _rename_folder(self, app_data: dict):
        """重命名文件夹"""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "重命名文件夹", "新名称:",
                                        text=app_data.get("name", ""))
        if not ok or not name.strip():
            return
        app_data["name"] = name.strip()
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message("文件夹已重命名")

    def _delete_folder(self, app_data: dict):
        """删除文件夹（内部应用移回主分类）"""
        from PySide6.QtWidgets import QMessageBox
        ret = QMessageBox.question(
            self, "删除文件夹",
            f"确定要删除文件夹「{app_data.get('name')}」吗？\n内部应用将移回当前分类。",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return
        cat = self.config.current_category
        apps = self.config.app_config.get(cat, [])
        if app_data in apps:
            apps.remove(app_data)
        for a in app_data.get("apps", []):
            apps.append(a)
        self.config.save()
        self._card_cache.pop(cat, None)
        self._refresh_grid()
        self.show_message("文件夹已删除")

    def _on_add_app(self):
        """添加应用（文件选择）"""
        from PySide6.QtWidgets import QFileDialog
        from services.app_info import get_app_info
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择应用", os.environ.get("PROGRAMFILES", ""),
            "可执行文件 (*.exe *.lnk *.bat *.cmd);;所有文件 (*.*)"
        )
        if not paths:
            return
        added = 0
        for path in paths:
            info = get_app_info(path)
            if self.config.add_app(self.config.current_category, info):
                added += 1
        if added:
            self.config.save()
            self._card_cache.pop(self.config.current_category, None)
            self._refresh_grid()
        self.show_message(f"已添加 {added} 个应用")

    def _open_settings(self):
        """打开设置面板"""
        from ui.dialogs import SettingsDialog
        dlg = SettingsDialog(self)
        self.register_dialog(dlg)
        dlg.exec()

    def register_dialog(self, dlg):
        """登记模态弹窗，主题变化时同步刷新；关闭后自动移除"""
        self._open_dialogs.append(dlg)
        dlg.finished.connect(lambda _=0, d=dlg: self._unregister_dialog(d))

    def _unregister_dialog(self, dlg):
        try:
            self._open_dialogs.remove(dlg)
        except ValueError:
            pass

    def show_message(self, text: str, duration_ms: int = 3000):
        """底部状态提示"""
        self.status_label.setText(text)
        QTimer.singleShot(duration_ms, lambda: self.status_label.setText(""))

    # ------------------------------------------------------------
    # 空白处右键菜单
    # ------------------------------------------------------------
    def _on_blank_right_clicked(self, pos):
        """空白处右键：新建菜单"""
        from ui import context_menu
        menu = context_menu.build_blank_menu(self, self.dark, {
            "new_folder": self._new_folder,
            "new_txt": lambda: self._create_new_file("txt"),
            "new_docx": lambda: self._create_new_file("docx"),
            "new_xlsx": lambda: self._create_new_file("xlsx"),
            "new_pptx": lambda: self._create_new_file("pptx"),
            "add_app": self._on_add_app,
            "settings": self._open_settings,
        })
        global_pos = self.sender().mapToGlobal(pos) if self.sender() else self.mapToGlobal(pos)
        menu.exec(global_pos)

    def _new_folder(self):
        """新建空文件夹"""
        from PySide6.QtWidgets import QInputDialog
        folders = self.config.get_folders(self.config.current_category)
        default = f"文件夹{len(folders) + 1}"
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称:", text=default)
        if not ok or not name.strip():
            return
        folder = {"type": "folder", "name": name.strip(), "apps": []}
        self.config.app_config.setdefault(self.config.current_category, []).append(folder)
        self.config.save()
        self._card_cache.pop(self.config.current_category, None)
        self._refresh_grid()
        self.show_message(f"已创建文件夹 {name}")

    def _create_new_file(self, kind: str):
        """在桌面新建文件并加入当前分类"""
        import time
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        ts = time.strftime("%Y%m%d_%H%M%S")
        ext_map = {"txt": ".txt", "docx": ".docx", "xlsx": ".xlsx", "pptx": ".pptx"}
        name_map = {"txt": "新建文本文档", "docx": "新建文档", "xlsx": "新建表格", "pptx": "新建演示"}
        filename = f"{name_map[kind]}_{ts}{ext_map[kind]}"
        path = os.path.join(desktop, filename)
        try:
            if kind == "txt":
                open(path, "w", encoding="utf-8").close()
            else:
                # 尝试用 Office COM 创建，失败则建空文件
                try:
                    import win32com.client
                    app_map = {"docx": "Word.Application", "xlsx": "Excel.Application",
                               "pptx": "PowerPoint.Application"}
                    app = win32com.client.Dispatch(app_map[kind])
                    if kind == "docx":
                        doc = app.Documents.Add()
                        doc.SaveAs(path)
                        doc.Close()
                    elif kind == "xlsx":
                        wb = app.Workbooks.Add()
                        wb.SaveAs(path)
                        wb.Close()
                    else:
                        pres = app.Presentations.Add()
                        pres.SaveAs(path)
                        pres.Close()
                    app.Quit()
                except Exception:
                    open(path, "w", encoding="utf-8").close()
            self.config.add_app(self.config.current_category,
                                {"name": filename, "path": path,
                                 "original_path": path, "icon_path": None})
            self.config.save()
            self._card_cache.pop(self.config.current_category, None)
            self._refresh_grid()
            self.show_message(f"已创建 {filename}")
        except Exception as e:
            logger.warning(f"新建文件失败: {e}")
            self.show_message("新建文件失败")

    # ------------------------------------------------------------
    # 拖放（外部文件拖入）
    # ------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """处理拖入的文件"""
        from services.app_info import get_app_info
        added, skipped = 0, 0
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path or os.path.isdir(path):
                continue
            info = get_app_info(path)
            if self.config.add_app(self.config.current_category, info):
                added += 1
            else:
                skipped += 1
        if added:
            self.config.save()
            self._card_cache.pop(self.config.current_category, None)
            self._refresh_grid()
        msg = f"已添加 {added} 个应用"
        if skipped:
            msg += f"，跳过 {skipped} 个重复"
        self.show_message(msg)
        event.acceptProposedAction()

    def closeEvent(self, event):
        """关闭时：最小化到任务栏（若启用），否则退出

        用 showMinimized() 而非 hide()，让窗口真正最小化到任务栏，
        这样点击任务栏图标恢复时是 Windows 原生动画。
        """
        # 正在退出流程中，直接放行
        if getattr(self, '_quitting', False):
            event.accept()
            return
        minimize = getattr(self.config, 'minimize_to_tray', True)
        logger.debug(f"[CLOSE] minimize={minimize} visible={self.isVisible()}")
        if minimize:
            event.ignore()
            self.showMinimized()
            logger.debug("窗口已最小化到任务栏")
        else:
            event.accept()
            self._force_quit()

    def changeEvent(self, event):
        """窗口状态变化：最小化时暂停安装监控，恢复时继续"""
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            if not hasattr(self, 'install_monitor'):
                return
            if self.isMinimized():
                self.install_monitor.pause()
            else:
                self.install_monitor.resume()
