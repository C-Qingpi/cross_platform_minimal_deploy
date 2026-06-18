# Minimal Agent Deploy — Windows
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example — set DEEPSEEK_API_KEY"
}

$env:DEPLOY_ROOT = if ($env:DEPLOY_ROOT) { $env:DEPLOY_ROOT } else { $Root }

$BackendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8921" }

Write-Host "Starting backend on port $BackendPort..."
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", $BackendPort -WorkingDirectory "$Root\backend"

Start-Sleep -Seconds 2

Write-Host "Starting agent runner..."
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "agent_runner.py" -WorkingDirectory "$Root\agent"

Start-Sleep -Seconds 1

Write-Host "Starting frontend on http://localhost:5175 ..."
Set-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) { npm install }
npm run dev
