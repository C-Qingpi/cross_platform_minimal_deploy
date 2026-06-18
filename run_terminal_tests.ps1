# Run terminal behavior tests on Windows (real agent workspace).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "=== Windows terminal test runner ==="
Write-Host "platform: win32 $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)"

pip install -e ..\arion_agent -q
pip install -r requirements.txt -q

Set-Location agent
python test_jobs_behaviors.py @args
