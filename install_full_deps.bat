@echo off
chcp 65001 > nul
title 安装完整Python依赖

echo ======================================
echo    安装完整Python依赖 - 忽略SSL验证
echo ======================================
echo.

echo 正在全局禁用SSL证书验证...
set PYTHONHTTPSVERIFY=0

echo 安装py7zr及其依赖...
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

echo.
if errorlevel 1 (
    echo [警告] 安装依赖项时出现问题，尝试使用国内镜像源...
    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    
    if errorlevel 1 (
        echo [错误] 安装依赖项失败。
        echo 请确认您已正确安装Visual C++ Build Tools。
        echo 访问: https://visualstudio.microsoft.com/visual-cpp-build-tools/
    ) else (
        echo [成功] 使用国内镜像源安装依赖项成功！
    )
) else (
    echo [成功] 安装依赖项成功！
)

pause 