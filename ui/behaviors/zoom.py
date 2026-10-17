# -*- coding: utf-8 -*-
"""界面缩放 Mixin：Ctrl+滚轮 / 设置滑块整体缩放 + 窗口最大化/全屏。

设计：
  - 缩放经 core.constants.set_scale 统一重算全部尺寸/字号常量，随后重建
    中央界面；默认 1.0 与历史版本逐像素一致（Windows 版零行为变化）。
  - 最大化/全屏按钮与 F11/Esc 快捷键仅在 Linux（麒麟）提供——
    Windows 版保持原有固定尺寸居中外观，标题栏不加按钮。
  - 最大化/全屏时网格列数随窗口宽度自适应，避免大窗口下内容稀疏居中。
"""

from PySide6.QtCore import Qt, QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

from core import constants as C
from core.logger import get_logger
from services.platform import IS_LINUX

logger = get_logger()

# Qt 的 QWIDGETSIZE_MAX（部分 PySide6 版本未从 QtWidgets 导出）
_WIDGET_SIZE_MAX = 16777215


class _WheelZoomFilter(QObject):
    """应用级滚轮事件过滤器：Ctrl+滚轮 → 主窗口整体缩放。

    必须是独立 QObject 子类：PySide 只为在自身 dict 中重写虚函数的类生成
    虚拟分派 trampoline——Mixin 继承来的 eventFilter 会被 MRO 中更靠前的
    QObject.eventFilter 遮蔽（QObject 在第 3 位、Mixin 在第 16 位，已验证），
    故按官方文档模式使用专用过滤器对象。
    """

    def __init__(self, window):
        super().__init__()
        self._window = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and (event.modifiers() & Qt.ControlModifier):
            w = obj if isinstance(obj, QWidget) else None
            try:
                same_window = w is not None and w.window() is self._window
            except RuntimeError:
                same_window = False
            if same_window:
                dy = event.angleDelta().y()
                if dy:
                    self._window.adjust_zoom(C.UI_SCALE_STEP if dy > 0 else -C.UI_SCALE_STEP)
                event.accept()
                return True
        return False


class ZoomMixin:
    """整体 UI 缩放与窗口状态控制（依赖 MainWindow 提供的方法/状态）"""

    def _setup_zoom(self):
        """安装应用级滚轮事件过滤（仅响应带 Ctrl 且作用于主窗口的滚轮）"""
        # 持引用防止被 GC；随窗口销毁时 Qt 自动移除该过滤器
        self._wheel_filter = _WheelZoomFilter(self)
        QApplication.instance().installEventFilter(self._wheel_filter)

    # ------------------------------------------------------------
    # 缩放
    # ------------------------------------------------------------
    def adjust_zoom(self, delta: float):
        """按步进增减缩放（自动夹取到 [UI_SCALE_MIN, UI_SCALE_MAX]）"""
        target = round(C.get_scale() + delta, 2)
        target = min(max(target, C.UI_SCALE_MIN), C.UI_SCALE_MAX)
        if abs(target - C.get_scale()) < 1e-6:
            return
        self.set_zoom(target)

    def set_zoom(self, factor: float, persist: bool = True):
        """应用指定缩放系数：重算常量 → 重建界面（persist=False 时不写配置，供设置面板预览）"""
        factor = min(max(float(factor), C.UI_SCALE_MIN), C.UI_SCALE_MAX)
        C.set_scale(factor)
        if persist:
            self.config.ui_scale = factor
            self.config.save()
        self._rebuild_for_zoom()
        if persist:
            self.show_message(f"界面缩放 {int(round(factor * 100))}%")

    def _rebuild_for_zoom(self):
        """按新缩放重建界面"""
        # 最大化/全屏状态下先恢复常态，避免固定尺寸约束冲突
        if self.isMaximized() or self.isFullScreen():
            self.showNormal()
        # 关闭文件夹窗口（其尺寸基于旧缩放；重新打开时按新缩放构建）
        for win in list(getattr(self, "_folder_windows", {}).values()):
            try:
                win.close()
            except Exception:
                pass
        self._folder_windows.clear()
        # 卡片缓存全部作废（卡片固定尺寸在构造时确定）
        self._card_cache.clear()
        # 重建中央界面（标题栏 / 标签栏 / 网格 / 状态栏）
        self._setup_ui()
        # 窗口尺寸随缩放等比变化，并保持居中
        self.setFixedSize(C.WINDOW_WIDTH, C.WINDOW_HEIGHT)
        self._center_window()
        self._apply_effects()
        self._refresh_grid()
        self._update_window_buttons()

    # ------------------------------------------------------------
    # 窗口状态（最大化 / 全屏）——仅 Linux 提供入口
    # ------------------------------------------------------------
    def toggle_maximize(self):
        """最大化 / 还原切换"""
        if self.isMaximized():
            self.showNormal()
            self.setFixedSize(C.WINDOW_WIDTH, C.WINDOW_HEIGHT)
            self._center_window()
        else:
            # frameless 窗口：先解除固定尺寸约束再最大化
            self.setFixedSize(_WIDGET_SIZE_MAX, _WIDGET_SIZE_MAX)
            self.showMaximized()
        self._update_window_buttons()
        self._refresh_grid()

    def toggle_fullscreen(self):
        """全屏 / 退出全屏切换"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self._update_window_buttons()
        self._refresh_grid()

    def _update_window_buttons(self):
        """同步标题栏按钮文字与窗口状态"""
        btn_max = getattr(self, "_btn_maximize", None)
        if btn_max is not None:
            btn_max.setText("还原" if self.isMaximized() else "最大化")
        btn_full = getattr(self, "_btn_fullscreen", None)
        if btn_full is not None:
            btn_full.setText("退出全屏" if self.isFullScreen() else "全屏")

    def keyPressEvent(self, event):
        if IS_LINUX:
            if event.key() == Qt.Key_F11:
                self.toggle_fullscreen()
                return
            if event.key() == Qt.Key_Escape and self.isFullScreen():
                self.showNormal()
                self._update_window_buttons()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 最大化/全屏时网格按窗口宽度重排列数（仅在实际列数变化时刷新）
        cols = self._effective_columns()
        if cols != getattr(self, "_cur_cols", None):
            self._cur_cols = cols
            self._refresh_grid()
