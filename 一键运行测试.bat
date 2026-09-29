@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   智能停车管理系统接口自动化测试
echo ============================================
echo.
echo [1/3] 检查 Python 环境...
python --version
if errorlevel 1 (
    echo 未检测到 Python，请先安装 Python 3.8 以上版本。
    pause
    exit /b 1
)
echo.
echo [2/3] 检查 pytest...
python -m pytest --version >nul 2>nul
if errorlevel 1 (
    echo 未安装 pytest，正在安装...
    python -m pip install -r requirements.txt
)
echo.
echo [3/3] 执行测试...
echo.
python -m pytest tests -v
echo.
echo ============================================
echo   测试结束。按任意键关闭窗口。
echo ============================================
pause >nul
