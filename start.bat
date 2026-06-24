@echo off
chcp 65001 >nul
title 混沌集

cd /d "%~dp0"

echo.
echo ========================================
echo   混沌集 — Chaos Collection
echo ========================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: Show Python version
for /f "tokens=*" %%a in ('python --version 2^>^&1') do echo Python: %%a
echo.

:: Install dependencies
echo [1/3] 检查依赖...
pip install -r requirements.txt -q 2>nul
if %errorlevel% neq 0 (
    echo [WARN] 依赖安装可能不完整，尝试继续...
)
echo [1/3] 依赖就绪

:: Initialize data directory
if not exist "data" mkdir data

:: Open browser after short delay
echo [2/3] 启动浏览器...
start "" http://127.0.0.1:8000

:: Start server
echo [3/3] 启动服务器...
echo.
echo   地址: http://127.0.0.1:8000
echo   日志: logs\chaos.log
echo   按 Ctrl+C 停止
echo ========================================
echo.

python main.py

pause
