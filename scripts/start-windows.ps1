# Private Windows launcher. Verifies the shared local service, then opens a Qt tool.
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$InstallOnly,
    [switch]$ResearchUI,
    [switch]$Expert,
    [switch]$Documents,
    [switch]$MCP,
    [switch]$Sensitivity,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Store = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\research-store'),
    [ValidateSet('material','data','numerical','pde','expert','runner','simulation','evaluation','study','report')][string]$Tool = 'runner',
    [string]$DocumentId,
    [string]$JobId,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
if ($Tool -eq 'runner' -and $DocumentId) { throw 'Use -JobId to select a Runner job.' }
if ($Tool -ne 'runner' -and $JobId) { throw 'Use -DocumentId to select a research document.' }
# The normal desktop and Research PrepareOnly paths prepare Qt automatically.
# NoBrowser and InstallOnly retain their explicitly requested optional extras.
$installResearchUI = $ResearchUI -or (-not $NoBrowser -and -not $InstallOnly)
function Normalize-Directory([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full.Length -gt $root.Length) { return $full.TrimEnd([IO.Path]::DirectorySeparatorChar) }
    return $full
}
$runtime = Normalize-Directory $RuntimeRoot
$storePath = Normalize-Directory $Store
& (Join-Path $PSScriptRoot 'install-windows.ps1') -RuntimeRoot $runtime -ResearchUI:$installResearchUI -Expert:$Expert -Documents:$Documents -MCP:$MCP -Sensitivity:$Sensitivity
if (-not $?) { throw 'Private Python installation failed.' }
if ($InstallOnly) { return }
New-Item -ItemType Directory -Force -Path $storePath | Out-Null
$python = Join-Path $runtime 'venv\Scripts\python.exe'
$pidPath = Join-Path $runtime ("server-$Port.pid")
$launchPath = Join-Path $runtime ("server-$Port.launch.json")
$url = "http://127.0.0.1:$Port"
$health = "http://127.0.0.1:$Port/api/overview"
$operatorConfig = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\workbench-config.json'
$configSha = if (Test-Path -LiteralPath $operatorConfig -PathType Leaf) { (Get-FileHash -LiteralPath $operatorConfig -Algorithm SHA256).Hash.ToLowerInvariant() } else { '' }
$install = Get-Content -LiteralPath (Join-Path $runtime 'install-receipt.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$sourceFiles = @(Get-ChildItem -LiteralPath (Join-Path $install.source_root 'caelab'),(Join-Path $install.source_root 'apps'),(Join-Path $install.source_root 'schemas'),(Join-Path $install.source_root 'plugins') -Recurse -File |
    Where-Object { $_.Extension -in @('.py','.html','.js','.css','.json') } | Sort-Object FullName)
