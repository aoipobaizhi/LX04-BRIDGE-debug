@echo off
cd /d "%~dp0"

rem  Launch LX04 host. ASCII-only on purpose: cmd parses .bat with the system
rem  ANSI codepage, so non-ASCII text here breaks the parser on some systems.

set "PACKED_DIR=%~dp0dist\LX04-PC-Bridge-Host\LX04-PC-Bridge-Host.exe"
set "PACKED_ONE=%~dp0dist\LX04-PC-Bridge-Host.exe"
set "VENV=%~dp0..\.tools\venv\Scripts\python.exe"
set "HOSTDIR=%~dp0host"

if exist "%PACKED_DIR%" (
    echo [LX04] starting packaged host ...
    start "" "%PACKED_DIR%"
    exit /b 0
)
if exist "%PACKED_ONE%" (
    echo [LX04] starting packaged host ...
    start "" "%PACKED_ONE%"
    exit /b 0
)

echo [LX04] packaged exe not found, starting development build ...
if not exist "%HOSTDIR%\pc_host.py" (
    echo [LX04] host\pc_host.py not found. Run this from the repo root.
    pause
    exit /b 1
)
cd /d "%HOSTDIR%"

if exist "%VENV%" (
    echo [LX04] using virtualenv: %VENV%
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
    echo [LX04] failed to start. Install dependencies first: host\install_deps.bat
    pause
)
