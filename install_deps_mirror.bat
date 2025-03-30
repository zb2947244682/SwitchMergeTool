@echo off
chcp 65001 > nul
title 安装Python依赖(国内镜像)

echo ======================================
echo    安装Python依赖 - 使用国内镜像
echo ======================================
echo.

echo 使用清华大学镜像源安装依赖...
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

echo.
if errorlevel 1 (
    echo [错误] 安装依赖项失败。尝试使用其他镜像源。
    echo 使用阿里云镜像源安装依赖...
    pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
    
    if errorlevel 1 (
        echo [错误] 使用阿里云镜像源安装依赖项也失败了。
        echo 请参考"SSL问题解决方案.txt"获取更多解决方法。
    ) else (
        echo [成功] 使用阿里云镜像源安装依赖项成功！
    )
) else (
    echo [成功] 使用清华镜像源安装依赖项成功！
)

pause 