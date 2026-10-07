# One bounded OpenScience model turn from the existing signed-in Windows profile.
# The profile's auth-only config is never modified; this process uses a temporary overlay.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json -AsHashtable
if ($request.model -notmatch '^openai-codex/[A-Za-z0-9._-]+$' -or
    $request.bridge_url -notmatch '^http://127\.0\.0\.1:[0-9]{1,5}$' -or
    $request.mcp_url -notmatch '^http://127\.0\.0\.1:[0-9]{1,5}/mcp$' -or
    $request.bridge_token -notmatch '^[A-Za-z0-9_-]{20,100}$' -or
    [int]$request.deadline -lt 1 -or [int]$request.deadline -gt 600 -or
    [int]$request.max_steps -lt 1 -or [int]$request.max_steps -gt 32) { throw 'Invalid bounded OpenScience invocation.' }
$profileInput = if ($request.profile_path) { [string]$request.profile_path } elseif ($env:CAELAB_OPENSCIENCE_PROFILE) { $env:CAELAB_OPENSCIENCE_PROFILE } else {
    Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\profiles\chatgpt-cae-20261001-02' }
$runtimeInput = if ($request.runtime_prefix) { [string]$request.runtime_prefix } elseif ($env:CAELAB_OPENSCIENCE_RUNTIME_PREFIX) { $env:CAELAB_OPENSCIENCE_RUNTIME_PREFIX } else {
    Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\runtimes\openscience-2.0.146' }
$profile = [IO.Path]::GetFullPath($profileInput)
$runtimePrefix = [IO.Path]::GetFullPath($runtimeInput)
$runtime = Join-Path $runtimePrefix 'node_modules\@synsci\openscience-windows-x64\bin\openscience.exe'
$profileConfig = Join-Path $profile 'config\openscience.json'
if (-not (Test-Path -LiteralPath (Join-Path $profile 'caelab-profile-owner.json')) -or
    -not (Test-Path -LiteralPath $runtime) -or -not (Test-Path -LiteralPath $profileConfig)) { throw 'Pinned OpenScience profile/runtime unavailable.' }
$marker = Get-Content -LiteralPath (Join-Path $profile 'caelab-profile-owner.json') -Raw | ConvertFrom-Json -AsHashtable
if ($marker.kind -cne 'autonomous-cae-lab.chatgpt-auth-profile' -or $marker.provider -cne 'openai-codex' -or
    $marker.profile_root -ine $profile -or $marker.runtime_version -cne '2.0.146') { throw 'OpenScience auth profile identity changed.' }
$binaryPin = @($marker.runtime_pin.NativeBinaries | Where-Object { $_.Path -ieq $runtime })
if ($binaryPin.Count -ne 1 -or (Get-FileHash -LiteralPath $runtime -Algorithm SHA256).Hash -ine $binaryPin[0].Sha256) {
    throw 'Pinned OpenScience executable identity changed.'
}
$base = Get-Content -LiteralPath $profileConfig -Raw | ConvertFrom-Json -AsHashtable
if ($base.permission['*'] -cne 'deny' -or $base.enabled_providers.Count -ne 1 -or
    $base.enabled_providers[0] -cne 'openai-codex') { throw 'Auth profile policy changed.' }
$tempRoot = [IO.Path]::GetFullPath((Join-Path $profile 'temp'))
$temp = [IO.Path]::GetFullPath((Join-Path $tempRoot ('caelab-expert-' + [Guid]::NewGuid().ToString('N'))))
if (-not $temp.StartsWith($tempRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Temporary config target escaped the owned profile.'
}
$configDir = Join-Path $temp 'config'
New-Item -ItemType Directory -Path $configDir | Out-Null
try {
    $toolPermissions = [ordered]@{ '*' = 'deny' }
    $mcpPermissions = [ordered]@{ '*' = 'deny' }
    foreach ($name in @($request.tool_names)) {
        if ($name -notmatch '^[a-z][a-z0-9_]{1,80}$') { throw 'Invalid scoped MCP tool name.' }
        $toolPermissions[('caelab_' + $name)] = 'allow'
        $mcpPermissions[('caelab_' + $name)] = 'allow'
    }
    $toolPermissions['mcp'] = $mcpPermissions
    $base.permission = $toolPermissions
    # OpenScience's tool-visibility layer requires explicit per-agent rules.
    $base.agent = @{ research = @{ permission = $toolPermissions; steps = [int]$request.max_steps } }
    # The external controller owns continuation, review, budgets and artifacts.
    # OpenScience 2.0.146 otherwise appends research deliverable follow-ups even
    # after the agent step limit, replacing the requested structured answer.
    # durable-jobs also gates bootstrap resumeInterrupted: a new bounded turn must
    # never revive a cancelled prior session with its new callback scope/budget.
    $base.harness = @{ deliverables=$false; acceptance=$false; unattended=$false;
        review=$false; budget=$false; redirect=$false; 'durable-jobs'=$false }
    # Windows has no sandbox backend. Only this named remote MCP may be used;
    # all other agent tools remain denied by the explicit permission map.
    $base.sandbox = @{ enabled = $false }
    $base.mcp = @{ caelab = @{ type = 'remote'; url = [string]$request.mcp_url;
        headers = @{ Authorization = ('Bearer ' + [string]$request.bridge_token) };
        oauth = $false; timeout = ([int]$request.deadline * 1000) } }
    $base | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $configDir 'openscience.json') -Encoding utf8NoBOM
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $runtime
    $info.WorkingDirectory = $profile
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.UTF8Encoding]::new($false)
    $info.StandardErrorEncoding = [Text.UTF8Encoding]::new($false)
    $arguments = @('run', '--format', 'json', '--workspace', 'isolated', '--delegation', 'off',
                   '--deny-prompts', '--model', $request.model, '--variant', 'high',
                   '--deadline', [string]$request.deadline, '--', [string]$request.prompt)
    foreach ($argument in $arguments) {
        $info.ArgumentList.Add([string]$argument)
    }
    $environment = @{
        OPENSCIENCE_TEST_HOME = (Join-Path $profile 'home'); OPENSCIENCE_CONFIG_DIR = $configDir
        OPENSCIENCE_DATA_DIR = (Join-Path $profile 'data'); XDG_CONFIG_HOME = (Join-Path $profile 'xdg-config')
        XDG_DATA_HOME = (Join-Path $profile 'xdg-data'); XDG_CACHE_HOME = (Join-Path $profile 'xdg-cache')
        XDG_STATE_HOME = (Join-Path $profile 'xdg-state'); TEMP = (Join-Path $profile 'temp')
        TMP = (Join-Path $profile 'temp'); OPENSCIENCE_DISABLE_AUTOUPDATE = '1'
        OPENSCIENCE_DISABLE_MODELS_FETCH = '1'; OPENSCIENCE_DISABLE_PROJECT_CONFIG = '1'
        OPENSCIENCE_DISABLE_LSP_DOWNLOAD = '1'
    }
    foreach ($name in $environment.Keys) { $info.Environment[$name] = [string]$environment[$name] }
    $process = [Diagnostics.Process]::Start($info)
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $stopReason = $null
        $statusUri = [string]$request.bridge_url + '/status'
        $statusHeaders = @{ Authorization = ('Bearer ' + [string]$request.bridge_token) }
        while (-not $process.WaitForExit(250)) {
            try {
                $status = Invoke-RestMethod -Method Get -Uri $statusUri -Headers $statusHeaders -TimeoutSec 2
                if ($status.cancel_requested -eq $true) { $stopReason = 'User cancellation observed'; break }
            } catch { $stopReason = 'Expert bridge status unavailable'; break }
            if ($watch.Elapsed.TotalSeconds -ge ([int]$request.deadline + 5)) {
                $stopReason = 'OpenScience deadline exceeded'; break
            }
        }
        if ($stopReason) {
            # This Process object is the exact child started above. Kill(true)
            # requests termination of its descendants too; failure to reap
            # the owned leader is an unconfirmed cleanup, never cancellation.
            if (-not $process.HasExited) { $process.Kill($true) }
            if (-not $process.WaitForExit(5000)) { throw 'OpenScience owned process cleanup unconfirmed' }
            @{status='stopped'; cleanup_confirmed=$true; reason=$stopReason} | ConvertTo-Json -Compress
            return
        }
        $raw = $stdout.GetAwaiter().GetResult()
        $errorText = $stderr.GetAwaiter().GetResult()
        $events = @($raw -split "`r?`n" | Where-Object { $_.Trim() } | ForEach-Object {
            try { $_ | ConvertFrom-Json -AsHashtable } catch { $null }
        } | Where-Object { $null -ne $_ })
        $done = @($events | Where-Object type -eq 'done' | Select-Object -Last 1)
        # A run may emit earlier assistant text before tool calls. Only the
        # final assistant text part is the structured answer for this turn.
        $parts = @($events | Where-Object type -eq 'text' | Select-Object -Last 1)
        $status = if ($process.ExitCode -eq 0 -and $done.Count -eq 1 -and $done[0].status -eq 'completed') { 'completed' } else { 'failed' }
        @{ status = $status; cleanup_confirmed=$true; text = if ($parts.Count) { [string]$parts[0].part.text } else { $null };
           reason = if ($status -eq 'completed') { $null } else { "$($done[0].status); exit=$($process.ExitCode); $($errorText.Substring(0,[Math]::Min(500,$errorText.Length)))" } } |
            ConvertTo-Json -Compress -Depth 10
    } finally { if (-not $process.HasExited) { $process.Kill($true) } }
} finally {
    if (Test-Path -LiteralPath $temp) {
        $resolvedTemp = (Resolve-Path -LiteralPath $temp).Path
        $resolvedRoot = (Resolve-Path -LiteralPath $tempRoot).Path
        if (-not $resolvedTemp.StartsWith($resolvedRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) { throw 'Refusing to remove a config outside the owned temporary root.' }
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}
