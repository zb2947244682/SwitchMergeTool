@echo off
chcp 65001 > nul
title Switch游戏合并工具

echo ======================================
echo    Switch游戏合并工具 - 初始化
echo ======================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请确保已安装Python 3.8或更高版本并添加到系统环境变量中。
    echo 您可以从 https://www.python.org/downloads/ 下载Python。
    echo.
    pause
    exit /b 1
)

REM 创建必要的目录结构
if not exist "tools" mkdir tools
if not exist "OUTPUT" mkdir OUTPUT
if not exist "TEMP" mkdir TEMP
if not exist "rom" mkdir rom

REM 检查依赖工具
set TOOLS_MISSING=0

if not exist "tools\hactoolnet.exe" (
    echo [警告] 未找到hactoolnet.exe
    echo 请从 https://github.com/Thealexbarney/libhac/releases 下载最新版本
    echo 并将hactoolnet.exe放置在tools目录下
    set TOOLS_MISSING=1
)

if not exist "tools\nsz.exe" (
    echo [警告] 未找到nsz.exe
    echo 请从 https://github.com/nicoboss/nsz/releases 下载最新版本
    echo 并将nsz.exe放置在tools目录下
    set TOOLS_MISSING=1
)

REM 检查必要文件
if not exist "prod.keys" (
    echo [警告] 未找到prod.keys文件
    echo 请确保prod.keys文件位于工具同级目录
    set TOOLS_MISSING=1
)

if not exist "Firmware" (
    echo [警告] 未找到Firmware目录
    echo 请创建Firmware目录并放入Switch固件文件
    set TOOLS_MISSING=1
)

if %TOOLS_MISSING% == 1 (
    echo.
    echo [警告] 缺少一些必要的文件或工具，请先准备好这些文件后再运行。
    echo 查看README.md获取更多信息。
    echo.
    pause
    exit /b 1
)

REM 安装Python依赖
echo 正在检查并安装Python依赖...
if not exist "install_deps.bat" (
    echo [警告] 未找到install_deps.bat，尝试使用默认安装方式...
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
) else (
    call install_deps.bat
)

echo.
echo ======================================
echo    Switch游戏合并工具 - 开始处理
echo ======================================
echo.

REM 运行Python脚本
python switch_rom_merger.py

echo.
if errorlevel 1 (
    echo [错误] 处理过程中出现错误，请查看rom_merger.log获取详细信息。
) else (
    echo [成功] 处理完成！输出文件位于OUTPUT文件夹中。
)

echo.
pause 