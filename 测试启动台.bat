@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   启动台 · Windows 开发机测试启动器
echo ------------------------------------------------------------
echo   本机运行的是「Windows 版本」：同一份源码，按 sys.platform 自动
echo   选择 Windows 后端（services/platform/_win）。你改麒麟代码时，
echo   Windows 后端不会被加载，因此这里测的是共用 UI / 功能。
echo   麒麟专属行为（.desktop 扫描 / UKUI / QLockFile 等）依赖 Linux
echo   API，只能在麒麟真机验证，Windows 上无法真正运行。
echo ============================================================
echo.

python main.py

echo.
echo [启动台已退出] 若上方有 Traceback 即为运行期异常；按任意键关闭本窗口...
pause >nul
