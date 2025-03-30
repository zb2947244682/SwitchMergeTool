@echo off
echo ===================================
echo Switch ROM 管理工具 - 安装依赖
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

:: 设置环境变量忽略SSL验证
echo 设置环境变量忽略SSL证书验证...
set PYTHONHTTPSVERIFY=0

:: 更新pip
echo 更新pip...
python -m pip install --upgrade pip --trusted-host pypi.org --trusted-host files.pythonhosted.org

:: 安装依赖
echo 安装依赖库...
python -m pip install tqdm py7zr pillow --trusted-host pypi.org --trusted-host files.pythonhosted.org

echo.
echo 依赖安装完成！
echo.
pause 