# -*- coding: utf-8 -*-
"""跨进程单实例：Windows 保持命名互斥体（main.py 原逻辑），Linux 用 QLocalServer。

Linux（麒麟）无 Win32 互斥体，改用 Qt 内置的 QLocalServer（Unix 域套接字），
零额外依赖，适合离线环境。第二个实例启动时向已有实例发送唤起请求后退出。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from core.logger import get_logger

logger = get_logger()

SERVER_NAME = "win11launcher_single_instance"


class LinuxSingleInstance(QObject):
    """Linux 单实例：其他实例请求唤起时发出 activated 信号"""

    activated = Signal()

    def __init__(self, name: str = SERVER_NAME):
        super().__init__()
        self.name = name
        self.server: QLocalServer | None = None

    def try_start(self) -> bool:
        """尝试成为唯一实例。

        Returns:
            True  = 本进程是唯一实例（已创建服务并保持监听）
            False = 已有实例在运行（已向其发送唤起请求，调用方应退出）
        """
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(150):
            # 已有实例：发送唤起请求
            try:
                socket.write(b"show")
                socket.flush()
                socket.waitForBytesWritten(150)
            except Exception as e:
                logger.debug(f"发送唤起请求失败: {e}")
            socket.disconnectFromServer()
            logger.debug("检测到已有实例，已发送唤起请求")
            return False

        # 清理上次进程崩溃可能残留的 socket 文件
        QLocalServer.removeServer(self.name)
        self.server = QLocalServer()
        if not self.server.listen(self.name):
            # 监听失败不阻断启动（退化为允许多实例，好于无法启动）
            logger.debug(f"QLocalServer 监听失败: {self.server.errorString()}")
            self.server = None
            return True
        self.server.newConnection.connect(self._on_new_connection)
        logger.debug("单实例服务已启动（QLocalServer）")
        return True

    def _on_new_connection(self):
        if self.server is None:
            return
        conn = self.server.nextPendingConnection()
        if conn is None:
            return
        try:
            conn.waitForReadyRead(150)
            conn.disconnectFromServer()
        except Exception:
            pass
        # 其他实例请求唤起：发信号，由主窗口响应
        self.activated.emit()
