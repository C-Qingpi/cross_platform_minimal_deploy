@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

for /f "delims=" %%i in ('"%PY%" "%ROOT%\deploy_config.py" --emit-cmd') do %%i
if errorlevel 1 (
  echo ERROR: missing deploy.config
  pause
  exit /b 1
)

echo Stopping %DEPLOY_MODE% deploy (ports %BACKEND_PORT% / %FRONTEND_PORT%) ...

for %%p in ("backend" "agent-runner" "frontend") do (
  taskkill /fi "WINDOWTITLE eq %%p" /f 2>nul
)

for %%q in (%BACKEND_PORT% %FRONTEND_PORT%) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%q " ^| findstr LISTENING') do (
    taskkill /pid %%a /f 2>nul
  )
)

echo Done.
pause
