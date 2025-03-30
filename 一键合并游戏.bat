@echo off
chcp 65001 > nul
title 一键合并Switch游戏

cls
echo ================================================
echo         Switch游戏合并工具 - 一键合并
echo ================================================
echo.
echo 该工具将自动扫描rom目录中的游戏文件并合并它们
echo.
echo 正在检查环境...

REM 禁用SSL证书验证
set PYTHONHTTPSVERIFY=0

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请确保已安装Python 3.8或更高版本并添加到系统环境变量中。
    echo 您可以从 https://www.python.org/downloads/ 下载Python。
    echo.
    pause
    exit /b 1
)

REM 检查必要目录
if not exist "OUTPUT" mkdir OUTPUT
if not exist "TEMP" mkdir TEMP
if not exist "rom" (
    echo [警告] 未找到rom目录，将创建该目录
    mkdir rom
)

REM 检查必要文件
set MISSING=0

if not exist "prod.keys" (
    echo [错误] 未找到prod.keys文件。
    set MISSING=1
)

if not exist "Firmware" (
    echo [错误] 未找到Firmware目录。
    set MISSING=1
)

if not exist "tools\hactoolnet.exe" (
    echo [错误] 未找到hactoolnet.exe工具。
    set MISSING=1
)

set NSZ_FOUND=0
if exist "tools\nsz.exe" (
    set NSZ_FOUND=1
) else (
    for /d %%i in (tools\*) do (
        if exist "%%i\nsz.exe" (
            set NSZ_FOUND=1
        )
    )
)

if %NSZ_FOUND% == 0 (
    echo [错误] 未找到nsz.exe工具。
    set MISSING=1
)

if %MISSING% == 1 (
    echo.
    echo [错误] 缺少必要的文件，无法继续。
    echo 请确保:
    echo   1. prod.keys文件位于当前目录
    echo   2. Firmware目录存在且包含文件
    echo   3. tools目录下有hactoolnet.exe和nsz.exe文件
    echo.
    pause
    exit /b 1
)

echo [成功] 环境检查通过！
echo.
echo 开始合并游戏文件...
echo.
echo ================================================

REM 运行Python脚本
python switch_rom_merger.py

echo.
if errorlevel 1 (
    echo [错误] 处理过程中出现错误，请查看rom_merger.log获取详细信息。
) else (
    echo [成功] 处理完成！输出文件位于OUTPUT文件夹中。
)

echo.
echo 按任意键打开输出目录...
pause >nul

start "" "OUTPUT"
exit /b 0 