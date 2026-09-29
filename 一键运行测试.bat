@echo off
setlocal
cd /d "%~dp0"
title 智能停车管理系统 · 接口自动化测试

echo ==================================================
echo   智能停车管理系统 · 接口自动化测试
echo ==================================================
echo.
echo [1/4] 探测可用的 Python 解释器...

set "PYEXE="

rem ---- 候选一：本项目当前使用环境 ----
call :set_py "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if defined PYEXE goto :found
call :set_py "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if defined PYEXE goto :found

rem ---- 候选二：常见安装位置 ----
call :set_py "C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe"
if defined PYEXE goto :found
call :set_py "C:\Python313\python.exe"
if defined PYEXE goto :found
call :set_py "C:\Python312\python.exe"
if defined PYEXE goto :found
call :set_py "C:\Python311\python.exe"
if defined PYEXE goto :found
call :set_py "C:\Python310\python.exe"
if defined PYEXE goto :found
call :set_py "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined PYEXE goto :found
call :set_py "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PYEXE goto :found
call :set_py "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if defined PYEXE goto :found

rem ---- 候选三：py 启动器（换机器时最通用）----
call :set_py_launcher 3.13
if defined PYEXE goto :found
call :set_py_launcher 3.12
if defined PYEXE goto :found
call :set_py_launcher 3.11
if defined PYEXE goto :found
call :set_py_launcher 3.10
if defined PYEXE goto :found
call :set_py_launcher 3.9
if defined PYEXE goto :found
call :set_py_launcher 3
if defined PYEXE goto :found
goto :nopython


:set_py
if defined PYEXE goto :eof
if not exist %1 goto :eof
%1 -c "import sys" >nul 2>nul
if errorlevel 1 goto :eof
set "PYEXE=%~1"
goto :eof

:set_py_launcher
if defined PYEXE goto :eof
for /f "delims=" %%I in ('py -%1 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
goto :eof


:found
echo       找到：%PYEXE%
"%PYEXE%" --version
echo.
echo [2/4] 检查 pytest...
"%PYEXE%" -m pytest --version >nul 2>nul
if not errorlevel 1 goto :run_tests
echo       未检测到 pytest，正在自动安装（只需装一次）...
"%PYEXE%" -m pip install pytest --quiet --disable-pip-version-check
"%PYEXE%" -m pytest --version >nul 2>nul
if not errorlevel 1 goto :run_tests
echo       换个方式再试一次...
"%PYEXE%" -m pip install pytest --user --quiet --disable-pip-version-check
"%PYEXE%" -m pytest --version >nul 2>nul
if errorlevel 1 goto :nopytest


:run_tests
echo.
echo [3/4] 开始执行测试...
echo.
"%PYEXE%" -m pytest tests -v
echo.
echo [4/4] 完成。
echo.
echo ==================================================
echo   测试结束，按任意键关闭窗口。
echo ==================================================
pause >nul
exit /b 0


:nopython
echo.
echo   [错误] 没有找到可用的 Python 解释器。
echo.
echo   本项目的测试脚本需要 Python 3.8 及以上版本。
echo   请到 https://www.python.org/downloads/ 下载安装，
echo   安装时务必勾选 "Add python.exe to PATH"，然后重新运行本脚本。
echo.
pause >nul
exit /b 1


:nopytest
echo.
echo   [错误] pytest 安装失败（通常是网络问题）。
echo   请手动执行下面这行命令，然后重新运行本脚本：
echo.
echo       "%PYEXE%" -m pip install pytest
echo.
pause >nul
exit /b 1
