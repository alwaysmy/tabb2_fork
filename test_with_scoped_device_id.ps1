$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:9900"

# Read signin scoped device id from Tabbit Preferences.
$prefPath = "C:\Users\AlwaysTS\AppData\Local\Tabbit\User Data\Default\Preferences"
$rawPref = Get-Content $prefPath -Raw
$m = [regex]::Match($rawPref, '"signin_scoped_device_id"\s*:\s*"([^"]+)"')
$scoped = if ($m.Success) { $m.Groups[1].Value } else { "" }
if (-not $scoped) { throw "signin_scoped_device_id not found" }

$login = Invoke-RestMethod -Method Post -Uri "$base/api/admin/login" -Body '{"password":"admin"}' -ContentType "application/json"
$headers = @{ Authorization = "Bearer $($login.token)" }
$tokensResp = Invoke-RestMethod -Method Get -Uri "$base/api/admin/tokens" -Headers $headers
if (@($tokensResp.tokens).Count -eq 0) { throw "No tokens found" }

$tok = $tokensResp.tokens[0]
$tokenId = $tok.id

# We only have preview in /tokens response, fetch full value from local config as fallback.
$cfgPath = ".\config.json"
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$full = ($cfg.tokens | Where-Object { $_.id -eq $tokenId })[0].value
if (-not $full) { throw "Cannot load full token value" }

$parts = $full.Split("|")
if ($parts.Length -eq 1) {
    $newVal = "$($parts[0])|$scoped"
} elseif ($parts.Length -eq 2) {
    $newVal = "$($parts[0])|$($parts[1])|$scoped"
} else {
    $newVal = "$($parts[0])|$($parts[1])|$scoped"
}

$updBody = @{ value = $newVal } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Put -Uri "$base/api/admin/tokens/$tokenId" -Headers $headers -ContentType "application/json" -Body $updBody | Out-Null

# test token and chat
$test = Invoke-RestMethod -Method Post -Uri "$base/api/admin/tokens/$tokenId/test" -Headers $headers
$chatBody = @{
    model = "best"
    messages = @(@{ role = "user"; content = "请只回复：OK" })
    stream = $false
} | ConvertTo-Json -Depth 6

try {
    $chat = Invoke-RestMethod -Method Post -Uri "$base/v1/chat/completions" -Headers @{ Authorization = "Bearer sk-local" } -ContentType "application/json" -Body $chatBody
    [PSCustomObject]@{
        scoped_device_id = $scoped
        token_test_ok = $test.ok
        chat_ok = $true
        content = $chat.choices[0].message.content
    } | ConvertTo-Json -Depth 6
}
catch {
    if ($_.Exception.Response) {
        $r = $_.Exception.Response
        $reader = New-Object System.IO.StreamReader($r.GetResponseStream())
        [PSCustomObject]@{
            scoped_device_id = $scoped
            token_test_ok = $test.ok
            chat_ok = $false
            http_status = [int]$r.StatusCode
            error_body = $reader.ReadToEnd()
        } | ConvertTo-Json -Depth 6
    } else {
        throw
    }
}
