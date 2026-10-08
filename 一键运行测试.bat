@echo off
rem  ============================================================
rem  ASCII ONLY on purpose: cmd.exe mis-parses UTF-8 bytes inside
rem  .bat files, so all Chinese output is printed by a Python
rem  helper instead. Do not put Chinese text in this file.
rem  ============================================================
chcp 65001 >nul
title Run pytest - project test suite
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1

set "PY="

rem --- candidate 1: managed python (versions) ---
for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
  if exist "%%~fD\python.exe" set "PY=%%~fD\python.exe"
)

rem --- candidate 2: managed python (venv, has pytest installed) ---
for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\envs\*") do (
  if exist "%%~fD\Scripts\python.exe" set "PY=%%~fD\Scripts\python.exe"
)

rem --- candidate 3: normal per-user install ---
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if not defined PY if exist "%%~fD\python.exe" set "PY=%%~fD\python.exe"
)

rem --- candidate 4: machine-wide install ---
for /d %%D in ("C:/Python3*") do (
  if not defined PY if exist "%%~fD\python.exe" set "PY=%%~fD\python.exe"
)

rem --- candidate 5: whatever is on PATH ---
if not defined PY (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PY set "PY=%%P"
  )
)

if not defined PY (
  echo.
  echo [ERROR] Python not found on this computer.
  echo Install Python 3 from https://www.python.org/downloads/
  echo Remember to tick "Add python.exe to PATH" during install.
  echo.
  pause
  exit /b 1
)

"%PY%" "_run_tests.py" "%PY%"

echo.
pause