$fingerprintText = ($sourceFiles | ForEach-Object { $_.FullName.Substring($install.source_root.Length) + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }) -join "`n"
$fingerprintBytes = [Text.Encoding]::UTF8.GetBytes($fingerprintText)
$sourceFingerprint = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($fingerprintBytes))).Replace('-','').ToLowerInvariant()
function Test-OperatorConfigPath([string]$Candidate) {
    if ([string]::IsNullOrWhiteSpace($Candidate)) { return $false }
    if ($Candidate -eq $operatorConfig) { return $true }
    # Packaged Windows apps may resolve the same file through LocalCache.
    # Compare file identity, never merely equal contents or a guessed alias.
    try {
        $same = & $python -c 'import os,sys; print(int(os.path.samefile(sys.argv[1],sys.argv[2])))' $operatorConfig $Candidate 2>$null
        return $LASTEXITCODE -eq 0 -and [string]$same -eq '1'
    } catch { return $false }
}
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
function Get-ProcessStart([int]$ProcessId) {
    try {
        $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($candidate -and $candidate.CreationDate -is [DateTime]) {
            return $candidate.CreationDate.ToUniversalTime().ToString('o')
        }
    } catch {}
    return ''
}
function Write-LauncherRecord([string]$Destination, [byte[]]$Bytes) {
    $receiptTemp = $Destination + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    $receiptBackup = $receiptTemp + '.bak'
    $receiptReplaced = $false
    try {
        [IO.File]::WriteAllBytes($receiptTemp, $Bytes)
        if ([IO.File]::Exists($Destination)) {
            [IO.File]::Replace($receiptTemp, $Destination, $receiptBackup)
        } else {
            [IO.File]::Move($receiptTemp, $Destination)
        }
        $receiptReplaced = $true
    } finally {
        if (Test-Path -LiteralPath $receiptTemp) { Remove-Item -LiteralPath $receiptTemp }
        if ($receiptReplaced -and (Test-Path -LiteralPath $receiptBackup)) {
            try { Remove-Item -LiteralPath $receiptBackup } catch {
                Write-Warning "Launch receipt updated; backup cleanup failed: $receiptBackup"
            }
        }
    }
}
function Write-LaunchReceipt($Receipt) {
    $encoding = [Text.UTF8Encoding]::new($true)
    [byte[]]$bytes = @($encoding.GetPreamble()) + @($encoding.GetBytes(($Receipt | ConvertTo-Json -Depth 3)))
    Write-LauncherRecord $launchPath $bytes
}
function Wait-OwnedReady([int]$ProcessId, [string]$ExpectedStart) {
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        if ((Test-OwnedProcess $ProcessId) -and (Test-OwnedListener $ProcessId) -and (Test-Ready)) {
            return $ExpectedStart -and $ExpectedStart -eq (Get-ProcessStart $ProcessId)
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}
$reuse = $false
if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
    $oldPid = 0
    $oldPidText = [IO.File]::ReadAllText($pidPath).Trim()
    if (-not [int]::TryParse($oldPidText,[ref]$oldPid)) {
        throw "The launcher PID record is empty or invalid: $pidPath. Choose another -Port; no server was started or stopped."
    }
    if ($oldPid -ge 0) {
        if (Test-OwnedProcess $oldPid) {
            if (-not (Test-ProcessStore $oldPid)) {
                throw "Port $Port is running this launcher with a different research store. Stop it explicitly or choose another -Port."
            }
            if (-not (Test-Path -LiteralPath $launchPath -PathType Leaf)) {
                throw "An older owned server is already running on port $Port without a verified launch receipt. Stop it explicitly before changing its workspace."
            }
            $launch = Get-Content -LiteralPath $launchPath -Encoding UTF8 -Raw | ConvertFrom-Json
            if ($launch.launch_state -and $launch.launch_state -notin @('STARTING','READY')) {
                throw 'The launcher receipt has an unknown startup state; no server was started or stopped.'
            }
            if ($launch.pid -ne $oldPid -or $launch.port -ne $Port -or $launch.store -ne $storePath -or
                $launch.source_root -ne $install.source_root -or $launch.project_sha256 -ne $install.project_sha256 -or
                $launch.source_fingerprint -ne $sourceFingerprint -or
                -not (Test-OperatorConfigPath $launch.config_path) -or
                @($install.installed_extras | Where-Object { $_ -notin $launch.installed_extras }).Count -ne 0) {
                throw "Port $Port is running a different store, source, operator configuration or optional dependency set. Stop that owned server explicitly or choose another -Port."
            }
            $recoveringLaunch = $launch.launch_state -eq 'STARTING'
            if ($launch.process_started_utc -and
                $launch.process_started_utc -ne (Get-ProcessStart $oldPid)) {
                throw 'The launcher receipt no longer identifies the same process; no server was started or stopped.'
            }
            if ($recoveringLaunch) {
                if (-not $launch.process_started_utc) {
                    throw 'The incomplete receipt no longer identifies the same process; no server was started or stopped.'
                }
                if ([string]$launch.config_sha256 -ne [string]$configSha) {
                    throw 'Operator settings changed during startup. Stop that owned server explicitly or choose another -Port.'
                }
                if (-not (Wait-OwnedReady $oldPid $launch.process_started_utc)) {
                    throw "The recorded server is still not ready. No second server was started. Retry this command or inspect $($launch.stderr_log)."
                }
            } elseif (-not (Test-OwnedListener $oldPid) -or -not (Test-Ready)) {
                throw 'The recorded server is not ready; no second server was started. Retry or stop it explicitly.'
            }
            # Check loaded settings on EVERY reuse: receipt A -> applied B ->
            # saved A is still an unapplied change, even though receipt == disk.
            $connection = Invoke-RestMethod -Uri "$url/api/workbench/expert-connection" -TimeoutSec 3
            if ($recoveringLaunch) {
                if (-not $connection.service_session_id -or
                    -not (Test-OperatorConfigPath $connection.operator_config_path) -or
                    [string]$connection.config_sha256 -ne [string]$configSha) {
                    throw 'Startup settings could not be verified. The incomplete receipt was retained; no second server was started.'
                }
                $launch.service_session_id = $connection.service_session_id
                $launch.launch_state = 'READY'
                Write-LaunchReceipt $launch
            }
            if (-not $launch.service_session_id -or
                $connection.service_session_id -ne $launch.service_session_id -or
                -not (Test-OperatorConfigPath $connection.operator_config_path) -or
                [string]$connection.config_sha256 -ne [string]$configSha) {
                throw 'Saved operator settings are not active. Apply them in Expert Connection after current jobs finish.'
            }
            if ($launch.config_sha256 -ne $configSha) {
                $launch.config_sha256 = $configSha
                Write-LaunchReceipt $launch
            }
            $reuse = $true
        }
    }
}
if (-not $reuse) {
    if (Test-Ready) { throw "Port $Port already serves an unowned Lab process. Choose -Port or stop it first." }
    try {
        # A wildcard or other interface listener can also reserve this port.
        # Inspect every local address rather than assuming loopback-only binds.
        $existingListeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)
    } catch {
        if ($_.CategoryInfo.Category -ne 'ObjectNotFound') { throw 'The selected port could not be checked; no server was started or stopped.' }
        $existingListeners = @()
    }
    if ($existingListeners.Count) { throw "Port $Port already has a listener whose service is not verified. Choose another -Port; no server was started or stopped." }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N')
    $stdout = Join-Path $runtime ("server-$Port-$stamp.stdout.log")
    $stderr = Join-Path $runtime ("server-$Port-$stamp.stderr.log")
    # Start-Process in Windows PowerShell joins ArgumentList. Explicit quotes keep paths with spaces intact.
    $arguments = @('-m','apps.lab.server','--store',('"' + $storePath + '"'),'--port',[string]$Port)
    if ($operatorConfig) {
        $arguments += @('--workbench-config',('"' + $operatorConfig + '"'))
    }
    $hadPidFile = [IO.File]::Exists($pidPath)
    [byte[]]$previousPid = @()
    if ($hadPidFile) { $previousPid = @([IO.File]::ReadAllBytes($pidPath)) }
    $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory (Split-Path -Parent $PSScriptRoot) -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    # Keep the returned process handle open through publication and rollback.
    # A held Windows process object also prevents this PID being recycled.
    $newProcessId = $process.Id
    $newProcessHandle = $process.Handle
    $newProcessStarted = $process.StartTime.ToUniversalTime().ToString('o')
    try {
        Write-LauncherRecord $pidPath ([Text.Encoding]::UTF8.GetBytes([string]$newProcessId))
        $launch = [pscustomobject][ordered]@{pid=$newProcessId;port=$Port;store=$storePath;source_root=$install.source_root;
            service_session_id='';launch_state='STARTING';process_started_utc=(Get-ProcessStart $newProcessId);
            project_sha256=$install.project_sha256;source_fingerprint=$sourceFingerprint;
            config_path=$operatorConfig;config_sha256=$configSha;installed_extras=$install.installed_extras;
            stdout_log=$stdout;stderr_log=$stderr;launched_utc=[DateTime]::UtcNow.ToString('o')}
        Write-LaunchReceipt $launch
    } catch {
        $publicationError = $_
        try {
            if (-not $process.HasExited) {
                if ($process.Id -ne $newProcessId -or $process.Handle -ne $newProcessHandle -or
                    $process.StartTime.ToUniversalTime().ToString('o') -ne $newProcessStarted) {
                    throw 'The new launch handle no longer identifies the same process; no other PID was stopped.'
                }
                # Only the newly created, still handle-owned launch tree. This
                # includes the venv redirector's base Python child, never /IM.
                & taskkill.exe /PID $newProcessId /T /F | Out-Null
                if (($LASTEXITCODE -ne 0 -and -not $process.HasExited) -or -not $process.WaitForExit(5000)) {
                    throw "The new launch tree could not be stopped (PID $newProcessId)."
                }
            }
            if ([IO.File]::Exists($pidPath) -and [IO.File]::ReadAllText($pidPath).Trim() -eq [string]$newProcessId) {
                if ($hadPidFile) { Write-LauncherRecord $pidPath $previousPid }
                else { [IO.File]::Delete($pidPath) }
            }
        } catch {
            throw "Startup publication failed: $($publicationError.Exception.Message) Rollback also failed: $($_.Exception.Message) Logs: $stderr"
        }
        throw $publicationError
    } finally {
        $process.Dispose()
    }
    $ready = Wait-OwnedReady $newProcessId $launch.process_started_utc
    if (-not $ready) {
        $tail = if (Test-Path -LiteralPath $stderr) { (Get-Content -LiteralPath $stderr -Tail 20) -join [Environment]::NewLine } else { '' }
        throw "Lab server did not become ready at $health. Its startup receipt and logs were retained; retry this command without starting another server. $tail"
    }
    $serviceConnection = Invoke-RestMethod -Uri "$url/api/workbench/expert-connection" -TimeoutSec 3
    if (-not $serviceConnection.service_session_id -or
        -not (Test-OperatorConfigPath $serviceConnection.operator_config_path) -or
        [string]$serviceConnection.config_sha256 -ne [string]$configSha) {
        throw 'Startup settings could not be verified. The incomplete receipt was retained; retry this command.'
    }
    $launch.service_session_id = $serviceConnection.service_session_id
    $launch.launch_state = 'READY'
    Write-LaunchReceipt $launch
}
Write-Host "Autonomous CAE Lab is ready: $url"
Write-Host "Research store: $storePath"
if ($PrepareOnly) {
    Write-Output ([pscustomobject]@{ServiceUrl=$url;Python=$python;Tool=$Tool;DocumentId=$DocumentId;JobId=$JobId})
    return
}
# Native Pre/Post and Research helpers use NoBrowser for bootstrap only.
if ($NoBrowser) { return }
# Do not call start_cae_research here: it already bootstraps through this script.
$desktopTool = $Tool.ToLowerInvariant()
$arguments = @('-m','apps.research.desktop','--service',$url,$desktopTool)
if ($DocumentId) { $arguments += @('--document-id',$DocumentId) }
if ($JobId) { $arguments += @('--job-id',$JobId) }
Push-Location -LiteralPath $install.source_root
try {
    & $python @arguments
    $desktopExitCode = $LASTEXITCODE
} finally { Pop-Location }
if ($desktopExitCode -ne 0) {
    Write-Error "$Tool desktop exited with code $desktopExitCode." -ErrorAction Continue
}
exit $desktopExitCode
