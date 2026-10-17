# -*- coding: utf-8 -*-
"""Linux 单实例（QLocalServer）测试：首个实例监听、次实例唤起、信号投递。

QLocalServer 在 Windows 上由命名管道实现，测试跨平台可运行。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from services.single_instance import LinuxSingleInstance


def _pump(ms: int = 300):
    """驱动事件循环，等待跨连接回调"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_first_instance_owns_server():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    si = LinuxSingleInstance("win11launcher_test_si")
    try:
        assert si.try_start() is True
        assert si.server is not None and si.server.isListening()
    finally:
        if si.server is not None:
            si.server.close()


def test_second_instance_signals_first():
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    name = "win11launcher_test_si_2"
    first = LinuxSingleInstance(name)
    assert first.try_start() is True

    received = []
    first.activated.connect(lambda: received.append(1))

    second = LinuxSingleInstance(name)
    assert second.try_start() is False   # 检测到已有实例
    assert second.server is None         # 次实例不起服务

    _pump()                              # 等待 first 收到连接
    assert received == [1]               # 唤起信号已投递

    first.server.close()


def test_restart_after_close():
    """首个实例关闭监听后，新实例可重新接管（无残留 socket 卡死）"""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    name = "win11launcher_test_si_3"
    a = LinuxSingleInstance(name)
    assert a.try_start() is True
    a.server.close()
    _pump(100)
    b = LinuxSingleInstance(name)
    assert b.try_start() is True
    b.server.close()
