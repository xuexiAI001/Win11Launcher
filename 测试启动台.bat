@echo off
cd /d "%~dp0"
set LAUNCHER_ALLOW_MULTI_INSTANCE=1

echo ============================================================
echo  启动台 - Windows 开发机测试启动器 (多开调试版)
echo ------------------------------------------------------------
echo  已开启多开模式(LAUNCHER_ALLOW_MULTI_INSTANCE=1)，可绕过单实例
echo  限制反复重开/多开，专供 Windows 开发机测试 UI 与功能使用。
echo  正式入口(启动启动台Qt.bat / 打包exe)仍保持单实例。
echo ============================================================
echo.

python main.py

echo.
echo [启动台已退出] 若上方有 Traceback 即为运行期异常; 按任意键关闭...
pause