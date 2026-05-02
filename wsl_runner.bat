@echo off
chcp 65001 > nul
setlocal

REM Run job_runner.sh inside WSL from a Windows shell.
REM Usage: wsl_runner.bat [transaction|asset|account|all] [extra args...]

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

where wsl >nul 2>&1
if errorlevel 1 (
    echo [ERROR] wsl command was not found. Enable or install WSL first.
    exit /b 1
)

for /f "usebackq delims=" %%I in (`wsl wslpath -a "%ROOT%"`) do set "WSL_ROOT=%%I"
if not defined WSL_ROOT (
    echo [ERROR] Failed to convert project path to a WSL path: %ROOT%
    exit /b 1
)

wsl --cd "%WSL_ROOT%" bash -lc './job_runner.sh "$@"' _ %*
exit /b %ERRORLEVEL%
