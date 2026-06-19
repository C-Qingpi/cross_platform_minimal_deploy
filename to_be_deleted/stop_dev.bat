@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "RUN_DIR=%ROOT%.run"
set "BACKEND_PORT=8920"
set "FRONTEND_PORT=5174"

echo Stopping DEVELOPMENT (ports %BACKEND_PORT% / %FRONTEND_PORT%) ...

:: Kill by window titles
for %%p in ("backend" "agent-runner" "frontend") do (
  taskkill /fi "WINDOWTITLE eq %%p" /f 2>nul
)

:: Kill by listening port
for %%q in (%BACKEND_PORT% %FRONTEND_PORT%) do (
  for /f "tokens=2" %%a in ('netstat -ano ^| findstr ":%%q "') do (
    taskkill /pid %%a /f 2>nul
  )
)

echo Done.
pause
