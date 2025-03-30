@echo off
chcp 65001 > nul
title 安装Python依赖

echo ======================================
echo    安装Python依赖 - 跳过SSL验证
echo ======================================
echo.

pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

echo.
if errorlevel 1 (
    echo [错误] 安装依赖项失败。
) else (
    echo [成功] 依赖项安装完成！
)

pause 