# Load deploy.config for this checkout. DEPLOY_ROOT is always the checkout dir.

function Import-DeployEnv {
    param([Parameter(Mandatory = $true)][string]$Root)

    $Root = (Resolve-Path $Root).Path
    $cfgPath = Join-Path $Root "deploy.config"
    if (-not (Test-Path $cfgPath)) {
        throw "missing deploy.config in $Root — copy deploy.config.example and set mode=dev or mode=prod"
    }

    $mode = ""
    $backendPort = ""
    $frontendPort = ""
    foreach ($raw in Get-Content $cfgPath) {
        $line = ($raw -replace "#.*$", "").Trim()
        if (-not $line -or $line -notmatch "=") { continue }
        $key, $val = $line.Split("=", 2)
        $key = $key.Trim().ToLowerInvariant()
        $val = $val.Trim()
        switch ($key) {
            "mode" { $mode = $val.ToLowerInvariant() }
            "backend_port" { $backendPort = $val }
            "frontend_port" { $frontendPort = $val }
        }
    }

    if ($mode -ne "dev" -and $mode -ne "prod") {
        throw "deploy.config mode must be dev or prod (got '$mode')"
    }

    $script:DeployMode = $mode
    if ($mode -eq "dev") {
        $env:BACKEND_PORT = if ($backendPort) { $backendPort } else { "8920" }
        $env:FRONTEND_PORT = if ($frontendPort) { $frontendPort } else { "5174" }
    } else {
        $env:BACKEND_PORT = if ($backendPort) { $backendPort } else { "8921" }
        $env:FRONTEND_PORT = if ($frontendPort) { $frontendPort } else { "5175" }
    }
    $env:ARION_DEPLOY_MODE = "dev"

    $env:DEPLOY_ROOT = $Root
    $env:DEPLOY_MODE = $mode
}
