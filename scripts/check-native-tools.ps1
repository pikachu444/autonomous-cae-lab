# Read installed native paths only. No download, configuration write or native run.
[CmdletBinding()]
param(
    [string]$FreeCADExe,
    [string]$ParaViewExe,
    [string]$ConfigPath = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\workbench-config.json')
)
$ErrorActionPreference = 'Stop'
$desktop = $null
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    try { $desktop = (Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json).desktop }
    catch { Write-Warning "설정 파일을 읽지 못했습니다. 실행 경로를 직접 지정하세요: $ConfigPath" }
}
$saved = Get-ItemProperty -LiteralPath 'HKCU:\Software\AutonomousCAELab\DesktopLaunchers' -ErrorAction SilentlyContinue
$tools = @(
    @{ Name='FreeCAD'; Key='freecad_executable'; Explicit=$FreeCADExe; Environment=$env:CAELAB_FREECAD_EXE; Commands=@('FreeCAD','freecad'); Option='-FreeCADExe'; License='https://github.com/FreeCAD/FreeCAD/blob/main/LICENSE' },
    @{ Name='ParaView'; Key='paraview_executable'; Explicit=$ParaViewExe; Environment=$env:CAELAB_PARAVIEW_EXE; Commands=@('paraview'); Option='-ParaViewExe'; License='https://www.paraview.org/license/' }
)
foreach ($tool in $tools) {
    $candidate = $tool.Explicit
    $origin = '직접 지정'
    if (-not $candidate -and $desktop) { $candidate = $desktop.($tool.Key); $origin = '연결 설정' }
    if (-not $candidate) { $candidate = $tool.Environment; $origin = '환경 변수' }
    if (-not $candidate) {
        foreach ($command in $tool.Commands) {
            $found = Get-Command -Name $command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) { $candidate = $found.Source; $origin = 'PATH'; break }
        }
    }
    if (-not $candidate -and $saved) { $candidate = $saved.($tool.Key); $origin = '이전에 선택한 위치' }
    $exists = $candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)
    $version = '미확인'
    if ($exists) {
        $candidate = (Resolve-Path -LiteralPath $candidate).Path
        try {
            $metadata = [Diagnostics.FileVersionInfo]::GetVersionInfo($candidate)
            if ($metadata.ProductVersion) { $version = $metadata.ProductVersion }
        } catch { Write-Warning "$($tool.Name) 파일 버전 정보는 읽지 못했습니다: $candidate" }
    }
    [pscustomobject]@{
        Tool=$tool.Name
        Status=$(if ($exists) { '실행 파일 있음' } elseif ($candidate) { '경로 복구 필요' } else { '연결 전' })
        Path=[string]$candidate
        PathSource=$(if ($candidate) { $origin } else { '' })
        FileVersion=$version
        CheckScope='파일 위치와 파일 버전 정보만 확인; GUI·계산은 미실행'
        Recovery=$(if ($exists) { '시작 메뉴에서 열어 실제 작업을 확인하세요.' } else { "기존 설치를 확인하고 시작 메뉴에서 다시 선택하거나 $($tool.Option)로 현재 실행 파일을 지정하세요." })
        LicenseNotice=$tool.License
    }
}
