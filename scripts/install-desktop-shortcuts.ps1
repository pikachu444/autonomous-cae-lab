# Current-user shortcuts only. Runtime preparation belongs to Install-CAE-Lab.cmd.
[CmdletBinding()]
param(
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath('Programs')) 'Autonomous CAE Lab'),
    [string]$SourceRoot
)
$ErrorActionPreference = 'Stop'
if (-not $SourceRoot) { $SourceRoot = Split-Path -Parent $PSScriptRoot }
$source = [IO.Path]::GetFullPath($SourceRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$destinationPath = [IO.Path]::GetFullPath($Destination)
$launcher = Join-Path $source 'Start-CAE-Lab.cmd'
if (-not [IO.File]::Exists($launcher)) {
    throw "Start-CAE-Lab.cmd was not found. Keep the source folder intact: $source"
}
$tools = [ordered]@{
    runner = '실행 관리'; data = '데이터'; material = '재료'; pde = '방정식'
    numerical = '수치 연구'; expert = '전문가 토론'; simulation = '해석'
    evaluation = '계산 절차'; study = '연구 기록'
    pre = '전처리'; post = '후처리'
}
$nativeLaunchers = @{ pre = 'Start-CAE-Pre.cmd'; post = 'Start-CAE-Post.cmd' }
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
        $reuse = $false
        if (Test-Path -LiteralPath $path) {
            if (-not [IO.File]::Exists($path)) { throw "Shortcut destination is not a file; it was not changed: $path" }
            $existing = $shell.CreateShortcut($path)
            try {
                $reuse = $existing.TargetPath -eq $target -and $existing.Arguments -ceq $arguments -and
                    $existing.WorkingDirectory -eq $source -and $existing.Description -ceq $description -and
                    $existing.WindowStyle -eq 1 -and $existing.Hotkey -eq '' -and $existing.IconLocation -eq ',0'
            } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($existing) }
            if (-not $reuse) {
                throw "Existing shortcut belongs to another source or was edited; it was not changed: $path. Choose -Destination, or explicitly remove the old shortcut before reinstalling after moving the source."
            }
        }
        $links += [pscustomobject]@{ Tool=$tool; Name=$tools[$tool]; Path=$path; Target=$target; Arguments=$arguments; Description=$description; Reuse=$reuse }
    }
    [void][IO.Directory]::CreateDirectory($destinationPath)
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
                $shortcut.WorkingDirectory = $source
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
