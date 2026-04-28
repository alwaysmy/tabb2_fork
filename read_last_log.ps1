$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:9900"
$login = Invoke-RestMethod -Method Post -Uri "$base/api/admin/login" -Body '{"password":"admin"}' -ContentType "application/json"
$headers = @{ Authorization = "Bearer $($login.token)" }
$logs = Invoke-RestMethod -Method Get -Uri "$base/api/admin/logs?page=1&page_size=3" -Headers $headers
$logs | ConvertTo-Json -Depth 8
