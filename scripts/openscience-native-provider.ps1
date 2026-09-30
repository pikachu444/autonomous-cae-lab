# Native official ChatGPT provider transport. No token copy or provider fallback.
# Loaded after the common lifecycle and authentication helpers; no entrypoint.
function Get-OpenScienceNativePluginSource {
    (Get-OpenScienceRepositoryPinSource) + "`n" + [IO.File]::ReadAllText((Join-Path (Split-Path -Parent $PSScriptRoot) 'openscience/native_guard.mjs'))
}

function Get-OpenScienceNativeContextSha256($Context) {
    $document = [Text.Json.JsonDocument]::Parse(($Context | ConvertTo-Json -Depth 30 -Compress))
    try { $identity = ConvertFrom-OpenScienceJsonElement $document.RootElement } finally { $document.Dispose() }
    foreach ($name in @('RuntimeURL', 'WorkspaceURL', 'ConnectorStatus', 'RuntimeDirectory', 'BootSource', 'BootSourceSha256')) {
        $identity.Remove($name) | Out-Null
    }
    Get-OpenScienceSourcePinSha256 -SourcePin $identity
}

function Assert-OpenScienceNativeContext($Context, [switch]$LifecycleOnly) {
    Assert-OpenScienceCondition ($Context.Model -ceq $Context.ModelId -and $Context.Model -cmatch '^openai-codex/[A-Za-z0-9._-]+$') 'Native research requires one explicit official ChatGPT model.'
    # Hidden controllers use a clean machine environment; resolve the actual
    # user's known folder independently of inherited LOCALAPPDATA values.
    $externalRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'AutonomousCAELab/profiles'
    Assert-OpenScienceContainedPath $Context.ProfileRoot $externalRoot | Out-Null
    foreach ($key in @('PluginPath', 'PluginSettingsPath', 'HookReceiptsPath', 'WslPythonCacheRoot')) {
        Assert-OpenScienceContainedPath $Context.$key $Context.ProfileRoot | Out-Null
    }
    Assert-OpenScienceContainedPath $Context.AuthProfileRoot $externalRoot | Out-Null
    $authMarkerPath = Assert-OpenScienceContainedPath (Join-Path $Context.AuthProfileRoot 'caelab-profile-owner.json') $Context.AuthProfileRoot
    $authMarker = Read-OpenScienceJson $authMarkerPath
    Assert-OpenScienceCondition ($authMarker.kind -ceq 'autonomous-cae-lab.chatgpt-auth-profile' -and $authMarker.schema -eq 2 -and
        $authMarker.profile_root -ceq $Context.AuthProfileRoot -and $authMarker.data_root -ceq $Context.Environment.OPENSCIENCE_DATA_DIR -and
        $authMarker.runtime_version -ceq $script:OpenSciencePinnedVersion -and $authMarker.source_commit -ceq $script:OpenSciencePinnedSource) 'Native transport authentication ownership changed.'
    $authPin = $authMarker.runtime_pin
    $nativePin = @($authPin.NativeBinaries | Where-Object { $_.Path -ceq $Context.NativePath })
    Assert-OpenScienceCondition ($nativePin.Count -eq 1 -and $Context.RuntimePrefix -ceq $authPin.RuntimePrefix -and
        $Context.NodePath -ceq $authPin.NodePath -and $Context.NodeSha256 -ceq $authPin.NodeSha256 -and
        $Context.LauncherPath -ceq $authPin.LauncherPath -and $Context.LauncherSha256 -ceq $authPin.LauncherSha256 -and
        (Get-OpenScienceSourcePinSha256 -SourcePin @{ binaries = $Context.NativeBinaries }) -ceq
        (Get-OpenScienceSourcePinSha256 -SourcePin @{ binaries = $authPin.NativeBinaries })) 'Native execution path/runtime differs from the independently owned authentication pin.'
    foreach ($native in $authPin.NativeBinaries) {
        Assert-OpenScienceContainedPath $native.Path $authPin.RuntimePrefix | Out-Null
        Assert-OpenScienceContainedPath $native.PackagePath $authPin.RuntimePrefix | Out-Null
        Assert-OpenScienceCondition ((Get-OpenScienceHash $native.PackagePath) -ceq $native.PackageSha256) 'Official native package bytes changed.'
    }
    $researchMarker = Read-OpenScienceJson (Join-Path $Context.ProfileRoot 'caelab-profile-owner.json')
    Assert-OpenScienceCondition ($researchMarker.transport -ceq 'ChatGPT' -and $researchMarker.context_sha256 -ceq
        (Get-OpenScienceNativeContextSha256 $Context)) 'Research context differs from the saved owned configuration; execution/lifecycle ownership is refused.'
    Assert-OpenScienceContainedPath $Context.Environment.OPENSCIENCE_DATA_DIR $Context.AuthProfileRoot | Out-Null
    Assert-OpenScienceContainedPath (Join-Path $Context.Environment.OPENSCIENCE_DATA_DIR 'auth.json') $Context.AuthProfileRoot | Out-Null
    foreach ($name in $Context.Environment.Keys) {
        if ($name -in @('OPENSCIENCE_DATA_DIR')) { continue }
        if ($Context.Environment[$name] -is [string] -and [IO.Path]::IsPathRooted($Context.Environment[$name])) {
            Assert-OpenScienceContainedPath $Context.Environment[$name] $Context.ProfileRoot | Out-Null
        }
    }
    Assert-OpenScienceCondition ((Get-OpenScienceHash $Context.NodePath) -ceq $Context.NodeSha256) 'Pinned Node bytes changed; native launch refused.'
    # Source/config/plugin drift rejects new inference, but exact owned HTTP
    # cancellation and process cleanup retain independent identity checks.
    if ($LifecycleOnly) { return }
    Assert-OpenScienceCondition ((Get-OpenScienceHash $Context.PluginPath) -ceq $Context.PluginSha256 -and
        (Get-OpenScienceHash $Context.ConfigPath) -ceq $Context.ConfigSha256) 'Owned native plugin/configuration changed; launch refused.'
    $config = Read-OpenScienceJson $Context.ConfigPath
    Assert-OpenScienceCondition ($config.model -ceq $Context.Model -and $config.small_model -ceq $Context.Model -and
        @($config.enabled_providers).Count -eq 1 -and $config.enabled_providers[0] -ceq 'openai-codex' -and
        @($config.plugin).Count -eq 1 -and $config.plugin[0] -ceq ([Uri]$Context.PluginPath).AbsoluteUri) 'Native config model/provider/plugin differs from its declared context.'
}

