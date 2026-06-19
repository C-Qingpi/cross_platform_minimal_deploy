# Stop only this deploy's backend, agent runner, and frontend (by saved PIDs).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. "$Root\deploy_env.ps1"
Import-DeployEnv -Root $Root

$RunDir = Join-Path $Root ".run"
$BackendPort = [int]$env:BACKEND_PORT
$FrontendPort = [int]$env:FRONTEND_PORT

function Stop-SavedPid {
    param([string]$Name, [string]$PidFile)
    if (-not (Test-Path $PidFile)) { return }
    $procId = [int](Get-Content $PidFile -Raw).Trim()
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Stopping $Name (pid $procId) ..."
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "  stopped $Name"
    } else {
        Write-Host "$Name not running (stale pid $procId)"
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Stop-CmdIfOurs {
    param([string]$Label, [string]$Needle)
    $matches = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Needle*" -and $_.CommandLine -like "*$Root*" }
    foreach ($proc in $matches) {
        Write-Host "Stopping $Label (pid $($proc.ProcessId)) ..."
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "  stopped $Label"
    }
}

function Stop-PortIfOurs {
    param([int]$Port, [string]$Label)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        $procId = $conn.OwningProcess
        if (-not $procId) { continue }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        $cmd = $proc.CommandLine
        if ($cmd -and ($cmd -like "*$Root*")) {
            Write-Host "Stopping $Label on port $Port (pid $procId) ..."
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "Stopping $env:DEPLOY_MODE deploy (ports $BackendPort / $FrontendPort) ..."
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
Stop-SavedPid "backend" (Join-Path $RunDir "backend.pid")
Stop-SavedPid "agent runner" (Join-Path $RunDir "agent.pid")
Stop-SavedPid "frontend" (Join-Path $RunDir "frontend.pid")
Stop-CmdIfOurs "backend" "uvicorn main:app"
Stop-CmdIfOurs "agent runner" "agent_runner.py"
Stop-PortIfOurs $BackendPort "backend"
Stop-PortIfOurs $FrontendPort "frontend"
Write-Host "Done."
