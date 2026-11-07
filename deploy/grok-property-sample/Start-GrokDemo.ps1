# Starts only the grok-property-sample compose project. Does not change Docker contexts.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function New-Token([int]$Length) {
  $chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".ToCharArray()
  $bytes = New-Object byte[] $Length
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($bytes)
  $out = New-Object System.Text.StringBuilder
  foreach ($b in $bytes) { [void]$out.Append($chars[$b % $chars.Length]) }
  return $out.ToString()
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker was not found. Install Docker Desktop, start it, and run this script again."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Docker Desktop's Linux engine is not running. Start Docker Desktop and wait until it is running. This script does not change Docker contexts, other projects, or other databases."
}

$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $raw = New-Object byte[] 32
  $rng.GetBytes($raw)
  $contact = [Convert]::ToBase64String($raw)
  @(
    "POSTGRES_PASSWORD=$(New-Token 32)"
    "GROK_APP_PASSWORD=$(New-Token 32)"
    "GROK_MIGRATOR_PASSWORD=$(New-Token 32)"
    "SESSION_SECRET=$(New-Token 48)"
    "CONTACT_ENCRYPTION_KEY=$contact"
  ) | Set-Content -Path $envFile -Encoding ascii
}

docker compose --env-file $envFile --project-name grok-property-sample -f (Join-Path $PSScriptRoot "compose.yaml") up --build -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

$ready = $false
foreach ($try in 1..60) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:3000/v1/health" -TimeoutSec 3
    if ($response.StatusCode -eq 200) { $ready = $true; break }
  } catch { }
  Start-Sleep -Seconds 5
}
if (-not $ready) {
  throw "http://127.0.0.1:3000/v1/health did not succeed. Run: docker compose --project-name grok-property-sample logs"
}
Write-Host "Open http://127.0.0.1:3000/"
