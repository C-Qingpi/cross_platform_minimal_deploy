# Stop DEVELOPMENT deployment (ports 8920 / 5174)
$BackendPort = 8920
$FrontendPort = 5174
Write-Host "Stopping DEVELOPMENT (ports $BackendPort / $FrontendPort) ..."

# Stop by window title
Get-Job -Name "backend","agent-runner","frontend" -ErrorAction SilentlyContinue | Stop-Job -ErrorAction SilentlyContinue
Get-Job -Name "backend","agent-runner","frontend" -ErrorAction SilentlyContinue | Remove-Job -ErrorAction SilentlyContinue

# Stop by port
$ports = @($BackendPort, $FrontendPort)
foreach ($port in $ports) {
    $connections = netstat -ano | Select-String ":$port "
    foreach ($conn in $connections) {
        $parts = $conn -split '\s+'
        $pid = $parts[-1]
        if ($pid -match '^\d+$') {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "Done."
