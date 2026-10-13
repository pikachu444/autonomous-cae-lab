# Optional pinned native package. No solver, PATH, registry, service or WSL changes.
[CmdletBinding()]
param(
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\runtimes\opencourant-windows-20261011'),
    [string]$Archive
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$release = 'latest-20261011'
$archiveName = 'OpenCourant_win64.zip'
$archiveSha = '6d0ea8b43b68aa12f0a2787b339384a554978cbb65a5d3dbaf1e40598f02e7e6'
$archiveUrl = "https://github.com/OpenCourant/OpenCourant/releases/download/$release/$archiveName"

function Get-FileDigest([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose(); $stream.Dispose() }
}

function Save-ArchiveCache([string]$InputArchive, [string]$Cached, [string]$OwnedDownload, [string]$ExpectedSha) {
    if (Test-Path -LiteralPath $Cached) {
        Assert-PlainPath $Cached
        if ((Get-FileDigest $Cached) -ne $ExpectedSha) {
            throw "Existing archive cache differs and was not replaced: $Cached"
        }
    } elseif ($OwnedDownload -and $InputArchive -eq $OwnedDownload) {
        [IO.File]::Move($InputArchive, $Cached)
    } else {
        # Offline input belongs to its caller, regardless of the file suffix.
        $partialCopy = $Cached + '.' + [guid]::NewGuid().ToString('N') + '.partial'
        [IO.File]::Copy($InputArchive, $partialCopy, $false)
        if ((Get-FileDigest $partialCopy) -ne $ExpectedSha) {
            throw "Archive changed while copying. Partial data is retained at $partialCopy"
        }
        [IO.File]::Move($partialCopy, $Cached)
    }
}

function Assert-PlainPath([string]$Path) {
    $probe = [IO.Path]::GetFullPath($Path)
    while ($probe) {
        if (Test-Path -LiteralPath $probe) {
            $item = Get-Item -LiteralPath $probe -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Linked installation paths are not supported: $probe. Select a separate ordinary folder."
            }
        }
        $parent = [IO.Path]::GetDirectoryName($probe)
        if ($parent -eq $probe) { break }
        $probe = $parent
    }
}

