# Creates only an isolated acceptance profile. It never installs a runtime,
# changes an Ollama model, or reads account credential values.
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$RunName = 'local-20260930-openscience-live-04',
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$ProfileTag = 'task',
    [string[]]$AllowedTools = @('caelab_study_create'),
    [ValidateRange(256, 2048)][int]$OutputTokens = 768,
    [ValidateRange(2, 4)][int]$Steps = 2,
    [ValidateRange(30, 600)][int]$ProviderTimeoutSeconds = 150,
    [string]$ModelId = 'openscience/qwen3-4b-ctx-16384',
    [string]$WslDistro = 'Ubuntu',
    [string]$WslPython = '/home/pikachu444/.local/share/autonomous-cae-lab/venv-py312/bin/python'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required for native ArgumentList handling.' }
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
if ($RepoRoot -notmatch '^([A-Za-z]):[\\/](.+)$') { throw 'The WSL bridge requires an absolute Windows drive path.' }
$taskWslRoot = '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + ($Matches[2] -replace '\\', '/')
$taskArtifacts = Join-Path $RepoRoot "artifacts\$RunName"
$taskStore = Join-Path $RepoRoot "runs\$RunName"
$taskProfile = Join-Path $taskArtifacts "profiles\$ProfileTag"
$taskOwner = Join-Path $taskProfile 'caelab-profile-owner.json'
$taskKnownTools = @(
    'caelab_study_create', 'caelab_study_inspect', 'caelab_parameters_discover',
    'caelab_parameters_register', 'caelab_parameters_list', 'caelab_experiment_run',
    'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare'
)
foreach ($taskTool in $AllowedTools) {
    if ($taskTool -notin $taskKnownTools) { throw "Tool is outside this bounded acceptance: $taskTool" }
}
if ((Test-Path -LiteralPath $taskProfile) -and -not (Test-Path -LiteralPath $taskOwner)) {
    throw 'The profile already exists without this acceptance ownership marker; it will not be changed.'
}
if (Test-Path -LiteralPath $taskOwner) {
    $taskPrior = Get-Content -LiteralPath $taskOwner -Raw | ConvertFrom-Json
    if ($taskPrior.run_name -ne $RunName -or $taskPrior.repo_root -ne $RepoRoot) {
        throw 'Profile ownership does not match this repository and run.'
    }
}
$taskRuntime = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\runtimes\openscience-2.0.146'
$taskLauncher = Join-Path $taskRuntime 'node_modules\@synsci\openscience\bin\openscience'
$taskPackage = Join-Path $taskRuntime 'node_modules\@synsci\openscience\package.json'
if (-not (Test-Path -LiteralPath $taskLauncher)) { throw 'The pinned task-owned OpenScience runtime is missing.' }
if ((Get-Content -LiteralPath $taskPackage -Raw | ConvertFrom-Json).version -ne '2.0.146') {
    throw 'The installed launcher package is not the verified 2.0.146 version.'
}
$taskNode = (Get-Command node.exe -ErrorAction Stop).Source
$taskEnv = [ordered]@{
    OPENSCIENCE_TEST_HOME = (Join-Path $taskProfile 'home')
    OPENSCIENCE_CONFIG_DIR = (Join-Path $taskProfile 'config')
    OPENSCIENCE_DATA_DIR = (Join-Path $taskProfile 'data')
    XDG_CONFIG_HOME = (Join-Path $taskProfile 'xdg-config')
    XDG_DATA_HOME = (Join-Path $taskProfile 'xdg-data')
    XDG_CACHE_HOME = (Join-Path $taskProfile 'xdg-cache')
    XDG_STATE_HOME = (Join-Path $taskProfile 'xdg-state')
    OPENSCIENCE_DISABLE_AUTOUPDATE = '1'
    OPENSCIENCE_DISABLE_AUTOCOMPACT = '1'
    OPENSCIENCE_DISABLE_PRUNE = '1'
    OPENSCIENCE_DISABLE_MODELS_FETCH = '1'
    OPENSCIENCE_DISABLE_LSP_DOWNLOAD = '1'
    OPENSCIENCE_DISABLE_PROJECT_CONFIG = '1'
    OPENSCIENCE_EXPERIMENTAL_OUTPUT_TOKEN_MAX = [string]$OutputTokens
    # MCP's Windows ownership handshake uses os.tmpdir() in parent and child.
    # Use the same explicit task directory for their ready/release markers.
    TEMP = (Join-Path $taskProfile 'temp')
    TMP = (Join-Path $taskProfile 'temp')
}
@($taskArtifacts, $taskStore, $taskProfile, $taskEnv.TEMP) + @($taskEnv.Values | Select-Object -First 7) |
    ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null }
