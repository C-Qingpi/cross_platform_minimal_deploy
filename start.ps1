# Minimal Agent Deploy — Windows
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
. "$Root\deploy_env.ps1"
Import-DeployEnv -Root $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example — set DEEPSEEK_API_KEY"
}

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

Write-Host "Starting $env:DEPLOY_MODE deploy (root=$env:DEPLOY_ROOT) backend :$env:BACKEND_PORT ..."
Start-Process -NoNewWindow -FilePath $python -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", $env:BACKEND_PORT -WorkingDirectory "$Root\backend"

Start-Sleep -Seconds 2

Write-Host "Starting agent runner (mode=$env:DEPLOY_MODE) ..."
Start-Process -NoNewWindow -FilePath $python -ArgumentList "agent_runner.py" -WorkingDirectory "$Root\agent"

Start-Sleep -Seconds 1

Write-Host "Starting frontend on http://localhost:$env:FRONTEND_PORT ..."
Set-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) { npm install }
npm run dev -- --host 127.0.0.1 --port $env:FRONTEND_PORT
