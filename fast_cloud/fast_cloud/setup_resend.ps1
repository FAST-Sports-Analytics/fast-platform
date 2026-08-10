$ErrorActionPreference = "Stop"

$cloudRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $cloudRoot ".env"
$examplePath = Join-Path $cloudRoot ".env.example"

if (-not (Test-Path $envPath)) {
    Copy-Item $examplePath $envPath
    Write-Host "[FAST Cloud] Created .env from .env.example."
}

$secureKey = Read-Host "Paste the Resend API key" -AsSecureString
$key = [System.Net.NetworkCredential]::new("", $secureKey).Password

if ([string]::IsNullOrWhiteSpace($key)) {
    throw "A Resend API key is required."
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $lines = @(Get-Content -LiteralPath $Path)
    $pattern = "^{0}=" -f [regex]::Escape($Name)
    $replacement = "$Name=$Value"
    $replaced = $false

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = $replacement
            $replaced = $true
            break
        }
    }

    if (-not $replaced) {
        if ($lines.Count -gt 0 -and $lines[-1] -ne "") {
            $lines += ""
        }
        $lines += $replacement
    }

    Set-Content -LiteralPath $Path -Value $lines -Encoding UTF8
}

Set-DotEnvValue $envPath "FAST_CLOUD_EMAIL_PROVIDER" "resend"
Set-DotEnvValue $envPath "FAST_CLOUD_RESEND_API_KEY" $key
Set-DotEnvValue $envPath "FAST_CLOUD_EMAIL_FROM_NAME" "FAST Sports Analytics"
Set-DotEnvValue $envPath "FAST_CLOUD_EMAIL_FROM_EMAIL" "no-reply@fastsportsanalytics.com"
Set-DotEnvValue $envPath "FAST_CLOUD_EMAIL_REPLY_TO" "support@fastsportsanalytics.com"
Set-DotEnvValue $envPath "FAST_CLOUD_PUBLIC_APP_URL" "https://www.fastsportsanalytics.com"

$key = $null
$secureKey = $null

Write-Host ""
Write-Host "[FAST Cloud] Resend configuration saved to .env."
Write-Host "[FAST Cloud] The API key was not written to source code."
Write-Host "[FAST Cloud] Start Cloud with .\run_server.bat"
