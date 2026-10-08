# Explicitly stop only a server started by start-windows.ps1.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][switch]$Force,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [ValidateRange(1024,65535)][int]$Port = 8766
)
$ErrorActionPreference = 'Stop'
if (-not $Force) { throw 'Stopping the server requires an explicit -Force switch.' }
$runtime = [IO.Path]::GetFullPath($RuntimeRoot)
if ($runtime.Length -gt [IO.Path]::GetPathRoot($runtime).Length) {
    $runtime = $runtime.TrimEnd([IO.Path]::DirectorySeparatorChar)
}
$pidPath = Join-Path $runtime ("server-$Port.pid")
$launchPath = Join-Path $runtime ("server-$Port.launch.json")
if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $launchPath -PathType Leaf)) { throw "No verified launcher receipt for port $Port." }
$processId = 0
if (-not [int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(),[ref]$processId)) { throw 'Invalid launcher PID.' }
$launch = Get-Content -LiteralPath $launchPath -Raw | ConvertFrom-Json
$python = Join-Path $runtime 'venv\Scripts\python.exe'
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction Stop
$expectedStore = '--store "' + $launch.store + '"'
if ($launch.pid -ne $processId -or $launch.port -ne $Port -or $null -eq $process -or
    $process.ExecutablePath -ne $python -or $process.CommandLine -notlike '*apps.lab.server*' -or
    $process.CommandLine -notlike "*--port $Port*" -or
    $process.CommandLine.IndexOf($expectedStore,[StringComparison]::OrdinalIgnoreCase) -lt 0) {
    throw 'The recorded PID no longer identifies this launcher and store; no process was stopped.'
}
$listeners = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction Stop)
$owned = $false
foreach ($listener in $listeners) {
    if ($listener.OwningProcess -eq $processId) { $owned = $true; break }
    $child = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction Stop
    if ($child -and $child.ParentProcessId -eq $processId -and
        $child.ExecutablePath.StartsWith((Join-Path $runtime 'python') + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -and
        $child.CommandLine -like '*apps.lab.server*' -and $child.CommandLine -like "*--port $Port*") { $owned = $true; break }
}
if (-not $owned) { throw 'The listener does not belong to the recorded server; no process was stopped.' }
Write-Warning 'Force stop interrupts in-flight jobs. Wait for jobs to finish before using this command.'
& taskkill.exe /PID $processId /T /F
if ($LASTEXITCODE -ne 0) { throw "taskkill failed with exit code $LASTEXITCODE" }
Write-Host "Stopped verified Lab server on port $Port. Research data and receipts were retained."
