@echo off
REM Usage: job_runner.bat [transaction|asset|account]
setlocal EnableDelayedExpansion
set ROOT=%~dp0
cd /d "%ROOT%"

if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        set "line=%%A"
        if not "!line:~0,1!"=="#" if not "%%A"=="" set "%%A=%%B"
    )
)

set "PY=%ROOT%.venv-win\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

set "CMD=%1"
if "%CMD%"=="" set "CMD=transaction"

if /i "%CMD%"=="transaction" set "SPIDER=mf_transaction"
if /i "%CMD%"=="trans"        set "SPIDER=mf_transaction"
if /i "%CMD%"=="asset"        set "SPIDER=mf_asset_allocation"
if /i "%CMD%"=="allocation"   set "SPIDER=mf_asset_allocation"
if /i "%CMD%"=="account"      set "SPIDER=mf_account"
if /i "%CMD%"=="accounts"     set "SPIDER=mf_account"

if not defined SPIDER (
    echo Usage: job_runner.bat ^<transaction^|asset^|account^> 1>&2
    exit /b 2
)

cd "%ROOT%src"
"%PY%" -m scrapy crawl "%SPIDER%"
