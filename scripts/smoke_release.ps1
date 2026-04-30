param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8013",
    [int]$TimeoutSec = 30
)

$ErrorActionPreference = "Stop"
$failCount = 0

function Invoke-SmokeCheck {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-Host "[$Name] running..."
    try {
        & $Action
        Write-Host "[$Name] OK" -ForegroundColor Green
    }
    catch {
        $script:failCount++
        Write-Host "[$Name] FAIL: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Invoke-SmokeCheck -Name "health" -Action {
    $headers = @{ "X-Request-ID" = "smoke-health-$([guid]::NewGuid())" }
    $resp = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/health" -Headers $headers -TimeoutSec $TimeoutSec
    if ($resp.status -ne "ok") { throw "status != ok" }
    if ($resp.service -ne "astrodvish-api") { throw "service mismatch" }
    if ($resp.version -ne "0.5.0") { throw "version mismatch" }
}

Invoke-SmokeCheck -Name "api-v1-health" -Action {
    $headers = @{ "X-Request-ID" = "smoke-api-v1-health-$([guid]::NewGuid())" }
    $resp = Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/api/v1/health" -Headers $headers -TimeoutSec $TimeoutSec
    if ($resp.status -ne "ok") { throw "status != ok" }
    if ($resp.service -ne "astrodvish-api") { throw "service mismatch" }
    if ($resp.version -ne "0.5.0") { throw "version mismatch" }
}

Invoke-SmokeCheck -Name "chart" -Action {
    $headers = @{
        "Content-Type" = "application/json"
        "X-Request-ID" = "smoke-chart-$([guid]::NewGuid())"
    }
    $payload = @{
        datetime_utc = "1984-11-13T11:35:00Z"
        latitude = 53.9006
        longitude = 27.5590
        house_system = "P"
        zodiac_mode = "tropical"
        sidereal_mode = $null
    } | ConvertTo-Json -Depth 10

    $resp = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/chart" -Headers $headers -Body $payload -TimeoutSec $TimeoutSec
    if (-not $resp.objects.sun) { throw "missing objects.sun" }
    if ($null -eq $resp.aspects) { throw "missing aspects" }
}

Invoke-SmokeCheck -Name "asc-sign-intervals" -Action {
    $headers = @{
        "Content-Type" = "application/json"
        "X-Request-ID" = "smoke-rect-$([guid]::NewGuid())"
    }
    $payload = @{
        birth_date_local = "2000-04-16"
        latitude = 53.9
        longitude = 27.56667
        house_system = "P"
        zodiac_mode = "tropical"
        sidereal_mode = $null
    } | ConvertTo-Json -Depth 10

    $resp = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/rectification/asc-sign-intervals" -Headers $headers -Body $payload -TimeoutSec $TimeoutSec
    if (-not $resp.birth_context.timezone) { throw "missing birth_context.timezone" }
    if ($resp.birth_context.timezone_source -ne "coordinates") { throw "timezone_source mismatch" }
    if (-not $resp.asc_sign_intervals) { throw "missing asc_sign_intervals" }
}

Invoke-SmokeCheck -Name "events-start" -Action {
    $headers = @{
        "Content-Type" = "application/json"
        "X-Request-ID" = "smoke-events-$([guid]::NewGuid())"
    }
    $payload = @{ dialog_history = @() } | ConvertTo-Json -Depth 10
    $resp = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/api/v1/rectification/events/start" -Headers $headers -Body $payload -TimeoutSec $TimeoutSec
    if ($resp.status -ne "ask_question" -and $resp.status -ne "finalized") {
        throw "unexpected events status: $($resp.status)"
    }
}

if ($failCount -gt 0) {
    Write-Host ""
    Write-Host "Smoke release checks FAILED: $failCount" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Smoke release checks PASSED" -ForegroundColor Green
exit 0
