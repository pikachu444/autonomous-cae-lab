param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]]$PythonArgs,
    [string]$Distribution = 'Ubuntu',
    [string]$RuntimeRoot
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$resolvedProjectPath = & wsl.exe -d $Distribution -- wslpath -a $projectRoot.Replace('\', '/')
if ($LASTEXITCODE -ne 0 -or -not $resolvedProjectPath) {
    throw 'Could not resolve the project path in WSL.'
}
$projectWslPath = $resolvedProjectPath.Trim()
if (-not $RuntimeRoot) {
    $linuxHomePath = (& wsl.exe -d $Distribution -- printenv HOME).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the WSL user directory.' }
    $RuntimeRoot = "$linuxHomePath/.local/share/autonomous-cae-lab"
}
$pythonPath = "$RuntimeRoot/venv-py312/bin/python"
& wsl.exe -d $Distribution -- test -x $pythonPath
if ($LASTEXITCODE -ne 0) { throw "Project Python environment is missing: $pythonPath" }
& wsl.exe -d $Distribution --cd $projectWslPath -- env `
    MPLBACKEND=Agg OMP_NUM_THREADS=2 QT_QPA_PLATFORM=offscreen `
    "FREECAD_APPIMAGE=$RuntimeRoot/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage" `
    "FREECAD_CMD=$RuntimeRoot/freecad_cmd.sh" `
    CAELAB_FENICSX_PYTHON=/usr/bin/python3 $pythonPath @PythonArgs
exit $LASTEXITCODE
