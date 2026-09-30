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

function Get-OpenScienceChatGptRuntimePin {
    param([Parameter(Mandatory)][string]$RuntimePrefix, $ExpectedNodePin)
    $prefix = [IO.Path]::GetFullPath($RuntimePrefix)
    $launcher = Join-Path $prefix 'node_modules\@synsci\openscience\bin\openscience'
    $packagePath = Join-Path $prefix 'node_modules\@synsci\openscience\package.json'
    Assert-OpenScienceContainedPath $launcher $prefix | Out-Null
    Assert-OpenScienceContainedPath $packagePath $prefix | Out-Null
    $package = Read-OpenScienceJson $packagePath
    Assert-OpenScienceCondition ($package.name -ceq '@synsci/openscience' -and $package.version -ceq $script:OpenSciencePinnedVersion) 'Unexpected official launcher package identity.'
    $native = @(Get-ChildItem -LiteralPath (Join-Path $prefix 'node_modules\@synsci') -Directory -ErrorAction Stop |
        Where-Object Name -cmatch '^openscience-windows-(x64|arm64)(-baseline)?$' | Sort-Object Name | ForEach-Object {
            $binaryPath = Join-Path $_.FullName 'bin\openscience.exe'
            $nativePackagePath = Join-Path $_.FullName 'package.json'
            Assert-OpenScienceContainedPath $binaryPath $prefix | Out-Null
            Assert-OpenScienceContainedPath $nativePackagePath $prefix | Out-Null
            $nativePackage = Read-OpenScienceJson $nativePackagePath
            Assert-OpenScienceCondition ($nativePackage.name -ceq ('@synsci/' + $_.Name) -and $nativePackage.version -ceq $script:OpenSciencePinnedVersion) 'Unexpected official native package identity.'
            [ordered]@{ Path = $binaryPath; PackagePath = $nativePackagePath; PackageSha256 = Get-OpenScienceHash $nativePackagePath; Sha256 = Get-OpenScienceHash $binaryPath }
        })
    Assert-OpenScienceCondition ($native.Count -gt 0) 'Official pinned Windows native runtime is missing.'
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    $nodeHash = Get-OpenScienceHash $node
    if ($null -ne $ExpectedNodePin) {
        Assert-OpenScienceCondition ($ExpectedNodePin.NodePath -ceq $node -and $ExpectedNodePin.NodeSha256 -ceq $nodeHash) 'Pinned Node changed; version execution and authentication refused.'
    }
    $versionInfo = [Diagnostics.ProcessStartInfo]::new()
    $versionInfo.FileName = $node; $versionInfo.UseShellExecute = $false; $versionInfo.CreateNoWindow = $true
    $versionInfo.RedirectStandardOutput = $true; $versionInfo.RedirectStandardError = $true; $versionInfo.ArgumentList.Add('--version')
    foreach ($name in @(Get-OpenScienceRemovedEnvironment @($versionInfo.Environment.Keys))) { $versionInfo.Environment.Remove($name) | Out-Null }
    $versionProcess = [Diagnostics.Process]::Start($versionInfo)
    $versionOut = $versionProcess.StandardOutput.ReadToEndAsync(); $versionError = $versionProcess.StandardError.ReadToEndAsync()
    if (-not $versionProcess.WaitForExit(5000)) { $versionProcess.Kill($true); throw 'Node version check timed out.' }
    $nodeVersion = $versionOut.GetAwaiter().GetResult().Trim()
    Assert-OpenScienceCondition ($versionProcess.ExitCode -eq 0 -and [string]::IsNullOrWhiteSpace($versionError.GetAwaiter().GetResult()) -and $nodeVersion -cmatch '^v[0-9]+\.[0-9]+\.[0-9]+$') 'Existing Node identity is unavailable.'
    return [ordered]@{ RuntimePrefix = $prefix; LauncherPath = $launcher; LauncherSha256 = Get-OpenScienceHash $launcher
        PackageSha256 = Get-OpenScienceHash $packagePath; NativeBinaries = $native
        NodePath = $node; NodeSha256 = $nodeHash; NodeVersion = $nodeVersion }
}

