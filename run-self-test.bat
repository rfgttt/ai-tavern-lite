@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title AI Tavern One-Click Self-Test
set "PYTHONUTF8=1"
set "PYTHON_EXE=backend\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" goto missing_python

"%PYTHON_EXE%" "scripts\self_test_runner.py"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" goto success

echo [WARN] Self-test found one or more problems.
echo Upload the newest ZIP from the self-test-results folder.
goto finish

:success
echo [OK] All self-tests passed.

:finish
echo.
pause
exit /b %EXIT_CODE%

:missing_python
echo [ERROR] Missing %PYTHON_EXE%
echo Create the backend virtual environment first, then run this file again.
echo.
pause
exit /b 1
