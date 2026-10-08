param(
    [string]$Project,
    [string]$ParaViewHome,
    [string]$OutputDirectory,
    [string]$Python = 'python',
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$postHome = Join-Path $repoRoot 'apps/desktop_post'
if (-not $ParaViewHome) {
    $ParaViewHome = Join-Path $repoRoot 'runs/prepost-session-20261008-01/tools/ParaView-6.2.0-Windows-Python3.12-msvc2017-AMD64'
}
$nativeGui = Join-Path $ParaViewHome 'bin/paraview.exe'
$nativePython = Join-Path $ParaViewHome 'bin/pvpython.exe'
if (-not (Test-Path -LiteralPath $nativeGui) -or -not (Test-Path -LiteralPath $nativePython)) {
    throw 'ParaView 6.2 portable runtime is missing. Pass -ParaViewHome with its extracted directory.'
}
if (-not $Project) {
    if (-not $OutputDirectory) {
        $runId = 'desktop-post-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0, 6))
        $OutputDirectory = Join-Path $repoRoot ('runs/' + $runId)
    }
    & $Python (Join-Path $postHome 'prepare.py') --output $OutputDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Retained source preparation failed.' }
    $Project = Join-Path $OutputDirectory 'project.json'
    & $nativePython --force-offscreen-rendering (Join-Path $postHome 'build_workspace.py') $Project
    if ($LASTEXITCODE -ne 0) { throw 'Native ParaView workspace build failed.' }
}
$Project = (Resolve-Path -LiteralPath $Project).Path
$document = Get-Content -Raw -LiteralPath $Project | ConvertFrom-Json
$projectFolder = Split-Path -Parent $Project
$state = Join-Path $projectFolder $document.workspace_file
if (-not (Test-Path -LiteralPath $state)) { throw 'The project has no prepared ParaView state.' }
if ($PrepareOnly) {
    Write-Output $Project
    return
}
# Only this child receives the app's command directory and project. User settings
# and retained source directories are never edited by the launcher.
if (-not (Get-Command Start-Process).Parameters.ContainsKey('Environment')) {
    throw 'Launching CAE Post requires PowerShell 7.4 or later for child-only environment values.'
}
$nativeArgs = '--disable-registry --script="{0}" --log="{1}"' -f (Join-Path $postHome 'startup.py'), (Join-Path $projectFolder 'native_gui.log')
$childEnvironment = @{
    PV_MACRO_PATH = Join-Path $postHome 'macros'
    CAE_POST_HOME = $postHome
    CAE_POST_PROJECT = $Project
}
$process = Start-Process -FilePath $nativeGui -ArgumentList $nativeArgs -WorkingDirectory $projectFolder -Environment $childEnvironment -PassThru -WindowStyle Normal
Write-Output ([pscustomobject]@{ProcessId=$process.Id;Project=$Project;State=$state})
