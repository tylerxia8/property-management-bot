# Deletes only the grok-property-sample volume, then starts that project again.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$composeFile = Join-Path $PSScriptRoot "compose.yaml"
if (-not (Test-Path -LiteralPath $composeFile)) { $composeFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "compose.demo.yaml" }
docker compose --env-file (Join-Path $PSScriptRoot ".env") --project-name grok-property-sample -f $composeFile down -v --remove-orphans
if ($LASTEXITCODE -ne 0) { throw "docker compose down failed" }
& (Join-Path $PSScriptRoot "Start-GrokDemo.ps1")
