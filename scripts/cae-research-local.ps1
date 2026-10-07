# Start the shared workbench. Models and native runtimes are optional operator configuration.
[CmdletBinding()]
param(
    [string]$Store = 'runs/workbench-local',
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Python,
    [ValidateSet('Auto','Windows','WSL')][string]$Execution = 'Auto',
    [string]$Distribution = 'Ubuntu',
    [string]$DeploymentConfigPath = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab/workbench-local.json'),
    [string]$WorkbenchConfigPath,
    [string]$AssemblyMeshConfigPath,
    [string[]]$Library = @(),
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$deployment = @{}
if (Test-Path -LiteralPath $DeploymentConfigPath -PathType Leaf) {
    $deployment = Get-Content -LiteralPath $DeploymentConfigPath -Raw | ConvertFrom-Json -AsHashtable
    foreach ($key in $deployment.Keys) {
        if ($key -notin @('Store','Port','Python','Execution','Distribution','WorkbenchConfigPath','AssemblyMeshConfigPath','Library','RepoRoot')) {
            throw "Unknown local deployment setting: $key"
        }
        if (-not $PSBoundParameters.ContainsKey($key)) { Set-Variable -Name $key -Value $deployment[$key] }
    }
}
$projectRoot = [IO.Path]::GetFullPath($RepoRoot)
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'apps/lab/__main__.py') -PathType Leaf)) {
    throw 'Select the installed CAE Lab source directory.'
}
if ($Store -match '[\r\n\x00]') { throw 'The workspace must be a single local path.' }
if ($Execution -eq 'Auto') {
    $Execution = if ($Python) { 'Windows' } else { 'WSL' }
}
function Convert-WorkbenchPath([string]$Path) {
    if ($Execution -ne 'WSL' -or -not [IO.Path]::IsPathRooted($Path) -or $Path.StartsWith('/')) { return $Path }
    $translated = & wsl.exe -d $Distribution -- wslpath -a $Path.Replace('\','/')
    if ($LASTEXITCODE -ne 0 -or -not $translated) { throw 'Could not translate local path for WSL.' }
    return $translated.Trim()
}
$Store = Convert-WorkbenchPath $Store
$arguments = @('-m','apps.lab','--store',$Store,'--port',[string]$Port)
foreach ($entry in @(@($WorkbenchConfigPath,'--workbench-config'),@($AssemblyMeshConfigPath,'--assembly-mesh-config'))) {
    if ($entry[0]) {
        $config = if ($Execution -eq 'WSL' -and $entry[0].StartsWith('/')) { $entry[0] } else { [IO.Path]::GetFullPath($entry[0]) }
        if (-not $config.StartsWith('/') -and -not (Test-Path -LiteralPath $config -PathType Leaf)) { throw 'The operator configuration file is missing.' }
        $arguments += @($entry[1],(Convert-WorkbenchPath $config))
    }
}
foreach ($entry in $Library) { $arguments += @('--library',(Convert-WorkbenchPath $entry)) }
Write-Host "CAE research workbench: http://127.0.0.1:$Port/workbench"
Write-Host 'The shared controller owns execution and safe cancellation. Stop with Ctrl+C.'
Push-Location $projectRoot
try {
    if ($Execution -eq 'WSL') {
        if ($Python) { throw 'WSL uses the existing native runtime Python selected by scripts/local.ps1; do not supply a Windows Python.' }
        Write-Host "Runtime: WSL/$Distribution; Python and native paths from scripts/local.ps1"
        & (Join-Path $projectRoot 'scripts/local.ps1') -Distribution $Distribution -PythonArgs $arguments
    } else {
        if (-not $Python) { $Python = 'python' }
        Write-Host "Runtime: Windows; Python $Python"
        & $Python @arguments
    }
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $resultCode
