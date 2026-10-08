param([ValidateSet('pre','runner','post','opt','expert','workbench')][string]$App='workbench', [int]$Port=8791)
$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$url = "http://127.0.0.1:$Port/$App"
$dataDir = [System.IO.Path]::GetFullPath((Join-Path $base 'user-data'))
$healthy = $false
try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
    $healthy = [bool]$response.ok
} catch { }
if ($healthy) {
    $servedDataDir = [System.IO.Path]::GetFullPath([string]$response.storage)
    if ($servedDataDir -ine $dataDir) {
        throw "Port $Port belongs to another Design Lab storage: $servedDataDir. Expected: $dataDir. Launch this copy with a different -Port."
    }
}
if (-not $healthy) {
    $repoRoot = [System.IO.Path]::GetFullPath((Join-Path $base '..\..'))
    $pythonCandidates = @()
    if ($env:CAE_LAB_PYTHON) { $pythonCandidates += $env:CAE_LAB_PYTHON }
    $pythonCandidates += @(
        (Join-Path $repoRoot '.venv\Scripts\python.exe'),
        (Join-Path $repoRoot '.venv-workbench\Scripts\python.exe'),
        (Join-Path $repoRoot 'venv\Scripts\python.exe')
    )
    $python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $python) { $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source }
    if (-not $python) { throw 'Python was not found on PATH.' }
    $serverFile = Join-Path $base 'server.py'
    $args = @('"' + $serverFile + '"', '--port', [string]$Port, '--data-dir', '"' + $dataDir + '"')
    Start-Process -FilePath $python -ArgumentList $args -WindowStyle Hidden | Out-Null
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        Start-Sleep -Milliseconds 200
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
        } catch { continue }
        if ($response.ok) {
            $servedDataDir = [System.IO.Path]::GetFullPath([string]$response.storage)
            if ($servedDataDir -ine $dataDir) { throw "Port $Port belongs to a different Design Lab data directory: $servedDataDir" }
            $healthy = $true
            break
        }
    }
}
if (-not $healthy) { throw 'The local Design Lab service did not start.' }
$edge = (Get-Command msedge.exe -ErrorAction SilentlyContinue).Source
if (-not $edge) {
    $paths = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe")
    $edge = $paths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if ($edge) { Start-Process -FilePath $edge -ArgumentList @("--app=$url",'--new-window') | Out-Null }
else { Start-Process $url | Out-Null }
