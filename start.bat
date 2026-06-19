@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "RUN_DIR=%ROOT%\.run"
if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"

set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

for /f "delims=" %%i in ('"%PY%" "%ROOT%\deploy_config.py" --emit-cmd') do %%i
if errorlevel 1 (
  echo ERROR: missing deploy.config — copy deploy.config.example and set mode=dev or mode=prod
  pause
  exit /b 1
)

echo Starting %DEPLOY_MODE% deploy backend :%BACKEND_PORT% ...
start "backend" cmd /c "cd /d "%ROOT%\backend" && "%PY%" -m uvicorn main:app --host 127.0.0.1 --port %BACKEND_PORT%"

timeout /t 3 /nobreak >nul
echo Starting agent runner ...
start "agent-runner" cmd /c "cd /d "%ROOT%\agent" && "%PY%" agent_runner.py"

timeout /t 1 /nobreak >nul
echo Starting frontend on http://localhost:%FRONTEND_PORT% ...
if not exist "%ROOT%\frontend\node_modules" (
  cd /d "%ROOT%\frontend"
  call npm install
)
start "frontend" cmd /c "cd /d "%ROOT%\frontend" && set BACKEND_PORT=%BACKEND_PORT% && set FRONTEND_PORT=%FRONTEND_PORT% && npm run dev -- --host 127.0.0.1 --port %FRONTEND_PORT%"

echo.
echo Open http://localhost:%FRONTEND_PORT%
echo.
pause
