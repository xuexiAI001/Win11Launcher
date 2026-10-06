# -*- coding: utf-8 -*-
"""
模块名：services.icon_loader
职责：图标异步加载——QThreadPool 封装，PIL Image → QPixmap 转换
依赖：services.icon_extractor, services.folder_icon, core.logger
"""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

import threading

from services.icon_extractor import get_app_icon
from services.folder_icon import get_cached_folder_icon
from core.logger import get_logger

logger = get_logger()

# PIL 的 Image.load()/copy()/floodfill 在多线程并发 + GC 时不是线程安全的，
# 会触发 C 层访问违规（0xC0000005）导致进程闪退。
# 用全局锁把所有 PIL 图像处理串行化，彻底规避该问题。
_PIL_LOCK = threading.RLock()


def pil_to_qpixmap(pil_image) -> QPixmap:
    """PIL Image (RGBA) → QPixmap"""
    if pil_image is None:
        return QPixmap()
    try:
        if pil_image.mode != "RGBA":
            pil_image = pil_image.convert("RGBA")
        data = pil_image.tobytes("raw", "RGBA")
        qimg = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)
        # 必须 copy，否则 data 释放后图像损坏
        return QPixmap.fromImage(qimg.copy())
    except Exception as e:
        logger.debug(f"PIL 转 QPixmap 失败: {e}")
        return QPixmap()


class _IconTask(QRunnable):
    """图标加载任务"""

    class Signals(QObject):
        done = Signal(object, QPixmap)   # (app_data, pixmap)
        folder_done = Signal(object, QPixmap)

    def __init__(self, app_data: dict, size: int, is_folder: bool, theme: str):
        super().__init__()
        # 禁止 Qt 自动删除：跨线程信号可能仍在事件队列中，
        # 若 C++ 对象被提前释放，投递时会访问已释放对象导致崩溃
        self.setAutoDelete(False)
        self.app_data = app_data
        self.size = size
        self.is_folder = is_folder
        self.theme = theme
        self.signals = _IconTask.Signals()

    @Slot()
    def run(self):
        try:
            # 所有 PIL 操作必须在锁内串行执行，避免多线程并发导致访问违规
            with _PIL_LOCK:
                if self.is_folder:
                    apps = self.app_data.get("apps", [])
                    pil = get_cached_folder_icon(apps, size=64, theme=self.theme)
                    if pil is not None:
                        pil = pil.resize((self.size, self.size))
                    pixmap = pil_to_qpixmap(pil)
                else:
                    path = self.app_data.get("path", "")
                    icon_path = self.app_data.get("icon_path")
                    original_path = self.app_data.get("original_path")
                    pil = get_app_icon(path, icon_path, size=self.size, original_path=original_path)
                    pixmap = pil_to_qpixmap(pil)
            # 信号发射放在锁外，避免阻塞其他任务
            if self.is_folder:
                self.signals.folder_done.emit(self.app_data, pixmap)
            else:
                self.signals.done.emit(self.app_data, pixmap)
        except Exception as e:
            logger.debug(f"图标加载任务失败: {e}")


class IconLoader(QObject):
    """图标异步加载器（全局单例）"""

    icon_ready = Signal(object, QPixmap)         # 普通应用图标就绪
    folder_icon_ready = Signal(object, QPixmap)  # 文件夹预览图就绪

    def __init__(self, max_workers: int = 1):
        super().__init__()
        self.pool = QThreadPool()
        # 必须单线程：PIL 的 Image 在 C 层持有缓冲区，
        # 多线程并发 + Python GC 回收会触发访问违规（0xC0000005）导致闪退。
        # 图标加载为 IO 密集型，单线程足够，且不阻塞 Qt 主线程。
        self.pool.setMaxThreadCount(1)
        # 持有运行中的任务引用，防止 Python GC 提前回收
        self._tasks: set = set()

    def load(self, app_data: dict, size: int = 48, is_folder: bool = False, theme: str = "light"):
        """提交图标加载任务"""
        task = _IconTask(app_data, size, is_folder, theme)
        task.signals.done.connect(self.icon_ready)
        task.signals.folder_done.connect(self.folder_icon_ready)
        # 任务完成后从集合移除，允许回收
        task.signals.done.connect(lambda *_: self._tasks.discard(task))
        task.signals.folder_done.connect(lambda *_: self._tasks.discard(task))
        self._tasks.add(task)
        self.pool.start(task)

    def shutdown(self):
        """等待所有任务完成"""
        self.pool.waitForDone(3000)
        self._tasks.clear()
