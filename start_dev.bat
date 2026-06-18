@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "RUN_DIR=%ROOT%.run"
if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"

set "BACKEND_PORT=8920"
set "FRONTEND_PORT=5174"

echo Starting DEVELOPMENT backend on :%BACKEND_PORT% ...
start "backend" cmd /c "cd /d "%ROOT%backend" && "%ROOT%.venv\Scripts\python" -m uvicorn main:app --host 127.0.0.1 --port %BACKEND_PORT%"

timeout /t 3 /nobreak >nul
echo Starting agent runner ...
start "agent-runner" cmd /c "cd /d "%ROOT%agent" && "%ROOT%.venv\Scripts\python" agent_runner.py"

timeout /t 1 /nobreak >nul
echo Starting DEVELOPMENT frontend on http://localhost:%FRONTEND_PORT% ...
if not exist "%ROOT%frontend\node_modules" (
  cd /d "%ROOT%frontend"
  call npm install
)
start "frontend" cmd /c "cd /d "%ROOT%frontend" && npm run dev -- --host 127.0.0.1 --port %FRONTEND_PORT%

echo.
echo PIDs saved under .run/ - logs under .run/logs/
echo Open http://localhost:%FRONTEND_PORT%
echo.
pause
