# Official pinned OpenScience ChatGPT authentication and model metadata.
# Credential files live outside the public repository. This is not a research
# acceptance runner; login or a catalog entry does not prove inference access.
[CmdletBinding()]
param(
    [switch]$Library,
    [ValidateSet('SignIn', 'Status', 'Models')][string]$Mode = 'Status',
    [Parameter(Mandatory)][string]$ProfileRoot,
    [string]$RuntimePrefix
)
$taskChatGptOptions = @{ Library = [bool]$Library; Mode = $Mode; ProfileRoot = $ProfileRoot; RuntimePrefix = $RuntimePrefix }
. (Join-Path $PSScriptRoot 'openscience-server-local.ps1') -Library

if ($taskChatGptOptions.Library) { return }
$ErrorActionPreference = 'Stop'
$taskChatGptContext = New-OpenScienceChatGptContext -ProfileRoot $taskChatGptOptions.ProfileRoot -RuntimePrefix $taskChatGptOptions.RuntimePrefix
if ($taskChatGptOptions.Mode -eq 'Status') {
    [pscustomobject]@{ provider = $taskChatGptContext.Provider; profile_root = $taskChatGptContext.ProfileRoot
        data_root = $taskChatGptContext.DataRoot; model = $null
        auth_file_exists = (Test-Path -LiteralPath (Join-Path $taskChatGptContext.DataRoot 'auth.json') -PathType Leaf)
        authenticated_inference = 'UNVERIFIED'; research_acceptance = 'OPEN' }
    return
}
$taskChatGptAuthPath = Join-Path $taskChatGptContext.DataRoot 'auth.json'
$taskChatGptAuthBefore = Get-Item -LiteralPath $taskChatGptAuthPath -ErrorAction SilentlyContinue
if ($taskChatGptOptions.Mode -eq 'Models' -and -not $taskChatGptAuthBefore) { throw 'ChatGPT sign-in has not completed in this profile. No provider/model request was made.' }
$taskChatGptInfo = New-OpenScienceChatGptProcessInfo -Context $taskChatGptContext -Operation $taskChatGptOptions.Mode
if ($taskChatGptOptions.Mode -eq 'Models') { $taskChatGptInfo.RedirectStandardOutput = $true; $taskChatGptInfo.RedirectStandardError = $true }
$taskChatGptProcess = [Diagnostics.Process]::Start($taskChatGptInfo)
$taskChatGptProcess.StandardInput.Close()
if ($taskChatGptOptions.Mode -eq 'Models') {
    $taskChatGptStdout = $taskChatGptProcess.StandardOutput.ReadToEndAsync()
    $taskChatGptStderr = $taskChatGptProcess.StandardError.ReadToEndAsync()
    if (-not $taskChatGptProcess.WaitForExit(30000)) { $taskChatGptProcess.Kill($true); throw 'Official model metadata request timed out. No inference or research success is claimed.' }
    ConvertFrom-OpenScienceChatGptCatalog -Output $taskChatGptStdout.GetAwaiter().GetResult() -ErrorOutput $taskChatGptStderr.GetAwaiter().GetResult() -ExitCode $taskChatGptProcess.ExitCode
    return
}
$taskChatGptProcess.WaitForExit()
if ($taskChatGptProcess.ExitCode -ne 0) { throw "Official OpenScience $($taskChatGptOptions.Mode) failed with exit code $($taskChatGptProcess.ExitCode). Existing authentication and research records are preserved." }
$taskChatGptAuthAfter = Get-Item -LiteralPath $taskChatGptAuthPath -ErrorAction SilentlyContinue
Assert-OpenScienceCondition ($null -ne $taskChatGptAuthAfter -and
    ($null -eq $taskChatGptAuthBefore -or $taskChatGptAuthAfter.LastWriteTimeUtc -gt $taskChatGptAuthBefore.LastWriteTimeUtc)) 'Official sign-in did not create/update the owned authentication file. Exit zero alone is not a completed login.'
[pscustomobject]@{ provider = 'openai-codex'; credential_file_updated = $true; authenticated_inference = 'UNVERIFIED'; research_acceptance = 'OPEN' }
