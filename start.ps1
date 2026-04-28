param(
    [switch]$UseProxy,
    [string]$ProxyUrl = "http://127.0.0.1:7890",
    [int]$Port = 9900
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$argsList = @("-ExecutionPolicy", "Bypass", "-File", ".\scripts\run_windows.ps1", "-ProxyUrl", $ProxyUrl, "-Port", "$Port")
if ($UseProxy) {
    $argsList += "-UseProxy"
}

powershell @argsList