if (-not (Test-Path -LiteralPath $taskOwner)) {
    [ordered]@{ run_name = $RunName; repo_root = $RepoRoot; created_utc = [DateTime]::UtcNow.ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $taskOwner -Encoding utf8
}
$taskPermission = [ordered]@{ '*' = 'deny' }
$taskMcpPermission = [ordered]@{ '*' = 'deny' }
foreach ($taskTool in $AllowedTools) { $taskPermission[$taskTool] = 'allow'; $taskMcpPermission[$taskTool] = 'allow' }
$taskPermission['mcp'] = $taskMcpPermission
$taskAgentPrompt = if ($AllowedTools.Count -eq 0) {
    'Interpret only the supplied actual CAE-Lab receipts. There are no tools to call. Do not plan aloud or invent evidence. Follow the requested short format and retain UNKNOWN and NOT_RELEASED. /no_think'
} else {
    'Execute the one requested CAE-Lab action with the actual available tool. Use the supplied arguments exactly. Do not plan aloud, invent paths, simulate calls, or repeat a completed action. After its receipt, stop with one sentence. Preserve UNKNOWN and NOT_RELEASED. /no_think'
}
$taskMcpCommand = @(
    "$env:WINDIR\System32\wsl.exe", '-d', $WslDistro, '--cd', $taskWslRoot, '--', '/usr/bin/env',
    "CAELAB_STORE=$taskWslRoot/runs/$RunName", $WslPython, "$taskWslRoot/openscience/mcp_server.py"
)
# Keys below are checked against the exact pinned upstream Config/Agent/model
# schema and LLM/ProviderTransform source. Output/steps bound each model turn;
# the verification script also imposes an external wall-clock timeout.
$taskConfig = [ordered]@{
    enabled_providers = @('ollama')
    model = "ollama/$ModelId"
    small_model = "ollama/$ModelId"
    default_agent = 'caelab-acceptance'
    snapshot = $false
    billing = @{ llm = 'byok' }
    compaction = @{ auto = $false; prune = $false }
    permission = $taskPermission
    sandbox = @{ enabled = $true; onUnavailable = 'warn' }
    harness = [ordered]@{
        'headless-policy' = $false; redirect = $false; deliverables = $false; acceptance = $false
        unattended = $false; review = $false; budget = $false; cost = $false
        'durable-jobs' = $false; workers = $false
    }
    agent = [ordered]@{
        title = @{ disable = $true }
        'caelab-acceptance' = @{
            mode = 'primary'; model = "ollama/$ModelId"; temperature = 0; steps = $Steps; skills = @()
            options = @{ reasoningEffort = 'none' }
            permission = $taskPermission
            prompt = $taskAgentPrompt
        }
    }
    provider = @{
        ollama = @{
            name = 'Task-local Ollama'; npm = '@ai-sdk/openai-compatible'; api = 'http://127.0.0.1:11434/v1'
            options = @{
                baseURL = 'http://127.0.0.1:11434/v1'; apiKey = 'local'; localRuntime = 'ollama'
                timeout = ($ProviderTimeoutSeconds * 1000); connectTimeout = ($ProviderTimeoutSeconds * 1000)
                idleTimeout = 60000
            }
            models = @{
                $ModelId = @{
                    name = $ModelId; tool_call = $true; reasoning = $false; temperature = $true
                    cost = @{ input = 0; output = 0 }; limit = @{ context = 16384; output = $OutputTokens }
                    options = @{ reasoningEffort = 'none' }
                }
            }
        }
    }
    mcp = @{ caelab = @{ type = 'local'; command = $taskMcpCommand; enabled = $true; timeout = 120000 } }
}
$taskConfigPath = Join-Path $taskEnv.OPENSCIENCE_CONFIG_DIR 'openscience.json'
$taskConfig | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $taskConfigPath -Encoding utf8
[pscustomobject]@{
    RepoRoot = $RepoRoot; RunName = $RunName; ArtifactRoot = $taskArtifacts; StoreRoot = $taskStore
    ProfileRoot = $taskProfile; ConfigPath = $taskConfigPath; NodePath = $taskNode; LauncherPath = $taskLauncher
    Environment = $taskEnv; Model = "ollama/$ModelId"; AllowedTools = $AllowedTools
    RemoveEnvironment = @('OPENSCIENCE_CONFIG', 'OPENSCIENCE_CONFIG_CONTENT', 'OPENSCIENCE_AUTH_TOKEN', 'OPENSCIENCE_BIN_PATH')
    SourceCommit = '4082a2ecb73e166d4503963798228ba700f3840f'
    SourceBase = 'https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src'
}