function New-OpenScienceChatGptContext {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$ProfileRoot, [string]$RuntimePrefix)
    Assert-OpenScienceCondition ($PSVersionTable.PSVersion.Major -ge 7) 'PowerShell 7 is required.'
    $profile = [IO.Path]::GetFullPath($ProfileRoot)
    $externalRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\profiles'))
    Assert-OpenScienceContainedPath $profile $externalRoot | Out-Null
    Assert-OpenScienceCondition ($profile -ne $externalRoot) 'Select a dedicated external profile subdirectory.'
    $repositoryRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
    Assert-OpenScienceCondition (-not $profile.StartsWith($repositoryRoot + '\', [StringComparison]::OrdinalIgnoreCase)) 'Authentication data must stay outside the public repository.'
    if (-not $RuntimePrefix) { $RuntimePrefix = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\runtimes\openscience-2.0.146' }
    $earlyMarkerPath = Join-Path $profile 'caelab-profile-owner.json'
    Assert-OpenScienceContainedPath $earlyMarkerPath $profile | Out-Null
    $expectedNodePin = if (Test-Path -LiteralPath $earlyMarkerPath -PathType Leaf) { (Read-OpenScienceJson $earlyMarkerPath).runtime_pin } else { $null }
    $runtimePin = Get-OpenScienceChatGptRuntimePin -RuntimePrefix $RuntimePrefix -ExpectedNodePin $expectedNodePin
    $launcher = $runtimePin.LauncherPath
    $architecture = if ([Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -eq 'Arm64') { 'arm64' } else { 'x64' }
    $selectedNative = @($runtimePin.NativeBinaries | Where-Object { (Split-Path -Parent (Split-Path -Parent $_.Path) | Split-Path -Leaf) -ceq "openscience-windows-$architecture" })
    Assert-OpenScienceCondition ($selectedNative.Count -eq 1) 'The explicit official native executable for this Windows architecture is missing.'
    $environment = [ordered]@{
        OPENSCIENCE_TEST_HOME = (Join-Path $profile 'home'); OPENSCIENCE_CONFIG_DIR = (Join-Path $profile 'config')
        OPENSCIENCE_DATA_DIR = (Join-Path $profile 'data'); XDG_CONFIG_HOME = (Join-Path $profile 'xdg-config')
        XDG_DATA_HOME = (Join-Path $profile 'xdg-data'); XDG_CACHE_HOME = (Join-Path $profile 'xdg-cache')
        XDG_STATE_HOME = (Join-Path $profile 'xdg-state'); TEMP = (Join-Path $profile 'temp'); TMP = (Join-Path $profile 'temp')
        OPENSCIENCE_DISABLE_AUTOUPDATE = '1'; OPENSCIENCE_DISABLE_MODELS_FETCH = '1'
        OPENSCIENCE_DISABLE_PROJECT_CONFIG = '1'; OPENSCIENCE_DISABLE_LSP_DOWNLOAD = '1'
    }
    $configPath = Join-Path $environment.OPENSCIENCE_CONFIG_DIR 'openscience.json'
    $markerPath = Join-Path $profile 'caelab-profile-owner.json'
    foreach ($path in @($markerPath, $configPath, (Join-Path $environment.OPENSCIENCE_DATA_DIR 'auth.json')) +
        @($environment.Values | Where-Object { $_.StartsWith($profile + '\') } | Sort-Object -Unique)) {
        Assert-OpenScienceContainedPath $path $profile | Out-Null
    }
    if (Test-Path -LiteralPath $profile) {
        Assert-OpenScienceCondition (Test-Path -LiteralPath $markerPath -PathType Leaf) 'Existing unowned profile will not be changed.'
        $marker = Read-OpenScienceJson $markerPath
        Assert-OpenScienceCondition ($marker.kind -eq 'autonomous-cae-lab.chatgpt-auth-profile' -and $marker.schema -eq 2 -and
            $marker.profile_root -eq $profile -and $marker.provider -ceq 'openai-codex' -and $null -eq $marker.model -and
            $marker.data_root -eq $environment.OPENSCIENCE_DATA_DIR -and $marker.config_path -eq $configPath -and
            $marker.runtime_version -ceq $script:OpenSciencePinnedVersion -and $marker.source_commit -ceq $script:OpenSciencePinnedSource -and
            $marker.launcher_sha256 -ceq (Get-OpenScienceHash $launcher)) 'Authentication profile ownership/runtime changed; it will not be reused.'
        $expectedPin = [Text.Json.Nodes.JsonNode]::Parse(($marker.runtime_pin | ConvertTo-Json -Depth 10 -Compress))
        $currentPin = [Text.Json.Nodes.JsonNode]::Parse(($runtimePin | ConvertTo-Json -Depth 10 -Compress))
        Assert-OpenScienceCondition ([Text.Json.Nodes.JsonNode]::DeepEquals($expectedPin, $currentPin)) 'Credential-bearing Node/native runtime changed; sign-in refused.'
        $config = Read-OpenScienceJson $configPath
        Assert-OpenScienceCondition ($config.Count -eq 4 -and @($config.enabled_providers).Count -eq 1 -and $config.enabled_providers[0] -ceq 'openai-codex' -and
            $config.snapshot -ceq $false -and $config.billing.Count -eq 1 -and $config.billing.llm -ceq 'byok' -and
            $config.permission.Count -eq 1 -and $config.permission['*'] -ceq 'deny') 'Auth-only configuration changed; it will not be reused.'
    } else {
        New-Item -ItemType Directory -Path $profile -ErrorAction Stop | Out-Null
        foreach ($directory in @($environment.Values | Where-Object { $_.StartsWith($profile + '\') } | Sort-Object -Unique)) {
            New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
        }
        Write-OpenScienceJson $configPath @{ enabled_providers = @('openai-codex'); snapshot = $false; billing = @{ llm = 'byok' }; permission = @{ '*' = 'deny' } } -CreateNew
        Write-OpenScienceJson $markerPath @{ kind = 'autonomous-cae-lab.chatgpt-auth-profile'; schema = 2
            profile_root = $profile; data_root = $environment.OPENSCIENCE_DATA_DIR; config_path = $configPath
            provider = 'openai-codex'; model = $null; runtime_version = $script:OpenSciencePinnedVersion
            source_commit = $script:OpenSciencePinnedSource; launcher_sha256 = (Get-OpenScienceHash $launcher)
            runtime_pin = $runtimePin
            created_utc = [DateTime]::UtcNow.ToString('o') } -CreateNew
    }
    return [pscustomobject]@{ ProfileRoot = $profile; DataRoot = $environment.OPENSCIENCE_DATA_DIR; ConfigPath = $configPath
        LauncherPath = $launcher; NodePath = $runtimePin.NodePath; RuntimePrefix = $runtimePin.RuntimePrefix; Environment = $environment
        NativePath = $selectedNative[0].Path; Provider = 'openai-codex'; Model = $null }
}

function New-OpenScienceChatGptProcessInfo {
    param([Parameter(Mandatory)]$Context, [Parameter(Mandatory)][ValidateSet('SignIn', 'Models')][string]$Operation)
    Assert-OpenScienceCondition (Test-Path -LiteralPath $Context.ProfileRoot -PathType Container) 'Authentication profile disappeared; launch refused.'
    $verified = New-OpenScienceChatGptContext -ProfileRoot $Context.ProfileRoot -RuntimePrefix $Context.RuntimePrefix
    Assert-OpenScienceCondition ($verified.NodePath -ceq $Context.NodePath -and $verified.LauncherPath -ceq $Context.LauncherPath -and
        $verified.DataRoot -ceq $Context.DataRoot -and $verified.ConfigPath -ceq $Context.ConfigPath -and
        $verified.NativePath -ceq $Context.NativePath) 'Authentication context identity changed; launch refused.'
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Context.NodePath; $info.WorkingDirectory = $Context.ProfileRoot
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true; $info.RedirectStandardInput = $true
    $info.ArgumentList.Add($Context.LauncherPath)
    foreach ($argument in $(if ($Operation -eq 'SignIn') { @('keys', 'signin') } else { @('model', 'openai-codex', '--flat') })) {
        $info.ArgumentList.Add($argument)
    }
    foreach ($name in @(Get-OpenScienceRemovedEnvironment @($info.Environment.Keys))) { $info.Environment.Remove($name) | Out-Null }
    foreach ($name in $verified.Environment.Keys) { $info.Environment[$name] = [string]$verified.Environment[$name] }
    # The official wrapper would otherwise prefer an unscoped/shadow package.
    # Bind its documented override to the verified executable in this child only.
    $info.Environment['OPENSCIENCE_BIN_PATH'] = $verified.NativePath
    return $info
}

function ConvertFrom-OpenScienceChatGptCatalog {
    param([string]$Output, [string]$ErrorOutput, [int]$ExitCode)
    $models = @($Output -split '\r?\n' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Assert-OpenScienceCondition ($ExitCode -eq 0 -and [string]::IsNullOrWhiteSpace($ErrorOutput) -and $models.Count -gt 0 -and
        @($models | Where-Object { $_ -cnotmatch '^openai-codex/[A-Za-z0-9._:/-]+$' }).Count -eq 0 -and
        @($models | Sort-Object -Unique).Count -eq $models.Count) 'Official ChatGPT catalog did not return verified model IDs. Exit zero alone is not success; authentication/catalog remains unverified.'
    return $models
}

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
