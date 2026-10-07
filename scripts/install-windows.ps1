# Windows x64 bootstrap for a source checkout or downloaded repository ZIP.
# All tools and Python packages stay under the current user's local profile.
[CmdletBinding()]
param(
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime')
)
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess) {
    throw 'Use 64-bit Windows PowerShell on x64 Windows 10 or 11.'
}
$sourceRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$runtime = [IO.Path]::GetFullPath($RuntimeRoot)
if ($runtime.Length -gt [IO.Path]::GetPathRoot($runtime).Length) {
    $runtime = $runtime.TrimEnd([IO.Path]::DirectorySeparatorChar)
}
$project = Join-Path $sourceRoot 'pyproject.toml'
if (-not (Test-Path -LiteralPath $project -PathType Leaf)) { throw "Project source was not found: $sourceRoot" }
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$bin = Join-Path $runtime 'bin'
$venv = Join-Path $runtime 'venv'
$uv = Join-Path $bin 'uv.exe'
$python = Join-Path $venv 'Scripts\python.exe'
$receiptPath = Join-Path $runtime 'install-receipt.json'
$uvVersion = '0.12.19'
$uvZipName = 'uv-x86_64-pc-windows-msvc.zip'
$uvUrl = "https://github.com/astral-sh/uv/releases/download/$uvVersion/$uvZipName"
# Published alongside the archive by the upstream uv release. Checked 2026-10-08.
$uvZipSha256 = '6dbb02d79e419522f1c500f0adb1cddcff0cda7d59b0d66ea7f5e3b4a1b2f5f0'
$uvExeSha256 = 'f94eddb81f3addca6ef8f2361a70c3edde31adcbd1000a55fc6674306ae0b1e7'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
$env:UV_CACHE_DIR = Join-Path $runtime 'cache'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
New-Item -ItemType Directory -Force -Path $env:UV_PYTHON_INSTALL_DIR,$env:UV_CACHE_DIR,$bin | Out-Null
function Invoke-Checked([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed with exit code $LASTEXITCODE" }
}
if (-not (Test-Path -LiteralPath $uv -PathType Leaf)) {
    $temporary = Join-Path $runtime ('download-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temporary | Out-Null
    try {
        $archive = Join-Path $temporary $uvZipName
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Write-Host "Downloading pinned uv $uvVersion from $uvUrl"
        Invoke-WebRequest -Uri $uvUrl -OutFile $archive -UseBasicParsing
        $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $uvZipSha256) { throw "uv archive checksum mismatch: $actual" }
        Expand-Archive -LiteralPath $archive -DestinationPath $temporary
        $extracted = Join-Path $temporary 'uv.exe'
        if (-not (Test-Path -LiteralPath $extracted -PathType Leaf)) { throw 'The verified uv archive has no uv.exe.' }
        Copy-Item -LiteralPath $extracted -Destination $uv
    } finally {
        # The target is generated directly under the verified private runtime.
        if ($temporary.StartsWith($runtime + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
$foundUvSha = (Get-FileHash -LiteralPath $uv -Algorithm SHA256).Hash.ToLowerInvariant()
if ($foundUvSha -ne $uvExeSha256) { throw "Pinned uv executable checksum mismatch at $uv. Remove only that executable to retry the verified download." }
$foundUvVersion = (& $uv --version).Trim()
if ($LASTEXITCODE -ne 0 -or -not $foundUvVersion.StartsWith("uv $uvVersion ")) {
    throw "Expected pinned uv $uvVersion at $uv; found $foundUvVersion. Remove only that executable to retry the verified download."
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Host 'Installing a private managed CPython 3.12 and virtual environment...'
    try {
        Invoke-Checked $uv @('venv','--python','3.12','--python-preference','only-managed',$venv)
    } catch {
        # uv 0.12.19 can leave a complete Windows interpreter behind when its
        # minor-version junction verification fails. Use only that private,
        # executable interpreter; never fall back to an unrelated system Python.
        $managed = @(Get-ChildItem -LiteralPath $env:UV_PYTHON_INSTALL_DIR -Directory |
            Where-Object { $_.Name -like 'cpython-3.12.*-windows-x86_64-none' -and
                           -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } |
            Sort-Object Name -Descending)
        $valid = $null
        foreach ($candidate in $managed) {
            $candidatePython = Join-Path $candidate.FullName 'python.exe'
            if (-not (Test-Path -LiteralPath $candidatePython -PathType Leaf)) { continue }
            $candidateVersion = (& $candidatePython -c 'import sys; print(sys.version_info.major, sys.version_info.minor)').Trim()
            if ($LASTEXITCODE -eq 0 -and $candidateVersion -eq '3 12') { $valid = $candidatePython; break }
        }
        if (-not $valid) { throw }
        Write-Warning 'uv installed CPython but could not verify its minor-version junction; using the verified private interpreter directly.'
        Invoke-Checked $uv @('venv','--python',$valid,$venv)
    }
}
$pyVersion = (& $python -c 'import sys; print(sys.version.split()[0])').Trim()
if ($LASTEXITCODE -ne 0 -or -not $pyVersion.StartsWith('3.12.')) { throw "Expected private CPython 3.12 at $python; found $pyVersion" }
$projectSha = (Get-FileHash -LiteralPath $project -Algorithm SHA256).Hash.ToLowerInvariant()
$installed = $false
if (Test-Path -LiteralPath $receiptPath -PathType Leaf) {
    try {
        $old = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
        $installed = $old.source_root -eq $sourceRoot -and $old.project_sha256 -eq $projectSha -and
                     $old.uv_version -eq $uvVersion -and $old.python_version -eq $pyVersion
    } catch { $installed = $false }
}
if (-not $installed) {
    Write-Host 'Installing the project with numerical and material dependencies...'
    $editable = $sourceRoot + '[numerical,material]'
    Invoke-Checked $uv @('pip','install','--python',$python,'--editable',$editable)
}
Invoke-Checked $python @('-c','import apps.lab.server, caelab, scipy, felupe')
Write-Host 'Base, numerical and material imports OK'
$receipt = [ordered]@{
    source_root = $sourceRoot
    project_sha256 = $projectSha
    installed_utc = [DateTime]::UtcNow.ToString('o')
    runtime_root = $runtime
    venv_python = $python
    python_version = $pyVersion
    uv_version = $uvVersion
    uv_source = $uvUrl
    uv_archive_sha256 = $uvZipSha256
    uv_executable_sha256 = (Get-FileHash -LiteralPath $uv -Algorithm SHA256).Hash.ToLowerInvariant()
    installed_extras = @('numerical','material')
}
$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
Write-Host "Ready: $python"
Write-Host "Receipt: $receiptPath"
Write-Host 'Included: base workbench, numerical studies and FELUPE material-point calculations. Native CAD/solver backends and expert models require separate operator setup.'
