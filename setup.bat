@echo off
chcp 65001 > nul
title Switch游戏合并工具 - 初始化设置

echo ======================================
echo   Switch游戏合并工具 - 初始化设置
echo ======================================
echo.
echo 本脚本将帮助您设置必要的目录结构和依赖项。
echo.

REM 创建必要的目录结构
echo 正在创建目录结构...
if not exist "tools" mkdir tools
if not exist "OUTPUT" mkdir OUTPUT
if not exist "TEMP" mkdir TEMP
if not exist "rom" mkdir rom
if not exist "Firmware" mkdir Firmware
echo 目录结构创建完成！
echo.

REM 检查Python是否安装
echo 正在检查Python安装...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请确保已安装Python 3.8或更高版本并添加到系统环境变量中。
    echo 您可以从 https://www.python.org/downloads/ 下载Python。
    echo.
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set pyver=%%i
    echo [成功] 检测到Python版本: %pyver%
)
echo.

REM 安装Python依赖
echo 正在安装Python依赖项...
call install_deps.bat
echo.

REM 检查工具
echo 检查必要工具...
set TOOLS_MISSING=0

if not exist "tools\hactoolnet.exe" (
    echo [警告] 未找到hactoolnet.exe
    echo 请从 https://github.com/Thealexbarney/libhac/releases 下载最新版本
    echo 并将hactoolnet.exe放置在tools目录下
    set TOOLS_MISSING=1
) else (
    echo [成功] 已找到hactoolnet.exe
)

if not exist "tools\nsz.exe" (
    echo [警告] 未找到nsz.exe
    echo 请从 https://github.com/nicoboss/nsz/releases 下载最新版本
    echo 并将nsz.exe放置在tools目录下
    set TOOLS_MISSING=1
) else (
    echo [成功] 已找到nsz.exe
)
echo.

REM 检查密钥和固件
echo 检查密钥和固件文件...
if not exist "prod.keys" (
    echo [警告] 未找到prod.keys文件
    echo 请确保prod.keys文件位于工具同级目录
    set TOOLS_MISSING=1
) else (
    echo [成功] 已找到prod.keys
)

if exist "title.keys" (
    echo [成功] 已找到title.keys
) else (
    echo [提示] 未找到title.keys文件（可选）
)

if not exist "Firmware\*.nca" (
    echo [警告] Firmware目录中未找到固件文件
    echo 请将解压后的Switch固件文件放入Firmware目录
    set TOOLS_MISSING=1
) else (
    echo [成功] 已找到固件文件
)
echo.

if %TOOLS_MISSING% == 1 (
    echo [警告] 仍然缺少一些必要的文件或工具。
    echo 请下载所需的工具并准备好密钥和固件文件。
    echo 查看README.md获取更多信息。
) else (
    echo [成功] 所有必要的文件和工具都已准备就绪！
    echo 您现在可以运行merge_switch_roms.bat开始合并游戏文件。
)

echo.
echo ======================================
echo.
echo 使用方法:
echo 1. 将游戏文件放在rom目录下
echo 2. 运行merge_switch_roms.bat
echo 3. 合并后的文件将保存在OUTPUT目录中
echo.

pause 