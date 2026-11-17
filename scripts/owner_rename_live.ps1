# Rename the live database's real competitor brands to Competitor A-F, then check the live page.
# The owner runs this, from the competitive-shelf-intelligence repo folder, with:
#
#   powershell -ExecutionPolicy Bypass -File scripts\owner_rename_live.ps1
#
# It opens a Fly proxy to competitive-shelf-pg on port 15433 and runs scripts\owner_rename_live.py, which reads
# DATABASE_URL from this repo's .env inside its own process (nothing prints it), prints the plan, backs up, asks for
# the typed confirm, writes in one transaction, clears the app's cache and runs the name check against the live
# page (PASS or FAIL). The proxy always closes.
#
#   -PageOnly        skip the database; only the page check (no proxy opened)
#   -NoProxy -Port   use a database already listening on that port (the harness test)
#   -Url -EnvFile -NoCacheClear   as in owner_rename_live.py

param(
    [int]$Port = 15433,
    [string]$Url = 'https://competitive.lailarallc.com',
    [string]$EnvFile = '',
    [switch]$PageOnly,
    [switch]$NoProxy,
    [switch]$NoCacheClear
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$need = @('python')
if (-not ($PageOnly -or $NoProxy)) { $need += 'flyctl' }
foreach ($tool in $need) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Host "Missing $tool on PATH. Nothing changed." -ForegroundColor Red
        exit 1
    }
}

$pyArgs = @('scripts\owner_rename_live.py', '--port', "$Port", '--url', $Url)
if ($EnvFile) { $pyArgs += @('--env-file', $EnvFile) }
if ($PageOnly) { $pyArgs += '--page-only' }
if ($NoCacheClear) { $pyArgs += '--no-cache-clear' }

$proxy = $null
$code = 1
try {
    if (-not ($PageOnly -or $NoProxy)) {
        Write-Host "Opening the Fly proxy to competitive-shelf-pg on port $Port ..."
        $proxy = Start-Process flyctl -ArgumentList "proxy $($Port):5432 -a competitive-shelf-pg" -PassThru -WindowStyle Hidden
    }
    if (-not $PageOnly) {
        $open = $false
        for ($i = 0; $i -lt 30 -and -not $open; $i++) {
            try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', $Port); $c.Close(); $open = $true }
            catch { Start-Sleep -Seconds 1 }
        }
        if (-not $open) { throw "Nothing is listening on port $Port. Is flyctl logged in (flyctl auth whoami)? Nothing changed." }
    }
    python @pyArgs
    $code = $LASTEXITCODE
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
}
finally {
    if ($proxy -and -not $proxy.HasExited) { Stop-Process -Id $proxy.Id -Force }
    if ($proxy) { Write-Host "Fly proxy closed." }
}
exit $code
