# Start the shared workbench. Models and native runtimes are optional operator configuration.
[CmdletBinding()]
param(
    [string]$Store = 'runs/workbench-local',
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$Python = 'python',
    [string]$WorkbenchConfigPath,
    [string]$AssemblyMeshConfigPath,
    [string[]]$Library = @(),
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($RepoRoot)
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'apps/lab/__main__.py') -PathType Leaf)) {
    throw 'Select the installed CAE Lab source directory.'
}
if ($Store -match '[\r\n\x00]') { throw 'The workspace must be a single local path.' }
$arguments = @('-m','apps.lab','--store',$Store,'--port',[string]$Port)
foreach ($entry in @(@($WorkbenchConfigPath,'--workbench-config'),@($AssemblyMeshConfigPath,'--assembly-mesh-config'))) {
    if ($entry[0]) {
        $config = [IO.Path]::GetFullPath($entry[0])
        if (-not (Test-Path -LiteralPath $config -PathType Leaf)) { throw 'The operator configuration file is missing.' }
        $arguments += @($entry[1],$config)
    }
}
foreach ($entry in $Library) { $arguments += @('--library',$entry) }
Write-Host "CAE research workbench: http://127.0.0.1:$Port/workbench"
Write-Host 'The shared controller owns execution and safe cancellation. Stop with Ctrl+C.'
Push-Location $projectRoot
try {
    & $Python @arguments
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $resultCode
