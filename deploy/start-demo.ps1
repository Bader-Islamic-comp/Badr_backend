# Starts the reviewer demo API in Docker and prints what to enter in the app.
#   powershell -ExecutionPolicy Bypass -File deploy\start-demo.ps1            # phone on the same Wi-Fi
#   powershell -ExecutionPolicy Bypass -File deploy\start-demo.ps1 -Local     # this PC / emulator only
#   powershell -ExecutionPolicy Bypass -File deploy\start-demo.ps1 -NewToken
# Stop with: docker compose down
param([switch]$Local, [switch]$NewToken)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

$envFile = 'deploy\demo.env'
if ($NewToken -and (Test-Path $envFile)) { Remove-Item $envFile }
if (-not (Test-Path $envFile) -or (Get-Item $envFile).Length -eq 0) {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    [IO.File]::WriteAllText((Join-Path (Get-Location) $envFile), "COMPANION_DEMO_TOKEN=$token`n")
}
$token = ((Get-Content $envFile) -match '^COMPANION_DEMO_TOKEN=' | Select-Object -First 1).Substring(21)

if ($Local) {
    $bind = '127.0.0.1'
} elseif ($env:DEMO_BIND) {
    $bind = $env:DEMO_BIND
} else {
    # The private address of the adapter that holds the default route (Wi-Fi or Ethernet).
    $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1
    $bind = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.ifIndex | Select-Object -First 1).IPAddress
    if ($bind -notmatch '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)') {
        throw "No private Wi-Fi/LAN address found (got '$bind'). Use -Local, or set `$env:DEMO_BIND."
    }
}
$port = if ($env:DEMO_PORT) { $env:DEMO_PORT } else { '8000' }

$env:DEMO_BIND = $bind
$env:DEMO_PORT = $port
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'docker compose failed.' }

Write-Host -NoNewline 'Waiting for the API'
$ok = $false
foreach ($i in 1..30) {
    try { Invoke-RestMethod "http://${bind}:$port/health/live" -TimeoutSec 2 | Out-Null; $ok = $true; break }
    catch { Write-Host -NoNewline '.'; Start-Sleep 1 }
}
Write-Host ''
if (-not $ok) { throw 'The API did not become healthy. See: docker compose logs api' }

$appUrl = if ($Local) { "http://10.0.2.2:$port (Android emulator) or http://127.0.0.1:$port (adb reverse)" } else { "http://${bind}:$port" }
Write-Host @"

Badr demo API is running (synthetic data, adult-operated development demo).

In the app: Parent area -> Development service -> enter
  Server address: $appUrl
  Operator token: $token

Keep the token private: no screenshots, chats or repositories.
If the phone cannot connect, allow port $port for Docker in Windows Firewall (private networks only).
Stop: docker compose down    New token: deploy\start-demo.ps1 -NewToken
"@
