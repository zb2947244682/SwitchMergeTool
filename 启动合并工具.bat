@echo off
chcp 65001 > nul
title 启动Switch游戏合并工具

echo 正在启动Switch游戏合并工具...

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误：未找到Python，请确保已安装Python并添加到系统环境变量中。
    echo 请先运行setup.bat进行环境设置。
    pause
    exit /b 1
)

REM 启动GUI
pythonw switch_rom_merger_gui.py

exit /b 0 