# Deletes only the grok-property-sample volume, then starts that project again.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
docker compose --env-file (Join-Path $PSScriptRoot ".env") --project-name grok-property-sample -f (Join-Path $PSScriptRoot "compose.yaml") down -v --remove-orphans
if ($LASTEXITCODE -ne 0) { throw "docker compose down failed" }
& (Join-Path $PSScriptRoot "Start-GrokDemo.ps1")
