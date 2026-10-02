@echo off
cd /d "%~dp0"

rem  Launch LX04 host (development build). ASCII-only on purpose.

set "VENV=%~dp0..\..\.tools\venv\Scripts\python.exe"

if exist "%VENV%" (
    echo [LX04] using virtualenv ...
    "%VENV%" pc_host.py
    goto done
)

echo [LX04] virtualenv not found, using system python ...
where python >nul 2>nul
if %errorlevel%==0 (
    python pc_host.py
) else (
    py -3 pc_host.py
)

:done
if errorlevel 1 (
    echo.
    echo [LX04] failed to start. Install dependencies first: install_deps.bat
    pause
)
