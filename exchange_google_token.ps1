param(
    [string]$IdToken = ""
)

$ErrorActionPreference = "Stop"

if (-not $IdToken) {
    if (Test-Path ".\id_token.txt") {
        $IdToken = (Get-Content ".\id_token.txt" -Raw).Trim()
    }
}

if (-not $IdToken) {
    throw "Missing IdToken. Pass -IdToken or create ./id_token.txt"
}

$login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9900/api/admin/login" -Body '{"password":"admin"}' -ContentType "application/json"
$headers = @{ Authorization = "Bearer $($login.token)" }

$body = @{ id_token = $IdToken } | ConvertTo-Json -Depth 5
$resp = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9900/api/admin/tokens/google-login" -Headers $headers -ContentType "application/json" -Body $body

$out = [PSCustomObject]@{
    ok = $resp.ok
    token_value_len = if ($resp.token_value) { $resp.token_value.Length } else { 0 }
}

$out | ConvertTo-Json -Depth 5
