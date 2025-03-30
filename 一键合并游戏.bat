@echo off
setlocal enabledelayedexpansion
REM 设置控制台为UTF-8编码
chcp 65001 >nul
TITLE Switch游戏合并工具

echo ====================================
echo      Switch游戏合并工具
echo ====================================
echo.

REM 创建日志目录和文件
set LOG_DIR=logs
set LOG_FILE=%LOG_DIR%\merge_log_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%.txt
set LOG_FILE=%LOG_FILE: =0%

if not exist %LOG_DIR% mkdir %LOG_DIR%
echo 开始运行时间: %date% %time% > "%LOG_FILE%"

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python环境，请先安装Python 3.8或更高版本 >> "%LOG_FILE%"
    echo [错误] 未检测到Python环境，请先安装Python 3.8或更高版本
    pause
    exit /b 1
)

REM 检查必要的目录
if not exist "OUTPUT" (
    echo [创建] 创建输出目录: OUTPUT >> "%LOG_FILE%"
    echo [创建] 创建输出目录: OUTPUT
    mkdir "OUTPUT"
)

if not exist "TEMP" (
    echo [创建] 创建临时目录: TEMP >> "%LOG_FILE%"
    echo [创建] 创建临时目录: TEMP
    mkdir "TEMP"
)

if not exist "rom" (
    echo [错误] 未找到rom目录，请创建rom目录并放入游戏文件 >> "%LOG_FILE%"
    echo [错误] 未找到rom目录，请创建rom目录并放入游戏文件
    pause
    exit /b 1
)

REM 检查必要的文件
set MISSING_FILES=0

if not exist "prod.keys" (
    echo [错误] 未找到prod.keys文件，请将密钥文件放到根目录 >> "%LOG_FILE%"
    echo [错误] 未找到prod.keys文件，请将密钥文件放到根目录
    set /a MISSING_FILES+=1
)

if not exist "Firmware" (
    echo [错误] 未找到Firmware目录，请下载固件文件 >> "%LOG_FILE%"
    echo [错误] 未找到Firmware目录，请下载固件文件
    set /a MISSING_FILES+=1
)

REM 检查工具目录下的必要文件
if not exist "tools\hactoolnet.exe" (
    echo [错误] 未找到hactoolnet.exe工具，请确保tools目录下有此文件 >> "%LOG_FILE%"
    echo [错误] 未找到hactoolnet.exe工具，请确保tools目录下有此文件
    set /a MISSING_FILES+=1
)

set NSZ_FOUND=0
if exist "tools\nsz.exe" (
    set NSZ_FOUND=1
) else (
    if exist "tools\nsz_v4.6.1_win64_portable\nsz.exe" (
        set NSZ_FOUND=1
    ) else (
        echo [错误] 未找到nsz.exe工具，请确保tools目录或其子目录下有此文件 >> "%LOG_FILE%"
        echo [错误] 未找到nsz.exe工具，请确保tools目录或其子目录下有此文件
        set /a MISSING_FILES+=1
    )
)

if %MISSING_FILES% gtr 0 (
    echo.
    echo [警告] 存在 %MISSING_FILES% 个缺失的文件或目录，可能会影响程序运行 >> "%LOG_FILE%"
    echo [警告] 存在 %MISSING_FILES% 个缺失的文件或目录，可能会影响程序运行
    echo 是否仍要继续？(Y/N)
    choice /c YN /m "请选择："
    if errorlevel 2 (
        echo 用户选择退出程序 >> "%LOG_FILE%"
        echo 用户选择退出程序
        pause
        exit /b 1
    )
)

echo.
echo [信息] 开始扫描游戏文件... >> "%LOG_FILE%"
echo [信息] 开始扫描游戏文件...
echo.

REM 执行Python脚本
echo [执行] python switch_rom_merger.py >> "%LOG_FILE%"
echo [执行] python switch_rom_merger.py
echo.

REM 创建目录变量，用于显示完整路径
set FULL_PATH=%cd%
set OUTPUT_DIR=%FULL_PATH%\OUTPUT

python switch_rom_merger.py >> "%LOG_FILE%" 2>&1

if %errorlevel% neq 0 (
    echo.
    echo [错误] 合并过程中出现错误，错误代码: %errorlevel% >> "%LOG_FILE%"
    echo [错误] 合并过程中出现错误，错误代码: %errorlevel%
    echo 请检查日志文件了解详细信息: %LOG_FILE%
    echo.
    pause
    exit /b %errorlevel%
)

echo.
echo ==================================== >> "%LOG_FILE%"
echo      合并处理完成 >> "%LOG_FILE%"
echo ==================================== >> "%LOG_FILE%"
echo.
echo ====================================
echo      合并处理完成
echo ====================================

REM 列出所有生成的文件
echo.
echo [信息] 输出文件列表: >> "%LOG_FILE%"
echo [信息] 输出文件列表:
echo.

set FILE_COUNT=0
for /r "%OUTPUT_DIR%" %%i in (*.xci) do (
    set /a FILE_COUNT+=1
    echo 文件 !FILE_COUNT!: "%%~nxi" [%%~zi 字节] >> "%LOG_FILE%"
    echo 文件 !FILE_COUNT!: "%%~nxi" [%%~zi 字节]
)

echo.
if %FILE_COUNT% equ 0 (
    echo [警告] 未找到输出的XCI文件！请检查日志以了解原因。 >> "%LOG_FILE%"
    echo [警告] 未找到输出的XCI文件！请检查日志以了解原因。
) else (
    echo [成功] 共生成 %FILE_COUNT% 个XCI文件 >> "%LOG_FILE%"
    echo [成功] 共生成 %FILE_COUNT% 个XCI文件
)

echo.
echo 合并结束时间: %date% %time% >> "%LOG_FILE%"
echo 日志文件保存在: %LOG_FILE%

echo.
echo 是否打开输出目录？(Y/N)
choice /c YN /m "请选择："
if errorlevel 1 if not errorlevel 2 start explorer "%OUTPUT_DIR%"

pause 