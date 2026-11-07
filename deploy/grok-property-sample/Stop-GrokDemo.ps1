# Stops only grok-property-sample. Keeps its volume.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
docker compose --env-file (Join-Path $PSScriptRoot ".env") --project-name grok-property-sample -f (Join-Path $PSScriptRoot "compose.yaml") down
if ($LASTEXITCODE -ne 0) { throw "docker compose down failed" }
Write-Host "Stopped grok-property-sample. The sample volume was kept."
