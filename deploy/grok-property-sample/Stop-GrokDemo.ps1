# Stops only grok-property-sample. Keeps its volume.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$composeFile = Join-Path $PSScriptRoot "compose.yaml"
if (-not (Test-Path -LiteralPath $composeFile)) { $composeFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "compose.demo.yaml" }
docker compose --env-file (Join-Path $PSScriptRoot ".env") --project-name grok-property-sample -f $composeFile down
if ($LASTEXITCODE -ne 0) { throw "docker compose down failed" }
Write-Host "Stopped grok-property-sample. The sample volume was kept."
