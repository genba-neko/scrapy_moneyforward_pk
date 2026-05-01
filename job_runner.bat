@echo off
REM Usage: job_runner.bat [transaction|asset|account|all] [extra args...]
REM
REM Issue #40 で spider が transaction/account/asset_allocation の 3 種別へ
REM 統合された後、 Windows 実行は WSL 経由 (wsl_runner.bat) を正路とする。
REM 本 .bat はその互換 wrapper。
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "WSL_LAUNCHER=%ROOT%\wsl_runner.bat"
if not exist "%WSL_LAUNCHER%" (
    echo [ERROR] wsl_runner.bat not found at %WSL_LAUNCHER% 1>&2
    exit /b 1
)

call "%WSL_LAUNCHER%" %*
exit /b %ERRORLEVEL%
