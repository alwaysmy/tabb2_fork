param(
    [string]$Base = "http://127.0.0.1:9900"
)

$ErrorActionPreference = "Stop"

$idToken = (Get-Content ".\id_token.txt" -Raw).Trim()
if (-not $idToken) { throw "id_token.txt is empty" }

$login = Invoke-RestMethod -Method Post -Uri "$Base/api/admin/login" -Body '{"password":"admin"}' -ContentType "application/json"
$headers = @{ Authorization = "Bearer $($login.token)" }

# 1) exchange id_token to token_value
$exchangeBody = @{ id_token = $idToken } | ConvertTo-Json -Depth 5
$exchange = Invoke-RestMethod -Method Post -Uri "$Base/api/admin/tokens/google-login" -Headers $headers -ContentType "application/json" -Body $exchangeBody
if (-not $exchange.ok) { throw "google-login exchange failed" }

# 2) add as a new token
$name = "Google Fresh " + (Get-Date -Format "HHmmss")
$addBody = @{ name = $name; value = $exchange.token_value; enabled = $true } | ConvertTo-Json -Depth 5
$added = Invoke-RestMethod -Method Post -Uri "$Base/api/admin/tokens" -Headers $headers -ContentType "application/json" -Body $addBody
$tokenId = $added.id

# 3) test token session creation
$test = Invoke-RestMethod -Method Post -Uri "$Base/api/admin/tokens/$tokenId/test" -Headers $headers

# 4) run chat completion
$chatBody = @{
    model = "best"
    messages = @(
        @{
            role = "user"
            content = "请只回复：OK"
        }
    )
    stream = $false
} | ConvertTo-Json -Depth 6

try {
    $chat = Invoke-RestMethod -Method Post -Uri "$Base/v1/chat/completions" -Headers @{ Authorization = "Bearer sk-local" } -ContentType "application/json" -Body $chatBody
    [PSCustomObject]@{
        token_id = $tokenId
        token_test_ok = $test.ok
        chat_ok = $true
        chat_content = $chat.choices[0].message.content
    } | ConvertTo-Json -Depth 6
}
catch {
    if ($_.Exception.Response) {
        $r = $_.Exception.Response
        $reader = New-Object System.IO.StreamReader($r.GetResponseStream())
        $errBody = $reader.ReadToEnd()
        [PSCustomObject]@{
            token_id = $tokenId
            token_test_ok = $test.ok
            chat_ok = $false
            http_status = [int]$r.StatusCode
            error_body = $errBody
        } | ConvertTo-Json -Depth 6
    } else {
        throw
    }
}
