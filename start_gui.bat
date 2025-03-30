@echo off
echo ===================================
echo Switch ROM 管理工具 - GUI界面
echo ===================================
echo.

:: 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python，请安装Python 3.6或更高版本
    echo 您可以从https://www.python.org/downloads/下载并安装Python
    pause
    exit /b 1
)

:: 运行GUI
echo 启动图形界面...
echo.
python switch_rom_merger_gui.py

echo.
echo GUI已关闭。
echo.
pause 