# -*- mode: python ; coding: utf-8 -*-
import os
import sys

PY = r'C:\Users\59260\AppData\Local\Programs\Python\Python314'

# 手动收集 tkinter 包
tkinter_datas = []
tk_src = os.path.join(PY, 'Lib', 'tkinter')
for root, dirs, files in os.walk(tk_src):
    for f in files:
        if f.endswith('.py'):
            src = os.path.join(root, f)
            rel = os.path.relpath(src, os.path.dirname(tk_src))
            tkinter_datas.append((src, os.path.dirname(rel)))

# tcl/tk 数据文件
tcl_datas = [
    (os.path.join(PY, 'tcl', 'tcl8.6'), '_tcl_data/tcl8.6'),
    (os.path.join(PY, 'tcl', 'tk8.6'), '_tk_data/tk8.6'),
]

# tcl/tk DLL
tcl_binaries = [
    (os.path.join(PY, 'DLLs', '_tkinter.pyd'), '.'),
    (os.path.join(PY, 'DLLs', 'tcl86t.dll'), '.'),
    (os.path.join(PY, 'DLLs', 'tk86t.dll'), '.'),
]

a = Analysis(
    ['main_ui.py'],
    pathex=[],
    binaries=tcl_binaries,
    datas=[('assets', 'assets')] + tkinter_datas + tcl_datas,
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.constants', 'tkinter.font',
                   'tkinter.messagebox', 'tkinter.filedialog', 'tkinter.simpledialog',
                   'tkinter.colorchooser', 'tkinter.scrolledtext', '_tkinter', 'tkinterdnd2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'scipy', 'matplotlib', 'pandas', 'PIL._avif', 'PIL._webp', 'unittest', 'pydoc'],
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
