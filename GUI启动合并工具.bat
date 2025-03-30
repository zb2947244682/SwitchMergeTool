@echo off
chcp 65001 >nul
title Switch游戏合并工具 - GUI界面

echo ====================================
echo      Switch游戏合并工具 - GUI界面
echo ====================================
echo.

REM 设置环境变量禁用SSL验证
set PYTHONHTTPSVERIFY=0

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python环境，请先安装Python 3.8或更高版本
    pause
    exit /b 1
)

REM 检查是否存在必要的Python包
python -c "import tkinter" >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未安装tkinter库，这是GUI界面必须的
    echo 请确保您的Python安装包含tkinter
    pause
    exit /b 1
)

REM 检查tools目录
if not exist "tools" (
    echo [错误] 未发现tools目录，请确保当前目录结构正确
    pause
    exit /b 1
)

REM 启动GUI
echo 正在启动图形界面，请稍候...
echo.

python switch_gui.py
if %errorlevel% neq 0 (
    echo.
    echo [错误] GUI运行失败，错误代码: %errorlevel%
    echo 尝试使用'一键合并游戏.bat'作为替代
    pause
)

exit /b 0 