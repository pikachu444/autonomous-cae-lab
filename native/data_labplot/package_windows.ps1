param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$SdkRoot,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $SourceRoot).Path
$sdkPath = (Resolve-Path -LiteralPath $SdkRoot).Path
$buildPath = (Resolve-Path -LiteralPath $BuildRoot).Path
$outputPath = [IO.Path]::GetFullPath($OutputRoot)
$pythonPath = (Get-Command $Python -ErrorAction Stop).Source
$buildManifest = Get-Content -LiteralPath (Join-Path $buildPath 'caelab-build-manifest.json') -Raw | ConvertFrom-Json
if ($buildManifest.executable_sha256 -ne (Get-FileHash -LiteralPath (Join-Path $buildPath 'bin/Release/labplot.exe')).Hash) { throw 'Executable and compiled-source receipt differ; rebuild first' }
$pinned = 'ffd1eb53fcd5d033810af092a255b25cab7c93d1'
if ((& git -C $sourcePath rev-parse HEAD).Trim() -ne $pinned) { throw 'Unexpected donor source commit' }
if (Test-Path -LiteralPath $outputPath) { throw 'Choose a new package output directory; existing packages are preserved' }
& $pythonPath -c 'import pefile'
if ($LASTEXITCODE -ne 0) { throw 'The build host needs its existing free pefile library; runtime users do not' }
New-Item -ItemType Directory -Path $outputPath | Out-Null
$binPath = Join-Path $outputPath 'bin'
New-Item -ItemType Directory -Path $binPath | Out-Null
Copy-Item -LiteralPath (Join-Path $buildPath 'bin/Release/labplot.exe') -Destination $binPath
$previousPath = $env:PATH
try {
    $env:PATH = "$sdkPath/bin;$sdkPath/dev-utils/bin;$previousPath"
    & (Join-Path $sdkPath 'bin/windeployqt.exe') --release --no-translations --no-system-d3d-compiler --dir $binPath (Join-Path $binPath 'labplot.exe') 2>&1 |
        Tee-Object -FilePath (Join-Path $outputPath 'qt-deploy.log')
    if ($LASTEXITCODE -ne 0) { throw 'Qt runtime deployment failed' }
    # Resolve only the PE imports used by the executable and deployed Qt plugins.
    # Windows system DLLs remain supplied by Windows, not by the SDK package.
    $dependencyScript = @'
import hashlib, json, os, pathlib, shutil, sys
import pefile
sdk, root = map(pathlib.Path, sys.argv[1:])
system = pathlib.Path(os.environ['SystemRoot']) / 'System32'
pending = list(root.rglob('*.exe')) + list(root.rglob('*.dll'))
seen, unresolved = set(), set()
while pending:
    path = pending.pop()
    if path.name.lower() in seen:
        continue
    seen.add(path.name.lower())
    with pefile.PE(str(path), fast_load=True) as pe:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'], pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
        names = [entry.dll.decode('ascii') for kind in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT') for entry in getattr(pe, kind, [])]
    for name in names:
        if name.lower().startswith(('api-ms-', 'ext-ms-')):
            continue
        compiler_runtime = name.lower().startswith(('vcruntime', 'msvcp', 'concrt', 'vcomp'))
        if (system / name).is_file() and not compiler_runtime:
            continue
        target = root / name
        if not target.is_file():
            source = sdk / 'bin' / name
            if not source.is_file():
                unresolved.add(name)
                continue
            shutil.copy2(source, target)
        pending.append(target)
if unresolved:
    raise SystemExit('Unresolved non-system runtime imports: ' + ', '.join(sorted(unresolved)))
(root.parent / 'runtime-imports.json').write_text(json.dumps(sorted(seen), indent=2), encoding='utf-8')
'@
    $dependencyScript | & $pythonPath - $sdkPath $binPath
    if ($LASTEXITCODE -ne 0) { throw 'Runtime PE dependency resolution failed' }

    # Qt and KF use different catalog locations. Keep their installed paths.
    $translations = Join-Path $binPath 'translations'
    New-Item -ItemType Directory -Path $translations | Out-Null
    foreach ($name in @('qt_ko.qm', 'qtbase_ko.qm')) {
        Copy-Item -LiteralPath (Join-Path $sdkPath "translations/$name") -Destination $translations
    }
    $locale = Join-Path $binPath 'data/locale/ko/LC_MESSAGES'
    New-Item -ItemType Directory -Path $locale -Force | Out-Null
    Copy-Item -Path (Join-Path $sdkPath 'bin/data/locale/ko/LC_MESSAGES/*') -Destination $locale
    $donorCatalog = Join-Path $buildPath 'locale/ko/LC_MESSAGES/labplot.mo'
    if (!(Test-Path -LiteralPath $donorCatalog)) {
        & (Join-Path $sdkPath 'bin/msgfmt.exe') -o (Join-Path $locale 'labplot.mo') (Join-Path $sourcePath 'po/ko/labplot.po')
        if ($LASTEXITCODE -ne 0) { throw 'Korean LabPlot catalog compilation failed' }
    } else { Copy-Item -LiteralPath $donorCatalog -Destination $locale }
    $dataPath = Join-Path $binPath 'data/labplot'
    New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
    foreach ($name in @('themes', 'color-schemes', 'colormaps', 'pics')) {
        Copy-Item -LiteralPath (Join-Path $sourcePath "data/$name") -Destination $dataPath -Recurse
    }
    Copy-Item -LiteralPath (Join-Path $sourcePath 'src/frontend/labplot.ico') -Destination $dataPath
    Copy-Item -LiteralPath (Join-Path $sourcePath 'src/frontend/splash.png') -Destination $dataPath
    '[Paths]' + "`nPrefix=.`nPlugins=.`nTranslations=translations`n" | Set-Content -LiteralPath (Join-Path $binPath 'qt.conf') -Encoding utf8

    $corresponding = Join-Path $outputPath 'corresponding-source'
    New-Item -ItemType Directory -Path $corresponding | Out-Null
    $archivePath = Join-Path $corresponding 'labplot-pinned-source.zip'
    & git -C $sourcePath archive --format=zip "--output=$archivePath" $pinned
    if ($LASTEXITCODE -ne 0) { throw 'Pinned donor source archive failed' }
    foreach ($name in @('CaelabDataBridge.h','CaelabDataSettings.h','CaelabDataProperties.h','patches')) {
        Copy-Item -LiteralPath (Join-Path $buildPath "caelab-compiled-source/$name") -Destination $corresponding -Recurse
    }
    Copy-Item -LiteralPath (Join-Path $buildPath 'caelab-build-manifest.json') -Destination $outputPath
    foreach ($name in @('build_windows.ps1','package_windows.ps1','NOTICE.md','LICENSES')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $corresponding -Recurse
    }
    $licenses = Join-Path $outputPath 'LICENSES'
    New-Item -ItemType Directory -Path $licenses | Out-Null
    Copy-Item -Path (Join-Path $sourcePath 'LICENSES/*') -Destination $licenses -Recurse
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'NOTICE.md') -Destination $outputPath
    @'
This local runtime is built from KDE LabPlot ffd1eb53fcd5d033810af092a255b25cab7c93d1
with the included GPL-2.0-or-later bridge/settings/properties and patches. Its full pinned
donor source, adapter source and build/package instructions are included under
corresponding-source. The runtime includes Qt 6.11.1, KDE Frameworks 6 and the
actual imported libraries listed in runtime-imports.json; Breeze icons are in
KF6BreezeIcons.dll. Per-file hashes are in package-manifest.json.

This is a private local acceptance package, not a public binary publication.
Before redistributing, provide the exact corresponding sources and license
notices for every included LGPL/GPL dependency, including local patches/build
options, under its applicable license. Qt sources: https://download.qt.io/archive/qt/
KDE sources: https://download.kde.org/stable/frameworks/
The SDK's matching source downloads/build records must be used to complete that
distribution set. Microsoft runtime files retain Microsoft's redistribution
terms. This manifest records outstanding source obligations; an upstream URL
alone is not represented as satisfying them. Do not ship the developer SDK.
'@ | Set-Content -LiteralPath (Join-Path $outputPath 'SOURCE-OBLIGATIONS.txt') -Encoding utf8
    $files = @(Get-ChildItem -LiteralPath $outputPath -File -Recurse | Sort-Object FullName | ForEach-Object {
        @{ path = [IO.Path]::GetRelativePath($outputPath, $_.FullName).Replace('\','/'); bytes = $_.Length;
           sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    @{ donor_commit=$pinned; qt_version='6.11.1'; executable='bin/labplot.exe'; files=$files;
       source_obligations='SOURCE-OBLIGATIONS.txt'; purpose='local runtime acceptance; no developer SDK at runtime' } |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputPath 'package-manifest.json') -Encoding utf8
    Write-Output "Prepared runtime: $binPath/labplot.exe"
} finally { $env:PATH = $previousPath }
