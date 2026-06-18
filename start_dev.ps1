# Start DEVELOPMENT deployment (ports 8920 / 5174)
param(
    [int]$BackendPort = 8920,
    [int]$FrontendPort = 5174
)

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$RUN_DIR = Join-Path $ROOT ".run"
if (-not (Test-Path $RUN_DIR)) { New-Item -ItemType Directory -Path $RUN_DIR -Force | Out-Null }

$venvPython = Join-Path $ROOT ".venv\Scripts\python.exe"

Write-Host "Starting DEVELOPMENT backend on :$BackendPort ..."
$backendJob = Start-Job -Name "backend" -ScriptBlock {
    param($r, $p, $bp)
    Set-Location (Join-Path $r "backend")
    & $p -m uvicorn main:app --host 127.0.0.1 --port $bp
} -ArgumentList $ROOT, $venvPython, $BackendPort

Start-Sleep -Seconds 2

Write-Host "Starting agent runner ..."
$agentJob = Start-Job -Name "agent-runner" -ScriptBlock {
    param($r, $p)
    Set-Location (Join-Path $r "agent")
    & $p agent_runner.py
} -ArgumentList $ROOT, $venvPython

Start-Sleep -Seconds 1

Write-Host "Starting DEVELOPMENT frontend http://localhost:$FrontendPort ..."
$frontendDir = Join-Path $ROOT "frontend"
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Push-Location $frontendDir
    npm install
    Pop-Location
}
$frontendJob = Start-Job -Name "frontend" -ScriptBlock {
    param($d, $fp)
    Set-Location $d
    npm run dev -- --host 127.0.0.1 --port $fp
} -ArgumentList $frontendDir, $FrontendPort

Write-Host "PIDs saved under .run/ - logs under .run/logs/"
Write-Host "Open http://localhost:$FrontendPort"
Write-Host ""
Write-Host "Press any key to stop all processes..."
[void][System.Console]::ReadKey($true)

Stop-Job $backendJob -ErrorAction SilentlyContinue
Stop-Job $agentJob -ErrorAction SilentlyContinue
Stop-Job $frontendJob -ErrorAction SilentlyContinue
Remove-Job $backendJob -ErrorAction SilentlyContinue
Remove-Job $agentJob -ErrorAction SilentlyContinue
Remove-Job $frontendJob -ErrorAction SilentlyContinue
Write-Host "Stopped."
