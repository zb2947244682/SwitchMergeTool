@echo off
echo ===================================
echo Switch ROM 管理工具 - 一键整理
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

:: 运行ROM整理脚本
echo 开始整理Switch游戏文件...
echo.
python switch_rom_merger.py

echo.
echo 处理完成！整理后的文件位于output目录中。
echo.
pause 