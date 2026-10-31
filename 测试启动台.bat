@echo off
cd /d "%~dp0"
set LAUNCHER_ALLOW_MULTI_INSTANCE=1

echo ============================================================
echo  启动台 - Windows 开发机测试启动器 (多开调试版)
echo ------------------------------------------------------------
echo  已开启多开模式，可绕过单实例限制反复重开/多开。
echo  固定使用系统 Python 3.14(带 PySide6)，避免命中 PATH 里
echo  未装 PySide6 的其他 python。
echo  正式入口(启动启动台Qt.bat / 打包exe)仍保持单实例。
echo ============================================================
echo.

rem 固定使用系统 Python 3.14（带 PySide6），勿改回裸 python（PATH 可能命中无 PySide6 的解释器）
"C:\Users\59260\AppData\Local\Programs\Python\Python314\python.exe" main.py

echo.
echo [启动台已退出] 若上方有 Traceback 即为运行期异常; 按任意键关闭...
pause