function New-OpenScienceNativeContext {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)][string]$RunName,
        [string]$ProfileTag, [string]$StoreRoot, [string]$RuntimePrefix, [string]$ModelId, [string]$AuthProfileRoot,
        [string]$WslDistro, [string]$WslPython, [AllowEmptyCollection()][string[]]$AllowedTools,
        [int]$OutputTokens, [int]$Steps, [int]$ProviderTimeoutSeconds)
    Assert-OpenScienceCondition ($ModelId -cmatch '^openai-codex/[A-Za-z0-9._-]+$') 'Select a full official ChatGPT model ID explicitly. No default or fallback model is permitted.'
    Assert-OpenScienceCondition (-not [string]::IsNullOrWhiteSpace($AuthProfileRoot)) 'The separately authenticated external profile is required.'
    $authRoot = [IO.Path]::GetFullPath($AuthProfileRoot)
    Assert-OpenScienceContainedPath $authRoot (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab/profiles') | Out-Null
    $authFile = Assert-OpenScienceContainedPath (Join-Path $authRoot 'data/auth.json') $authRoot
    Assert-OpenScienceCondition (Test-Path -LiteralPath $authFile -PathType Leaf) 'ChatGPT sign-in is not complete. No research profile, model request or credential copy was made.'
    $auth = New-OpenScienceChatGptContext -ProfileRoot $authRoot -RuntimePrefix $RuntimePrefix
    $authPin = (Read-OpenScienceJson (Join-Path $authRoot 'caelab-profile-owner.json')).runtime_pin
    $RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
    if (-not $StoreRoot) { $StoreRoot = Join-Path $RepoRoot "runs/$RunName" }
    $StoreRoot = [IO.Path]::GetFullPath($StoreRoot)
    Assert-OpenScienceContainedPath $StoreRoot $RepoRoot | Out-Null
    $profile = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "AutonomousCAELab/profiles/$RunName-$ProfileTag-research"))
    Assert-OpenScienceContainedPath $profile (Join-Path $env:LOCALAPPDATA 'AutonomousCAELab/profiles') | Out-Null
    Assert-OpenScienceCondition ($profile -cne $authRoot) 'Research configuration must not overwrite the authentication profile.'
    Assert-OpenScienceCondition ($WslDistro -match '^[A-Za-z0-9_.-]+$' -and $WslPython -match '^/[^\r\n]+$') 'Invalid existing WSL runtime reference.'
    Assert-OpenScienceCondition (@($AllowedTools | Sort-Object -Unique).Count -eq @($AllowedTools).Count) 'Duplicate tools are not permitted.'
    foreach ($tool in $AllowedTools) { Assert-OpenScienceCondition ($tool -cin $script:OpenScienceBoundedTools) 'Tool is outside the nine-tool research acceptance.' }
    $hostGit = $null; $originalWslPath = $null
    $gitPointer = Join-Path $RepoRoot '.git'
    if ((Test-Path -LiteralPath $gitPointer -PathType Leaf) -and ((Get-Content -LiteralPath $gitPointer -TotalCount 1) -match '^gitdir: [A-Za-z]:')) {
        $hostGit = (Get-Command git.exe -ErrorAction Stop).Source
        $originalWslPath = & wsl.exe -d $WslDistro -- /usr/bin/printenv PATH
        Assert-OpenScienceCondition ($LASTEXITCODE -eq 0 -and @($originalWslPath).Count -eq 1) 'Could not read the existing WSL command path.'
    }
    $mcpGit = New-OpenScienceMcpGitTransport -RepoRoot $RepoRoot -HostGitPath $hostGit -OriginalWslPath $originalWslPath
    $pluginSource = Get-OpenScienceNativePluginSource
    $pluginHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.UTF8Encoding]::new($false).GetBytes($pluginSource))).ToLowerInvariant()
    $intent = [ordered]@{ transport = 'ChatGPT'; repo_root = $RepoRoot; run_name = $RunName; profile_tag = $ProfileTag
        store_root = $StoreRoot; auth_profile_root = $authRoot; runtime_prefix = $auth.RuntimePrefix; model = $ModelId
        wsl_distro = $WslDistro; wsl_python = $WslPython; allowed_tools = @($AllowedTools); output_tokens = $OutputTokens
        steps = $Steps; provider_timeout_seconds = $ProviderTimeoutSeconds; mcp_git_transport = $mcpGit; plugin_sha256 = $pluginHash }
    $intentHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes(($intent | ConvertTo-Json -Depth 12 -Compress)))).ToLowerInvariant()
    $markerPath = Assert-OpenScienceContainedPath (Join-Path $profile 'caelab-profile-owner.json') $profile
    $contextPath = Assert-OpenScienceContainedPath (Join-Path $profile 'context.json') $profile
    if (Test-Path -LiteralPath $profile) {
        Assert-OpenScienceCondition (Test-Path -LiteralPath $markerPath -PathType Leaf) 'An existing unowned external profile will not be changed.'
        $marker = Read-OpenScienceJson $markerPath
        Assert-OpenScienceCondition ($marker.intent_sha256 -ceq $intentHash) 'Research ownership/configuration differs; choose a new run.'
        $saved = [pscustomobject](Read-OpenScienceJson $contextPath)
        Assert-OpenScienceContext $saved
        return $saved
    }
    Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $StoreRoot)) 'Use a new experiment store; historical experiments will not be overwritten.'
    $environment = [ordered]@{ OPENSCIENCE_DATA_DIR = $auth.DataRoot; OPENSCIENCE_CONFIG_DIR = (Join-Path $profile 'config')
        OPENSCIENCE_TEST_HOME = (Join-Path $profile 'home'); XDG_CONFIG_HOME = (Join-Path $profile 'xdg-config')
        XDG_DATA_HOME = (Join-Path $profile 'xdg-data'); XDG_CACHE_HOME = (Join-Path $profile 'xdg-cache')
        XDG_STATE_HOME = (Join-Path $profile 'xdg-state'); TEMP = (Join-Path $profile 'temp'); TMP = (Join-Path $profile 'temp')
        OPENSCIENCE_DISABLE_AUTOUPDATE = '1'; OPENSCIENCE_DISABLE_AUTOCOMPACT = '1'; OPENSCIENCE_DISABLE_PRUNE = '1'
        OPENSCIENCE_DISABLE_MODELS_FETCH = '1'; OPENSCIENCE_DISABLE_PROJECT_CONFIG = '1'; OPENSCIENCE_DISABLE_LSP_DOWNLOAD = '1'
        OPENSCIENCE_EXPERIMENTAL_OUTPUT_TOKEN_MAX = [string]$OutputTokens }
    $context = [pscustomobject]@{ Transport = 'ChatGPT'; AuthProfileRoot = $authRoot; RepoRoot = $RepoRoot; RunName = $RunName
        ProfileTag = $ProfileTag; ProfileRoot = $profile; ArtifactRoot = (Join-Path $RepoRoot "artifacts/$RunName"); StoreRoot = $StoreRoot
        ConfigPath = (Join-Path $profile 'config/openscience.json'); PluginPath = (Join-Path $profile 'native-guard.mjs')
        PluginSettingsPath = (Join-Path $profile 'native-guard-settings.json'); HookReceiptsPath = (Join-Path $profile 'hook-receipts')
        PluginSha256 = $pluginHash; NodePath = $auth.NodePath; NodeSha256 = $authPin.NodeSha256; LauncherPath = $auth.LauncherPath
        LauncherSha256 = $authPin.LauncherSha256; RuntimePrefix = $auth.RuntimePrefix; NativePath = $auth.NativePath
        NativeBinaries = $authPin.NativeBinaries; Environment = $environment; RemoveEnvironment = @()
        Model = $ModelId; ModelId = $ModelId; AllowedTools = @($AllowedTools); OutputTokens = $OutputTokens; Steps = $Steps
        ProviderTimeoutSeconds = $ProviderTimeoutSeconds; SourceCommit = $script:OpenSciencePinnedSource; McpGitTransport = $mcpGit
        WslPythonCacheRoot = (Join-Path $profile 'wsl-pycache'); IntentSha256 = $intentHash
        OwnerPath = (Join-Path $profile 'runtime-owner.json'); GuardPath = (Join-Path $profile 'expected-tools.json')
        SandboxLimitation = 'Windows has no native OpenScience sandbox backend. warn fallback is explicit; application permissions are not OS containment.' }
    $permission = [ordered]@{ '*' = 'deny' }; $mcpPermission = [ordered]@{ '*' = 'deny' }
    foreach ($tool in $AllowedTools) { $permission[$tool] = 'allow'; $mcpPermission[$tool] = 'allow' }
    $permission['mcp'] = $mcpPermission
    $agent = [ordered]@{ mode = 'primary'; model = $ModelId; steps = $Steps; skills = @(); options = @{ reasoningEffort = 'low' }
        permission = $permission; prompt = 'Use the requested CAE Lab function once with the exact supplied JSON arguments. Then briefly report its receipt. For interpretation, use only supplied actual receipts. Preserve UNKNOWN and NOT_RELEASED.' }
    $config = [ordered]@{ enabled_providers = @('openai-codex'); model = $ModelId; small_model = $ModelId; default_agent = 'research'
        plugin = @(([Uri]$context.PluginPath).AbsoluteUri); snapshot = $false; billing = @{ llm = 'byok' }
        compaction = @{ auto = $false; prune = $false }; permission = $permission; sandbox = @{ enabled = $true; onUnavailable = 'warn' }
        harness = @{ 'headless-policy' = $false; redirect = $false; deliverables = $false; acceptance = $false; unattended = $false
            review = $false; budget = $false; cost = $false; 'durable-jobs' = $false; workers = $false }
        agent = @{ title = @{ disable = $true }; research = $agent; 'caelab-acceptance' = $agent }
        provider = @{ 'openai-codex' = @{ options = @{ timeout = ($ProviderTimeoutSeconds * 1000)
            connectTimeout = ($ProviderTimeoutSeconds * 1000); idleTimeout = 60000 } } }
        mcp = @{ caelab = @{ type = 'local'; enabled = $true; timeout = 120000; environment = $mcpGit.SubprocessEnvironment; command = @(
            "$env:WINDIR/System32/wsl.exe", '-d', $WslDistro, '--cd', (ConvertTo-OpenScienceWslPath $RepoRoot), '--', '/usr/bin/env',
            ('CAELAB_STORE=' + (ConvertTo-OpenScienceWslPath $StoreRoot)), ('PYTHONPYCACHEPREFIX=' + (ConvertTo-OpenScienceWslPath $context.WslPythonCacheRoot))) +
            @($mcpGit.Environment) + @($WslPython, ((ConvertTo-OpenScienceWslPath $RepoRoot) + '/openscience/mcp_server.py')) } } }
    New-Item -ItemType Directory -Path $profile -ErrorAction Stop | Out-Null
    foreach ($directory in @($environment.Values | Where-Object { $_.StartsWith($profile + '\') -or $_.StartsWith($profile + '/') } | Sort-Object -Unique) +
        @($context.HookReceiptsPath, $context.WslPythonCacheRoot)) {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
    }
    [IO.File]::WriteAllText($context.PluginPath, $pluginSource, [Text.UTF8Encoding]::new($false))
    Write-OpenScienceJson $context.ConfigPath $config -CreateNew
    $context | Add-Member -NotePropertyName ConfigSha256 -NotePropertyValue (Get-OpenScienceHash $context.ConfigPath)
    Write-OpenScienceJson $contextPath $context -CreateNew
    Write-OpenScienceJson $markerPath @{ kind = 'autonomous-cae-lab.openscience-profile'; schema = 1; transport = 'ChatGPT'
        repo_root = $RepoRoot; run_name = $RunName; profile_root = $profile; intent_sha256 = $intentHash
        context_sha256 = (Get-OpenScienceNativeContextSha256 $context); created_utc = [DateTime]::UtcNow.ToString('o') } -CreateNew
    Initialize-OpenScienceToolGuard $context
    return $context
}

function Initialize-OpenScienceNativeGuard($Context, $Owner) {
    Write-OpenScienceJson $Context.PluginSettingsPath @{ schema = 1; kind = 'autonomous-cae-lab.openscience-native-guard'
        repo_root = $Context.RepoRoot; run_name = $Context.RunName; profile_root = $Context.ProfileRoot; model = $Context.Model
        allowed = @($Context.AllowedTools); guardPath = $Context.GuardPath; configPath = $Context.ConfigPath; config_sha256 = $Context.ConfigSha256
        pluginPath = $Context.PluginPath; plugin_sha256 = $Context.PluginSha256; receipts = $Context.HookReceiptsPath
        boot_source = $Owner.boot_source; boot_source_sha256 = $Owner.boot_source_sha256 } -CreateNew
    $Owner.plugin_settings_sha256 = Get-OpenScienceHash $Context.PluginSettingsPath
}

function Assert-OpenScienceNativeGuardLoaded($Context, $Owner) {
    Assert-OpenScienceContainedPath $Context.PluginSettingsPath $Context.ProfileRoot | Out-Null
    Assert-OpenScienceCondition ((Get-OpenScienceHash $Context.PluginSettingsPath) -ceq $Owner.plugin_settings_sha256) 'Native hook settings changed; new research is refused.'
    $loaded = @(Get-ChildItem -LiteralPath $Context.HookReceiptsPath -File -Filter '*.json' -ErrorAction Stop | ForEach-Object {
        Assert-OpenScienceContainedPath $_.FullName $Context.ProfileRoot | Out-Null
        Read-OpenScienceJson $_.FullName
    } | Where-Object { $_.hook -ceq 'plugin.loaded' -and $_.pid -eq $Owner.native.Pid -and $_.accepted -ceq $true -and
        $_.boot_source_sha256 -ceq $Owner.boot_source_sha256 })
    Assert-OpenScienceCondition ($loaded.Count -gt 0) 'The actual official native process has no loaded guard receipt; research is refused.'
}
