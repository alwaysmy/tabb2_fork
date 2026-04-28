param(
    [switch]$UseProxy,
    [string]$ProxyUrl = "http://127.0.0.1:7890",
    [int]$Port = 8800
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot\..

if ($UseProxy) {
    $env:http_proxy = $ProxyUrl
    $env:https_proxy = $ProxyUrl
    $env:HTTP_PROXY = $ProxyUrl
    $env:HTTPS_PROXY = $ProxyUrl
    Write-Host "Proxy enabled: $ProxyUrl"
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' not found. Please install Python 3.11+ first."
}

if (-not (Test-Path ".venv\\Scripts\\python.exe")) {
    if (Test-Path ".venv") {
        Remove-Item -Recurse -Force ".venv"
    }
    py -3 -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "Starting Tabbit2API on port $Port ..."
& ".\.venv\Scripts\python.exe" -m uvicorn tabbit2api:app --host 0.0.0.0 --port $Port
