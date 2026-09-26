# Boots the whole local ATLAS stack in the right order.
#   risk-model (8000) > finance (8001) > scheduling (8002) > mcp (8003)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1          # auth off
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Auth    # MCP bearer auth on
#
# Run from the repo root (atlas/). Dashboard is started separately from dashboard/.

param([switch]$Auth)

$ErrorActionPreference = "Stop"
$Root = (Get-Location).Path

if (-not (Test-Path "$Root\atlas.db")) {
    Write-Host "Warning: atlas.db not found at repo root - services will create it."
}

$env:ATLAS_DATABASE_URL = "sqlite:///$($Root -replace '\\', '/')/atlas.db"
if ($Auth) { $env:ATLAS_REQUIRE_AUTH = "1" } else { $env:ATLAS_REQUIRE_AUTH = "0" }

$Services = @(
    @{ Name = "risk-model";       Dir = "services\risk-model";       App = "app.main:app";                  Port = 8000 },
    @{ Name = "finance-service";  Dir = "services\finance-service";  App = "app.main:app";                  Port = 8001 },
    @{ Name = "scheduling-svc";   Dir = "services\scheduling-service"; App = "app.main:app";                Port = 8002 },
    @{ Name = "mcp-server";       Dir = "mcp-server";                App = "atlas_mcp_server.server:app";   Port = 8003 }
)

foreach ($s in $Services) {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*$($s.Port)*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Seconds 1

foreach ($s in $Services) {
    Write-Host "starting $($s.Name) on :$($s.Port)"
    Start-Process -FilePath "python" `
        -ArgumentList "-m", "uvicorn", $s.App, "--port", "$($s.Port)", "--log-level", "warning" `
        -WorkingDirectory (Join-Path $Root $s.Dir) -WindowStyle Hidden
    Start-Sleep -Seconds 6
}

Write-Host "`nATLAS stack is up (auth=$($env:ATLAS_REQUIRE_AUTH)):"
Write-Host "  risk-model   http://127.0.0.1:8000/health"
Write-Host "  finance      http://127.0.0.1:8001/health"
Write-Host "  scheduling   http://127.0.0.1:8002/health"
Write-Host "  mcp          http://127.0.0.1:8003/health"
Write-Host "Dashboard (separate): cd dashboard; npm run dev"