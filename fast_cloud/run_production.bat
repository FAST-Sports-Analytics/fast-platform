\
@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [FAST Cloud] .venv not found. Run run_server.bat once to build dependencies.
  exit /b 1
)

set "FAST_CLOUD_ENV=production"
".venv\Scripts\python.exe" -m scripts.production_preflight
if errorlevel 1 exit /b 1

if "%FAST_CLOUD_BOOTSTRAP_ADMIN%"=="true" (
  ".venv\Scripts\python.exe" -m scripts.create_admin
  if errorlevel 1 exit /b 1
)

echo [FAST Cloud] Starting production profile...
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8766 --proxy-headers --forwarded-allow-ips="*"