function Get-PackageLayout($Zip) {
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $files = @{}
    $paths = @{'OpenCourant' = $true}
    foreach ($entry in $Zip.Entries) {
        $name = $entry.FullName
        $clean = $name.TrimEnd('/')
        if ($name.Contains('\') -or $name.Contains(':') -or $name.StartsWith('/') -or
            ($clean -ne 'OpenCourant' -and -not $clean.StartsWith('OpenCourant/'))) {
            throw "Unsafe ZIP path or unexpected package root: $name"
        }
        foreach ($part in $clean.Split('/')) {
            if (-not $part -or $part -in @('.', '..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or
                $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$') {
                throw "Unsafe ZIP path: $name"
            }
        }
        if (($entry.ExternalAttributes -band 0x400) -or
            (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) {
            throw "Linked ZIP entries are not supported: $name"
        }
        if (-not $seen.Add($clean)) { throw "Duplicate ZIP path: $name" }
        $paths[$clean] = $true
        $parent = $clean
        while ($parent.Contains('/')) {
            $parent = $parent.Substring(0, $parent.LastIndexOf('/'))
            $paths[$parent] = $true
        }
        if (-not $name.EndsWith('/')) { $files[$clean] = $entry }
    }
    foreach ($required in @('exec/starter_win64.exe', 'exec/engine_win64.exe',
        'exec/anim_to_vtk_win64.exe', 'exec/th_to_csv_win64.exe', 'COPYRIGHT.md',
        'licenses/hm_reader_license.txt', 'licenses/h3d_license.txt',
        'extlib/intelOneAPI_runtime/license/NOTICE.txt',
        'extlib/hm_reader/win64/hm_reader_win64.dll', 'extlib/h3d/lib/win64/h3dwriter.dll')) {
        if (-not $files.ContainsKey('OpenCourant/' + $required)) {
            throw "The package is incomplete: $required is missing."
        }
    }
    if (-not @($files.Keys | Where-Object { $_.StartsWith('OpenCourant/hm_cfg_files/') }).Count) {
        throw 'The package has no reader configuration files.'
    }
    return @{Files = $files; Paths = $paths}
}

function Get-PackageHashes($Layout) {
    $hashes = [ordered]@{}
    foreach ($name in ($Layout.Files.Keys | Sort-Object)) {
        $stream = $Layout.Files[$name].Open()
        $hash = [Security.Cryptography.SHA256]::Create()
        try { $hashes[$name] = [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $hash.Dispose(); $stream.Dispose() }
    }
    return $hashes
}

function Assert-PackageFiles([string]$Parent, $Layout, $Hashes) {
    $package = Join-Path $Parent 'OpenCourant'
    Assert-PlainPath $package
    if (-not (Test-Path -LiteralPath $package -PathType Container)) {
        throw "The package folder is missing or is a file: $package"
    }
    $folders = New-Object 'System.Collections.Generic.Stack[string]'
    $folders.Push($package)
    $count = 0
    while ($folders.Count) {
        foreach ($item in (Get-ChildItem -LiteralPath $folders.Pop() -Force)) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Existing installation contains a link and was not changed: $($item.FullName)"
            }
            $name = $item.FullName.Substring($Parent.Length + 1).Replace('\', '/')
            if (-not $Layout.Paths.ContainsKey($name)) {
                throw "Existing installation has an additional item and was not changed: $($item.FullName)"
            }
            if ($item.PSIsContainer) { $folders.Push($item.FullName); continue }
            if (-not $Layout.Files.ContainsKey($name) -or
                (Get-FileDigest $item.FullName) -ne $Hashes[$name]) {
                throw "Existing installation has a modified file and was not changed: $($item.FullName)"
            }
            $count++
        }
    }
    if ($count -ne $Hashes.Count) {
        throw "Existing installation is incomplete and was not changed: $package. Select a new RuntimeRoot or restore the original files."
    }
}

# Tests may dot-source the validation helpers; installation always uses the fixed pin.
if ($MyInvocation.InvocationName -eq '.') { return }
if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess -or $env:OS -ne 'Windows_NT') {
    throw 'Use 64-bit Windows PowerShell on x64 Windows 10 or 11.'
}
$runtime = [IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\', '/')
if ($runtime -eq [IO.Path]::GetPathRoot($runtime).TrimEnd('\', '/')) { throw 'Select a separate installation folder, not a drive root.' }
Assert-PlainPath $runtime
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$lock = $null
$zip = $null
$archiveGuard = $null
$downloadPartial = $null
try {
    try { $lock = [IO.File]::Open((Join-Path $runtime '.install.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
    catch { throw 'This RuntimeRoot is already being installed or is not writable. Existing files were not changed.' }
    $cached = Join-Path $runtime $archiveName
    $inputArchive = if ($Archive) { [IO.Path]::GetFullPath($Archive) } else { $cached }
    Assert-PlainPath $inputArchive
    if ($Archive -and -not (Test-Path -LiteralPath $inputArchive -PathType Leaf)) {
        throw "The offline archive does not exist: $inputArchive"
    }
    if (-not (Test-Path -LiteralPath $inputArchive -PathType Leaf)) {
        $partial = $cached + '.' + [guid]::NewGuid().ToString('N') + '.partial'
        $downloadPartial = $partial
        Write-Host "Downloading the optional Windows package: $archiveUrl"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        try { Invoke-WebRequest -Uri $archiveUrl -OutFile $partial -UseBasicParsing }
        catch { throw "Download did not complete. Partial data is retained at $partial. Use -Archive with a complete official ZIP to retry. $($_.Exception.Message)" }
        $inputArchive = $partial
    }
    # Keep the verified bytes stable through extraction and existing-file comparison.
    $archiveGuard = [IO.File]::Open($inputArchive, 'Open', 'Read', 'Read')
    $found = Get-FileDigest $inputArchive
    if ($found -ne $archiveSha) {
        throw "Archive checksum mismatch. File retained at $inputArchive. Expected the official $release Windows ZIP; no package files were changed."
    }
    if (Test-Path -LiteralPath $cached) {
        Assert-PlainPath $cached
        if ((Get-FileDigest $cached) -ne $archiveSha) {
            throw "Existing archive cache differs and was not replaced: $cached"
        }
    }
    $zip = [IO.Compression.ZipFile]::OpenRead($inputArchive)
    $layout = Get-PackageLayout $zip
    $hashes = Get-PackageHashes $layout
    $packageRoot = Join-Path $runtime 'OpenCourant'
    $receiptPath = Join-Path $runtime 'install-receipt.json'
    Assert-PlainPath $receiptPath
    if (Test-Path -LiteralPath $receiptPath) {
        $old = Get-Content -LiteralPath $receiptPath -Encoding UTF8 -Raw | ConvertFrom-Json
        if ($old.release -ne $release -or $old.platform -ne 'windows-x86_64' -or
            $old.archive_sha256 -ne $archiveSha -or $old.runtime_root -ne $packageRoot -or
            @($old.file_sha256.PSObject.Properties).Count -ne $hashes.Count) {
            throw 'Existing installation receipt differs and was not replaced.'
        }
        foreach ($name in $hashes.Keys) {
            if ($old.file_sha256.PSObject.Properties[$name].Value -ne $hashes[$name]) {
                throw 'Existing installation receipt differs and was not replaced.'
            }
        }
    }
    if (Test-Path -LiteralPath $packageRoot) {
        Assert-PackageFiles $runtime $layout $hashes
        Write-Host 'Existing package matches every file in the verified archive; reusing it.'
    } else {
        $stage = Join-Path $runtime ('.extract-' + [guid]::NewGuid().ToString('N').Substring(0,8))
        if (@($layout.Files.Keys | Where-Object { (Join-Path $stage $_).Length -ge 260 }).Count) {
            throw 'The extraction path is too long for Windows PowerShell 5.1. Choose a shorter RuntimeRoot.'
        }
        New-Item -ItemType Directory -Path $stage | Out-Null
        foreach ($name in $layout.Paths.Keys) {
            if (-not $layout.Files.ContainsKey($name)) {
                New-Item -ItemType Directory -Path (Join-Path $stage $name.Replace('/', '\')) -Force | Out-Null
            }
        }
        foreach ($name in ($layout.Files.Keys | Sort-Object)) {
            $destination = [IO.Path]::GetFullPath((Join-Path $stage $name.Replace('/', '\')))
            if (-not $destination.StartsWith($stage + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'ZIP extraction would escape its private staging folder.'
            }
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($destination)) -Force | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($layout.Files[$name], $destination, $false)
        }
        Assert-PackageFiles $stage $layout $hashes
        $stagedPackage = [IO.Path]::GetFullPath((Join-Path $stage 'OpenCourant'))
        if (-not $stagedPackage.StartsWith($runtime + '\', [StringComparison]::OrdinalIgnoreCase) -or
            -not $packageRoot.StartsWith($runtime + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'The checked install paths must stay inside RuntimeRoot.'
        }
        Assert-PlainPath $stagedPackage
        Assert-PlainPath $packageRoot
        [IO.Directory]::Move($stagedPackage, $packageRoot)  # Fails if another writer created the destination.
        Write-Host "Installed the original package at $packageRoot"
    }
    $zip.Dispose(); $zip = $null
    $archiveGuard.Dispose(); $archiveGuard = $null
    Save-ArchiveCache $inputArchive $cached $downloadPartial $archiveSha
    if (-not (Test-Path -LiteralPath $receiptPath)) {
        $receipt = [ordered]@{release=$release; platform='windows-x86_64'; runtime_root=$packageRoot;
            archive_url=$archiveUrl; archive_sha256=$archiveSha; installed_utc=[DateTime]::UtcNow.ToString('o');
            file_sha256=$hashes; scope='Original package files verified; solver was not executed; environment was not changed.'}
        $bytes = [Text.Encoding]::UTF8.GetBytes(($receipt | ConvertTo-Json -Depth 4))
        $receiptFile = [IO.File]::Open($receiptPath, 'CreateNew', 'Write', 'None')
        try { $receiptFile.Write($bytes, 0, $bytes.Length) } finally { $receiptFile.Dispose() }
    }
    Write-Host "Ready for explicit runtime selection: $packageRoot"
    Write-Host "Verification receipt: $receiptPath"
    Write-Host 'No solver was run. Original notices are retained. PATH, active services and the default runtime were not changed.'
} finally {
    if ($zip) { $zip.Dispose() }
    if ($archiveGuard) { $archiveGuard.Dispose() }
    if ($lock) { $lock.Dispose() }
}
