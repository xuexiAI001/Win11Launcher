# -*- coding: utf-8 -*-
"""主题应用 Mixin：解析/预览/应用主题与窗口特效"""
from core import constants as C
from core.logger import get_logger
from ui import window_effects

logger = get_logger()


class ThemeApplyMixin:
    """主题解析、预览与整体应用（依赖 MainWindow 提供的方法/状态）"""

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
    # 窗口特效
    # ------------------------------------------------------------
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
