# -*- coding: utf-8 -*-
"""拖放 Mixin：处理外部文件拖入窗口"""
import os

from core.logger import get_logger

logger = get_logger()


class DragDropMixin:
    """外部文件拖入窗口的处理（依赖 MainWindow 提供的方法/状态）"""

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
        from services.platform import get_app_info
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
