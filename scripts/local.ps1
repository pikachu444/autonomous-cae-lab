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
$labGitEnvironment = @()
$labWorktreePointer = Join-Path $projectRoot '.git'
if ((Test-Path -LiteralPath $labWorktreePointer -PathType Leaf) -and
    ((Get-Content -LiteralPath $labWorktreePointer -TotalCount 1) -match '^gitdir: [A-Za-z]:')) {
    # Windows Git owns this managed worktree. Its .git pointer is a Windows
    # path, so native Linux Git cannot read its source identity. This bridge is
    # local to this invocation and leaves Git configuration and PATH unchanged.
    $labHostGit = (Get-Command git.exe -ErrorAction Stop).Source
    $labHostGitWsl = (& wsl.exe -d $Distribution -- wslpath -a $labHostGit.Replace('\', '/')).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not resolve host Git for this worktree.' }
    $labBridgeInvocation = [guid]::NewGuid().ToString('N')
    $labGitBridgeDirectory = "$RuntimeRoot/windows-git-bridge-v2/$labBridgeInvocation/bin"
    & wsl.exe -d $Distribution -- mkdir -p $labGitBridgeDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Could not create task-local Git bridge.' }
    $labGitBridgeText = '#!/bin/sh' + "`n" + 'exec "$CAELAB_HOST_GIT" "$@"' + "`n"
    $labGitBridgeText | & wsl.exe -d $Distribution -- tee "$labGitBridgeDirectory/git" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not write task-local Git bridge.' }
    & wsl.exe -d $Distribution -- chmod 755 "$labGitBridgeDirectory/git"
    if ($LASTEXITCODE -ne 0) { throw 'Could not enable task-local Git bridge.' }
    $labOriginalWslPath = (& wsl.exe -d $Distribution -- printenv PATH).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the WSL command path.' }
    $labGitEnvironment = @("PATH=${labGitBridgeDirectory}:$labOriginalWslPath", "CAELAB_HOST_GIT=$labHostGitWsl")
}
& wsl.exe -d $Distribution --cd $projectWslPath -- env `
    MPLBACKEND=Agg OMP_NUM_THREADS=2 QT_QPA_PLATFORM=offscreen `
    "FREECAD_APPIMAGE=$RuntimeRoot/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage" `
    "FREECAD_CMD=$RuntimeRoot/freecad_cmd.sh" `
    "CAELAB_CODEASTER_IMAGE=$RuntimeRoot/code_aster_17.4.0-oci.sif" `
    CAELAB_CODEASTER_IMAGE_SHA256=f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64 `
    "CAELAB_OPENRADIOSS_ROOT=$RuntimeRoot/openradioss-latest-20260728/OpenRadioss" `
    CAELAB_FENICSX_PYTHON=/usr/bin/python3 @labGitEnvironment $pythonPath @PythonArgs
exit $LASTEXITCODE
