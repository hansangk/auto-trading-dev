$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host ""
Write-Host "AutoGrid Alpaca connection test" -ForegroundColor Cyan
Write-Host "The key is used only in this PowerShell process and is cleared when finished."
Write-Host "Do not paste the key into chat or save it in the project folder."
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Install Python 3.11 or newer from https://www.python.org/downloads/ and run this file again."
}

$ApiKey = Read-Host "Paste ALPACA API Key ID"
$SecureSecret = Read-Host "Paste ALPACA Secret Key (input is hidden)" -AsSecureString
$SecretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureSecret)

try {
    $ApiSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($SecretPointer)
    $env:ALPACA_API_KEY_ID = $ApiKey.Trim()
    $env:ALPACA_API_SECRET_KEY = $ApiSecret.Trim()

    Write-Host "Installing/checking AutoGrid dependencies..." -ForegroundColor Yellow
    python -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw "Python package installation failed." }

    $End = (Get-Date).ToUniversalTime().Date.AddDays(-1).ToString("yyyy-MM-dd")
    $Start = (Get-Date).ToUniversalTime().Date.AddDays(-14).ToString("yyyy-MM-dd")
    $Output = "data/alpaca_connection_test.csv"

    Write-Host "Testing delayed SIP historical data..." -ForegroundColor Yellow
    python -m autogrid.cli download-alpaca `
        --output $Output `
        --start $Start `
        --end $End `
        --symbols "SPY,QQQ,GLD,SLV,IBIT,BITI,BITX" `
        --feed sip

    if ($LASTEXITCODE -ne 0) {
        throw "Connection failed. The key may be invalid or this account may not have delayed SIP access."
    }

    Write-Host ""
    Write-Host "SUCCESS: Alpaca connection and SIP sample download completed." -ForegroundColor Green
    Write-Host "Created: $ProjectRoot\$Output"
    Write-Host "Tell ChatGPT only: connection successful. Never send the keys."
}
finally {
    $env:ALPACA_API_KEY_ID = $null
    $env:ALPACA_API_SECRET_KEY = $null
    if ($SecretPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($SecretPointer)
    }
    $ApiSecret = $null
    $SecureSecret = $null
}

Read-Host "Press Enter to close"
