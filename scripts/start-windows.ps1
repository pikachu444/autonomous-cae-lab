# Private Windows launcher. Runs the loopback server and opens the workbench.
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$InstallOnly,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Store = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\research-store')
)
$ErrorActionPreference = 'Stop'
function Normalize-Directory([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.Length -gt $root.Length) { return $full.TrimEnd([IO.Path]::DirectorySeparatorChar) }
    return $full
}
$runtime = Normalize-Directory $RuntimeRoot
$storePath = Normalize-Directory $Store
& (Join-Path $PSScriptRoot 'install-windows.ps1') -RuntimeRoot $runtime
if (-not $?) { throw 'Private Python installation failed.' }
if ($InstallOnly) { return }
New-Item -ItemType Directory -Force -Path $storePath | Out-Null
$python = Join-Path $runtime 'venv\Scripts\python.exe'
$pidPath = Join-Path $runtime ("server-$Port.pid")
$launchPath = Join-Path $runtime ("server-$Port.launch.json")
$url = "http://127.0.0.1:$Port/workbench"
$health = "http://127.0.0.1:$Port/api/overview"
$operatorConfig = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\workbench-config.json'
if (-not (Test-Path -LiteralPath $operatorConfig -PathType Leaf)) { $operatorConfig = '' }
$configSha = if ($operatorConfig) { (Get-FileHash -LiteralPath $operatorConfig -Algorithm SHA256).Hash.ToLowerInvariant() } else { '' }
$install = Get-Content -LiteralPath (Join-Path $runtime 'install-receipt.json') -Raw | ConvertFrom-Json
$sourceFiles = @(Get-ChildItem -LiteralPath (Join-Path $install.source_root 'caelab'),(Join-Path $install.source_root 'apps'),(Join-Path $install.source_root 'schemas'),(Join-Path $install.source_root 'plugins') -Recurse -File |
    Where-Object { $_.Extension -in @('.py','.html','.js','.css','.json') } | Sort-Object FullName)
$fingerprintText = ($sourceFiles | ForEach-Object { $_.FullName.Substring($install.source_root.Length) + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }) -join "`n"
$fingerprintBytes = [Text.Encoding]::UTF8.GetBytes($fingerprintText)
$sourceFingerprint = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($fingerprintBytes))).Replace('-','').ToLowerInvariant()
function Test-Ready {
    try {
        $response = Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -ne 200) { return $false }
        $overview = $response.Content | ConvertFrom-Json
        return -not [string]::IsNullOrWhiteSpace($overview.token)
    } catch { return $false }
}
function Test-OwnedProcess([int]$ProcessId) {
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        return $null -ne $process -and $process.ExecutablePath -eq $python -and
            $process.CommandLine -like '*apps.lab.server*' -and $process.CommandLine -like "*--port $Port*"
    } catch { return $false }
}
function Test-ProcessStore([int]$ProcessId) {
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        $expectedStore = '--store "' + $storePath + '"'
        return $null -ne $process -and $process.CommandLine.IndexOf($expectedStore,[StringComparison]::OrdinalIgnoreCase) -ge 0
    } catch { return $false }
}
function Test-OwnedListener([int]$ProcessId) {
    try {
        $listeners = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction Stop)
        foreach ($listener in $listeners) {
            if ($listener.OwningProcess -eq $ProcessId) { return $true }
            # On Windows a virtualenv python.exe may be a redirector parent;
            # the managed base interpreter then owns the listening socket.
            $child = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction Stop
            $baseRoot = Join-Path $runtime 'python'
            if ($child -and $child.ParentProcessId -eq $ProcessId -and
                $child.ExecutablePath.StartsWith($baseRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -and
                $child.CommandLine -like '*apps.lab.server*' -and $child.CommandLine -like "*--port $Port*") { return $true }
        }
        return $false
    } catch { return $false }
}
$reuse = $false
if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
    $oldPid = 0
    if ([int]::TryParse((Get-Content -LiteralPath $pidPath -Raw).Trim(),[ref]$oldPid)) {
        if ((Test-OwnedProcess $oldPid) -and (Test-OwnedListener $oldPid) -and (Test-Ready)) {
            if (-not (Test-ProcessStore $oldPid)) {
                throw "Port $Port is running this launcher with a different research store. Stop it explicitly or choose another -Port."
            }
            if (-not (Test-Path -LiteralPath $launchPath -PathType Leaf)) {
                throw "An older owned server is already running on port $Port without a verified launch receipt. Stop it explicitly before changing its workspace."
            }
            $launch = Get-Content -LiteralPath $launchPath -Raw | ConvertFrom-Json
            if ($launch.pid -ne $oldPid -or $launch.store -ne $storePath -or
                $launch.source_root -ne $install.source_root -or $launch.project_sha256 -ne $install.project_sha256 -or
                $launch.source_fingerprint -ne $sourceFingerprint -or
                $launch.config_path -ne $operatorConfig -or $launch.config_sha256 -ne $configSha) {
                throw "Port $Port is running a different store, source or operator configuration. Stop that owned server explicitly or choose another -Port."
            }
            $reuse = $true
        }
    }
}
if (-not $reuse) {
    if (Test-Ready) { throw "Port $Port already serves an unowned Lab process. Choose -Port or stop it first." }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $stdout = Join-Path $runtime ("server-$Port-$stamp.stdout.log")
    $stderr = Join-Path $runtime ("server-$Port-$stamp.stderr.log")
    # Start-Process in Windows PowerShell joins ArgumentList. Explicit quotes keep paths with spaces intact.
    $arguments = @('-m','apps.lab.server','--store',('"' + $storePath + '"'),'--port',[string]$Port)
    if ($operatorConfig) {
        $arguments += @('--workbench-config',('"' + $operatorConfig + '"'))
    }
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $PSScriptRoot) -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    [IO.File]::WriteAllText($pidPath,[string]$process.Id)
    $ready = $false
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        if ((Test-OwnedProcess $process.Id) -and (Test-OwnedListener $process.Id) -and (Test-Ready)) { $ready = $true; break }
        if ($process.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) {
        $tail = if (Test-Path -LiteralPath $stderr) { (Get-Content -LiteralPath $stderr -Tail 20) -join [Environment]::NewLine } else { '' }
        throw "Lab server did not become ready at $health. $tail"
    }
    [ordered]@{pid=$process.Id;port=$Port;store=$storePath;source_root=$install.source_root;
        project_sha256=$install.project_sha256;
        source_fingerprint=$sourceFingerprint;config_path=$operatorConfig;config_sha256=$configSha;
        launched_utc=[DateTime]::UtcNow.ToString('o')} |
        ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $launchPath -Encoding UTF8
}
Write-Host "Autonomous CAE Lab is ready: $url"
Write-Host "Research store: $storePath"
if (-not $NoBrowser) { Start-Process -FilePath $url }
