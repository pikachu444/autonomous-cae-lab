param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$SdkRoot,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [switch]$PatchOnly
)
$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $SourceRoot).Path
$sdkPath = (Resolve-Path -LiteralPath $SdkRoot).Path
$buildPath = [IO.Path]::GetFullPath($BuildRoot)
$pinned = 'ffd1eb53fcd5d033810af092a255b25cab7c93d1'
$actual = (& git -C $sourcePath rev-parse HEAD).Trim()
if ($actual -ne $pinned) { throw "Expected LabPlot $pinned; found $actual" }
$patchReceipts = Join-Path $buildPath 'caelab-applied-patches'
New-Item -ItemType Directory -Path $patchReceipts -Force | Out-Null
foreach ($patch in Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'patches') -Filter '*.patch' | Sort-Object Name) {
    $priorPatch = Join-Path $patchReceipts $patch.Name
    & git -C $sourcePath apply --reverse --check $patch.FullName 2>$null
    if ($LASTEXITCODE -ne 0) {
        $reversedPrior = $false
        if ((Test-Path -LiteralPath $priorPatch) -and
            [IO.File]::ReadAllText($priorPatch) -cne [IO.File]::ReadAllText($patch.FullName)) {
            & git -C $sourcePath apply --reverse --check $priorPatch
            if ($LASTEXITCODE -ne 0) { throw "Previous patch has local edits; preserve them before updating: $($patch.Name)" }
            & git -C $sourcePath apply --reverse $priorPatch
            if ($LASTEXITCODE -ne 0) { throw "Could not reverse the prior owned patch: $($patch.Name)" }
            $reversedPrior = $true
        }
        & git -C $sourcePath apply --check $patch.FullName
        if ($LASTEXITCODE -ne 0) {
            if ($reversedPrior) { & git -C $sourcePath apply $priorPatch }
            throw "Patch does not apply cleanly: $($patch.Name)"
        }
        & git -C $sourcePath apply $patch.FullName
        if ($LASTEXITCODE -ne 0) { throw "Could not apply: $($patch.Name)" }
    }
    Copy-Item -LiteralPath $patch.FullName -Destination $priorPatch
}
$adapterSource = Join-Path $PSScriptRoot 'CaelabDataBridge.h'
$adapterTarget = Join-Path $sourcePath 'src/frontend/CaelabDataBridge.h'
if (!(Test-Path -LiteralPath $adapterTarget) -or
    [IO.File]::ReadAllText($adapterSource) -cne [IO.File]::ReadAllText($adapterTarget)) {
    Copy-Item -LiteralPath $adapterSource -Destination $adapterTarget
}
$settingsSource = Join-Path $PSScriptRoot 'CaelabDataSettings.h'
$settingsTarget = Join-Path $sourcePath 'src/frontend/CaelabDataSettings.h'
if (!(Test-Path -LiteralPath $settingsTarget) -or
    [IO.File]::ReadAllText($settingsSource) -cne [IO.File]::ReadAllText($settingsTarget)) {
    Copy-Item -LiteralPath $settingsSource -Destination $settingsTarget
}
$propertiesSource = Join-Path $PSScriptRoot 'CaelabDataProperties.h'
$propertiesTarget = Join-Path $sourcePath 'src/frontend/CaelabDataProperties.h'
if (!(Test-Path -LiteralPath $propertiesTarget) -or
    [IO.File]::ReadAllText($propertiesSource) -cne [IO.File]::ReadAllText($propertiesTarget)) {
    Copy-Item -LiteralPath $propertiesSource -Destination $propertiesTarget
}
if ($PatchOnly) { return }
$cmakePath = Join-Path $sdkPath 'dev-utils/bin/cmake.exe'
if (-not (Test-Path -LiteralPath $cmakePath)) { throw "Craft CMake is missing: $cmakePath" }
$previousPath = $env:PATH
try {
    $env:PATH = "$sdkPath/bin;$sdkPath/dev-utils/bin;$sdkPath/msys/usr/bin;$previousPath"
    New-Item -ItemType Directory -Path $buildPath -Force | Out-Null
    $configure = @('-S', $sourcePath, '-B', $buildPath, '-G', 'Visual Studio 17 2022', '-A', 'x64',
        "-DCMAKE_PREFIX_PATH=$sdkPath", "-DECM_DIR=$sdkPath/share/ECM/cmake", '-DENABLE_REPRODUCIBLE=ON')
    # Keep MainWin, ProjectExplorer, Spreadsheet/Worksheet, Undo, properties and QADS.
    # Optional import formats, embedded runtimes and SDKs are outside this trial.
    foreach ($feature in @('TESTS','SDK','SDK_EXAMPLES','PYTHON_SDK','PYTHON_SCRIPTING','CANTOR','FFTW',
        'HDF5','NETCDF','FITS','LIBCERF','LIBORIGIN','ROOT','READSTAT','MATIO','MQTT','QTSERIALPORT',
        'QTSVG','DISCOUNT','XLSX','ORCUS','VECTOR_BLF','EIGEN3','MCAP','TOUCHBAR','PARQUET')) {
        $configure += "-DENABLE_${feature}=OFF"
    }
    # Native CMake warnings on stderr are diagnostics; exit codes decide failure.
    $ErrorActionPreference = 'Continue'
    & $cmakePath @configure 2>&1 | Tee-Object -FilePath (Join-Path $buildPath 'configure.log')
    if ($LASTEXITCODE -ne 0) { throw 'Pinned LabPlot configure failed; see configure.log' }
    & $cmakePath --build $buildPath --config Release --parallel 4 2>&1 |
        Tee-Object -FilePath (Join-Path $buildPath 'build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Pinned LabPlot build failed; see build.log' }
    $snapshotPath = Join-Path $buildPath 'caelab-compiled-source'
    New-Item -ItemType Directory -Path $snapshotPath -Force | Out-Null
    Copy-Item -LiteralPath $adapterTarget -Destination $snapshotPath
    Copy-Item -LiteralPath $settingsTarget -Destination $snapshotPath
    Copy-Item -LiteralPath $propertiesTarget -Destination $snapshotPath
    New-Item -ItemType Directory -Path (Join-Path $snapshotPath 'patches') -Force | Out-Null
    Copy-Item -Path (Join-Path $patchReceipts '*.patch') -Destination (Join-Path $snapshotPath 'patches') -Force
    $executablePath = Join-Path $buildPath 'bin/Release/labplot.exe'
    @{ donor_commit=$pinned; executable_sha256=(Get-FileHash -LiteralPath $executablePath).Hash;
       bridge_sha256=(Get-FileHash -LiteralPath $adapterTarget).Hash;
       settings_sha256=(Get-FileHash -LiteralPath $settingsTarget).Hash;
       properties_sha256=(Get-FileHash -LiteralPath $propertiesTarget).Hash } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildPath 'caelab-build-manifest.json') -Encoding utf8
} finally {
    $ErrorActionPreference = 'Stop'
    $env:PATH = $previousPath
}
