# Current-user shortcuts only. Runtime preparation belongs to Install-CAE-Lab.cmd.
[CmdletBinding()]
param(
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath('Programs')) 'Autonomous CAE Lab'),
    [string]$SourceRoot,
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime'),
    [string]$Store = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\research-store'),
    [ValidateRange(1024,65535)][int]$Port = 8766
)
$ErrorActionPreference = 'Stop'
$customResearchTarget = $PSBoundParameters.ContainsKey('RuntimeRoot') -or
    $PSBoundParameters.ContainsKey('Store') -or $PSBoundParameters.ContainsKey('Port')
if ($customResearchTarget) {
    if ([string]::IsNullOrWhiteSpace($RuntimeRoot) -or [string]::IsNullOrWhiteSpace($Store)) {
        throw 'RuntimeRoot and Store must identify explicit folders; shortcuts were not changed.'
    }
    $RuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
    $Store = [IO.Path]::GetFullPath($Store)
}
if (-not $SourceRoot) { $SourceRoot = Split-Path -Parent $PSScriptRoot }
$source = [IO.Path]::GetFullPath($SourceRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$destinationPath = [IO.Path]::GetFullPath($Destination)
$launcher = Join-Path $source 'Start-CAE-Lab.cmd'
if (-not [IO.File]::Exists($launcher)) {
    throw "Start-CAE-Lab.cmd was not found. Keep the source folder intact: $source"
}
$tools = [ordered]@{
    workbench = '워크벤치'; runner = '실행 관리'; data = '데이터'; material = '재료'; pde = '방정식'
    numerical = '수치 연구'; expert = '전문가 토론'; simulation = '해석'
    evaluation = '계산 절차'; study = '연구 기록'; report = '보고서'
    pre = '전처리'; post = '후처리'; connection = '문서 연결'
}
$nativeLaunchers = @{ pre = 'Start-CAE-Pre.cmd'; post = 'Start-CAE-Post.cmd' }
$researchLauncher = Join-Path $source 'scripts\start_cae_research.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if ($customResearchTarget -and (-not [IO.File]::Exists($researchLauncher) -or -not [IO.File]::Exists($powershell))) {
    throw "Research launcher was not found; shortcuts were not changed: $researchLauncher"
}
# Store paths in one literal launcher: Windows shortcut COM truncates long arguments.
function Quote-ShortcutLiteral([string]$Value) {
    if ($Value.Contains('"') -or $Value.Contains("`r") -or $Value.Contains("`n")) {
        throw 'Shortcut folder arguments cannot contain quotes or line breaks.'
    }
    return "'" + $Value.Replace("'", "''") + "'"
}
$profilePath = Join-Path $destinationPath '.caelab-research-start.ps1'
$profileBytes = $null
function Test-ShortcutProfile {
    return [IO.File]::Exists($profilePath) -and
        ([IO.FileInfo]$profilePath).Length -eq $profileBytes.Length -and
        [Convert]::ToBase64String([IO.File]::ReadAllBytes($profilePath)) -ceq [Convert]::ToBase64String($profileBytes)
}
if ($customResearchTarget) {
    $profileSource = @(
        '# Managed Research shortcut target. Reinstall in another folder to change it.'
        'param([string]$Tool)'
        '$env:PSModulePath=[IO.Path]::Combine($PSHOME,''Modules'')+'';''+$env:PSModulePath'
        ('& ' + (Quote-ShortcutLiteral $researchLauncher) + ' -Tool $Tool -RuntimeRoot ' +
            (Quote-ShortcutLiteral $RuntimeRoot) + ' -Port ' + $Port +
            ' -Store ' + (Quote-ShortcutLiteral $Store) + ' -DesktopShortcut')
        'exit $LASTEXITCODE'
    ) -join "`r`n"
    $encoding = [Text.UTF8Encoding]::new($true)
    [byte[]]$profileBytes = @($encoding.GetPreamble()) + @($encoding.GetBytes($profileSource))
    if (Test-Path -LiteralPath $profilePath) {
        if (-not (Test-ShortcutProfile)) {
            throw "The Research shortcut support file belongs to another target or was edited; it was not changed: $profilePath. Choose another -Destination."
        }
    }
}
$shell = New-Object -ComObject WScript.Shell
$links = @()
try {
    # Check every collision before creating any new shortcut. No source migration.
    foreach ($tool in $tools.Keys) {
        $path = Join-Path $destinationPath ($tools[$tool] + '.lnk')
        $target = if ($nativeLaunchers.ContainsKey($tool)) { Join-Path $source $nativeLaunchers[$tool] } else { $launcher }
        if (-not [IO.File]::Exists($target)) { throw "Launcher was not found; shortcuts were not changed: $target" }
        $arguments = if ($nativeLaunchers.ContainsKey($tool)) { '' } else { '-Tool ' + $tool + ' -DesktopShortcut' }
        $description = 'Autonomous CAE Lab: ' + $tools[$tool] + ' / ' + $source
        $workingDirectory = $source
        if ($customResearchTarget -and -not $nativeLaunchers.ContainsKey($tool)) {
            $target = $powershell
            $arguments = '-NoProfile -ExecutionPolicy Bypass -File .caelab-research-start.ps1 -Tool ' + $tool
            $workingDirectory = $destinationPath
            $description = 'Autonomous CAE Lab: ' + $tools[$tool] + ' / ' + $Store + ' / ' + $Port
            if ($description.Length -gt 240) { $description = $description.Substring(0,237) + '...' }
        }
        $reuse = $false
        if (Test-Path -LiteralPath $path) {
            if (-not [IO.File]::Exists($path)) { throw "Shortcut destination is not a file; it was not changed: $path" }
            $existing = $shell.CreateShortcut($path)
            try {
                $reuse = $existing.TargetPath -eq $target -and $existing.Arguments -ceq $arguments -and
                    $existing.WorkingDirectory -eq $workingDirectory -and $existing.Description -ceq $description -and
                    $existing.WindowStyle -eq 1 -and $existing.Hotkey -eq '' -and $existing.IconLocation -eq ',0'
            } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($existing) }
            if (-not $reuse) {
                throw "Existing shortcut belongs to another source or was edited; it was not changed: $path. Choose -Destination, or explicitly remove the old shortcut before reinstalling after moving the source."
            }
        }
        $links += [pscustomobject]@{ Tool=$tool; Name=$tools[$tool]; Path=$path; Target=$target; Arguments=$arguments; Description=$description; WorkingDirectory=$workingDirectory; Reuse=$reuse }
    }
    [void][IO.Directory]::CreateDirectory($destinationPath)
    # Another installer may have published after preflight; never adopt its target.
    if ($customResearchTarget) {
        if (Test-Path -LiteralPath $profilePath) {
            if (-not (Test-ShortcutProfile)) {
                throw "The Research shortcut support file changed during installation; no new links were created: $profilePath. Choose another -Destination."
            }
        } else {
            $profileTemp = $profilePath + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
            try {
                [IO.File]::WriteAllBytes($profileTemp, $profileBytes)
                [IO.File]::Move($profileTemp, $profilePath)
                [IO.File]::SetAttributes($profilePath, ([IO.File]::GetAttributes($profilePath) -bor [IO.FileAttributes]::Hidden))
            } finally {
                if ([IO.File]::Exists($profileTemp)) { [IO.File]::Delete($profileTemp) }
            }
        }
    }
    foreach ($link in $links) {
        if ($link.Reuse) {
            Write-Output ([pscustomobject]@{ Name=$link.Name; Tool=$link.Tool; Path=$link.Path; Action='Reused' })
            continue
        }
        $temporary = Join-Path $destinationPath ('.caelab-' + [guid]::NewGuid().ToString('N') + '.lnk')
        try {
            $shortcut = $shell.CreateShortcut($temporary)
            try {
                $shortcut.TargetPath = $link.Target
                $shortcut.Arguments = $link.Arguments
                $shortcut.WorkingDirectory = $link.WorkingDirectory
                $shortcut.Description = $link.Description
                $shortcut.WindowStyle = 1
                $shortcut.Save()
            } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) }
            # File.Move refuses a destination created after the preflight check.
            [IO.File]::Move($temporary, $link.Path)
        } finally {
            if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
        }
        Write-Output ([pscustomobject]@{ Name=$link.Name; Tool=$link.Tool; Path=$link.Path; Action='Created' })
    }
} finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
