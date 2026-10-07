param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]]$PythonArgs,
    [string]$Distribution = 'Ubuntu',
    [string]$RuntimeRoot
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'windows-git-transport.ps1')
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
if ((Get-OpenScienceMcpGitTransportMode -RepoRoot $projectRoot) -cne 'NATIVE_WSL_GIT') {
    # Windows Git owns this drive checkout or managed Windows gitdir. Reuse
    # the tracked, inert-config bridge only for this Python invocation.
    $labHostGit = (Get-Command git.exe -ErrorAction Stop).Source
    $labHostGitWsl = (& wsl.exe -d $Distribution -- wslpath -a $labHostGit.Replace('\', '/')).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not resolve host Git for this checkout.' }
    $labGitBridge = Join-Path $projectRoot 'scripts/wsl-windows-git/git'
    $labGitConfig = Join-Path $projectRoot 'scripts/wsl-windows-git/empty.config'
    $labExpectedBridge = (@('#!/bin/sh', '[ -n "$CAELAB_GIT_CONFIG" ] && [ -f "$CAELAB_GIT_CONFIG" ] || exit 125',
        'GIT_CONFIG_GLOBAL="$CAELAB_GIT_CONFIG"', 'GIT_CONFIG_NOSYSTEM=1', 'GIT_TERMINAL_PROMPT=0',
        'WSLENV=GIT_CONFIG_GLOBAL/p:GIT_CONFIG_NOSYSTEM:GIT_TERMINAL_PROMPT',
        'export GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM GIT_TERMINAL_PROMPT WSLENV',
        'exec "$CAELAB_HOST_GIT" "$@"') -join [char]10) + [char]10
    $labExpectedConfig = '# CAE provenance probes use no global Git settings.' + [char]10
    foreach ($labGitSource in @(@($labGitBridge, $labExpectedBridge), @($labGitConfig, $labExpectedConfig))) {
        $labExpectedHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
            [Text.UTF8Encoding]::new($false).GetBytes($labGitSource[1]))).ToLowerInvariant()
        if (-not (Test-Path -LiteralPath $labGitSource[0] -PathType Leaf) -or
            (Get-FileHash -LiteralPath $labGitSource[0] -Algorithm SHA256).Hash.ToLowerInvariant() -cne $labExpectedHash) {
            throw 'Local Git bridge and inert config must retain their exact tracked LF-only source.'
        }
    }
    $labGitBridgeDirectory = (& wsl.exe -d $Distribution -- wslpath -a (Split-Path -Parent $labGitBridge).Replace('\', '/')).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the tracked Git bridge.' }
    $labGitConfigWsl = (& wsl.exe -d $Distribution -- wslpath -a $labGitConfig.Replace('\', '/')).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the inert Git config.' }
    $labOriginalWslPath = & wsl.exe -d $Distribution -- printenv PATH
    if ($LASTEXITCODE -ne 0 -or @($labOriginalWslPath).Count -ne 1 -or
        -not $labOriginalWslPath -or $labOriginalWslPath -match '[\r\n]') { throw 'Could not read the existing one-line WSL command path.' }
    $labGitEnvironment = @("PATH=${labGitBridgeDirectory}:$labOriginalWslPath", "CAELAB_HOST_GIT=$labHostGitWsl", "CAELAB_GIT_CONFIG=$labGitConfigWsl")
}
$labOptionalEnvironment = @()
$labNativeConfig = "$RuntimeRoot/native-environment.json"
& wsl.exe -d $Distribution -- test -f $labNativeConfig
if ($LASTEXITCODE -eq 0) {
    $labNativeValues = (& wsl.exe -d $Distribution -- cat $labNativeConfig) | ConvertFrom-Json -AsHashtable
    foreach ($labNativeKey in $labNativeValues.Keys) {
        if ($labNativeKey -notin @('CAELAB_MFRONT_PREPARED_LIBRARY','CAELAB_MFRONT_PREPARED_LIBRARY_SHA256')) {
            throw 'Unknown operator native runtime registration.'
        }
        $labOptionalEnvironment += "$labNativeKey=$($labNativeValues[$labNativeKey])"
    }
}
& wsl.exe -d $Distribution --cd $projectWslPath -- env `
    MPLBACKEND=Agg OMP_NUM_THREADS=2 QT_QPA_PLATFORM=offscreen `
    "FREECAD_APPIMAGE=$RuntimeRoot/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage" `
    "FREECAD_CMD=$RuntimeRoot/freecad_cmd.sh" `
    "CAELAB_CODEASTER_IMAGE=$RuntimeRoot/code_aster_17.4.0-oci.sif" `
    CAELAB_CODEASTER_IMAGE_SHA256=f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64 `
    "CAELAB_OPENRADIOSS_ROOT=$RuntimeRoot/opencourant-latest-20261006/OpenCourant" `
    CAELAB_FENICSX_PYTHON=/usr/bin/python3 @labGitEnvironment @labOptionalEnvironment $pythonPath @PythonArgs
exit $LASTEXITCODE
