[CmdletBinding()]
param(
    [string]$Python,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$taskRoot = [IO.Path]::GetFullPath((Join-Path $sourceRoot '..\..\..'))
$workRoot = [IO.Path]::GetFullPath((Join-Path $taskRoot 'work'))
$distRoot = [IO.Path]::GetFullPath((Join-Path $workRoot 'native-dist'))
$buildRoot = [IO.Path]::GetFullPath((Join-Path $workRoot 'native-build'))
$bundle = [IO.Path]::GetFullPath((Join-Path $distRoot 'CAELab'))
$entry = Join-Path $sourceRoot 'desktop.py'

function Assert-ChildPath([string]$Path, [string]$Parent) {
    $resolved = [IO.Path]::GetFullPath($Path)
    $base = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target is outside the expected workspace: $resolved"
    }
    return $resolved
}

$distRoot = Assert-ChildPath $distRoot $taskRoot
$buildRoot = Assert-ChildPath $buildRoot $taskRoot
$bundle = Assert-ChildPath $bundle $distRoot

if (-not $Python) { $Python = Join-Path $workRoot 'qt-prototype-venv\Scripts\python.exe' }
$Python = [IO.Path]::GetFullPath($Python)
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python not found: $Python" }
if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) { throw "Entry point not found: $entry" }

& $Python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller is not installed in the selected environment.' }

$apps = @(
    @{ Name = 'Preprocessor'; Kind = 'pre'; File = 'pre.caeprep' },
    @{ Name = 'Solver-Runner'; Kind = 'runner'; File = 'runner.caerun' },
    @{ Name = 'Postprocessor'; Kind = 'post'; File = 'post.caepost' },
    @{ Name = 'Optimizer'; Kind = 'opt'; File = 'opt.caestudy' },
    @{ Name = 'Expert'; Kind = 'expert'; File = 'expert.caechat' },
    @{ Name = 'Workbench'; Kind = 'workbench'; File = 'workbench.caeproject' }
)
$examplesRoot = Join-Path $sourceRoot 'examples'

if ($ValidateOnly) {
    Write-Output "Source: $sourceRoot"
    Write-Output "Python: $Python"
    Write-Output "Output: $bundle"
    foreach ($app in $apps) {
        $path = Join-Path $examplesRoot $app.File
        Write-Output "Example $($app.Kind): $(Test-Path -LiteralPath $path -PathType Leaf) $path"
    }
    return
}

$chartImports = Get-ChildItem -LiteralPath $sourceRoot -Filter '*.py' -File |
    Select-String -Pattern 'PySide6\.QtCharts|\bQtCharts\b'
if ($chartImports) { throw 'QtCharts remains in the source. Convert to pyqtgraph before packaging.' }
foreach ($app in $apps) {
    $path = Join-Path $examplesRoot $app.File
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Example missing: $path" }
}
$exampleHistory = Join-Path $examplesRoot '.history'
if (-not (Test-Path -LiteralPath $exampleHistory -PathType Container)) {
    throw "Example revision history missing: $exampleHistory"
}

# The only recursive removal is of this task's verified build and bundle paths.
if (Test-Path -LiteralPath $bundle) { Remove-Item -LiteralPath $bundle -Recurse -Force }
if (Test-Path -LiteralPath $buildRoot) { Remove-Item -LiteralPath $buildRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $distRoot, $buildRoot | Out-Null

& $Python -m PyInstaller --noconfirm --onedir --windowed --name CAELab `
    --distpath $distRoot --workpath $buildRoot --specpath $buildRoot `
    --paths $sourceRoot `
    --hidden-import workspaces --hidden-import collaboration_spaces --hidden-import native_pre `
    --exclude-module PySide6.QtCharts --exclude-module PySide6.QtGraphs `
    $entry
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

$exe = Join-Path $bundle 'CAELab.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Executable missing: $exe" }
# Qt 6.11.2 imports unversioned Windows ICU symbols. PyInstaller 6.16.0
# picks up an ICU 78 DLL with version-suffixed exports; that DLL shadows the
# compatible Windows system ICU and causes QtCore import to fail. Preserve the
# two picked-up files under build artifacts rather than shipping them.
$icuHold = Assert-ChildPath (Join-Path $buildRoot 'excluded-icu') $buildRoot
New-Item -ItemType Directory -Force -Path $icuHold | Out-Null
foreach ($name in @('icuuc.dll', 'icudt78.dll')) {
    $candidate = Assert-ChildPath (Join-Path $bundle "_internal\$name") $bundle
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        Move-Item -LiteralPath $candidate -Destination (Join-Path $icuHold $name)
    }
}
$chartFiles = Get-ChildItem -LiteralPath $bundle -Recurse -File |
    Where-Object { $_.Name -match '(?i)qtcharts|qt6charts' }
if ($chartFiles) { throw "QtCharts binary was bundled: $($chartFiles[0].FullName)" }

$bundleExamples = Join-Path $bundle 'examples'
$bundleData = Join-Path $bundle 'user-data'
$licenseRoot = Join-Path $bundle 'licenses'
New-Item -ItemType Directory -Force -Path $bundleExamples, $bundleData, $licenseRoot | Out-Null
foreach ($app in $apps) {
    Copy-Item -LiteralPath (Join-Path $examplesRoot $app.File) -Destination (Join-Path $bundleExamples $app.File)
    $launcher = @'
@echo off
setlocal
start "" "%~dp0CAELab.exe" --app __KIND__ --file "%~dp0examples\__FILE__"
'@.Replace('__KIND__', $app.Kind).Replace('__FILE__', $app.File)
    [IO.File]::WriteAllText((Join-Path $bundle ("Start-$($app.Name).cmd")), $launcher + "`r`n", [Text.Encoding]::ASCII)
}
Copy-Item -LiteralPath $exampleHistory -Destination (Join-Path $bundleExamples '.history') -Recurse -Force

$sitePackages = Join-Path (Split-Path $Python -Parent) '..\Lib\site-packages'
Copy-Item -LiteralPath (Join-Path $sitePackages 'pyqtgraph-0.14.0.dist-info\licenses\LICENSE.txt') `
    -Destination (Join-Path $licenseRoot 'pyqtgraph-MIT.txt')
Copy-Item -LiteralPath (Join-Path $sitePackages 'pyinstaller-6.16.0.dist-info\licenses\COPYING.txt') `
    -Destination (Join-Path $licenseRoot 'PyInstaller-COPYING.txt')
foreach ($name in @('LGPL-3.0.txt', 'GPL-2.0.txt', 'GPL-3.0.txt', 'NumPy-BSD-3-Clause.txt', 'SciPy-BSD-3-Clause.txt')) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot "licenses\$name") -Destination (Join-Path $licenseRoot $name)
}
Copy-Item -LiteralPath (Join-Path $sourceRoot 'THIRD_PARTY_NOTICES.txt') -Destination $bundle
Copy-Item -LiteralPath (Join-Path $sourceRoot 'README.md') -Destination $bundle

Write-Output "Built: $exe"
Write-Output "Launchers: $($apps.Count)"
Write-Output "Writable data: $bundleData"
