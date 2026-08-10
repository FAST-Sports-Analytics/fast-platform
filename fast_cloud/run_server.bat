@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

rem Validate the existing virtual environment. A venv copied between PCs can
rem still exist but point to a Python installation that is not present.
if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>&1
    if errorlevel 1 (
        echo [FAST Cloud] Existing .venv is not usable on this computer.
        echo [FAST Cloud] Rebuilding the virtual environment...
        rmdir /s /q ".venv"
    )
)

if not exist "%VENV_PY%" (
    call :find_python
    if errorlevel 1 exit /b 1

    echo [FAST Cloud] Creating .venv with %PY_DESC%...
    %PY_CMD% -m venv ".venv"
    if errorlevel 1 (
        echo [FAST Cloud] Failed to create the virtual environment.
        exit /b 1
    )
)

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo [FAST Cloud] Created .env from .env.example.
    echo [FAST Cloud] Review .env before using this installation outside development.
)

echo [FAST Cloud] Checking Python dependencies...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [FAST Cloud] Dependency installation failed.
    exit /b 1
)

"%VENV_PY%" -m pip check
if errorlevel 1 (
    echo [FAST Cloud] Python environment has broken dependencies.
    exit /b 1
)

echo [FAST Cloud] Preparing administrator...
"%VENV_PY%" -m scripts.create_admin
if errorlevel 1 exit /b 1

echo [FAST Cloud] Starting on http://127.0.0.1:8766
"%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8766 --reload
exit /b %errorlevel%

:find_python
set "PY_CMD="
set "PY_DESC="

py -3.10 --version >nul 2>&1 && (
    set "PY_CMD=py -3.10"
    set "PY_DESC=Python 3.10"
    exit /b 0
)
py -3.11 --version >nul 2>&1 && (
    set "PY_CMD=py -3.11"
    set "PY_DESC=Python 3.11"
    exit /b 0
)
py -3.12 --version >nul 2>&1 && (
    set "PY_CMD=py -3.12"
    set "PY_DESC=Python 3.12"
    exit /b 0
)

if exist "C:\Program Files\Python310\python.exe" (
    set PY_CMD="C:\Program Files\Python310\python.exe"
    set "PY_DESC=Python 3.10"
    exit /b 0
)
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
    set PY_CMD="%LocalAppData%\Programs\Python\Python311\python.exe"
    set "PY_DESC=Python 3.11"
    exit /b 0
)
if exist "C:\Program Files\Python312\python.exe" (
    set PY_CMD="C:\Program Files\Python312\python.exe"
    set "PY_DESC=Python 3.12"
    exit /b 0
)

echo [FAST Cloud] No supported Python installation was found.
echo [FAST Cloud] Install Python 3.10, 3.11, or 3.12 and run this file again.
exit /b 1
