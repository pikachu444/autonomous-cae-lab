# Read installed native paths only. No download, configuration write or native run.
[CmdletBinding()]
param(
    [string]$FreeCADExe,
    [string]$ParaViewExe,
    [string]$Python,
    [string]$ConfigPath = (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\workbench-config.json')
)
$ErrorActionPreference = 'Stop'
if (-not $Python -and $env:LOCALAPPDATA) {
    $managedPython = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime\venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $managedPython -PathType Leaf) { $Python = $managedPython }
}
$discovery = $null
if ($Python) {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python 실행 파일이 없습니다: $Python" }
    $finder = Join-Path (Split-Path $PSScriptRoot -Parent) 'caelab\native_tools.py'
    $finderArgs = @('--config-path', $ConfigPath)
    if ($FreeCADExe) { $finderArgs += @('--freecad-exe', $FreeCADExe) }
    if ($ParaViewExe) { $finderArgs += @('--paraview-exe', $ParaViewExe) }
    $json = & $Python $finder @finderArgs
    if ($LASTEXITCODE -ne 0) { throw '설치 경로 확인에 실패했습니다. Python 출력 내용을 확인하세요.' }
    $discovery = ($json -join "`n") | ConvertFrom-Json
    foreach ($warning in $discovery.warnings) { Write-Warning $warning }
}
$desktop = $null
if (-not $discovery -and (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    try { $desktop = (Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json).desktop }
    catch { Write-Warning "설정 파일을 읽지 못했습니다. 실행 경로를 직접 지정하세요: $ConfigPath" }
}
$saved = Get-ItemProperty -LiteralPath 'HKCU:\Software\AutonomousCAELab\DesktopLaunchers' -ErrorAction SilentlyContinue
$tools = @(
    @{ Name='FreeCAD'; Key='freecad_executable'; Explicit=$FreeCADExe; Environment=$env:CAELAB_FREECAD_EXE; Commands=@('FreeCAD','freecad'); Option='-FreeCADExe'; License='https://github.com/FreeCAD/FreeCAD/blob/main/LICENSE' },
    @{ Name='ParaView'; Key='paraview_executable'; Explicit=$ParaViewExe; Environment=$env:CAELAB_PARAVIEW_EXE; Commands=@('paraview'); Option='-ParaViewExe'; License='https://www.paraview.org/license/' }
)
foreach ($tool in $tools) {
    $selection = $null
    if ($discovery) {
        $selection = $discovery.tools | Where-Object { $_.key -eq $tool.Key } | Select-Object -First 1
        if (-not $selection) { throw "실행 경로 확인 결과가 없습니다: $($tool.Key)" }
    }
    $candidate = $tool.Explicit
    $origin = '직접 지정'
    if (-not $candidate -and $desktop) { $candidate = $desktop.($tool.Key); $origin = '연결 설정' }
    if (-not $candidate) { $candidate = $tool.Environment; $origin = '환경 변수' }
    if (-not $candidate -and $saved) {
        $remembered = $saved.($tool.Key)
        if ($remembered -and (Test-Path -LiteralPath $remembered -PathType Leaf)) {
            $candidate = $remembered; $origin = '이전에 선택한 위치'
        }
    }
    if (-not $candidate) {
        foreach ($command in $tool.Commands) {
            $found = Get-Command -Name $command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) { $candidate = $found.Source; $origin = 'PATH'; break }
        }
    }
    if ($selection) {
        $candidate = $selection.path
        $origin = switch -Wildcard ($selection.source) {
            '--executable' { '직접 지정' }
            'desktop.*' { '연결 설정' }
            'saved' { '이전에 선택한 위치' }
            'CAELAB_*' { '환경 변수' }
            default { [string]$selection.source }
        }
    }
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
        Status=$(if ($selection -and $selection.status -eq 'MULTIPLE') { '여러 설치 중 선택 필요' } elseif ($exists) { '실행 파일 있음' } elseif ($candidate) { '경로 복구 필요' } else { '연결 전' })
        Path=[string]$candidate
        PathSource=$(if ($candidate) { $origin } else { '' })
        FileVersion=$version
        CheckScope=$(if ($discovery) { '실행기와 같은 경로 탐색; 파일 위치·버전 정보만 확인; GUI·계산은 미실행, 호환성은 미확인' } else { 'Python 미지정: 설정·저장 경로·PATH만 확인; GUI·계산은 미실행' })
        Recovery=$(if ($selection -and $selection.status -eq 'INVALID') { "$origin 경로를 수정하세요: $candidate. 직접 지정할 때는 $($tool.Option)를 사용하세요." } elseif ($exists) { '시작 메뉴에서 열어 실제 작업을 확인하세요.' } else { "기존 설치를 확인하고 시작 메뉴에서 선택하거나 $($tool.Option)로 현재 실행 파일을 지정하세요." })
        CandidatePaths=$(if ($selection) { @($selection.candidates | ForEach-Object { $_.path }) } else { @() })
        LicenseNotice=$tool.License
    }
}
