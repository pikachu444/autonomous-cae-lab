# Read-only regression for the actual native acceptance provider-observation seam.
# Exercise checked-in case preparation with LF and Windows CRLF, without importing
# controller code, reading authentication, or executing the research case body.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$taskHarnessRepo=Split-Path -Parent $PSScriptRoot
$taskHarnessText=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'verify_openscience_native_live.ps1')).Replace("`r`n","`n")
$taskHarnessLiveText=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'verify_openscience_live.ps1')).Replace("`r`n","`n")
function Assert-Task([bool]$Condition,[string]$Message) { if(-not $Condition){throw $Message} }
function Test-OpenScienceHarnessSeam([string]$HarnessText,[string]$LiveText,[bool]$ExpectedRefusal) {
    $tokens=$null;$errors=$null
    $harness=[Management.Automation.Language.Parser]::ParseInput($HarnessText,[ref]$tokens,[ref]$errors)
    Assert-Task ($errors.Count -eq 0) 'Harness source failed to parse.'
    $taskNativeAst=[Management.Automation.Language.Parser]::ParseInput($LiveText.Replace("`r`n","`n"),[ref]$tokens,[ref]$errors)
    Assert-Task ($errors.Count -eq 0) 'Original case source failed to parse.'
    $statements=@($harness.EndBlock.Statements)
    $start=@(0..($statements.Count-1)|Where-Object {$statements[$_].Extent.Text.StartsWith('$taskNativeTry =')})
    $end=@(0..($statements.Count-1)|Where-Object {$statements[$_].Extent.Text -ceq '. ([scriptblock]::Create($taskNativeCases))'})
    Assert-Task ($start.Count -eq 1 -and $end.Count -eq 1 -and $end[0] -gt $start[0]) 'The exact preparation/body boundary changed.'
    $preparation=($statements[$start[0]..($end[0]-1)]|ForEach-Object {$_.Extent.Text}) -join "`n"
    $refused=$false
    try { . ([scriptblock]::Create($preparation)) } catch { $refused=$true }
    Assert-Task ($refused -eq $ExpectedRefusal) 'Line endings changed seam recognition or a changed seam was accepted.'
    if(-not $ExpectedRefusal) {
        Assert-Task (-not $taskNativeCases.Contains('127.0.0.1:11434') -and
            $taskNativeCases.Contains('selected-native-model.json') -and $taskNativeCases.Contains('native-hook-files.json')) 'Only the native provider observations must remain.'
    }
}
$taskHarnessChecks=[Collections.Generic.List[string]]::new()
foreach($ending in @('LF','CRLF')) {
    $text=$(if($ending -ceq 'CRLF'){$taskHarnessText.Replace("`n","`r`n")}else{$taskHarnessText})
    $live=$(if($ending -ceq 'CRLF'){$taskHarnessLiveText.Replace("`n","`r`n")}else{$taskHarnessLiveText})
    Test-OpenScienceHarnessSeam $text $live $false
    $taskHarnessChecks.Add($ending+'_exact_case_preparation_passes_without_body_execution')
    Test-OpenScienceHarnessSeam $text ($live.Replace("'ollama-models.json'","'different-provider-seam.json'")) $true
    $taskHarnessChecks.Add($ending+'_changed_provider_seam_refused')
}
[ordered]@{status='PASS_NATIVE_HARNESS_LINE_ENDINGS';checks=$taskHarnessChecks.ToArray();
    native_harness_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'verify_openscience_native_live.ps1') -Algorithm SHA256).Hash.ToLower();
    original_case_sha256=(Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'verify_openscience_live.ps1') -Algorithm SHA256).Hash.ToLower();
    provider_calls=0;core_calls=0;research_body_executed=$false} | ConvertTo-Json -Depth 5
