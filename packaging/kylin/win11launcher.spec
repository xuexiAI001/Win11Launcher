# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 - Linux（银河麒麟 V10 桌面版 / UKUI）

与根目录 Win11LauncherQt.spec（Windows 版）的差异：
  - 入口 main.py 在 Linux 上自动走 services.platform._linux 后端
    （.desktop 应用发现 / SVG 图标 / QLocalServer 单实例 / XDG 自启动），
    Windows 专有模块（icon_extractor / install_monitor / autostart 等）
    在麒麟上永远不会被 import，故一并排除以瘦身体积；
  - 排除 numpy（Linux 图标链路不用；仅 Windows 的 icon_extractor 需要）；
  - pynput 的 X11 后端是 importlib 动态加载的，静态分析不可见，
    必须在 hiddenimports 显式声明（否则打包后全局快捷键静默失效）；
  - Linux ELF 不支持内嵌图标（icon 参数仅 Windows 有效），桌面图标
    由 .deb 安装 hicolor 图标 + win11launcher.desktop 提供；
  - upx=False：麒麟机器未必安装 upx，且 Qt 库压缩后偶有兼容问题。

用法（在麒麟机器上，由 build_on_kylin.sh 调用）：
    pyinstaller --noconfirm --clean \
        --distpath <dist> --workpath <work> \
        packaging/kylin/win11launcher.spec
"""

import os

# spec 位于 <项目根>/packaging/kylin/，项目根向上两级。
# 不依赖 __file__（`python -m PyInstaller` 下 spec 命名空间可能未定义它）。
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

a = Analysis(
    ['main.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[(os.path.join(PROJECT_ROOT, 'assets'), 'assets')],
    hiddenimports=[
        # —— 本项目惰性 / 条件 import（静态分析不可见）——
        'PySide6.QtSvg',            # linux_icons.py 函数内 import（SVG 图标渲染）
        'PySide6.QtNetwork',        # single_instance.py（QLocalServer 单实例）
        'services.platform._linux',
        'services.platform.linux_apps',
        'services.platform.linux_icons',
        'services.platform.linux_autostart',
        'services.single_instance',
        'services.folder_icon',
        'services.icon_loader',
        'services.hotkey',
        # —— pynput：后端经 importlib.import_module 动态选择，需显式声明 ——
        'pynput', 'pynput.keyboard', 'pynput.keyboard._xorg',
        'pynput._util.xorg', 'pynput._util.xorg_keysyms',
        'Xlib', 'Xlib.display', 'Xlib.ext', 'Xlib.ext.xtest',
        'Xlib.X', 'Xlib.XK', 'Xlib.protocol', 'Xlib.threaded',
        # Xlib.XK.load_keysym_group 用 __import__ 动态加载全部 keysymdef 分组，
        # 静态分析不可见；漏一个则 import pynput.keyboard 直接失败（快捷键静默失效）
        'Xlib.keysymdef.apl', 'Xlib.keysymdef.arabic', 'Xlib.keysymdef.cyrillic',
        'Xlib.keysymdef.greek', 'Xlib.keysymdef.hebrew', 'Xlib.keysymdef.katakana',
        'Xlib.keysymdef.korean', 'Xlib.keysymdef.latin1', 'Xlib.keysymdef.latin2',
        'Xlib.keysymdef.latin3', 'Xlib.keysymdef.latin4', 'Xlib.keysymdef.miscellany',
        'Xlib.keysymdef.publishing', 'Xlib.keysymdef.special',
        'Xlib.keysymdef.technical', 'Xlib.keysymdef.thai', 'Xlib.keysymdef.xf86',
        'Xlib.keysymdef.xk3270', 'Xlib.keysymdef.xkb',
        'six', 'six.moves',
        # —— UI 模块（main.py 静态链可达，显式声明与 Windows spec 对齐）——
        'ui.window_effects', 'ui.app_card', 'ui.folder_window',
        'ui.context_menu', 'ui.dialogs', 'ui.tray', 'ui.main_window',
        'ui.behaviors.theme_watcher', 'ui.behaviors.system_integration',
        'ui.behaviors.theme', 'ui.behaviors.ui_builder', 'ui.behaviors.grid',
        'ui.behaviors.app_ops', 'ui.behaviors.context_menus',
        'ui.behaviors.dragdrop', 'ui.behaviors.window_events',
        'ui.behaviors.zoom',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Linux 不需要 / 未安装的包（避免 missing-module 噪音与体积）
        'numpy', 'scipy', 'matplotlib', 'pandas', 'tkinter',
        'winreg', 'win32gui', 'win32com', 'win32api', 'win32con',
        'pythoncom', 'pywintypes', 'pywin32',
        # 未使用的大型 Qt 模块（Essentials 轮子内置，排除可显著瘦身）
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.Qt3DCore', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DQuick',
        'PySide6.Qt3DRender', 'PySide6.QtMultimedia', 'PySide6.QtQuick',
        'PySide6.QtQml', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
    ],
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
    upx=False,                    # 麒麟机器未必有 upx；Qt 库压缩有兼容风险
    console=False,                # GUI 程序，不弹终端
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 注意：不设 icon —— Linux ELF 无法内嵌图标；
    #       桌面图标由 .deb 的 hicolor 图标提供。
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Win11Launcher',
)
