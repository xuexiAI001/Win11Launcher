# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 - Qt 版"""
import os
import sys

PY = r'C:\Users\59260\AppData\Local\Programs\Python\Python314'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'services.icon_extractor', 'services.app_info', 'services.folder_icon',
        'services.icon_loader', 'services.install_monitor', 'services.autostart',
        'services.hotkey', 'ui.window_effects', 'ui.app_card', 'ui.folder_window',
        'ui.context_menu', 'ui.dialogs', 'ui.tray', 'ui.main_window',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'scipy', 'matplotlib', 'pandas', 'tkinter',
              'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.Qt3DCore', 'PySide6.QtMultimedia', 'PySide6.QtQuick',
              'PySide6.QtQml', 'PySide6.QtCharts', 'PySide6.QtDataVisualization'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Win11Launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Win11Launcher',
)
