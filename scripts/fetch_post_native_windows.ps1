# SPDX-License-Identifier: BSD-3-Clause
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$WorkRoot)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-PinnedDownload([string]$Url, [string]$Destination, [string]$Sha256) {
    if (-not (Test-Path -LiteralPath $Destination)) {
        Invoke-WebRequest -Uri $Url -OutFile $Destination -MaximumRetryCount 3 -RetryIntervalSec 3
    }
    $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Sha256) { throw "SHA256 mismatch; preserve the failed input: $Destination" }
}

function Assert-ArchiveMembers([string[]]$Members) {
    foreach ($member in $Members) {
        $name = $member.Replace('\','/')
        if ($name.StartsWith('/') -or $name -match '^[A-Za-z]:' -or '..' -in $name.Split('/')) {
            throw "Unsafe archive member: $member"
        }
    }
}

function Expand-PinnedArchive([string]$Archive, [string]$Destination) {
    $tar = (Get-Command tar.exe -CommandType Application -ErrorAction Stop).Source
    $members = @(& $tar -tf $Archive)
    if ($LASTEXITCODE -ne 0) { throw "Cannot list verified archive: $Archive" }
    Assert-ArchiveMembers $members
    $details = @(& $tar -tvf $Archive)
    if ($LASTEXITCODE -ne 0 -or @($details | Where-Object { $_ -match '^[lh]' }).Count) {
        throw "Archive listing failed or contains links: $Archive"
    }
    & $tar -xf $Archive -C $Destination
    if ($LASTEXITCODE -ne 0) { throw "Archive extraction failed: $Archive" }
}

function Get-PostNativeInputs {
    $qtRoot = 'https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/qt6_690/qt6_690/'
    $qtStamp = '6.9.0-0-202503301022'
    $qtSuffix = '-Windows-Windows_11_23H2-MSVC2022-Windows-Windows_11_23H2-X86_64.7z'
    $rows = @(
        @{name='qtbase'; hash='5a2db7a2cabb0ce09171d5600a8d420d0395d159389d62a1edbc58a4f3237537'},
        @{name='qttools'; hash='5f5749bde8fe8e931cfd51a4dcfc5439c090489bc9b79f34483edaa1e77cbb35'},
        @{name='qtsvg'; hash='99076dbc1ddc97b23d76b6658b3b6613850db316d388e59c1d8563ddc2f1521b'},
        @{name='qt5compat'; hash='86d3737cff83ce06420869becf90cc1f9d5c882e5d6a4bbbe011e0f3cf04435c'}
    )
    foreach ($row in $rows) {
        $package = if ($row.name -eq 'qt5compat') { 'qt.qt6.690.addons.qt5compat.win64_msvc2022_64/' } else { 'qt.qt6.690.win64_msvc2022_64/' }
        [pscustomobject]@{name=$row.name; file=($row.name+'.7z'); url=($qtRoot+$package+$qtStamp+$row.name+$qtSuffix); sha256=$row.hash; kind='qt'}
    }
    [pscustomobject]@{name='ParaView'; file='ParaView-v6.2.0.tar.xz'; url='https://www.paraview.org/files/v6.2/ParaView-v6.2.0.tar.xz'; sha256='373afd566ef5f6c650c3acf4a5d4f43ad75975537f7fe225cb53ed20fe41cd20'; kind='source'}
    [pscustomobject]@{name='numpy'; file='numpy-2.3.5-cp312-cp312-win_amd64.whl'; url='https://files.pythonhosted.org/packages/2d/57/8aeaf160312f7f489dea47ab61e430b5cb051f59a98ae68b7133ce8fa06a/numpy-2.3.5-cp312-cp312-win_amd64.whl'; sha256='86945f2ee6d10cdfd67bcb4069c1662dd711f7e2a4343db5cecec06b87cf31aa'; kind='wheel'}
}

function Initialize-PostNativeInputs {
    $fullRoot = [IO.Path]::GetFullPath($WorkRoot)
    if (Test-Path -LiteralPath $fullRoot) { throw 'Use a new SDK work directory; prior logs/outputs are preserved.' }
    New-Item -ItemType Directory -Path $fullRoot | Out-Null
    $downloads = Join-Path $fullRoot 'downloads'
    $qt = Join-Path $fullRoot 'qt'
    $source = Join-Path $fullRoot 'source'
    New-Item -ItemType Directory -Path $downloads,$qt,$source | Out-Null
    $inputs = @(Get-PostNativeInputs)
    foreach ($inputFile in $inputs) {
        $path = Join-Path $downloads $inputFile.file
        Get-PinnedDownload $inputFile.url $path $inputFile.sha256
        if ($inputFile.kind -eq 'qt') { Expand-PinnedArchive $path $qt }
        elseif ($inputFile.kind -eq 'source') { Expand-PinnedArchive $path $source }
    }
    foreach ($module in @('qtbase','qttools','qtsvg','qt5compat')) {
        $folder = Join-Path $qt "source-license-notices/$module"
        New-Item -ItemType Directory -Path $folder -Force | Out-Null
        Get-PinnedDownload "https://raw.githubusercontent.com/qt/$module/v6.9.0/LICENSES/LGPL-3.0-only.txt" (Join-Path $folder 'LICENSE.LGPL3') 'da7eabb7bafdf7d3ae5e9f223aa5bdc1eece45ac569dc21b3b037520b4464768'
    }
    foreach ($file in @('qt/lib/cmake/Qt6/Qt6Config.cmake','source/ParaView-v6.2.0/CMakeLists.txt','source/ParaView-v6.2.0/Copyright.txt')) {
        if (-not (Test-Path -LiteralPath (Join-Path $fullRoot $file))) { throw "Required source/license input missing: $file" }
    }
    @{inputs=$inputs; qt_version='6.9.0'; paraview_version='6.2.0'; numpy_version='2.3.5';
      source='Official ParaView release and public Qt MSVC2022 archives; same SDK/runtime build required';
      qt_pin_reference='paraview-superbuild v6.2.0 commit4f547849f948101d359f521cb00e85e24693da0d';
      native_acceptance='NOT_RUN'; storage_upload='NONE'} | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath (Join-Path $fullRoot 'inputs.json') -Encoding utf8
    Write-Output "Verified public SDK inputs prepared: $fullRoot"
}

if ($MyInvocation.InvocationName -ne '.') { Initialize-PostNativeInputs }
