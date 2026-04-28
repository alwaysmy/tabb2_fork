param(
    [string]$BaseUrl = "http://127.0.0.1:9900/v1",
    [string]$BearerToken = "sk-local",
    [string]$Model = "best"
)

$ErrorActionPreference = "Stop"

$modelsUrl = "{0}/models" -f $BaseUrl
$chatUrl = "{0}/chat/completions" -f $BaseUrl
$countUrl = "{0}/messages/count_tokens" -f $BaseUrl

Write-Host "== Tabbit2API Windows Test =="
Write-Host ("BaseUrl: {0}" -f $BaseUrl)
Write-Host ""

Write-Host "[1/3] GET /models"
$models = Invoke-RestMethod -Method Get -Uri $modelsUrl
$modelCount = @($models.data).Count
$firstModels = @($models.data | Select-Object -First 6 | ForEach-Object { $_.id }) -join ", "
Write-Host ("Model count: {0}" -f $modelCount)
Write-Host ("First models: {0}" -f $firstModels)
Write-Host ""

Write-Host ("[2/3] POST /chat/completions (Authorization: Bearer {0})" -f $BearerToken)
$headers = @{ Authorization = ("Bearer {0}" -f $BearerToken) }
$chatBody = @{
    model = $Model
    messages = @(
        @{
            role = "user"
            content = "reply OK only"
        }
    )
    stream = $false
} | ConvertTo-Json -Depth 6
$chat = Invoke-RestMethod -Method Post -Uri $chatUrl -Headers $headers -ContentType "application/json" -Body $chatBody
$reply = $chat.choices[0].message.content
Write-Host ("Chat response: {0}" -f $reply)
Write-Host ""

Write-Host "[3/3] POST /messages/count_tokens"
$countBody = @{
    messages = @(
        @{
            role = "user"
            content = "hello"
        }
    )
} | ConvertTo-Json -Depth 6
$count = Invoke-RestMethod -Method Post -Uri $countUrl -ContentType "application/json" -Body $countBody
Write-Host ("input_tokens: {0}" -f $count.input_tokens)
Write-Host ""
Write-Host "All tests passed."
