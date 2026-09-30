param(
    [switch]$Install,
    [string[]]$OpenScienceArgs = @('--version')
)

$ErrorActionPreference = 'Stop'
$taskBase = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab'
$taskInstall = Join-Path $taskBase 'runtimes\openscience-2.0.146'
$taskNpmCache = Join-Path $taskBase 'cache\npm'
$taskProfile = Join-Path $taskBase 'profiles\openscience-primary-20260930'
$env:OPENSCIENCE_TEST_HOME = Join-Path $taskProfile 'home'
$env:OPENSCIENCE_CONFIG_DIR = Join-Path $taskProfile 'config'
$env:OPENSCIENCE_DATA_DIR = Join-Path $taskProfile 'data'
$env:XDG_CONFIG_HOME = Join-Path $taskProfile 'xdg-config'
$env:XDG_DATA_HOME = Join-Path $taskProfile 'xdg-data'
$env:XDG_CACHE_HOME = Join-Path $taskProfile 'xdg-cache'
$env:XDG_STATE_HOME = Join-Path $taskProfile 'xdg-state'
$env:OPENSCIENCE_DISABLE_AUTOUPDATE = '1'

@($taskInstall, $taskNpmCache, $env:OPENSCIENCE_TEST_HOME,
  $env:OPENSCIENCE_CONFIG_DIR, $env:OPENSCIENCE_DATA_DIR,
  $env:XDG_CONFIG_HOME, $env:XDG_DATA_HOME, $env:XDG_CACHE_HOME,
  $env:XDG_STATE_HOME) | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}

if ($Install) {
    $taskNpm = (Get-Command npm.cmd -ErrorAction Stop).Source
    & $taskNpm install --global=false --prefix $taskInstall --cache $taskNpmCache `
        --include=optional --no-audit --no-fund '@synsci/openscience@2.0.146'
    if ($LASTEXITCODE -ne 0) { throw 'Isolated OpenScience installation failed' }
}
$taskCli = Join-Path $taskInstall 'node_modules\@synsci\openscience\bin\openscience'
if (-not (Test-Path -LiteralPath $taskCli)) {
    throw 'The task-owned OpenScience runtime has not been installed'
}
$taskNode = (Get-Command node.exe -ErrorAction Stop).Source
# Invoke the official JavaScript launcher directly. The npm .cmd shim truncates
# multiline research prompts at the Windows command-shell boundary.
& $taskNode $taskCli @OpenScienceArgs
exit $LASTEXITCODE
