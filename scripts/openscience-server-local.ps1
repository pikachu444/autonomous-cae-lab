# Task-owned Windows OpenScience 2.0.146. No installation, model changes or
# browser launch. Dot-source with -Library to use the runner helpers.
[CmdletBinding()]
param(
    [switch]$Library,
    [Alias('ServerMode')][ValidateSet('Start', 'Status', 'Stop', 'ServeInternal', 'SelfTest')][string]$Mode = 'Status',
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName = 'local-openscience-runtime',
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$ProfileTag = 'runtime',
    [string]$StoreRoot,
    [string]$RuntimePrefix,
    [string]$ModelId,
    [ValidateSet('Ollama', 'ChatGPT')][string]$Transport = 'Ollama',
    [string]$AuthProfileRoot,
    [string]$WslDistro = 'Ubuntu',
    [string]$WslPython = '/home/pikachu444/.local/share/autonomous-cae-lab/venv-py312/bin/python',
    [string[]]$AllowedTools = @('caelab_study_create', 'caelab_study_inspect', 'caelab_parameters_discover',
        'caelab_parameters_register', 'caelab_parameters_list', 'caelab_experiment_run',
        'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare'),
    [ValidateRange(256, 4096)][int]$OutputTokens = 4096,
    [ValidateRange(1, 3)][int]$Steps = 3,
    [ValidateRange(30, 600)][int]$ProviderTimeoutSeconds = 260,
    [ValidateRange(0, 65535)][int]$Port = 4098,
    [ValidateRange(5, 180)][int]$StartupTimeoutSeconds = 120,
    [string]$OwnerPath,
    # Internal controller arguments are public ownership identifiers, not auth.
    [string]$ContextPath,
    [string]$LaunchToken
)

$script:OpenScienceServerScriptPath = $PSCommandPath
$script:OpenSciencePinnedVersion = '2.0.146'
$script:OpenSciencePinnedSource = '4082a2ecb73e166d4503963798228ba700f3840f'
$script:OpenScienceBoundedTools = @('caelab_study_create', 'caelab_study_inspect', 'caelab_parameters_discover',
    'caelab_parameters_register', 'caelab_parameters_list', 'caelab_experiment_run',
    'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare')

function Assert-OpenScienceCondition($Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Get-OpenScienceHash([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function Write-OpenScienceJson([string]$Path, $Value, [switch]$CreateNew) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 40) + "`n")
    if ($CreateNew) {
        $stream = [IO.FileStream]::new($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read, 1)
        try { $stream.Write($bytes); $stream.Flush($true) } finally { $stream.Dispose() }
    } else {
        $temporary = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
        try {
            Write-OpenScienceJson -Path $temporary -Value $Value -CreateNew
            [IO.File]::Move($temporary, $Path, $true)
        } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
    }
}

function ConvertFrom-OpenScienceJsonElement([Text.Json.JsonElement]$Element) {
    # Older PowerShell 7 has no -DateKind. JsonElement never guesses a date
    # from a JSON string, so PID creation text and all other strings stay exact.
    switch ($Element.ValueKind) {
        'Object' {
            $value = [Collections.Specialized.OrderedDictionary]::new([StringComparer]::Ordinal)
            foreach ($property in $Element.EnumerateObject()) {
                Assert-OpenScienceCondition (-not $value.Contains($property.Name)) 'Duplicate JSON property is not permitted in runtime records.'
                $value.Add($property.Name, (ConvertFrom-OpenScienceJsonElement $property.Value))
            }
            return $value
        }
        'Array' {
            $value = [Collections.Generic.List[object]]::new()
            foreach ($item in $Element.EnumerateArray()) { $value.Add((ConvertFrom-OpenScienceJsonElement $item)) }
            return ,$value.ToArray()
        }
        'String' { return $Element.GetString() }
        'Number' {
            [long]$integer = 0
            if ($Element.TryGetInt64([ref]$integer)) { return $integer }
            return $Element.GetDouble()
        }
        'True' { return $true }
        'False' { return $false }
        'Null' { return $null }
        default { throw 'Unsupported JSON value in runtime record.' }
    }
}

function Read-OpenScienceJson([string]$Path) {
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop
    if ((Get-Command ConvertFrom-Json -CommandType Cmdlet).Parameters.ContainsKey('DateKind')) {
        return $content | ConvertFrom-Json -AsHashtable -Depth 40 -DateKind String -ErrorAction Stop
    }
    $document = [Text.Json.JsonDocument]::Parse($content)
    try { return ConvertFrom-OpenScienceJsonElement $document.RootElement } finally { $document.Dispose() }
}

function Get-OpenScienceRepositoryPinSource {
    # Shared by the public snapshot helper and every proxy model POST. No
    # shell, Git hooks/fsmonitor, repository code import or provider call.
    @'
import sourceFs from 'node:fs';
import sourcePath from 'node:path';
import sourceCrypto from 'node:crypto';
import {execFileSync as sourceExec} from 'node:child_process';
const sourceDigest = bytes => sourceCrypto.createHash('sha256').update(bytes).digest('hex');
const sourceCanonical = value => JSON.stringify(value,(_,item)=>item&&typeof item==='object'&&!Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
const sourcePinSha = pin => sourceDigest(sourceCanonical(pin));
function captureRepositorySourcePin(repoRoot,gitPath) {
  repoRoot=sourcePath.resolve(repoRoot);gitPath=sourcePath.resolve(gitPath);
  const deadline=Date.now()+20000;
  const gitEnvironment={...process.env};
  for(const name of Object.keys(gitEnvironment))if(/^GIT_/i.test(name))delete gitEnvironment[name];
  const git=(root,args)=>{
    if(Date.now()>=deadline)throw new Error('Bounded source snapshot expired');
    return sourceExec(gitPath,['-C',root,'-c','core.fsmonitor=false',...args],
      {encoding:'utf8',timeout:Math.min(10000,deadline-Date.now()),maxBuffer:16*1024*1024,windowsHide:true,
       stdio:['ignore','pipe','pipe'],env:gitEnvironment});
  };
  const samePath=(left,right)=>process.platform==='win32'
    ? sourcePath.resolve(left).toLowerCase()===sourcePath.resolve(right).toLowerCase():sourcePath.resolve(left)===sourcePath.resolve(right);
  const owned=(root,relative)=>{
    if(sourcePath.isAbsolute(relative)||relative.split(/[\\/]/).includes('..'))throw new Error('Source path escapes repository');
    const absolute=sourcePath.resolve(root,relative);
    if(!samePath(absolute,root)&&!absolute.startsWith(root+sourcePath.sep))throw new Error('Source path escapes repository');
    let current=root;
    if(sourceFs.lstatSync(current).isSymbolicLink())throw new Error('Linked source is not pinned');
    for(const part of relative.split(/[\\/]/).filter(Boolean)){
      current=sourcePath.join(current,part);
      if(sourceFs.lstatSync(current).isSymbolicLink())throw new Error('Linked source is not pinned');
    }
    return absolute;
  };
  const ignoredImport=relative=>{
    const parts=relative.replaceAll('\\','/').split('/');
    if(['artifacts','runs','.venv','venv','node_modules','.git','.pytest_cache','.mypy_cache','.ruff_cache'].includes(parts[0]))return true;
    return parts.includes('__pycache__')&&relative.endsWith('.pyc');
  };
  const snapshot=()=>{
    const files=[],submodules=[],dirty=[];
    const visit=(root,prefix)=>{
      if(!samePath(git(root,['rev-parse','--show-toplevel']).trim(),root))throw new Error('Submodule checkout is unavailable');
      const head=git(root,['rev-parse','--verify','HEAD']).trim();
      if(!/^[0-9a-f]{40,64}$/.test(head))throw new Error('Repository HEAD is unavailable');
      const inventory=git(root,['ls-files','--stage','-z']);
      const status=git(root,['status','--porcelain=v1','--untracked-files=all','-z']);
      dirty.push(...status.split('\0').filter(Boolean).map(value=>prefix+value));
      const untracked=[...git(root,['ls-files','--others','--exclude-standard','-z']).split('\0'),
        ...git(root,['ls-files','--others','--ignored','--exclude-standard','-z','--','*.py','*.pyi','*.pyc','*.pyd','*.so','*.pth']).split('\0')];
      for(const relative of untracked.filter(Boolean)){
        if(!ignoredImport(relative)&&/\.(py|pyi|pyc|pyd|so|pth)$/i.test(relative))throw new Error('Untracked importable repository source is not pinned');
      }
      for(const entry of inventory.split('\0').filter(Boolean)){
        const match=/^(\d{6}) ([0-9a-f]{40,64}) (\d)\t([\s\S]+)$/.exec(entry);
        if(!match||match[3]!=='0')throw new Error('Unmerged source cannot be pinned');
        const [ ,mode,indexObject,,relative]=match,absolute=owned(root,relative),name=prefix+relative.replaceAll('\\','/');
        if(mode==='160000'){
          if(!sourceFs.statSync(absolute).isDirectory())throw new Error('Submodule source is unavailable');
          const nested=visit(absolute,name+'/');
          submodules.push({path:name,head:nested,index_commit:indexObject});
        }else{
          if(!['100644','100755'].includes(mode)||!sourceFs.statSync(absolute).isFile())throw new Error('Tracked source is missing or unsupported');
          files.push({path:name,sha256:sourceDigest(sourceFs.readFileSync(absolute)),index_object:indexObject,index_mode:mode});
        }
      }
      if(head!==git(root,['rev-parse','--verify','HEAD']).trim()||inventory!==git(root,['ls-files','--stage','-z'])||
        status!==git(root,['status','--porcelain=v1','--untracked-files=all','-z']))throw new Error('Repository changed during source capture');
      return head;
    };
    const head=visit(repoRoot,'');
    files.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);submodules.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);dirty.sort();
    return {schema:1,kind:'autonomous-cae-lab.repository-source-pin',repo_root:repoRoot,git_path:gitPath,
      git_sha256:sourceDigest(sourceFs.readFileSync(gitPath)),source_commit:head,
      source_tree_sha256:sourceDigest(sourceCanonical({files,submodules})),source_dirty:dirty,files,submodules};
  };
  const first=snapshot(),second=snapshot();
  if(sourceCanonical(first)!==sourceCanonical(second))throw new Error('Source bytes changed during capture');
  return second;
}
function assertRepositorySourcePin(expected,current){
  if(!expected||expected.schema!==1||expected.kind!=='autonomous-cae-lab.repository-source-pin'||
    sourceCanonical(expected)!==sourceCanonical(current))throw new Error('Repository source differs from the owned startup snapshot');
}
'@
}

function Invoke-OpenScienceSourceNode([string]$Source, [string[]]$Arguments, [string]$WorkingDirectory, [string]$NodePath) {
    if (-not $NodePath) { $NodePath = (Get-Command $(if ($IsWindows) { 'node.exe' } else { 'node' }) -ErrorAction Stop).Source }
    $info = [Diagnostics.ProcessStartInfo]::new(); $info.FileName = $NodePath; $info.WorkingDirectory = $WorkingDirectory
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true; $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.UTF8Encoding]::new($false); $info.StandardErrorEncoding = [Text.UTF8Encoding]::new($false)
    foreach ($name in @(Get-OpenScienceRemovedEnvironment @($info.Environment.Keys))) { $info.Environment.Remove($name) | Out-Null }
    foreach ($argument in @('--input-type=module', '--eval', $Source, '--') + $Arguments) { $info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $info
    try {
        Assert-OpenScienceCondition ($process.Start()) 'Local source snapshot reader could not start.'
        $output = $process.StandardOutput.ReadToEndAsync(); $errors = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(25000)) { $process.Kill(); throw 'Local source snapshot exceeded its bounded read time.' }
        Assert-OpenScienceCondition ($process.ExitCode -eq 0) 'Local repository source snapshot was refused; source files, submodules or importable untracked files are unresolved.'
        return $output.GetAwaiter().GetResult()
    } finally { $process.Dispose() }
}

function Get-OpenScienceRepositorySourcePin {
    [CmdletBinding(DefaultParameterSetName = 'Repository')]
    param([Parameter(Mandatory, ParameterSetName = 'Repository')][string]$RepoRoot,
        [Parameter(Mandatory, ParameterSetName = 'Context')]$Context, [string]$GitPath, [string]$GitSha256)
    if ($PSCmdlet.ParameterSetName -eq 'Context') { $RepoRoot = $Context.RepoRoot }
    $RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
    if (-not $GitPath -and $Context.BootSource) { $GitPath = $Context.BootSource.git_path; $GitSha256 = $Context.BootSource.git_sha256 }
    $git = $(if ($GitPath) { [IO.Path]::GetFullPath($GitPath) } else { (Get-Command $(if ($IsWindows) { 'git.exe' } else { 'git' }) -ErrorAction Stop).Source })
    if ($GitSha256) { Assert-OpenScienceCondition ((Get-OpenScienceHash $git) -ceq $GitSha256) 'Pinned source reader Git executable changed; invocation is refused.' }
    $source = (Get-OpenScienceRepositoryPinSource) + "`ntry { process.stdout.write(JSON.stringify(captureRepositorySourcePin(process.argv[1],process.argv[2]))); } catch { process.exitCode=1; }"
    $node = $(if ($Context) { $Context.NodePath } else { $null })
    $content = Invoke-OpenScienceSourceNode $source @($RepoRoot, $git) $RepoRoot $node
    $document = [Text.Json.JsonDocument]::Parse($content)
    try { return ConvertFrom-OpenScienceJsonElement $document.RootElement } finally { $document.Dispose() }
}

function Get-OpenScienceSourcePinSha256 {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$SourcePin)
    $document = [Text.Json.JsonDocument]::Parse(($SourcePin | ConvertTo-Json -Depth 40 -Compress))
    function ConvertTo-SourceCanonical([Text.Json.JsonElement]$Element) {
        if ($Element.ValueKind -eq 'Object') {
            $value = [ordered]@{}
            foreach ($property in @($Element.EnumerateObject() | Sort-Object Name -CaseSensitive)) { $value[$property.Name] = ConvertTo-SourceCanonical $property.Value }
            return $value
        }
        if ($Element.ValueKind -eq 'Array') { return ,@($Element.EnumerateArray() | ForEach-Object { ConvertTo-SourceCanonical $_ }) }
        return ConvertFrom-OpenScienceJsonElement $Element
    }
    try { $canonical = ConvertTo-SourceCanonical $document.RootElement | ConvertTo-Json -Depth 40 -Compress } finally { $document.Dispose() }
    [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($canonical))).ToLowerInvariant()
}

function Assert-OpenScienceRepositorySourcePin {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Expected, [Parameter(Mandatory)]$Current)
    Assert-OpenScienceCondition ($Expected.schema -eq 1 -and $Expected.kind -ceq 'autonomous-cae-lab.repository-source-pin' -and
        (Get-OpenScienceSourcePinSha256 $Expected) -ceq (Get-OpenScienceSourcePinSha256 $Current)) 'Repository source differs from this runtime startup snapshot; start a fresh owned runtime.'
}

function Assert-OpenScienceRuntimeBootSource($Owner, [switch]$LifecycleOnly) {
    # Core/MCP/plugin/HEAD drift must not prevent exact session abort/Stop.
    # Controller script/process ownership remains strict in the caller.
    if ($LifecycleOnly) { return }
    Assert-OpenScienceCondition ($Owner.boot_source -and $Owner.boot_source_sha256 -ceq (Get-OpenScienceSourcePinSha256 $Owner.boot_source)) 'Owned runtime has no verified startup source snapshot; inference is refused.'
    Assert-OpenScienceRepositorySourcePin $Owner.boot_source (Get-OpenScienceRepositorySourcePin -Context $Owner.context -GitPath $Owner.boot_source.git_path -GitSha256 $Owner.boot_source.git_sha256)
}

function Assert-OpenScienceContainedPath([string]$Path, [string]$Root) {
    $absolute = [IO.Path]::GetFullPath($Path)
    $parent = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    Assert-OpenScienceCondition ($absolute.StartsWith($parent + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) 'Runtime path escapes its owned profile.'
    # Refuse junctions/symlinks in existing ancestors before writing or reading.
    $candidate = $absolute
    while ($candidate -and $candidate.Length -ge $parent.Length) {
        if (Test-Path -LiteralPath $candidate) {
            Assert-OpenScienceCondition (-not ((Get-Item -LiteralPath $candidate -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) 'Runtime paths must not traverse links or junctions.'
        }
        if ($candidate -eq $parent) { break }
        $candidate = Split-Path -Parent $candidate
    }
    return $absolute
}

function ConvertTo-OpenScienceWslPath([string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    Assert-OpenScienceCondition ($absolute -match '^([A-Za-z]):[\\/](.+)$') 'The MCP bridge requires an absolute Windows drive path.'
    '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + ($Matches[2] -replace '\\', '/')
}

function Get-OpenScienceRemovedEnvironment([string[]]$Names) {
    # Inspect names only. Do not retrieve or log credential values.
    @($Names | Where-Object { $_ -match '(?i)(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|COOKIE|AUTH)' -or
        $_ -match '^(?i:OPENSCIENCE_|CODEX_|AWS_|AZURE_|GOOGLE_|GEMINI_|ANTHROPIC_|OPENAI_|OPENROUTER_|GH_|GITHUB_|OLLAMA_)' -or
        $_ -in @('NODE_OPTIONS', 'NODE_PATH', 'BUN_OPTIONS', 'BUN_INSPECT', 'WSLENV', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY') } | Sort-Object -Unique)
}

function Assert-OpenSciencePinnedRuntime($Context) {
    $packagePath = Join-Path $Context.RuntimePrefix 'node_modules\@synsci\openscience\package.json'
    Assert-OpenScienceCondition ((Read-OpenScienceJson $packagePath).version -eq $script:OpenSciencePinnedVersion) 'The official launcher package must be 2.0.146.'
    Assert-OpenScienceCondition ($Context.LauncherPath -eq (Join-Path $Context.RuntimePrefix 'node_modules\@synsci\openscience\bin\openscience')) 'Unexpected official launcher path.'
    Assert-OpenScienceCondition ((Test-Path -LiteralPath $Context.NodePath -PathType Leaf) -and (Test-Path -LiteralPath $Context.LauncherPath -PathType Leaf)) 'Existing Node and official launcher are required; this script does not install them.'
    Assert-OpenScienceCondition ((Get-OpenScienceHash $Context.LauncherPath) -eq $Context.LauncherSha256) 'Official launcher bytes changed.'
    foreach ($native in $Context.NativeBinaries) {
        Assert-OpenScienceCondition ((Read-OpenScienceJson $native.PackagePath).version -eq $script:OpenSciencePinnedVersion) 'Native package version changed.'
        Assert-OpenScienceCondition ((Get-OpenScienceHash $native.Path) -eq $native.Sha256) 'Pinned native executable bytes changed.'
    }
}

function Assert-OpenScienceContext($Context, [switch]$LifecycleOnly) {
    $markerPath = Assert-OpenScienceContainedPath (Join-Path $Context.ProfileRoot 'caelab-profile-owner.json') $Context.ProfileRoot
    $marker = Read-OpenScienceJson $markerPath
    Assert-OpenScienceCondition ($marker.kind -eq 'autonomous-cae-lab.openscience-profile' -and $marker.schema -eq 1 -and
        $marker.run_name -eq $Context.RunName -and $marker.repo_root -eq $Context.RepoRoot -and
        $marker.profile_root -eq $Context.ProfileRoot -and $marker.intent_sha256 -eq $Context.IntentSha256) 'Profile ownership does not match this repository, run and configuration.'
    foreach ($key in @('ConfigPath', 'GuardPath', 'OwnerPath')) { Assert-OpenScienceContainedPath $Context.$key $Context.ProfileRoot | Out-Null }
    Assert-OpenSciencePinnedRuntime $Context
    if ($Context.Transport -ceq 'ChatGPT') { Assert-OpenScienceNativeContext $Context -LifecycleOnly:$LifecycleOnly }
}

function New-OpenScienceMcpGitTransport {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$RepoRoot, [string]$HostGitPath, [string]$OriginalWslPath)
    $pointer = Join-Path $RepoRoot '.git'
    if (-not ((Test-Path -LiteralPath $pointer -PathType Leaf) -and
        ((Get-Content -LiteralPath $pointer -TotalCount 1) -match '^gitdir: [A-Za-z]:'))) {
        return [pscustomobject]@{ Mode = 'NATIVE_WSL_GIT'; Environment = @() }
    }
    # The local.ps1 bridge pattern is reused, but its executable source is
    # tracked here so every model POST's repository pin also checks these bytes.
    $bridge = Join-Path $RepoRoot 'scripts/wsl-windows-git/git'
    Assert-OpenScienceCondition (Test-Path -LiteralPath $bridge -PathType Leaf) 'Tracked MCP Git bridge is missing.'
    $expected = '#!/bin/sh' + [char]10 + 'exec "$CAELAB_HOST_GIT" "$@"' + [char]10
    $expectedHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
        [Text.UTF8Encoding]::new($false).GetBytes($expected))).ToLowerInvariant()
    Assert-OpenScienceCondition ((Get-OpenScienceHash $bridge) -ceq $expectedHash) 'MCP Git bridge must retain its exact LF-only source.'
    Assert-OpenScienceCondition ($HostGitPath -and (Test-Path -LiteralPath $HostGitPath -PathType Leaf)) 'Existing host Git is required for this managed worktree.'
    Assert-OpenScienceCondition ($OriginalWslPath -and $OriginalWslPath -notmatch '[\r\n]') 'Existing WSL PATH is missing or multiline.'
    $bridgeDirectory = ConvertTo-OpenScienceWslPath (Split-Path -Parent $bridge)
    $hostGitWslPath = ConvertTo-OpenScienceWslPath $HostGitPath
    return [pscustomobject]@{
        Mode = 'WINDOWS_MANAGED_WORKTREE_GIT'; BridgePath = $bridge; BridgeSha256 = $expectedHash
        HostGitPath = $HostGitPath; HostGitSha256 = Get-OpenScienceHash $HostGitPath
        Environment = @(('PATH=' + $bridgeDirectory + ':' + $OriginalWslPath), "CAELAB_HOST_GIT=$hostGitWslPath")
    }
}

function New-OpenScienceLocalContext {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$RepoRoot,
        [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName,
        [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$ProfileTag = 'runtime',
        [string]$StoreRoot, [string]$RuntimePrefix,
        [string]$ModelId,
        [ValidateSet('Ollama', 'ChatGPT')][string]$Transport = 'Ollama', [string]$AuthProfileRoot,
        [string]$WslDistro = 'Ubuntu',
        [string]$WslPython = '/home/pikachu444/.local/share/autonomous-cae-lab/venv-py312/bin/python',
        [AllowEmptyCollection()][string[]]$AllowedTools = $script:OpenScienceBoundedTools,
        [ValidateRange(256, 4096)][int]$OutputTokens = 4096,
        [ValidateRange(1, 3)][int]$Steps = 3,
        [ValidateRange(30, 600)][int]$ProviderTimeoutSeconds = 260
    )
    Assert-OpenScienceCondition ($PSVersionTable.PSVersion.Major -ge 7) 'PowerShell 7 is required for native ArgumentList handling.'
    if ($Transport -ceq 'ChatGPT') {
        return New-OpenScienceNativeContext -RepoRoot $RepoRoot -RunName $RunName -ProfileTag $ProfileTag -StoreRoot $StoreRoot -RuntimePrefix $RuntimePrefix `
            -ModelId $ModelId -AuthProfileRoot $AuthProfileRoot -WslDistro $WslDistro -WslPython $WslPython -AllowedTools $AllowedTools `
            -OutputTokens $OutputTokens -Steps $Steps -ProviderTimeoutSeconds $ProviderTimeoutSeconds
    }
    $RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
    $wslRoot = ConvertTo-OpenScienceWslPath $RepoRoot
    if (-not $StoreRoot) { $StoreRoot = Join-Path $RepoRoot "runs\$RunName" }
    $StoreRoot = [IO.Path]::GetFullPath($StoreRoot)
    $wslStore = ConvertTo-OpenScienceWslPath $StoreRoot
    if (-not $RuntimePrefix) { $RuntimePrefix = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\runtimes\openscience-2.0.146' }
    $RuntimePrefix = [IO.Path]::GetFullPath($RuntimePrefix)
    Assert-OpenScienceCondition (-not [string]::IsNullOrWhiteSpace($ModelId)) 'Choose a provider/model explicitly. No research model is selected automatically; the legacy Ollama transport does not support ChatGPT OAuth.'
    Assert-OpenScienceCondition ($ModelId -eq 'openscience/qwen3-4b-ctx-16384') 'This legacy Ollama transport only accepts its explicitly selected historical alias. Use the official ChatGPT connection for OAuth; no fallback is permitted.'
    Assert-OpenScienceCondition ($WslDistro -match '^[A-Za-z0-9_.-]+$' -and $WslPython -match '^/[^\r\n]+$') 'Invalid existing WSL runtime reference.'
    $AllowedTools = @($AllowedTools)
    Assert-OpenScienceCondition (@($AllowedTools | Sort-Object -Unique).Count -eq $AllowedTools.Count) 'Duplicate allowed tools are not permitted.'
    foreach ($tool in $AllowedTools) { Assert-OpenScienceCondition ($tool -cin $script:OpenScienceBoundedTools) "Tool is outside the nine-tool CAE boundary: $tool" }
    $artifacts = Join-Path $RepoRoot "artifacts\$RunName"
    $profile = Join-Path $artifacts "profiles\$ProfileTag"
    Assert-OpenScienceContainedPath $profile $RepoRoot | Out-Null
    $markerPath = Assert-OpenScienceContainedPath (Join-Path $profile 'caelab-profile-owner.json') $profile
    $gitPointer = Join-Path $RepoRoot '.git'
    $hostGit = $null; $originalWslPath = $null
    if ((Test-Path -LiteralPath $gitPointer -PathType Leaf) -and
        ((Get-Content -LiteralPath $gitPointer -TotalCount 1) -match '^gitdir: [A-Za-z]:')) {
        $hostGit = (Get-Command git.exe -ErrorAction Stop).Source
        $originalWslPath = & wsl.exe -d $WslDistro -- /usr/bin/printenv PATH
        Assert-OpenScienceCondition ($LASTEXITCODE -eq 0 -and @($originalWslPath).Count -eq 1) 'Could not read the existing WSL command path.'
    }
    $mcpGit = New-OpenScienceMcpGitTransport -RepoRoot $RepoRoot -HostGitPath $hostGit -OriginalWslPath $originalWslPath
    $intent = [ordered]@{ profile_schema = 3; repo_root = $RepoRoot; run_name = $RunName; profile_tag = $ProfileTag; store_root = $StoreRoot
        runtime_prefix = $RuntimePrefix; model = $ModelId; wsl_distro = $WslDistro; wsl_python = $WslPython
        allowed_tools = $AllowedTools; output_tokens = $OutputTokens; steps = $Steps; provider_timeout_seconds = $ProviderTimeoutSeconds
        mcp_git_transport = $mcpGit }
    $intentBytes = [Text.Encoding]::UTF8.GetBytes(($intent | ConvertTo-Json -Depth 10 -Compress))
    $intentHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($intentBytes)).ToLowerInvariant()
    if (Test-Path -LiteralPath $profile) {
        Assert-OpenScienceCondition (Test-Path -LiteralPath $markerPath -PathType Leaf) 'Existing unmarked profile will not be changed.'
        $prior = Read-OpenScienceJson $markerPath
        Assert-OpenScienceCondition ($prior.kind -eq 'autonomous-cae-lab.openscience-profile' -and $prior.schema -eq 1 -and
            $prior.run_name -eq $RunName -and $prior.repo_root -eq $RepoRoot -and $prior.profile_root -eq $profile -and
            $prior.intent_sha256 -eq $intentHash) 'Existing profile belongs to another run or configuration; choose a new profile tag.'
        $saved = [pscustomobject](Read-OpenScienceJson (Join-Path $profile 'context.json'))
        Assert-OpenScienceContext $saved
        # Never rewrite a matching profile, especially while its server is active.
        return $saved
    }
    $launcher = Join-Path $RuntimePrefix 'node_modules\@synsci\openscience\bin\openscience'
    Assert-OpenScienceCondition ((Read-OpenScienceJson (Join-Path $RuntimePrefix 'node_modules\@synsci\openscience\package.json')).version -eq $script:OpenSciencePinnedVersion) 'Existing runtime is not pinned OpenScience 2.0.146.'
    $nativeBinaries = @(Get-ChildItem -LiteralPath (Join-Path $RuntimePrefix 'node_modules\@synsci') -Directory -ErrorAction Stop |
        Where-Object Name -match '^openscience-windows-(x64|arm64)(-baseline)?$' | ForEach-Object {
            $binary = Join-Path $_.FullName 'bin\openscience.exe'
            $package = Join-Path $_.FullName 'package.json'
            Assert-OpenScienceCondition ((Read-OpenScienceJson $package).version -eq $script:OpenSciencePinnedVersion) 'Installed native package is not 2.0.146.'
            [ordered]@{ Path = $binary; PackagePath = $package; Sha256 = Get-OpenScienceHash $binary }
        })
    Assert-OpenScienceCondition ($nativeBinaries.Count -gt 0) 'Pinned Windows native runtime is missing.'
    $environment = [ordered]@{
        OPENSCIENCE_TEST_HOME = (Join-Path $profile 'home'); OPENSCIENCE_CONFIG_DIR = (Join-Path $profile 'config')
        OPENSCIENCE_DATA_DIR = (Join-Path $profile 'data'); HOME = (Join-Path $profile 'home'); USERPROFILE = (Join-Path $profile 'home')
        HOMEDRIVE = ([IO.Path]::GetPathRoot($profile).TrimEnd('\')); HOMEPATH = ((Join-Path $profile 'home').Substring(2))
        APPDATA = (Join-Path $profile 'appdata'); LOCALAPPDATA = (Join-Path $profile 'localappdata')
        XDG_CONFIG_HOME = (Join-Path $profile 'xdg-config'); XDG_DATA_HOME = (Join-Path $profile 'xdg-data')
        XDG_CACHE_HOME = (Join-Path $profile 'xdg-cache'); XDG_STATE_HOME = (Join-Path $profile 'xdg-state')
        TEMP = (Join-Path $profile 'temp'); TMP = (Join-Path $profile 'temp')
        OPENSCIENCE_DISABLE_AUTOUPDATE = '1'; OPENSCIENCE_DISABLE_AUTOCOMPACT = '1'; OPENSCIENCE_DISABLE_PRUNE = '1'
        OPENSCIENCE_DISABLE_MODELS_FETCH = '1'; OPENSCIENCE_DISABLE_LSP_DOWNLOAD = '1'; OPENSCIENCE_DISABLE_PROJECT_CONFIG = '1'
        OPENSCIENCE_EXPERIMENTAL_OUTPUT_TOKEN_MAX = [string]$OutputTokens
    }
    $context = [pscustomobject]@{
        RepoRoot = $RepoRoot; RunName = $RunName; ProfileTag = $ProfileTag; ArtifactRoot = $artifacts; StoreRoot = $StoreRoot
        ProfileRoot = $profile; ConfigPath = (Join-Path $environment.OPENSCIENCE_CONFIG_DIR 'openscience.json')
        NodePath = (Get-Command node.exe -ErrorAction Stop).Source; LauncherPath = $launcher; RuntimePrefix = $RuntimePrefix
        LauncherSha256 = (Get-OpenScienceHash $launcher); NativeBinaries = $nativeBinaries; Environment = $environment
        RemoveEnvironment = @('OPENSCIENCE_CONFIG', 'OPENSCIENCE_CONFIG_CONTENT', 'OPENSCIENCE_AUTH_TOKEN', 'OPENSCIENCE_BIN_PATH', 'OPENSCIENCE_PERMISSION', 'NODE_OPTIONS', 'NODE_PATH', 'WSLENV')
        Model = "ollama/$ModelId"; ModelId = $ModelId; AllowedTools = $AllowedTools; OutputTokens = $OutputTokens; Steps = $Steps
        ProviderTimeoutSeconds = $ProviderTimeoutSeconds; SourceCommit = $script:OpenSciencePinnedSource
        WslPythonCacheRoot = (Join-Path $profile 'wsl-pycache')
        McpGitTransport = $mcpGit
        IntentSha256 = $intentHash; OwnerPath = (Join-Path $profile 'runtime-owner.json'); GuardPath = (Join-Path $profile 'expected-tools.json')
        SandboxLimitation = 'Windows has no native OpenScience sandbox backend. warn fallback is explicit; application permissions are not OS containment.'
    }
    $permission = [ordered]@{ '*' = 'deny' }; $mcpPermission = [ordered]@{ '*' = 'deny' }
    foreach ($tool in $AllowedTools) { $permission[$tool] = 'allow'; $mcpPermission[$tool] = 'allow' }
    $permission['mcp'] = $mcpPermission
    $agent = [ordered]@{ mode = 'primary'; model = $context.Model; temperature = 0.6; top_p = 0.95; steps = $Steps
        skills = @(); options = @{ reasoningEffort = 'low' }; permission = $permission
        prompt = 'Use the requested CAE Lab function once with the exact supplied JSON arguments. Then briefly report its receipt. For interpretation, use only supplied actual receipts. Preserve UNKNOWN and NOT_RELEASED.' }
    $config = [ordered]@{
        enabled_providers = @('ollama'); model = $context.Model; small_model = $context.Model; default_agent = 'research'
        snapshot = $false; billing = @{ llm = 'byok' }; compaction = @{ auto = $false; prune = $false }; permission = $permission
        sandbox = @{ enabled = $true; onUnavailable = 'warn' }
        harness = @{ 'headless-policy' = $false; redirect = $false; deliverables = $false; acceptance = $false; unattended = $false
            review = $false; budget = $false; cost = $false; 'durable-jobs' = $false; workers = $false }
        agent = @{ title = @{ disable = $true }; research = $agent; 'caelab-acceptance' = $agent }
        provider = @{ ollama = @{ name = 'Task-local guarded Ollama'; npm = '@ai-sdk/openai-compatible'
            # Fail closed until this profile's own proxy has published readiness.
            api = 'http://127.0.0.1:1/v1'; options = @{ baseURL = 'http://127.0.0.1:1/v1'; apiKey = 'local'; localRuntime = 'ollama'
                timeout = ($ProviderTimeoutSeconds * 1000); connectTimeout = ($ProviderTimeoutSeconds * 1000); idleTimeout = 60000 }
            models = @{ $ModelId = @{ name = $ModelId; tool_call = $true; reasoning = $true; temperature = $true
                cost = @{ input = 0; output = 0 }; limit = @{ context = 16384; output = $OutputTokens }; options = @{ reasoningEffort = 'low' } } } } }
        mcp = @{ caelab = @{ type = 'local'; enabled = $true; timeout = 120000; command = @(
            "$env:WINDIR\System32\wsl.exe", '-d', $WslDistro, '--cd', $wslRoot, '--', '/usr/bin/env',
            "CAELAB_STORE=$wslStore", ('PYTHONPYCACHEPREFIX=' + (ConvertTo-OpenScienceWslPath $context.WslPythonCacheRoot))) +
            @($mcpGit.Environment) + @($WslPython, "$wslRoot/openscience/mcp_server.py") } }
    }
    New-Item -ItemType Directory -Path $profile -ErrorAction Stop | Out-Null
    Write-OpenScienceJson $markerPath ([ordered]@{ kind = 'autonomous-cae-lab.openscience-profile'; schema = 1; run_name = $RunName
        repo_root = $RepoRoot; profile_root = $profile; intent_sha256 = $intentHash; created_utc = [DateTime]::UtcNow.ToString('o')
        source_commit = $script:OpenSciencePinnedSource; sandbox_limitation = $context.SandboxLimitation }) -CreateNew
    foreach ($directory in @($environment.Values | Where-Object { $_ -is [string] -and $_.StartsWith($profile + '\') } | Sort-Object -Unique)) {
        New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
    }
    New-Item -ItemType Directory -Path $context.WslPythonCacheRoot -ErrorAction Stop | Out-Null
    Write-OpenScienceJson $context.ConfigPath $config -CreateNew
    Write-OpenScienceJson (Join-Path $profile 'context.json') $context -CreateNew
    Initialize-OpenScienceToolGuard -Context $context
    return $context
}

function New-OpenScienceLocalProcessInfo {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Context, [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$Arguments)
    Assert-OpenScienceContext $Context
    $separator = [Array]::IndexOf($Arguments, '--')
    $commandArguments = $(if ($separator -lt 0) { @($Arguments) } else { @($Arguments | Select-Object -First $separator) })
    if ($commandArguments -contains 'run') {
        Assert-OpenScienceCondition ($Arguments[0] -ceq 'run') 'Model actions require run as the explicit first command; prefix options cannot bypass readiness.'
        Assert-OpenScienceCondition ($Context.RuntimeURL) 'Model actions require a verified persistent runtime.'
        $verified = Get-OpenScienceLocalRuntime -OwnerPath $Context.OwnerPath
        $attachAt = [Array]::IndexOf($Arguments, '--attach')
        Assert-OpenScienceCondition ($attachAt -ge 0 -and $attachAt + 1 -lt $Arguments.Count -and
            $Arguments[$attachAt + 1] -eq $verified.RuntimeURL -and $Context.RuntimeURL -eq $verified.RuntimeURL) 'Model action must attach to this current owned runtime.'
    }
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Context.NodePath; $info.WorkingDirectory = $Context.RepoRoot
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $info.ArgumentList.Add($Context.LauncherPath)
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    foreach ($name in @(Get-OpenScienceRemovedEnvironment @($info.Environment.Keys)) + @($Context.RemoveEnvironment)) { $info.Environment.Remove($name) | Out-Null }
    foreach ($name in $Context.Environment.Keys) { $info.Environment[$name] = [string]$Context.Environment[$name] }
    if ($Context.Transport -ceq 'ChatGPT') { $info.Environment['OPENSCIENCE_BIN_PATH'] = $Context.NativePath }
    return $info
}

function Open-OpenScienceLiveLog {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    # Buffer size one prevents a short readiness line from remaining unreadable
    # until a long-lived server exits. Readers never acquire write access.
    [IO.FileStream]::new($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read, 1, [IO.FileOptions]::Asynchronous)
}

function Get-OpenScienceProcessIdentity {
    [CmdletBinding()]
    param([Parameter(Mandatory)][ValidateRange(1, 2147483647)][int]$ProcessId)
    $item = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
    if ($null -eq $item) { return $null }
    Assert-OpenScienceCondition ($item.CreationDate -and $item.CommandLine -and $item.ExecutablePath) 'Process identity is incomplete; ownership cannot be established.'
    [pscustomobject]@{ Pid = [int]$item.ProcessId; ParentPid = [int]$item.ParentProcessId
        CreationUtc = $item.CreationDate.ToUniversalTime().ToString('o'); ExecutablePath = [string]$item.ExecutablePath; CommandLine = [string]$item.CommandLine }
}

function Assert-OpenScienceProcessIdentity($Expected, $Actual) {
    Assert-OpenScienceCondition ($null -ne $Expected -and $null -ne $Actual -and $Expected.Pid -eq $Actual.Pid -and
        $Expected.CreationUtc -ceq $Actual.CreationUtc -and $Expected.CommandLine -ceq $Actual.CommandLine -and
        $Expected.ExecutablePath -eq $Actual.ExecutablePath) 'Process PID/creation/command changed or is not owned.'
}

function Test-OpenScienceCommandPrefix([string]$Command, [string[]]$Paths) {
    $prefix = '^\s*' + (($Paths | ForEach-Object { '(?:"' + [regex]::Escape($_) + '"|' + [regex]::Escape($_) + ')' }) -join '\s+') + '(?:\s|$)'
    [regex]::IsMatch($Command, $prefix, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
}

function Assert-OpenScienceNativeIdentity($Context, $Identity) {
    $native = @($Context.NativeBinaries | Where-Object { $_.Path -eq $Identity.ExecutablePath })
    Assert-OpenScienceCondition ($native.Count -eq 1 -and (Test-OpenScienceCommandPrefix $Identity.CommandLine @($native[0].Path))) 'Process is not a verified pinned native child.'
    Assert-OpenScienceCondition ((Get-OpenScienceHash $native[0].Path) -eq $native[0].Sha256) 'Native child executable changed.'
}

function Get-OpenScienceDescendants([int]$RootPid) {
    # Only tree IDs are read for unrelated processes. Fetch command lines later
    # for actual descendants, never persist an unrelated process inventory.
    $snapshot = @(Get-CimInstance Win32_Process -Property ProcessId, ParentProcessId -ErrorAction Stop)
    $ids = [Collections.Generic.HashSet[int]]::new(); $ids.Add($RootPid) | Out-Null
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($item in $snapshot) {
            if ($ids.Contains([int]$item.ParentProcessId) -and $ids.Add([int]$item.ProcessId)) { $changed = $true }
        }
    }
    @($snapshot | Where-Object { $_.ProcessId -ne $RootPid -and $ids.Contains([int]$_.ProcessId) } | ForEach-Object { Get-OpenScienceProcessIdentity -ProcessId $_.ProcessId })
}

function Assert-OpenScienceLocalUrl([string]$Url, [string]$Path = '/') {
    $uri = $null
    Assert-OpenScienceCondition ([Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -and $uri.Scheme -eq 'http' -and
        $uri.Host -eq '127.0.0.1' -and $uri.Port -gt 0 -and -not $uri.UserInfo -and -not $uri.Query -and -not $uri.Fragment -and
        $uri.AbsolutePath -eq $Path) 'Only the declared numeric loopback URL is accepted.'
    return $uri
}

function Assert-OpenScienceReadiness($Context, [string]$Url, [int]$ReadyPid, $NativeIdentity, $Connections, $Health, [string]$ExpectedRunId) {
    $uri = Assert-OpenScienceLocalUrl $Url
    Assert-OpenScienceNativeIdentity $Context $NativeIdentity
    Assert-OpenScienceCondition ($ReadyPid -eq $NativeIdentity.Pid) 'Readiness PID is foreign.'
    Assert-OpenScienceCondition (@($Connections | Where-Object { $_.OwningProcess -eq $NativeIdentity.Pid -and $_.LocalAddress -notin @('127.0.0.1', '::1') }).Count -eq 0) 'Owned runtime has a public listening socket.'
    Assert-OpenScienceCondition (@($Connections | Where-Object { $_.OwningProcess -eq $NativeIdentity.Pid -and $_.LocalAddress -eq '127.0.0.1' -and $_.LocalPort -eq $uri.Port }).Count -eq 1) 'Loopback readiness socket is not owned by the recorded native process.'
    if ($null -ne $Health) {
        Assert-OpenScienceCondition ($Health.healthy -eq $true -and $Health.version -eq $script:OpenSciencePinnedVersion -and $Health.runId) 'Pinned runtime health/version is unavailable.'
        if ($ExpectedRunId) { Assert-OpenScienceCondition ($Health.runId -ceq $ExpectedRunId) 'Health belongs to a different server run.' }
    }
}

function Invoke-OpenScienceHttp([string]$Uri, [string]$Method = 'GET', [hashtable]$Headers = @{}, [int]$TimeoutSeconds = 15) {
    Invoke-WebRequest -Uri $Uri -Method $Method -Headers $Headers -TimeoutSec $TimeoutSeconds -MaximumRedirection 0 -SkipHttpErrorCheck -ErrorAction Stop
}

function Read-OpenScienceRuntimeOwner([string]$Path, [switch]$LifecycleOnly) {
    $owner = Read-OpenScienceJson ([IO.Path]::GetFullPath($Path))
    Assert-OpenScienceCondition ($owner.kind -eq 'autonomous-cae-lab.openscience-runtime' -and $owner.schema -eq 1) 'Unrecognized runtime ownership marker.'
    $context = [pscustomobject]$owner.context
    Assert-OpenScienceContext $context -LifecycleOnly:$LifecycleOnly
    Assert-OpenScienceCondition ([IO.Path]::GetFullPath($Path) -eq $context.OwnerPath -and
        $owner.run_name -eq $context.RunName -and $owner.repo_root -eq $context.RepoRoot -and $owner.profile_root -eq $context.ProfileRoot) 'Runtime owner path or repository identity does not match.'
    Assert-OpenScienceContainedPath $owner.runtime_directory $context.ProfileRoot | Out-Null
    return $owner
}

function Get-OpenScienceLocalRuntime {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$OwnerPath, [switch]$LifecycleOnly)
    $owner = Read-OpenScienceRuntimeOwner $OwnerPath -LifecycleOnly:$LifecycleOnly
    Assert-OpenScienceCondition ($owner.state -eq 'ready' -or ($LifecycleOnly -and $owner.state -in @('stopping', 'guard_failed'))) "Owned runtime is not ready (state=$($owner.state))."
    Assert-OpenScienceRuntimeBootSource $owner -LifecycleOnly:$LifecycleOnly
    $context = [pscustomobject]$owner.context
    Assert-OpenScienceProcessIdentity $owner.controller (Get-OpenScienceProcessIdentity -ProcessId $owner.controller.Pid)
    Assert-OpenScienceCondition ($owner.controller.CommandLine.Contains($owner.launch_token) -and $owner.controller.CommandLine.Contains($owner.context_path) -and
        $owner.script_path -eq $script:OpenScienceServerScriptPath -and $owner.script_sha256 -eq (Get-OpenScienceHash $script:OpenScienceServerScriptPath)) 'Controller command/source is not this owned runtime.'
    Assert-OpenScienceProcessIdentity $owner.launcher (Get-OpenScienceProcessIdentity -ProcessId $owner.launcher.Pid)
    Assert-OpenScienceCondition ($owner.launcher.ExecutablePath -eq $context.NodePath -and (Test-OpenScienceCommandPrefix $owner.launcher.CommandLine @($context.NodePath, $context.LauncherPath))) 'Official launcher identity does not match.'
    $native = Get-OpenScienceProcessIdentity -ProcessId $owner.native.Pid
    Assert-OpenScienceProcessIdentity $owner.native $native
    Assert-OpenScienceCondition (@(Get-OpenScienceDescendants $owner.launcher.Pid | Where-Object Pid -eq $native.Pid).Count -eq 1) 'Runtime native PID is not the official launcher descendant.'
    $connections = @(Get-NetTCPConnection -State Listen -OwningProcess $native.Pid -ErrorAction Stop)
    Assert-OpenScienceReadiness $context $owner.runtime_url $owner.native.Pid $native $connections $null $null
    if (-not $LifecycleOnly -or $context.Transport -cne 'ChatGPT') {
    Assert-OpenScienceCondition ((Get-OpenScienceHash $context.ConfigPath) -eq $owner.config_sha256) 'Active profile configuration changed.'
    $config = Read-OpenScienceJson $context.ConfigPath
    if ($context.Transport -ceq 'ChatGPT') {
        Assert-OpenScienceCondition ($config.model -ceq $context.Model -and @($config.enabled_providers).Count -eq 1 -and
            $config.enabled_providers[0] -ceq 'openai-codex' -and -not $owner.proxy) 'Native provider/model differs from this owned runtime.'
        if (-not $LifecycleOnly) {
            Assert-OpenScienceNativeGuardLoaded $context $owner
            Assert-OpenScienceCondition (-not (Read-OpenScienceJson $context.GuardPath).stopping) 'This profile is stopping; new research is blocked.'
        }
    } else {
    Assert-OpenScienceCondition ($config.provider.ollama.options.baseURL -eq $owner.proxy_url -and $config.provider.ollama.api -eq $owner.proxy_url -and
        $config.model -eq $context.Model) 'Active provider/model differs from the owned proxy configuration.'
    if (-not $LifecycleOnly) {
        Assert-OpenScienceProcessIdentity $owner.proxy (Get-OpenScienceProcessIdentity -ProcessId $owner.proxy.Pid)
        Assert-OpenScienceCondition ($owner.proxy.ExecutablePath -eq $context.NodePath -and (Test-OpenScienceCommandPrefix $owner.proxy.CommandLine @($context.NodePath, $owner.proxy_script)) -and
            (Get-OpenScienceHash $owner.proxy_script) -eq $owner.proxy_script_sha256) 'Proxy source/process is not owned.'
        $proxyUri = Assert-OpenScienceLocalUrl $owner.proxy_url '/v1'
        $proxySockets = @(Get-NetTCPConnection -State Listen -OwningProcess $owner.proxy.Pid -ErrorAction Stop)
        Assert-OpenScienceCondition (@($proxySockets | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') }).Count -eq 0 -and
            @($proxySockets | Where-Object { $_.LocalAddress -eq '127.0.0.1' -and $_.LocalPort -eq $proxyUri.Port }).Count -eq 1) 'Guard proxy loopback socket is not owned.'
        $proxyHealthResponse = Invoke-OpenScienceHttp ($owner.proxy_url.Substring(0, $owner.proxy_url.Length - 3) + '/_caelab/health')
        Assert-OpenScienceCondition ($proxyHealthResponse.StatusCode -eq 200) 'Current owned tool guard is not healthy.'
        $proxyHealth = $proxyHealthResponse.Content | ConvertFrom-Json -AsHashtable
        Assert-OpenScienceCondition ($proxyHealth.kind -eq 'autonomous-cae-lab.openscience-proxy' -and $proxyHealth.pid -eq $owner.proxy.Pid -and
            $proxyHealth.run_name -eq $context.RunName -and $proxyHealth.profile_root -eq $context.ProfileRoot -and
            $proxyHealth.guard_sha256 -eq (Get-OpenScienceHash $context.GuardPath)) 'Guard health belongs to a different profile or guard revision.'
        Assert-OpenScienceCondition ($proxyHealth.boot_source_sha256 -ceq $owner.boot_source_sha256) 'Proxy startup source belongs to another runtime.'
        Assert-OpenScienceCondition (-not (Read-OpenScienceJson $context.GuardPath).stopping) 'This profile is stopping; new model actions are blocked.'
    }
    }
    }
    $healthResponse = Invoke-OpenScienceHttp "$($owner.runtime_url)/global/health"
    Assert-OpenScienceCondition ($healthResponse.StatusCode -eq 200) 'Current owned health request failed.'
    $health = $healthResponse.Content | ConvertFrom-Json -AsHashtable
    Assert-OpenScienceReadiness $context $owner.runtime_url $owner.native.Pid $native $connections $health $owner.health_run_id
    if (-not $LifecycleOnly) {
        $mcpResponse = Invoke-OpenScienceHttp "$($owner.runtime_url)/mcp" -Headers @{ 'x-openscience-directory' = $context.RepoRoot } -TimeoutSeconds 60
        Assert-OpenScienceCondition ($mcpResponse.StatusCode -eq 200 -and ($mcpResponse.Content | ConvertFrom-Json).caelab.status -eq 'connected') 'Current GET /mcp is not connected; model action blocked.'
    }
    Assert-OpenScienceProcessIdentity $owner.native (Get-OpenScienceProcessIdentity -ProcessId $owner.native.Pid)
    if (-not $LifecycleOnly -and $context.Transport -cne 'ChatGPT') { Assert-OpenScienceProcessIdentity $owner.proxy (Get-OpenScienceProcessIdentity -ProcessId $owner.proxy.Pid) }
    Assert-OpenScienceRuntimeBootSource $owner -LifecycleOnly:$LifecycleOnly
    $context | Add-Member -NotePropertyName RuntimeURL -NotePropertyValue $owner.runtime_url -Force
    $context | Add-Member -NotePropertyName WorkspaceURL -NotePropertyValue $owner.workspace_url -Force
    $context | Add-Member -NotePropertyName ConnectorStatus -NotePropertyValue $(if ($LifecycleOnly) { 'not_checked_for_lifecycle' } else { 'connected' }) -Force
    $context | Add-Member -NotePropertyName RuntimeDirectory -NotePropertyValue $owner.runtime_directory -Force
    $context | Add-Member -NotePropertyName BootSource -NotePropertyValue $owner.boot_source -Force
    $context | Add-Member -NotePropertyName BootSourceSha256 -NotePropertyValue $owner.boot_source_sha256 -Force
    return $context
}

function Open-OpenScienceToolGuardLock($Context) {
    $path = Assert-OpenScienceContainedPath (Join-Path $Context.ProfileRoot 'guard-mutation.lock') $Context.ProfileRoot
    try { return [IO.FileStream]::new($path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None, 1) }
    catch { throw 'Another operation owns this profile guard mutation lock; the guard was not changed.' }
}

function Assert-OpenScienceToolGuard($Context, $Guard) {
    Assert-OpenScienceCondition ($Guard.schema -eq 1 -and $Guard.kind -ceq 'autonomous-cae-lab.openscience-tool-guard' -and
        $Guard.run_name -ceq $Context.RunName -and $Guard.repo_root -ceq $Context.RepoRoot -and
        $Guard.profile_root -ceq $Context.ProfileRoot -and $Guard.model -ceq $Context.ModelId) 'Tool guard ownership or model changed; mutation refused.'
    $allowed = @($Context.AllowedTools)
    Assert-OpenScienceCondition ($Guard.allowed -is [array] -and $Guard.allowed.Count -eq $allowed.Count) 'Tool guard allowed schema changed; mutation refused.'
    for ($index = 0; $index -lt $allowed.Count; $index++) {
        Assert-OpenScienceCondition ($Guard.allowed[$index] -ceq $allowed[$index] -and $allowed[$index] -cin $script:OpenScienceBoundedTools) 'Tool guard allowed schema changed; mutation refused.'
    }
    Assert-OpenScienceCondition ($Guard.no_tools -is [bool] -and $Guard.stopping -is [bool] -and
        ($null -eq $Guard.required -or ($Guard.required -is [string] -and $Guard.required -cin $allowed)) -and
        -not ($Guard.no_tools -and $Guard.required)) 'Tool guard state is invalid; mutation refused.'
}

function New-OpenScienceToolGuard($Context, [string]$RequiredTool, [switch]$NoTools) {
    [ordered]@{ schema = 1; kind = 'autonomous-cae-lab.openscience-tool-guard'; repo_root = $Context.RepoRoot
        run_name = $Context.RunName; profile_root = $Context.ProfileRoot; model = $Context.ModelId
        allowed = @($Context.AllowedTools); required = $(if ($RequiredTool) { $RequiredTool } else { $null }); no_tools = [bool]$NoTools; stopping = $false
        updated_utc = [DateTime]::UtcNow.ToString('o') }
}

function Initialize-OpenScienceToolGuard($Context) {
    Assert-OpenScienceContext $Context
    $lock = Open-OpenScienceToolGuardLock $Context
    try {
        Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $Context.GuardPath) -and
            -not (Test-Path -LiteralPath $Context.OwnerPath)) 'Only a newly created owned profile may initialize its guard.'
        Write-OpenScienceJson $Context.GuardPath (New-OpenScienceToolGuard $Context) -CreateNew
    } finally { $lock.Dispose() }
}

function Reset-OpenScienceToolGuardForFreshStartup($Context) {
    Assert-OpenScienceContext $Context
    $lock = Open-OpenScienceToolGuardLock $Context
    try {
        Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $Context.OwnerPath)) 'A historical runtime owner requires a fresh RunName; its guard will not be reset.'
        $history = Assert-OpenScienceContainedPath (Join-Path $Context.ProfileRoot 'server-runs') $Context.ProfileRoot
        Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $history) -or
            @(Get-ChildItem -LiteralPath $history -Force -ErrorAction Stop).Count -eq 0) 'Prior startup evidence requires a fresh RunName; its guard will not be reset.'
        $guard = Read-OpenScienceJson $Context.GuardPath
        Assert-OpenScienceToolGuard $Context $guard
        Assert-OpenScienceCondition (-not $guard.stopping) 'A stopped profile requires a fresh RunName; model forwards remain blocked.'
        Write-OpenScienceJson $Context.GuardPath (New-OpenScienceToolGuard $Context)
    } finally { $lock.Dispose() }
}

function Set-OpenScienceExpectedTools {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Context, [string]$RequiredTool, [switch]$NoTools)
    Assert-OpenScienceContext $Context
    Assert-OpenScienceCondition (-not ($NoTools -and $RequiredTool)) 'A no-tools stage cannot require a tool.'
    if ($RequiredTool) { Assert-OpenScienceCondition ($RequiredTool -cin @($Context.AllowedTools)) 'Required tool is not enabled in this owned profile.' }
    $lock = Open-OpenScienceToolGuardLock $Context
    try {
        $guard = Read-OpenScienceJson $Context.GuardPath
        Assert-OpenScienceToolGuard $Context $guard
        Assert-OpenScienceCondition (-not $guard.stopping) 'This profile is stopping; tool changes and guard restoration are refused.'
        $guard.required = $(if ($RequiredTool) { $RequiredTool } else { $null }); $guard.no_tools = [bool]$NoTools
        $guard.updated_utc = [DateTime]::UtcNow.ToString('o')
        Write-OpenScienceJson $Context.GuardPath $guard
    } finally { $lock.Dispose() }
}

function Invoke-OpenScienceSessionAbort {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Context, [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$SessionId)
    # MCP/provider availability must never prevent cancelling an owned session.
    $current = Get-OpenScienceLocalRuntime -OwnerPath $Context.OwnerPath -LifecycleOnly
    Assert-OpenScienceCondition ($Context.RuntimeURL -eq $current.RuntimeURL) 'Abort context is not the current owned runtime.'
    $directory = Join-Path $Context.ProfileRoot ('lifecycle\abort-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '-' + [Guid]::NewGuid().ToString('N'))
    Assert-OpenScienceContainedPath $directory $Context.ProfileRoot | Out-Null
    New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
    $uri = "$($current.RuntimeURL)/session/$SessionId/abort"
    $request = [ordered]@{ method = 'POST'; uri = $uri; session_id = $SessionId; abort_source = 'runner_timeout'; requested_utc = [DateTime]::UtcNow.ToString('o') }
    Write-OpenScienceJson (Join-Path $directory 'request.json') $request -CreateNew
    try {
        $response = Invoke-OpenScienceHttp $uri -Method POST -Headers @{ 'x-openscience-directory' = $current.RepoRoot; 'x-openscience-abort-source' = 'runner_timeout' } -TimeoutSeconds 20
        [IO.File]::WriteAllText((Join-Path $directory 'response.txt'), [string]$response.Content, [Text.UTF8Encoding]::new($false))
        $receipt = [ordered]@{ session_id = $SessionId; method = 'POST'; uri = $uri; status_code = [int]$response.StatusCode
            Confirmed = ($response.StatusCode -eq 200 -and ([string]$response.Content).Trim() -eq 'true'); StatusCode = [int]$response.StatusCode; SessionId = $SessionId
            completed_utc = [DateTime]::UtcNow.ToString('o'); response_sha256 = Get-OpenScienceHash (Join-Path $directory 'response.txt'); directory = $directory }
        Write-OpenScienceJson (Join-Path $directory 'receipt.json') $receipt -CreateNew
        Assert-OpenScienceCondition ($response.StatusCode -eq 200 -and ([string]$response.Content).Trim() -eq 'true') 'Official session abort did not confirm cancellation; logs and response are retained.'
        return [pscustomobject]$receipt
    } catch {
        Write-OpenScienceJson (Join-Path $directory 'failure.json') @{ error = $_.Exception.Message; session_id = $SessionId; failed_utc = [DateTime]::UtcNow.ToString('o') } -CreateNew
        throw
    }
}

function Get-OpenScienceOwnedSessionStatus($Context, [string]$ReceiptPath) {
    $response = Invoke-OpenScienceHttp "$($Context.RuntimeURL)/session/status" -Headers @{ 'x-openscience-directory' = $Context.RepoRoot } -TimeoutSeconds 15
    $stream = Open-OpenScienceLiveLog $ReceiptPath
    try { $stream.Write([Text.Encoding]::UTF8.GetBytes([string]$response.Content)); $stream.Flush($true) } finally { $stream.Dispose() }
    Assert-OpenScienceCondition ($response.StatusCode -eq 200) 'Current owned session status is unavailable; termination refused.'
    $status = $response.Content | ConvertFrom-Json -AsHashtable -ErrorAction Stop
    Assert-OpenScienceCondition ($status -is [Collections.IDictionary]) 'Session status response is not a map; termination refused.'
    foreach ($sessionId in $status.Keys) {
        Assert-OpenScienceCondition ($sessionId -match '^ses_[A-Za-z0-9]+$' -and $status[$sessionId].type -is [string]) 'Session status has an invalid exact ID/state; termination refused.'
    }
    return ,$status
}

function Get-OpenScienceNonIdleSessionIds($Status) {
    @($Status.Keys | Where-Object { $Status[$_].type -ne 'idle' } | Sort-Object)
}

function Pause-OpenScienceModelForwards($Context, [string]$Directory) {
    Assert-OpenScienceContext $Context -LifecycleOnly
    $snapshot = Assert-OpenScienceContainedPath (Join-Path $Directory 'guard-before-stop.json') $Context.ProfileRoot
    $lock = Open-OpenScienceToolGuardLock $Context
    try {
        $guard = Read-OpenScienceJson $Context.GuardPath
        Assert-OpenScienceToolGuard $Context $guard
        Write-OpenScienceJson $snapshot $guard -CreateNew
        $guard.stopping = $true; $guard.updated_utc = [DateTime]::UtcNow.ToString('o')
        Write-OpenScienceJson $Context.GuardPath $guard
    } finally { $lock.Dispose() }
}

function Confirm-OpenScienceSessionsIdleForStop($Context) {
    $current = Get-OpenScienceLocalRuntime $Context.OwnerPath -LifecycleOnly
    $directory = Join-Path $Context.ProfileRoot ('lifecycle\stop-preflight-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '-' + [Guid]::NewGuid().ToString('N'))
    Assert-OpenScienceContainedPath $directory $Context.ProfileRoot | Out-Null
    New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
    $receipts = [Collections.Generic.List[object]]::new()
    $paused = $false
    try {
        Pause-OpenScienceModelForwards $current $directory
        $paused = $true
        $before = Get-OpenScienceOwnedSessionStatus $current (Join-Path $directory 'session-status-before.json')
        foreach ($sessionId in @(Get-OpenScienceNonIdleSessionIds $before)) {
            $sessionResponse = Invoke-OpenScienceHttp "$($current.RuntimeURL)/session/$sessionId" -Headers @{ 'x-openscience-directory' = $current.RepoRoot } -TimeoutSeconds 15
            Write-OpenScienceJson (Join-Path $directory "$sessionId-metadata.json") ($sessionResponse.Content | ConvertFrom-Json -AsHashtable -ErrorAction Stop) -CreateNew
            $session = $sessionResponse.Content | ConvertFrom-Json -AsHashtable -ErrorAction Stop
            Assert-OpenScienceCondition ($sessionResponse.StatusCode -eq 200 -and $session.id -ceq $sessionId -and
                [IO.Path]::GetFullPath($session.directory) -eq $current.RepoRoot) 'Active session is not the exact owned project session; termination refused.'
            $receipt = Invoke-OpenScienceSessionAbort $current $sessionId
            Assert-OpenScienceCondition ($receipt.Confirmed -and $receipt.StatusCode -eq 200 -and $receipt.SessionId -ceq $sessionId) 'Cancellation was not confirmed; termination refused.'
            $receipts.Add($receipt)
        }
        $watch = [Diagnostics.Stopwatch]::StartNew(); $sequence = 0
        do {
            $status = Get-OpenScienceOwnedSessionStatus $current (Join-Path $directory ('session-status-after-' + (++$sequence).ToString('000') + '.json'))
            if (@(Get-OpenScienceNonIdleSessionIds $status).Count -eq 0) {
                $record = [ordered]@{ state = 'IDLE_CONFIRMED'; directory = $directory; cancelled_sessions = @($receipts)
                    observed_utc = [DateTime]::UtcNow.ToString('o'); provider_calls = 0 }
                Write-OpenScienceJson (Join-Path $directory 'receipt.json') $record -CreateNew
                return [pscustomobject]$record
            }
            Start-Sleep -Milliseconds 300
        } while ($watch.Elapsed.TotalSeconds -lt 20)
        throw 'Owned sessions did not settle to idle after confirmed abort; termination refused.'
    } catch {
        Write-OpenScienceJson (Join-Path $directory 'failure.json') @{ error = $_.Exception.Message; cancelled_sessions = @($receipts)
            termination_refused = $true; model_forwards_paused = $paused; observed_utc = [DateTime]::UtcNow.ToString('o') } -CreateNew
        throw
    }
}

function Stop-OpenScienceOwnedLauncher {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Context, [Parameter(Mandatory)]$ProcessIdentity)
    Assert-OpenScienceContext $Context -LifecycleOnly
    $actual = Get-OpenScienceProcessIdentity -ProcessId $ProcessIdentity.Pid
    if ($null -eq $actual) { return [pscustomobject]@{ AlreadyExited = $true; StoppedPids = @(); LauncherPid = $ProcessIdentity.Pid } }
    Assert-OpenScienceProcessIdentity $ProcessIdentity $actual
    Assert-OpenScienceCondition ($actual.ExecutablePath -eq $Context.NodePath -and (Test-OpenScienceCommandPrefix $actual.CommandLine @($Context.NodePath, $Context.LauncherPath))) 'Stop refused: process is not this official launcher.'
    $children = @(Get-OpenScienceDescendants $actual.Pid | Where-Object { $_.ExecutablePath -in @($Context.NativeBinaries.Path) })
    foreach ($child in $children) { Assert-OpenScienceNativeIdentity $Context $child; Assert-OpenScienceProcessIdentity $child (Get-OpenScienceProcessIdentity -ProcessId $child.Pid) }
    Assert-OpenScienceProcessIdentity $ProcessIdentity (Get-OpenScienceProcessIdentity -ProcessId $ProcessIdentity.Pid)
    $stopped = [Collections.Generic.List[int]]::new()
    foreach ($child in $children) {
        Assert-OpenScienceProcessIdentity $child (Get-OpenScienceProcessIdentity -ProcessId $child.Pid)
        Stop-Process -Id $child.Pid -ErrorAction Stop; $stopped.Add($child.Pid)
    }
    $latest = Get-OpenScienceProcessIdentity -ProcessId $ProcessIdentity.Pid
    if ($latest) { Assert-OpenScienceProcessIdentity $ProcessIdentity $latest; Stop-Process -Id $ProcessIdentity.Pid -ErrorAction Stop; $stopped.Add($ProcessIdentity.Pid) }
    [pscustomobject]@{ AlreadyExited = $false; StoppedPids = @($stopped); LauncherPid = $ProcessIdentity.Pid }
}

function Stop-OpenScienceOwnedProxy($Context, $Owner) {
    if (-not $Owner.proxy) { return }
    Assert-OpenScienceContext $Context -LifecycleOnly
    $actual = Get-OpenScienceProcessIdentity -ProcessId $Owner.proxy.Pid
    if ($null -eq $actual) { return }
    Assert-OpenScienceProcessIdentity $Owner.proxy $actual
    Assert-OpenScienceContainedPath $Owner.proxy_script $Context.ProfileRoot | Out-Null
    Assert-OpenScienceCondition ($actual.ExecutablePath -eq $Context.NodePath -and (Test-OpenScienceCommandPrefix $actual.CommandLine @($Context.NodePath, $Owner.proxy_script)) -and
        (Get-OpenScienceHash $Owner.proxy_script) -eq $Owner.proxy_script_sha256) 'Stop refused: guard process/source is not owned.'
    Stop-Process -Id $actual.Pid -ErrorAction Stop
}

function Get-OpenScienceProxySource {
    (Get-OpenScienceRepositoryPinSource) + "`n" + @'
// Generated into one owned, ignored runtime directory. Production upstream is
// fixed numeric loopback Ollama. --self-test exercises an in-memory mock only.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { PassThrough, Writable } from 'node:stream';

const known = ['caelab_study_create','caelab_study_inspect','caelab_parameters_discover',
  'caelab_parameters_register','caelab_parameters_list','caelab_experiment_run',
  'caelab_experiment_inspect','caelab_experiment_summary','caelab_experiment_compare'];
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const writeNew = (file, bytes) => fs.writeFileSync(file, bytes, {flag:'wx'});
const jsonNew = (file, value) => writeNew(file, JSON.stringify(value, null, 2)+'\n');
function guardFor(settings) {
  const bytes = fs.readFileSync(settings.guardPath);
  const guard = JSON.parse(bytes.toString('utf8'));
  assert.equal(guard.schema, 1); assert.equal(guard.kind, 'autonomous-cae-lab.openscience-tool-guard');
  for (const key of ['repo_root','run_name','profile_root']) assert.equal(guard[key], settings[key]);
  assert.equal(guard.model, settings.model);
  assert.ok(Array.isArray(guard.allowed));
  assert.equal(new Set(guard.allowed).size, guard.allowed.length);
  assert.deepEqual(guard.allowed, settings.allowed);
  assert.ok(guard.allowed.every(name => known.includes(name)));
  assert.ok(guard.required === null || (typeof guard.required === 'string' && guard.allowed.includes(guard.required)));
  assert.equal(typeof guard.no_tools, 'boolean');
  assert.ok(guard.stopping === undefined || typeof guard.stopping === 'boolean');
  assert.ok(!(guard.no_tools && guard.required));
  return {...guard, sha256:digest(bytes)};
}
function sourceFor(settings) {
  const boot=settings.boot_source;
  assert.equal(boot?.repo_root,settings.repo_root);
  assert.equal(sourcePinSha(boot),settings.boot_source_sha256);
  assert.ok(sourcePath.isAbsolute(boot.git_path));
  assert.equal(sourceDigest(sourceFs.readFileSync(boot.git_path)),boot.git_sha256);
  assertRepositorySourcePin(boot,captureRepositorySourcePin(settings.repo_root,boot.git_path));
  return settings.boot_source_sha256;
}
function inspect(body, guard) {
  if (guard.stopping) return {rejection:'Owned runtime is stopping; model actions are blocked', offered:[]};
  let value;
  try { value = JSON.parse(body.toString('utf8')); } catch { return {rejection:'Invalid JSON request', offered:[]}; }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {rejection:'Invalid request object', offered:[]};
  if (value.model !== guard.model) return {rejection:'Unexpected model', offered:[]};
  if (value.tools !== undefined && !Array.isArray(value.tools)) return {rejection:'Invalid tool schema list', offered:[]};
  const tools = value.tools || [], offered = tools.map(item => item?.function?.name);
  if (tools.some(item => item?.type !== 'function' || typeof item.function?.name !== 'string' ||
      !item.function.parameters || typeof item.function.parameters !== 'object' || Array.isArray(item.function.parameters)))
    return {rejection:'Malformed function schema', offered};
  if (new Set(offered).size !== offered.length || offered.some(name => !guard.allowed.includes(name)))
    return {rejection:'Tool outside the exact CAE allowlist', offered};
  if (guard.required && !offered.includes(guard.required)) return {rejection:'Required current MCP tool schema is absent', offered};
  if (guard.no_tools && tools.length) return {rejection:'Interpretation must not offer tools', offered};
  return {offered};
}
function createGuardedServer(settings, upstreamRequest = http.request) {
  let sequence = 0;
  return http.createServer((request, response) => {
    if (request.method === 'GET' && request.url === '/_caelab/health') {
      try { const guard = guardFor(settings); response.writeHead(200, {'content-type':'application/json'});
        response.end(JSON.stringify({kind:'autonomous-cae-lab.openscience-proxy',pid:process.pid,
          run_name:settings.run_name,profile_root:settings.profile_root,guard_sha256:guard.sha256,boot_source_sha256:settings.boot_source_sha256}));
      } catch { response.writeHead(412); response.end('Owned guard is invalid'); }
      return;
    }
    if (!((request.method === 'POST' && request.url === '/v1/chat/completions') ||
          (request.method === 'GET' && request.url === '/v1/models'))) {
      response.writeHead(403); response.end('Only declared local Ollama chat/model endpoints are allowed'); return;
    }
    const id = String(++sequence).padStart(6,'0'), started = new Date().toISOString();
    let size = 0, chunks = [], overflow = false;
    request.on('data', chunk => { size += chunk.length; if (size > 16*1024*1024) overflow = true; else chunks.push(chunk); });
    request.on('end', () => {
      const body = Buffer.concat(chunks), file = name => path.join(settings.receipts, `${name}-${id}`);
      writeNew(file('request')+'.json', body);
      const base = {sequence:id,started_utc:started,method:request.method,path:request.url,
        request_sha256:digest(body),request_size_bytes:body.length,authorization_present:Boolean(request.headers.authorization)};
      let guard, inspected = {offered:[]}, rejection = overflow ? 'Request exceeds capture bound' : undefined;
      try { guard = guardFor(settings); if (request.method === 'POST' && !rejection) inspected = inspect(body,guard); }
      catch { rejection = 'Owned guard is missing or invalid'; }
      rejection ||= inspected.rejection;
      let sourceVerified=false;
      if(request.method==='POST'&&!rejection){
        try { sourceFor(settings);sourceVerified=true; }
        catch { rejection='Core/MCP repository source differs from startup; a fresh owned runtime is required'; }
      }
      if (rejection) {
        const bytes = Buffer.from(JSON.stringify({error:{message:rejection,type:'caelab_schema_guard'}}));
        writeNew(file('response')+'.bin',bytes);
        jsonNew(file('receipt')+'.json',{...base,completed_utc:new Date().toISOString(),status:412,rejection,
          forwarded:false,offered_tools:inspected.offered,guard_sha256:guard?.sha256,boot_source_sha256:settings.boot_source_sha256,
          source_verified:sourceVerified,response_sha256:digest(bytes),response_size_bytes:bytes.length});
        response.writeHead(412,{'content-type':'application/json'}); response.end(bytes); return;
      }
      const output = fs.openSync(file('response')+'.bin','wx'), hash = crypto.createHash('sha256');
      let received = 0, finished = false, status = 502;
      const finish = error => {
        if (finished) return; finished = true; fs.fsyncSync(output); fs.closeSync(output);
        jsonNew(file('receipt')+'.json',{...base,completed_utc:new Date().toISOString(),status,error,
          offered_tools:inspected.offered,guard_sha256:guard.sha256,boot_source_sha256:settings.boot_source_sha256,
          source_verified:sourceVerified,forwarded:true,upstream:'http://127.0.0.1:11434',
          forwarded_body_unchanged:true,response_sha256:hash.digest('hex'),response_size_bytes:received});
      };
      const retain = bytes => { hash.update(bytes); received += bytes.length; fs.writeFileSync(output,bytes); };
      const upstream = upstreamRequest({hostname:'127.0.0.1',port:11434,path:request.url,method:request.method,
        headers:{'content-type':'application/json','content-length':body.length,authorization:'Bearer local'}}, result => {
        status = result.statusCode || 502;
        response.writeHead(status,{'content-type':result.headers['content-type'] || 'application/json'});
        result.on('data', chunk => { if (finished) return; retain(chunk); if (!response.write(chunk)) { result.pause(); response.once('drain',()=>result.resume()); } });
        result.on('end',()=>{ response.end(); finish(); });
        result.on('error',()=>{ response.destroy(); finish('upstream_response_error'); });
        result.on('aborted',()=>{ response.destroy(); finish('upstream_response_aborted'); });
      });
      upstream.setTimeout(settings.timeoutMs,()=>upstream.destroy(new Error('upstream_timeout')));
      upstream.on('error',()=>{ if (finished) return; const bytes = Buffer.from('{"error":{"message":"Local upstream transport failed"}}');
        if (!response.headersSent) { response.writeHead(502,{'content-type':'application/json'}); retain(bytes); response.end(bytes); }
        else response.destroy(); finish('upstream_transport_error'); });
      response.on('close',()=>{ if (!response.writableFinished) { upstream.destroy(); finish('client_cancelled'); } });
      // Never reserialize a valid model request or inject tool_choice/settings.
      upstream.end(body);
    });
    request.on('error',()=>response.destroy());
  });
}
async function selfTest(directory) {
  fs.mkdirSync(directory,{recursive:true});
  const gitPath=process.argv[4],repo=path.join(directory,'source-fixture');fs.mkdirSync(repo);
  const fixtureGit=args=>sourceExec(gitPath,['-C',repo,'-c','core.hooksPath='+path.join(directory,'no-hooks'),...args],
    {encoding:'utf8',windowsHide:true,stdio:['ignore','pipe','pipe']});
  fixtureGit(['init','--quiet']);fs.mkdirSync(path.join(repo,'caelab'));
  const sourceFile=path.join(repo,'caelab','__init__.py');fs.writeFileSync(sourceFile,'value = "source-A"\n');
  fixtureGit(['add','.']);fixtureGit(['-c','user.name=Runtime Mock','-c','user.email=runtime-mock@example.invalid','commit','--quiet','-m','mock source A']);
  const boot=captureRepositorySourcePin(repo,gitPath);
  const settings = {repo_root:repo,run_name:'mock-run',profile_root:directory,model:'openscience/qwen3-4b-ctx-16384',
    boot_source:boot,boot_source_sha256:sourcePinSha(boot),
    allowed:known,guardPath:path.join(directory,'guard.json'),receipts:directory,timeoutMs:1000};
  const guard = {schema:1,kind:'autonomous-cae-lab.openscience-tool-guard',repo_root:settings.repo_root,
    run_name:settings.run_name,profile_root:settings.profile_root,model:settings.model,allowed:known,required:known[0],no_tools:false};
  fs.writeFileSync(settings.guardPath,JSON.stringify(guard));
  const forwarded = [];
  const mock = (options, callback) => {
    assert.equal(options.hostname,'127.0.0.1'); assert.equal(options.port,11434);
    assert.equal(options.headers.authorization,'Bearer local');
    const target = new Writable({write(chunk,encoding,done){forwarded.push(Buffer.from(chunk));done();}});
    target.setTimeout = () => target;
    target.on('finish',()=>{ const result = new PassThrough(); result.statusCode=200; result.headers={'content-type':'application/json'};
      callback(result); result.end('{"mock":true}'); });
    return target;
  };
  const server = createGuardedServer(settings,mock);
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const body = Buffer.from('{\n  "model": "openscience/qwen3-4b-ctx-16384",\n  "messages": [{"role":"user","content":"line1\\nline2"}],\n  "tools": [{"type":"function","function":{"name":"caelab_study_create","parameters":{"type":"object"}}}],\n  "tool_choice": "auto"\n}');
  const post = async value => { const result = await fetch(base+'/v1/chat/completions',{method:'POST',body:value,headers:{authorization:'Bearer do-not-record'}});
    await result.text(); return result.status; };
  try {
    assert.equal(await post(body),200); assert.deepEqual(Buffer.concat(forwarded),body);
    assert.deepEqual(fs.readFileSync(path.join(directory,'request-000001.json')),body);
    let receipt=JSON.parse(fs.readFileSync(path.join(directory,'receipt-000001.json')));
    assert.equal(receipt.request_sha256,digest(body)); assert.equal(receipt.response_sha256,digest(Buffer.from('{"mock":true}')));
    assert.equal(receipt.forwarded_body_unchanged,true); assert.equal(receipt.authorization_present,true);
    assert.ok(!JSON.stringify(receipt).includes('do-not-record'));
    assert.equal(await post(body.toString().replace('qwen3-4b-ctx-16384','different-model')),412);
    assert.equal(await post(body.toString().replace('caelab_study_create','shell')),412);
    const absent=JSON.stringify({model:settings.model,messages:[]}); assert.equal(await post(absent),412);
    guard.required=null;guard.no_tools=true;fs.writeFileSync(settings.guardPath,JSON.stringify(guard));
    assert.equal(await post(body),412);assert.equal(await post(absent),200);
    const count=forwarded.length;guard.allowed=['shell'];fs.writeFileSync(settings.guardPath,JSON.stringify(guard));
    assert.equal(await post(absent),412);assert.equal(forwarded.length,count);
    guard.allowed=known;guard.stopping=true;fs.writeFileSync(settings.guardPath,JSON.stringify(guard));
    assert.equal(await post(absent),412);assert.equal(forwarded.length,count);
    guard.stopping=false;fs.writeFileSync(settings.guardPath,JSON.stringify(guard));
    fs.writeFileSync(sourceFile,'value = "source-B"\n');
    assert.equal(await post(absent),412);assert.equal(forwarded.length,count);
    const latestReceipt=fs.readdirSync(directory).filter(name=>/^receipt-\d+\.json$/.test(name)).sort().at(-1);
    const driftReceipt=JSON.parse(fs.readFileSync(path.join(directory,latestReceipt)));
    assert.equal(driftReceipt.forwarded,false);assert.equal(driftReceipt.source_verified,false);
    assert.ok(driftReceipt.rejection.includes('repository source'));
    assert.equal((await fetch(base+'/v1/models')).status,200);
    assert.equal((await fetch(base+'/v1/arbitrary')).status,403);
    console.log(JSON.stringify({status:'PASS',checks:['unchanged_multiline_body','request_response_sha256','credential_value_not_recorded',
      'wrong_model_rejected','foreign_tool_rejected','required_schema_absence_rejected','no_tools_rejected','tampered_guard_rejected','stopping_blocks_new_model_forwards',
      'proxy_post_rejects_source_drift_without_provider_forward','metadata_models_remains_harmless_under_source_drift','endpoint_allowlist'],provider_calls:0}));
  } finally { await new Promise(resolve=>server.close(resolve)); }
}
if (process.argv[2] === '--self-test') {
  await selfTest(path.resolve(process.argv[3]));
} else {
  const settings = JSON.parse(fs.readFileSync(path.resolve(process.argv[2]),'utf8'));
  const profile = path.resolve(settings.profile_root);
  for (const key of ['guardPath','receipts','readyPath']) assert.ok(path.resolve(settings[key]).startsWith(profile+path.sep));
  const marker = JSON.parse(fs.readFileSync(path.join(profile,'caelab-profile-owner.json'),'utf8'));
  assert.equal(marker.kind,'autonomous-cae-lab.openscience-profile');
  for (const key of ['repo_root','run_name','profile_root']) assert.equal(marker[key],settings[key]);
  assert.equal(settings.model,'openscience/qwen3-4b-ctx-16384');guardFor(settings);
  sourceFor(settings);
  const server = createGuardedServer(settings);
  server.listen(0,'127.0.0.1',()=>jsonNew(settings.readyPath,{kind:'autonomous-cae-lab.openscience-proxy',schema:1,pid:process.pid,
    url:`http://127.0.0.1:${server.address().port}/v1`,run_name:settings.run_name,profile_root:settings.profile_root,
    preserves_request_bytes:true,upstream:'http://127.0.0.1:11434',started_utc:new Date().toISOString()}));
  process.on('SIGTERM',()=>server.close(()=>process.exit(0)));
}
'@
}

function Save-OpenScienceRuntimeOwner($Owner) {
    $history = Join-Path $Owner.runtime_directory ('owner-' + $Owner.state + '-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '-' + [Guid]::NewGuid().ToString('N') + '.json')
    Write-OpenScienceJson $history $Owner -CreateNew
    Write-OpenScienceJson $Owner.context.OwnerPath $Owner
}

function Start-OpenScienceLoggedProcess($Info, [string]$Directory, [string]$Name) {
    $output = Open-OpenScienceLiveLog (Join-Path $Directory "$Name-stdout.jsonl")
    try { $errorLog = Open-OpenScienceLiveLog (Join-Path $Directory "$Name-stderr.txt") } catch { $output.Dispose(); throw }
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $Info
    try {
        Assert-OpenScienceCondition ($process.Start()) 'Owned process failed to start.'
        [pscustomobject]@{ Process = $process; Identity = (Get-OpenScienceProcessIdentity $process.Id)
            Output = $output; ErrorLog = $errorLog; Copies = @($process.StandardOutput.BaseStream.CopyToAsync($output), $process.StandardError.BaseStream.CopyToAsync($errorLog)) }
    } catch { $output.Dispose(); $errorLog.Dispose(); $process.Dispose(); throw }
}

function Close-OpenScienceLoggedProcess($Logged) {
    if ($null -eq $Logged) { return }
    try {
        if ($Logged.Process.HasExited) { [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]$Logged.Copies, 10000) | Out-Null }
    } finally { $Logged.Output.Dispose(); $Logged.ErrorLog.Dispose(); $Logged.Process.Dispose() }
}

function Find-OpenScienceServerReady($Context, $Launcher, [string]$Directory) {
    $children = @(Get-OpenScienceDescendants $Launcher.Pid | Where-Object { $_.ExecutablePath -in @($Context.NativeBinaries.Path) -and $_.CommandLine -match '\sserve(?:\s|$)' })
    Assert-OpenScienceCondition ($children.Count -le 1) 'Multiple native serve descendants; readiness ownership is ambiguous.'
    if ($children.Count -eq 0) { return $null }
    $native = $children[0]; Assert-OpenScienceNativeIdentity $Context $native
    $connections = @(Get-NetTCPConnection -State Listen -OwningProcess $native.Pid -ErrorAction SilentlyContinue)
    if ($connections.Count -eq 0) { return $null }
    $ready = $null
    foreach ($line in (Get-Content -LiteralPath (Join-Path $Directory 'server-stdout.jsonl') -ErrorAction Stop)) {
        try { $value = $line | ConvertFrom-Json -ErrorAction Stop } catch { continue }
        if ($value.type -eq 'server.ready') {
            Assert-OpenScienceCondition ($value.schemaVersion -eq 1 -and $value.version -eq $script:OpenSciencePinnedVersion) 'Unexpected official readiness schema/version.'
            $ready = @{ Url = $value.url.TrimEnd('/'); Pid = [int]$value.pid; Source = 'official server.ready JSON'; Official = $value }
        }
    }
    if (-not $ready) {
        $loopback = @($connections | Where-Object LocalAddress -eq '127.0.0.1')
        Assert-OpenScienceCondition ($loopback.Count -eq 1) 'Owned socket fallback is ambiguous.'
        $ready = @{ Url = "http://127.0.0.1:$($loopback[0].LocalPort)"; Pid = $native.Pid; Source = 'actual pinned native descendant and owned listening socket; stdout JSON pending' }
    }
    Assert-OpenScienceReadiness $Context $ready.Url $ready.Pid $native $connections $null $null
    $ready.Native = $native; $ready.Connections = $connections
    return $ready
}

function Invoke-OpenScienceServeInternal([string]$ContextPath, [string]$LaunchToken) {
    $spec = Read-OpenScienceJson $ContextPath
    $context = [pscustomobject]$spec.context
    Assert-OpenScienceContext $context
    Assert-OpenScienceContainedPath $ContextPath $context.ProfileRoot | Out-Null
    Assert-OpenScienceCondition ($spec.launch_token -ceq $LaunchToken -and $spec.script_path -eq $script:OpenScienceServerScriptPath -and
        $spec.script_sha256 -eq (Get-OpenScienceHash $script:OpenScienceServerScriptPath)) 'Internal controller launch marker/source does not match.'
    $directory = Assert-OpenScienceContainedPath $spec.runtime_directory $context.ProfileRoot
    Assert-OpenScienceCondition ($spec.port -ge 0 -and $spec.port -le 65535 -and $spec.startup_timeout_seconds -ge 5 -and $spec.startup_timeout_seconds -le 180) 'Invalid internal startup bounds.'
    Assert-OpenScienceCondition ($spec.boot_source_sha256 -ceq (Get-OpenScienceSourcePinSha256 $spec.boot_source)) 'Immutable startup source digest changed.'
    Assert-OpenScienceRepositorySourcePin $spec.boot_source (Get-OpenScienceRepositorySourcePin -Context $context -GitPath $spec.boot_source.git_path -GitSha256 $spec.boot_source.git_sha256)
    $owner = [ordered]@{ kind = 'autonomous-cae-lab.openscience-runtime'; schema = 1; state = 'starting'
        repo_root = $context.RepoRoot; run_name = $context.RunName; profile_root = $context.ProfileRoot; context = $context
        context_path = $ContextPath; launch_token = $LaunchToken; runtime_directory = $directory
        script_path = $script:OpenScienceServerScriptPath; script_sha256 = $spec.script_sha256
        boot_source = $spec.boot_source; boot_source_sha256 = $spec.boot_source_sha256
        controller = Get-OpenScienceProcessIdentity $PID; launcher = $null; native = $null; proxy = $null
        proxy_script = (Join-Path $directory 'ollama-guard.mjs'); started_utc = [DateTime]::UtcNow.ToString('o') }
    Save-OpenScienceRuntimeOwner $owner
    $proxyLogged = $null; $serverLogged = $null; $stoppedExplicitly = $false
    try {
        if ($context.Transport -ceq 'ChatGPT') {
            Initialize-OpenScienceNativeGuard $context $owner
            $watch = [Diagnostics.Stopwatch]::StartNew()
            $config = Read-OpenScienceJson $context.ConfigPath
            Write-OpenScienceJson (Join-Path $directory 'config-before-serve.json') $config -CreateNew
        } else {
        [IO.File]::WriteAllText($owner.proxy_script, (Get-OpenScienceProxySource), [Text.UTF8Encoding]::new($false))
        $owner.proxy_script_sha256 = Get-OpenScienceHash $owner.proxy_script
        $receipts = Join-Path $directory 'http-receipts'; New-Item -ItemType Directory -Path $receipts -ErrorAction Stop | Out-Null
        $proxyReadyPath = Join-Path $directory 'proxy-ready.json'; $proxySettingsPath = Join-Path $directory 'proxy-settings.json'
        Write-OpenScienceJson $proxySettingsPath @{ repo_root = $context.RepoRoot; run_name = $context.RunName; profile_root = $context.ProfileRoot
            model = $context.ModelId; allowed = @($context.AllowedTools); guardPath = $context.GuardPath
            boot_source = $owner.boot_source; boot_source_sha256 = $owner.boot_source_sha256
            receipts = $receipts; readyPath = $proxyReadyPath; timeoutMs = ($context.ProviderTimeoutSeconds * 1000) } -CreateNew
        $proxyInfo = New-OpenScienceLocalProcessInfo $context @('--version')
        $proxyInfo.ArgumentList.Clear(); $proxyInfo.ArgumentList.Add($owner.proxy_script); $proxyInfo.ArgumentList.Add($proxySettingsPath)
        $proxyLogged = Start-OpenScienceLoggedProcess $proxyInfo $directory 'proxy'
        $owner.proxy = $proxyLogged.Identity; Save-OpenScienceRuntimeOwner $owner
        $watch = [Diagnostics.Stopwatch]::StartNew()
        while (-not (Test-Path -LiteralPath $proxyReadyPath -PathType Leaf)) {
            Assert-OpenScienceCondition (-not $proxyLogged.Process.HasExited -and $watch.Elapsed.TotalSeconds -lt $spec.startup_timeout_seconds) 'Owned proxy did not publish bounded readiness.'
            Start-Sleep -Milliseconds 200
        }
        $proxyReady = Read-OpenScienceJson $proxyReadyPath
        Assert-OpenScienceCondition ($proxyReady.kind -eq 'autonomous-cae-lab.openscience-proxy' -and $proxyReady.pid -eq $owner.proxy.Pid -and
            $proxyReady.run_name -eq $context.RunName -and $proxyReady.profile_root -eq $context.ProfileRoot) 'Proxy readiness identity does not match.'
        $proxyUri = Assert-OpenScienceLocalUrl $proxyReady.url '/v1'
        $proxySockets = @(Get-NetTCPConnection -State Listen -OwningProcess $owner.proxy.Pid -ErrorAction Stop)
        Assert-OpenScienceCondition (@($proxySockets | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') }).Count -eq 0 -and
            @($proxySockets | Where-Object { $_.LocalAddress -eq '127.0.0.1' -and $_.LocalPort -eq $proxyUri.Port }).Count -eq 1) 'Proxy socket is not this owned loopback process.'
        $owner.proxy_url = $proxyReady.url
        $config = Read-OpenScienceJson $context.ConfigPath
        $config.provider.ollama.api = $proxyReady.url; $config.provider.ollama.options.baseURL = $proxyReady.url
        Write-OpenScienceJson (Join-Path $directory 'config-before-serve.json') $config -CreateNew
        Write-OpenScienceJson $context.ConfigPath $config
        }
        $owner.config_sha256 = Get-OpenScienceHash $context.ConfigPath
        Assert-OpenScienceRepositorySourcePin $owner.boot_source (Get-OpenScienceRepositorySourcePin -Context $context -GitPath $owner.boot_source.git_path -GitSha256 $owner.boot_source.git_sha256)
        $arguments = @('serve', '--port', [string]$spec.port, '--format', 'json')
        $serverLogged = Start-OpenScienceLoggedProcess (New-OpenScienceLocalProcessInfo $context $arguments) $directory 'server'
        $owner.launcher = $serverLogged.Identity; $owner.arguments = $arguments; Save-OpenScienceRuntimeOwner $owner
        $ready = $null
        while (-not $ready) {
            Assert-OpenScienceCondition (-not $serverLogged.Process.HasExited -and $watch.Elapsed.TotalSeconds -lt $spec.startup_timeout_seconds) 'Official serve did not publish bounded owned readiness.'
            $ready = Find-OpenScienceServerReady $context $owner.launcher $directory
            if (-not $ready) { Start-Sleep -Milliseconds 300 }
        }
        $owner.native = $ready.Native; $owner.runtime_url = $ready.Url; $owner.readiness_source = $ready.Source
        Save-OpenScienceRuntimeOwner $owner
        $healthResponse = Invoke-OpenScienceHttp "$($ready.Url)/global/health" -TimeoutSeconds 10
        Assert-OpenScienceCondition ($healthResponse.StatusCode -eq 200) 'Owned global health probe failed.'
        $health = $healthResponse.Content | ConvertFrom-Json -AsHashtable
        Assert-OpenScienceReadiness $context $ready.Url $ready.Pid $ready.Native $ready.Connections $health $null
        $owner.health_run_id = $health.runId
        Write-OpenScienceJson (Join-Path $directory 'global-health.json') $health -CreateNew
        $remaining = [int][Math]::Floor($spec.startup_timeout_seconds - $watch.Elapsed.TotalSeconds)
        Assert-OpenScienceCondition ($remaining -gt 0) 'No startup time remains for MCP readiness.'
        $mcpResponse = Invoke-OpenScienceHttp "$($ready.Url)/mcp" -Headers @{ 'x-openscience-directory' = $context.RepoRoot } -TimeoutSeconds ([Math]::Min(60, $remaining))
        $mcp = $mcpResponse.Content | ConvertFrom-Json -AsHashtable
        Write-OpenScienceJson (Join-Path $directory 'mcp-current.json') $mcp -CreateNew
        Assert-OpenScienceCondition ($mcpResponse.StatusCode -eq 200 -and $mcp.caelab.status -eq 'connected') 'Current owned MCP is not connected; startup remains failed.'
        if ($context.Transport -ceq 'ChatGPT') { Assert-OpenScienceNativeGuardLoaded $context $owner }
        Assert-OpenScienceRepositorySourcePin $owner.boot_source (Get-OpenScienceRepositorySourcePin -Context $context -GitPath $owner.boot_source.git_path -GitSha256 $owner.boot_source.git_sha256)
        $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($context.RepoRoot)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        $owner.workspace_url = "$($ready.Url)/$encoded/session"
        $owner.state = 'ready'; $owner.ready_utc = [DateTime]::UtcNow.ToString('o'); Save-OpenScienceRuntimeOwner $owner
        Write-Output ("Owned OpenScience ready at " + $owner.runtime_url)
        $handledStopRequests = [Collections.Generic.HashSet[string]]::new()
        while (-not $serverLogged.Process.WaitForExit(500)) {
            if ($proxyLogged -and $proxyLogged.Process.HasExited -and $owner.state -ne 'guard_failed') {
                $owner.state = 'guard_failed'; $owner.guard_failure = 'Proxy exited. Inference is blocked; lifecycle cancellation remains available.'
                Save-OpenScienceRuntimeOwner $owner
            }
            $stopPath = @(Get-ChildItem -LiteralPath $directory -File -Filter 'stop-request-*.json' | Sort-Object Name |
                Where-Object { -not $handledStopRequests.Contains($_.FullName) } | Select-Object -First 1).FullName
            if ($stopPath) {
                $handledStopRequests.Add($stopPath) | Out-Null
                try {
                    $request = Read-OpenScienceJson $stopPath
                    Assert-OpenScienceCondition ($request.launch_token -ceq $LaunchToken -and $request.run_name -eq $context.RunName -and $request.repo_root -eq $context.RepoRoot) 'Stop request is not owned.'
                    $owner.state = 'stopping'; $owner.stop_request_path = $stopPath; $owner.stop_refused = $false; Save-OpenScienceRuntimeOwner $owner
                    $stopCheckDirectory = Join-Path $directory ('stop-check-' + [Guid]::NewGuid().ToString('N'))
                    New-Item -ItemType Directory -Path $stopCheckDirectory -ErrorAction Stop | Out-Null
                    $current = Get-OpenScienceLocalRuntime $context.OwnerPath -LifecycleOnly
                    Pause-OpenScienceModelForwards $current $stopCheckDirectory
                    $status = Get-OpenScienceOwnedSessionStatus $current (Join-Path $stopCheckDirectory 'session-status.json')
                    Assert-OpenScienceCondition (@(Get-OpenScienceNonIdleSessionIds $status).Count -eq 0) 'Active owned sessions remain. Official exact-session abort/idle confirmation is required before stop.'
                    $stoppedExplicitly = $true
                    $owner.stop_result = Stop-OpenScienceOwnedLauncher $context $owner.launcher
                    $serverLogged.Process.WaitForExit(10000) | Out-Null
                    break
                } catch {
                    $owner.state = $(if ($proxyLogged -and $proxyLogged.Process.HasExited) { 'guard_failed' } else { 'ready' })
                    $owner.stop_refused = $true; $owner.stop_refusal = $_.Exception.Message; $owner.stop_refused_utc = [DateTime]::UtcNow.ToString('o')
                    Save-OpenScienceRuntimeOwner $owner
                }
            }
        }
        Assert-OpenScienceCondition ($stoppedExplicitly) 'Official persistent server exited before an explicit stop.'
        $owner.state = 'stopped'; $owner.stopped_utc = [DateTime]::UtcNow.ToString('o')
    } catch {
        $owner.state = 'failed'; $owner.failure = $_.Exception.Message; $owner.failed_utc = [DateTime]::UtcNow.ToString('o')
        Write-OpenScienceJson (Join-Path $directory ('failure-' + [Guid]::NewGuid().ToString('N') + '.json')) @{ error = $owner.failure; utc = $owner.failed_utc } -CreateNew
        if ($owner.launcher) {
            try { $owner.cleanup = Stop-OpenScienceOwnedLauncher $context $owner.launcher } catch { $owner.cleanup_failure = $_.Exception.Message }
        }
    } finally {
        try { Stop-OpenScienceOwnedProxy $context $owner } catch { $owner.proxy_cleanup_failure = $_.Exception.Message; $owner.state = 'failed' }
        Close-OpenScienceLoggedProcess $serverLogged; Close-OpenScienceLoggedProcess $proxyLogged
        $owner.closed_utc = [DateTime]::UtcNow.ToString('o'); Save-OpenScienceRuntimeOwner $owner
    }
    if ($owner.state -eq 'failed') { throw "Owned server failed; evidence retained at $directory. $($owner.failure)" }
}

function ConvertTo-OpenScienceWindowsArgument([string]$Value) {
    # Start-Process joins ArgumentList on Windows. Quote each argument using
    # CommandLineToArgvW rules; no shell or command-string execution is involved.
    '"' + ([regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1')) + '"'
}

function Start-OpenScienceLocalServer($Context, [int]$Port, [int]$StartupTimeoutSeconds) {
    Assert-OpenScienceContext $Context
    Assert-OpenScienceCondition ($IsWindows) 'Persistent server lifecycle uses Windows process/socket identities.'
    $lockPath = Assert-OpenScienceContainedPath (Join-Path $Context.ProfileRoot 'runtime-start.lock') $Context.ProfileRoot
    try { $lock = [IO.FileStream]::new($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None, 1) }
    catch { throw 'Another start owns this profile startup lock; no second controller will be launched.' }
    try { return Start-OpenScienceLocalServerLocked $Context $Port $StartupTimeoutSeconds } finally { $lock.Dispose() }
}

function Start-OpenScienceLocalServerLocked($Context, [int]$Port, [int]$StartupTimeoutSeconds) {
    if (Test-Path -LiteralPath $Context.OwnerPath -PathType Leaf) {
        $prior = Read-OpenScienceRuntimeOwner $Context.OwnerPath
        $live = $null
        if ($prior.controller) { $live = Get-OpenScienceProcessIdentity $prior.controller.Pid }
        if ($live) {
            Assert-OpenScienceProcessIdentity $prior.controller $live
            if ($prior.state -eq 'ready') { return Get-OpenScienceLocalRuntime $Context.OwnerPath }
            throw "An owned controller already exists in state $($prior.state); use Status or Stop."
        }
        foreach ($identity in @($prior.launcher, $prior.native, $prior.proxy) | Where-Object { $null -ne $_ }) {
            Assert-OpenScienceCondition ($null -eq (Get-OpenScienceProcessIdentity $identity.Pid)) 'A prior runtime process remains; restart refused without verified cleanup.'
        }
        throw 'This profile has historical runtime ownership; choose a fresh RunName instead of restarting it.'
    }
    if ($Port) {
        Assert-OpenScienceCondition (@(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue).Count -eq 0) 'Requested port is already in use; no existing server will be taken over.'
    }
    Reset-OpenScienceToolGuardForFreshStartup $Context
    Assert-OpenScienceCondition ($Context.WslPythonCacheRoot) 'Fresh startup requires the source-pinned profile template; choose a new RunName.'
    $cacheRoot = Assert-OpenScienceContainedPath $Context.WslPythonCacheRoot $Context.ProfileRoot
    Assert-OpenScienceCondition (@(Get-ChildItem -LiteralPath $cacheRoot -Recurse -Force -ErrorAction Stop).Count -eq 0) 'Fresh startup requires an empty owned Python cache; choose a new RunName.'
    Assert-OpenScienceCondition ((Read-OpenScienceJson $Context.ConfigPath).mcp.caelab.command -ccontains
        ('PYTHONPYCACHEPREFIX=' + (ConvertTo-OpenScienceWslPath $cacheRoot))) 'MCP command does not bind the fresh owned Python cache.'
    $bootSource = Get-OpenScienceRepositorySourcePin -Context $Context
    if ($Context.McpGitTransport.Mode -eq 'WINDOWS_MANAGED_WORKTREE_GIT') {
        $bridgePin = @($bootSource.files | Where-Object path -eq 'scripts/wsl-windows-git/git')
        Assert-OpenScienceCondition ($bridgePin.Count -eq 1 -and $bridgePin[0].sha256 -ceq $Context.McpGitTransport.BridgeSha256 -and
            $bootSource.git_path -ceq $Context.McpGitTransport.HostGitPath -and
            $bootSource.git_sha256 -ceq $Context.McpGitTransport.HostGitSha256) 'MCP bridge and host Git must belong to the tracked boot source identity.'
    }
    $directory = Join-Path $Context.ProfileRoot ('server-runs\' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '-' + [Guid]::NewGuid().ToString('N'))
    Assert-OpenScienceContainedPath $directory $Context.ProfileRoot | Out-Null
    New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
    $specPath = Join-Path $directory 'launch-context.json'; $token = [Guid]::NewGuid().ToString('N')
    $spec = [ordered]@{ context = $Context; runtime_directory = $directory; launch_token = $token
        script_path = $script:OpenScienceServerScriptPath; script_sha256 = Get-OpenScienceHash $script:OpenScienceServerScriptPath
        boot_source = $bootSource; boot_source_sha256 = Get-OpenScienceSourcePinSha256 $bootSource
        port = $Port; startup_timeout_seconds = $StartupTimeoutSeconds }
    Write-OpenScienceJson $specPath $spec -CreateNew
    $pwsh = (Get-Command pwsh.exe -ErrorAction Stop).Source
    $arguments = @('-NoLogo', '-NoProfile', '-NonInteractive', '-File', $script:OpenScienceServerScriptPath,
        '-Mode', 'ServeInternal', '-ContextPath', $specPath, '-LaunchToken', $token) | ForEach-Object { ConvertTo-OpenScienceWindowsArgument $_ }
    # A fresh machine environment prevents inherited user provider credentials
    # from reaching the hidden controller; child PSIs also filter by key name.
    $controller = Start-Process -FilePath $pwsh -ArgumentList $arguments -WorkingDirectory $Context.RepoRoot -WindowStyle Hidden -UseNewEnvironment -PassThru -ErrorAction Stop `
        -RedirectStandardOutput (Join-Path $directory 'controller-stdout.txt') -RedirectStandardError (Join-Path $directory 'controller-stderr.txt')
    $identity = Get-OpenScienceProcessIdentity $controller.Id
    Write-OpenScienceJson (Join-Path $directory 'controller-launch.json') @{ identity = $identity; launch_token = $token; context_path = $specPath } -CreateNew
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while ($watch.Elapsed.TotalSeconds -lt $StartupTimeoutSeconds + 5) {
        Assert-OpenScienceCondition (-not $controller.HasExited) "Hidden controller exited; logs retained at $directory."
        if (Test-Path -LiteralPath $Context.OwnerPath -PathType Leaf) {
            $owner = Read-OpenScienceRuntimeOwner $Context.OwnerPath
            if ($owner.launch_token -ceq $token) {
                if ($owner.state -eq 'ready') { return Get-OpenScienceLocalRuntime $Context.OwnerPath }
                Assert-OpenScienceCondition ($owner.state -notin @('failed', 'stopped')) "Startup failed; logs retained at $directory. $($owner.failure)"
            }
        }
        Start-Sleep -Milliseconds 300
    }
    Write-OpenScienceJson (Join-Path $directory ('stop-request-' + [Guid]::NewGuid().ToString('N') + '.json')) @{ launch_token = $token; run_name = $Context.RunName; repo_root = $Context.RepoRoot
        reason = 'startup_timeout'; requested_utc = [DateTime]::UtcNow.ToString('o') } -CreateNew
    throw "Owned startup timeout; stop request and logs retained at $directory."
}

function Stop-OpenScienceLocalServer([string]$OwnerPath) {
    $owner = Read-OpenScienceRuntimeOwner $OwnerPath -LifecycleOnly
    $context = [pscustomobject]$owner.context
    if ($owner.state -eq 'stopped') { return [pscustomobject]@{ State = 'stopped'; OwnerPath = $OwnerPath; AlreadyStopped = $true } }
    $controller = Get-OpenScienceProcessIdentity $owner.controller.Pid
    Assert-OpenScienceProcessIdentity $owner.controller $controller
    Assert-OpenScienceCondition ($controller.CommandLine.Contains($owner.context_path) -and $controller.CommandLine.Contains($owner.launch_token) -and
        (Get-OpenScienceHash $owner.script_path) -eq $owner.script_sha256) 'Stop refused: hidden controller/source is not owned.'
    if ($owner.launcher) { Assert-OpenScienceProcessIdentity $owner.launcher (Get-OpenScienceProcessIdentity $owner.launcher.Pid) }
    if ($owner.native) { Assert-OpenScienceProcessIdentity $owner.native (Get-OpenScienceProcessIdentity $owner.native.Pid); Assert-OpenScienceNativeIdentity $context $owner.native }
    if ($owner.proxy) { $proxy = Get-OpenScienceProcessIdentity $owner.proxy.Pid; if ($proxy) { Assert-OpenScienceProcessIdentity $owner.proxy $proxy } }
    $preflight = Confirm-OpenScienceSessionsIdleForStop $context
    $requestPath = Join-Path $owner.runtime_directory ('stop-request-' + [Guid]::NewGuid().ToString('N') + '.json')
    Write-OpenScienceJson $requestPath @{ launch_token = $owner.launch_token; run_name = $context.RunName; repo_root = $context.RepoRoot
        reason = 'explicit_stop'; idle_receipt = $preflight.directory; requested_utc = [DateTime]::UtcNow.ToString('o') } -CreateNew
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while ($watch.Elapsed.TotalSeconds -lt 30) {
        $current = Read-OpenScienceRuntimeOwner $OwnerPath -LifecycleOnly
        Assert-OpenScienceCondition (-not ($current.stop_refused -and $current.stop_request_path -eq $requestPath)) "Controller refused termination: $($current.stop_refusal). Receipts remain at $($preflight.directory)."
        if ($current.state -in @('stopped', 'failed') -and $current.closed_utc) {
            Assert-OpenScienceCondition ($current.state -eq 'stopped') 'Owned cleanup failed; preserved owner diagnostics identify the unverified process.'
            return [pscustomobject]@{ State = 'stopped'; OwnerPath = $OwnerPath; StopResult = $current.stop_result }
        }
        Start-Sleep -Milliseconds 300
    }
    throw 'Controller did not confirm bounded cleanup. Stop request is retained; unverified processes were not terminated.'
}

function Invoke-OpenScienceRuntimeSelfTest([string]$RepoRoot, [string]$RunName) {
    $root = Join-Path ([IO.Path]::GetFullPath($RepoRoot)) "artifacts\$RunName"
    Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $root)) 'SelfTest requires a new ignored artifact path.'
    New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
    $checks = [Collections.Generic.List[string]]::new()
    $logPath = Join-Path $root 'live-log.txt'; $stream = Open-OpenScienceLiveLog $logPath
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes("first readiness line`nsecond line`n")
        $stream.Write($bytes)
        $readerStream = [IO.FileStream]::new($logPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        $reader = [IO.StreamReader]::new($readerStream)
        try { $liveText = $reader.ReadToEnd() } finally { $reader.Dispose() }
        Assert-OpenScienceCondition ($liveText -ceq "first readiness line`nsecond line`n") 'Open log is not immediately readable.'
        $checks.Add('live_log_readable_before_close')
    } finally { $stream.Dispose() }
    $info = [Diagnostics.ProcessStartInfo]::new(); $prompt = "one`n two `"quoted`"`nthree"
    $info.ArgumentList.Add($prompt)
    Assert-OpenScienceCondition ($info.ArgumentList.Count -eq 1 -and $info.ArgumentList[0] -ceq $prompt) 'Native ArgumentList changed the multiline prompt.'
    $checks.Add('multiline_argument_preserved')
    $stripped = @(Get-OpenScienceRemovedEnvironment @('PATH', 'OPENAI_API_KEY', 'SOME_COMPANY_PASSWORD', 'OPENSCIENCE_CONFIG_CONTENT', 'NODE_OPTIONS', 'WSLENV'))
    Assert-OpenScienceCondition ($stripped.Count -eq 5 -and 'PATH' -notin $stripped) 'Credential/config/environment name filtering failed.'
    $checks.Add('credential_names_filtered_without_values')
    foreach ($url in @('http://0.0.0.0:4098', 'http://example.com:4098', 'http://127.0.0.1:4098/other', 'http://user:pass@127.0.0.1:4098')) {
        $rejected = $false; try { Assert-OpenScienceLocalUrl $url | Out-Null } catch { $rejected = $true }
        Assert-OpenScienceCondition $rejected 'Public/ambiguous readiness URL was accepted.'
    }
    $checks.Add('public_url_rejected')
    $git = (Get-Command $(if ($IsWindows) { 'git.exe' } else { 'git' }) -ErrorAction Stop).Source
    $nativeGitFixture = Join-Path $root 'native-git-fixture'
    New-Item -ItemType Directory -Path (Join-Path $nativeGitFixture '.git') -ErrorAction Stop | Out-Null
    $nativeTransport = New-OpenScienceMcpGitTransport -RepoRoot $nativeGitFixture
    Assert-OpenScienceCondition ($nativeTransport.Mode -eq 'NATIVE_WSL_GIT' -and $nativeTransport.Environment.Count -eq 0) 'Native Git checkout gained a Windows bridge.'
    $checks.Add('native_git_checkout_keeps_original_mcp_environment')
    $managedGitFixture = Join-Path $root 'managed git fixture'
    New-Item -ItemType Directory -Path $managedGitFixture -ErrorAction Stop | Out-Null
    [IO.File]::WriteAllText((Join-Path $managedGitFixture '.git'), ('gitdir: C:/mock/.git/worktrees/example' + [char]10), [Text.UTF8Encoding]::new($false))
    $rejected = $false
    try { New-OpenScienceMcpGitTransport -RepoRoot $managedGitFixture -HostGitPath $git -OriginalWslPath '/usr/local/bin:/usr/bin:/bin' | Out-Null }
    catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'Managed worktree without tracked bridge was accepted.'
    $checks.Add('missing_managed_git_bridge_rejected')
    $managedBridge = Join-Path $managedGitFixture 'scripts/wsl-windows-git/git'
    New-Item -ItemType Directory -Path (Split-Path -Parent $managedBridge) -ErrorAction Stop | Out-Null
    $bridgeBytes = [IO.File]::ReadAllBytes((Join-Path $RepoRoot 'scripts/wsl-windows-git/git'))
    [IO.File]::WriteAllBytes($managedBridge, $bridgeBytes)
    $managedTransport = New-OpenScienceMcpGitTransport -RepoRoot $managedGitFixture -HostGitPath $git -OriginalWslPath '/usr/local/bin:/usr/bin:/bin'
    Assert-OpenScienceCondition ($managedTransport.Environment.Count -eq 2 -and
        $managedTransport.Environment[0] -ceq ('PATH=' + (ConvertTo-OpenScienceWslPath (Split-Path -Parent $managedBridge)) + ':/usr/local/bin:/usr/bin:/bin') -and
        $managedTransport.Environment[1] -ceq ('CAELAB_HOST_GIT=' + (ConvertTo-OpenScienceWslPath $git)) -and
        $managedTransport.HostGitSha256 -ceq (Get-OpenScienceHash $git)) 'MCP Git bridge changed spaces, WSL PATH or host Git identity.'
    $checks.Add('managed_git_bridge_preserves_spaces_original_path_and_pinned_host_git')
    [IO.File]::WriteAllText($managedBridge, ([Text.Encoding]::UTF8.GetString($bridgeBytes) -replace '\n', ([string][char]13 + [char]10)), [Text.UTF8Encoding]::new($false))
    $rejected = $false
    try { New-OpenScienceMcpGitTransport -RepoRoot $managedGitFixture -HostGitPath $git -OriginalWslPath '/usr/bin:/bin' | Out-Null }
    catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'CRLF Git shell bridge was accepted.'
    $checks.Add('crlf_managed_git_bridge_rejected')
    [IO.File]::WriteAllBytes($managedBridge, $bridgeBytes)
    $rejected = $false
    try { New-OpenScienceMcpGitTransport -RepoRoot $managedGitFixture -HostGitPath $git -OriginalWslPath ('/usr/bin' + [char]10 + '/bin') | Out-Null }
    catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'Multiline WSL PATH was accepted.'
    $checks.Add('multiline_wsl_path_rejected')
    $fixtureSource = (Get-OpenScienceRepositoryPinSource) + "`n" + @'
const base=sourcePath.resolve(process.argv[1]),git=sourcePath.resolve(process.argv[2]);
const noHooks=sourcePath.join(base,'no-hooks');sourceFs.mkdirSync(noHooks);
const run=(root,args)=>sourceExec(git,['-C',root,'-c','core.hooksPath='+noHooks,'-c','commit.gpgsign=false',
  '-c','user.name=Runtime Mock','-c','user.email=runtime-mock@example.invalid',...args],
  {encoding:'utf8',windowsHide:true,stdio:['ignore','pipe','pipe']});
const make=(name,file)=>{const root=sourcePath.join(base,name);sourceFs.mkdirSync(root);run(root,['init','--quiet']);
  sourceFs.mkdirSync(sourcePath.dirname(sourcePath.join(root,file)),{recursive:true});sourceFs.writeFileSync(sourcePath.join(root,file),'VALUE = "source-A"\n');
  run(root,['add','.']);run(root,['commit','--quiet','-m','mock source A']);return root;};
const kernel=make('kernel-source','kernel.py'),plugin=make('plugin-source','models/model.py'),repo=make('repository','caelab/__init__.py');
run(plugin,['-c','protocol.file.allow=always','submodule','add','--quiet',kernel,'vendor/kernel']);
run(plugin,['commit','--quiet','-am','mock nested plugin']);
sourceFs.mkdirSync(sourcePath.join(repo,'openscience'));sourceFs.writeFileSync(sourcePath.join(repo,'openscience/mcp_server.py'),'VALUE = "source-A"\n');
sourceFs.mkdirSync(sourcePath.join(repo,'scripts/wsl-windows-git'),{recursive:true});
sourceFs.copyFileSync(process.argv[3],sourcePath.join(repo,'scripts/wsl-windows-git/git'));
sourceFs.writeFileSync(sourcePath.join(repo,'.gitignore'),'artifacts/\n__pycache__/\n');
run(repo,['-c','protocol.file.allow=always','submodule','add','--quiet',plugin,'plugins/fixture']);
run(repo,['add','.']);run(repo,['commit','--quiet','-m','mock recursive fixture']);
run(repo,['-c','protocol.file.allow=always','submodule','update','--init','--recursive','--quiet']);
process.stdout.write(JSON.stringify({repo,core:sourcePath.join(repo,'caelab/__init__.py'),
  nested:sourcePath.join(repo,'plugins/fixture/vendor/kernel/kernel.py'),plugin:sourcePath.join(repo,'plugins/fixture'),noHooks}));
'@
    $fixture = Invoke-OpenScienceSourceNode $fixtureSource @($root, $git, (Join-Path $RepoRoot 'scripts/wsl-windows-git/git')) $root | ConvertFrom-Json -AsHashtable
    $bootFixture = Get-OpenScienceRepositorySourcePin -RepoRoot $fixture.repo
    Write-OpenScienceJson (Join-Path $root 'boot-source-A.json') $bootFixture -CreateNew
    Assert-OpenScienceRepositorySourcePin $bootFixture (Get-OpenScienceRepositorySourcePin -RepoRoot $fixture.repo)
    Assert-OpenScienceCondition ($bootFixture.submodules.Count -eq 2 -and
        @($bootFixture.files | Where-Object path -eq 'plugins/fixture/vendor/kernel/kernel.py').Count -eq 1) 'Real snapshot omitted recursive pinned plugin source.'
    $checks.Add('real_git_snapshot_pins_recursive_submodule_heads_and_files')
    $checks.Add('unchanged_boot_source_reusable_before_first_acceptance')
    $canonicalSource = (Get-OpenScienceRepositoryPinSource) + "`nprocess.stdout.write(sourcePinSha(JSON.parse(process.argv[1])));"
    $nodePinHash = Invoke-OpenScienceSourceNode $canonicalSource @(($bootFixture | ConvertTo-Json -Depth 40 -Compress)) $fixture.repo
    Assert-OpenScienceCondition ($nodePinHash -ceq (Get-OpenScienceSourcePinSha256 $bootFixture)) 'Public and proxy source-pin digests differ.'
    $checks.Add('public_and_proxy_source_pin_canonical_hashes_match')
    $fixtureOwner = @{ context = @{ RepoRoot = $fixture.repo }; boot_source = $bootFixture; boot_source_sha256 = Get-OpenScienceSourcePinSha256 $bootFixture }
    Assert-OpenScienceRuntimeBootSource $fixtureOwner
    $pinnedBridge = Join-Path $fixture.repo 'scripts/wsl-windows-git/git'
    try {
        [IO.File]::WriteAllText($pinnedBridge, ('# changed bridge' + [char]10), [Text.UTF8Encoding]::new($false))
        $rejected = $false; try { Assert-OpenScienceRuntimeBootSource $fixtureOwner } catch { $rejected = $true }
        Assert-OpenScienceCondition $rejected 'Tracked Git bridge drift was accepted after boot.'
        $checks.Add('tracked_git_bridge_drift_rejected_before_inference')
    } finally { [IO.File]::WriteAllBytes($pinnedBridge, $bridgeBytes) }
    [IO.File]::WriteAllText($fixture.core, "VALUE = `"source-B`"`n", [Text.UTF8Encoding]::new($false))
    $rejected = $false; try { Assert-OpenScienceRuntimeBootSource $fixtureOwner } catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'A Core edit between boot and the first lookup was accepted.'
    $checks.Add('boot_A_core_edit_B_before_first_lookup_rejected')
    [IO.File]::WriteAllText($fixture.core, "VALUE = `"source-A`"`n", [Text.UTF8Encoding]::new($false))
    $beforeHead = Get-OpenScienceRepositorySourcePin -RepoRoot $fixture.repo
    $headSource = (Get-OpenScienceRepositoryPinSource) + "`n" + @'
sourceExec(process.argv[2],['-C',process.argv[1],'-c','core.hooksPath='+process.argv[3],'-c','commit.gpgsign=false',
  '-c','user.name=Runtime Mock','-c','user.email=runtime-mock@example.invalid','commit','--allow-empty','--quiet','-m','mock HEAD drift'],
  {encoding:'utf8',windowsHide:true,stdio:['ignore','pipe','pipe']});
process.stdout.write('{}');
'@
    Invoke-OpenScienceSourceNode $headSource @($fixture.repo, $git, $fixture.noHooks) $fixture.repo | Out-Null
    $afterHead = Get-OpenScienceRepositorySourcePin -RepoRoot $fixture.repo
    $rejected = $false; try { Assert-OpenScienceRuntimeBootSource $fixtureOwner } catch { $rejected = $true }
    Assert-OpenScienceCondition ($rejected -and $beforeHead.source_tree_sha256 -ceq $afterHead.source_tree_sha256 -and
        $beforeHead.source_commit -cne $afterHead.source_commit) 'HEAD drift with unchanged file bytes was accepted.'
    $checks.Add('real_HEAD_only_drift_rejected_before_inference')
    [IO.File]::WriteAllText($fixture.nested, "VALUE = `"nested-B`"`n", [Text.UTF8Encoding]::new($false))
    $afterNested = Get-OpenScienceRepositorySourcePin -RepoRoot $fixture.repo
    $rejected = $false; try { Assert-OpenScienceRepositorySourcePin $afterHead $afterNested } catch { $rejected = $true }
    Assert-OpenScienceCondition ($rejected -and $afterNested.source_commit -ceq $afterHead.source_commit) 'Nested plugin byte drift was accepted.'
    $checks.Add('real_recursive_submodule_byte_drift_rejected')
    Invoke-OpenScienceSourceNode $headSource @($fixture.plugin, $git, $fixture.noHooks) $fixture.repo | Out-Null
    $afterPluginHead = Get-OpenScienceRepositorySourcePin -RepoRoot $fixture.repo
    $rejected = $false; try { Assert-OpenScienceRepositorySourcePin $afterNested $afterPluginHead } catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'Submodule HEAD drift was accepted.'
    $checks.Add('real_submodule_HEAD_drift_rejected')
    [IO.File]::WriteAllText((Join-Path $fixture.repo 'caelab/untracked_import.py'), "VALUE = 'untracked'`n", [Text.UTF8Encoding]::new($false))
    $rejected = $false; try { Get-OpenScienceRepositorySourcePin -RepoRoot $fixture.repo | Out-Null } catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'Untracked importable source was accepted.'
    $checks.Add('untracked_importable_source_rejected_without_import')
    # Dynamically scoped mocks exercise the actual readiness/abort/stop helpers
    # without invoking a provider, backend, native executable or OS termination.
    $mockNative = [pscustomobject]@{ Pid = 7002; ParentPid = 7001; CreationUtc = 'mock-native'; ExecutablePath = 'mock-native.exe'; CommandLine = 'mock-native.exe serve' }
    $mockLauncher = [pscustomobject]@{ Pid = 7001; ParentPid = 7000; CreationUtc = 'mock-launcher'; ExecutablePath = 'mock-node.exe'; CommandLine = 'mock-node.exe mock-launcher run --attach http://127.0.0.1:4098' }
    $mockContext = [pscustomobject]@{ RepoRoot = $RepoRoot; RunName = $RunName; ProfileRoot = $root; OwnerPath = (Join-Path $root 'mock-owner.json')
        RuntimeURL = 'http://127.0.0.1:4098'; NodePath = 'mock-node.exe'; LauncherPath = 'mock-launcher'; NativeBinaries = @(@{ Path = 'mock-native.exe' })
        GuardPath = (Join-Path $root 'stop-guard.json'); ModelId = 'openscience/qwen3-4b-ctx-16384'
        AllowedTools = @('caelab_experiment_inspect', 'caelab_experiment_run')
        Environment = @{ OPENSCIENCE_EXPERIMENTAL_OUTPUT_TOKEN_MAX = '4096' }; RemoveEnvironment = @('OPENSCIENCE_CONFIG', 'OPENSCIENCE_AUTH_TOKEN') }
    $trace = [Collections.Generic.List[string]]::new()
    $httpScenario = 'abort'; $mockHttpState = @{ Aborted = $false }
    $mockSourceOwner = $fixtureOwner
    function Assert-OpenScienceContext($Context) { }
    function Assert-OpenScienceNativeIdentity($Context, $Identity) { Assert-OpenScienceCondition ($Identity.ExecutablePath -eq 'mock-native.exe') 'Mock native mismatch.' }
    function Get-OpenScienceLocalRuntime([string]$OwnerPath, [switch]$LifecycleOnly) {
        Assert-OpenScienceCondition $LifecycleOnly 'Mock MCP is disconnected; inference lookup is blocked.'
        Assert-OpenScienceRuntimeBootSource $mockSourceOwner -LifecycleOnly:$LifecycleOnly
        return $mockContext
    }
    function Invoke-OpenScienceHttp([string]$Uri, [string]$Method = 'GET', [hashtable]$Headers, [int]$TimeoutSeconds) {
        if ($httpScenario -in @('stopgate', 'stoprefusal') -and $Method -eq 'GET') {
            Assert-OpenScienceCondition ($Headers['x-openscience-directory'] -eq $RepoRoot) 'Stop status/project header changed.'
            if ($Uri -eq 'http://127.0.0.1:4098/session/status') {
                return [pscustomobject]@{ StatusCode = 200; Content = $(if ($mockHttpState.Aborted) { '{}' } else { '{"ses_stop123":{"type":"busy"}}' }) }
            }
            Assert-OpenScienceCondition ($Uri -eq 'http://127.0.0.1:4098/session/ses_stop123') 'Stop looked up a foreign session.'
            return [pscustomobject]@{ StatusCode = 200; Content = (@{ id = 'ses_stop123'; directory = $RepoRoot } | ConvertTo-Json -Compress) }
        }
        $expectedSession = $(if ($httpScenario -eq 'abort') { 'ses_exact123' } else { 'ses_stop123' })
        Assert-OpenScienceCondition ($Method -eq 'POST' -and $Uri -ceq "http://127.0.0.1:4098/session/$expectedSession/abort" -and
            $Headers['x-openscience-abort-source'] -eq 'runner_timeout') 'Cancellation did not preserve the exact session or official abort semantics.'
        $trace.Add("abort:$expectedSession"); $mockHttpState.Aborted = $true
        return [pscustomobject]@{ StatusCode = 200; Content = $(if ($httpScenario -eq 'stoprefusal') { 'false' } else { 'true' }) }
    }
    function Get-OpenScienceProcessIdentity([int]$ProcessId) { if ($ProcessId -eq 7001) { return $mockLauncher }; if ($ProcessId -eq 7002) { return $mockNative }; throw 'Foreign PID requested.' }
    function Get-OpenScienceDescendants([int]$RootPid) { Assert-OpenScienceCondition ($RootPid -eq 7001) 'Foreign launcher requested.'; return $mockNative }
    function Stop-Process([int]$Id) { Assert-OpenScienceCondition ($Id -in @(7001, 7002) -and $trace[0] -eq 'abort:ses_exact123') 'Owned stop preceded official cancellation or touched a foreign PID.'; $trace.Add("stop:$Id") }
    Initialize-OpenScienceToolGuard $mockContext
    $initialGuard = Read-OpenScienceJson $mockContext.GuardPath; Assert-OpenScienceToolGuard $mockContext $initialGuard
    $initialHash = Get-OpenScienceHash $mockContext.GuardPath
    $rejected = $false; try { Initialize-OpenScienceToolGuard $mockContext } catch { $rejected = $true }
    Assert-OpenScienceCondition ($rejected -and -not $initialGuard.stopping -and -not $initialGuard.no_tools -and
        $null -eq $initialGuard.required -and (Get-OpenScienceHash $mockContext.GuardPath) -ceq $initialHash) 'Guard initialization overwrote an existing owned guard.'
    $checks.Add('owned_guard_initialization_is_create_once')
    Set-OpenScienceExpectedTools $mockContext -NoTools
    Reset-OpenScienceToolGuardForFreshStartup $mockContext
    $freshGuard = Read-OpenScienceJson $mockContext.GuardPath; Assert-OpenScienceToolGuard $mockContext $freshGuard
    Assert-OpenScienceCondition (-not $freshGuard.stopping -and -not $freshGuard.no_tools -and $null -eq $freshGuard.required) 'A fresh unused profile did not reset its stage flags.'
    $checks.Add('fresh_unused_startup_resets_stage_flags')
    Set-OpenScienceExpectedTools $mockContext -RequiredTool 'caelab_experiment_inspect'
    $beforePauseHash = Get-OpenScienceHash $mockContext.GuardPath
    $pauseDirectory = Join-Path $root 'guard-lock-pause'; New-Item -ItemType Directory -Path $pauseDirectory -ErrorAction Stop | Out-Null
    $heldGuardLock = Open-OpenScienceToolGuardLock $mockContext
    try {
        $rejected = $false; try { Set-OpenScienceExpectedTools $mockContext -RequiredTool 'caelab_experiment_run' } catch { $rejected = $true }
        Assert-OpenScienceCondition ($rejected -and (Get-OpenScienceHash $mockContext.GuardPath) -ceq $beforePauseHash) 'A held mutation lock allowed a schema update.'
        $checks.Add('held_guard_mutation_lock_refuses_schema_update')
        $rejected = $false; try { Pause-OpenScienceModelForwards $mockContext $pauseDirectory } catch { $rejected = $true }
        Assert-OpenScienceCondition ($rejected -and (Get-OpenScienceHash $mockContext.GuardPath) -ceq $beforePauseHash -and
            -not (Test-Path -LiteralPath (Join-Path $pauseDirectory 'guard-before-stop.json'))) 'A held mutation lock allowed a stop snapshot or guard update.'
        $checks.Add('held_guard_mutation_lock_refuses_stop_pause')
    } finally { $heldGuardLock.Dispose() }
    Pause-OpenScienceModelForwards $mockContext $pauseDirectory
    $beforePause = Read-OpenScienceJson (Join-Path $pauseDirectory 'guard-before-stop.json')
    $pausedGuard = Read-OpenScienceJson $mockContext.GuardPath; Assert-OpenScienceToolGuard $mockContext $pausedGuard
    Assert-OpenScienceCondition (-not $beforePause.stopping -and $beforePause.required -ceq 'caelab_experiment_inspect' -and
        $pausedGuard.stopping -and $pausedGuard.required -ceq $beforePause.required -and
        (Get-OpenScienceHash (Join-Path $pauseDirectory 'guard-before-stop.json')) -ceq $beforePauseHash) 'Stop pause did not preserve the exact prior schema snapshot.'
    $checks.Add('stop_pause_snapshots_schema_and_sets_stopping_under_lock')
    $pausedHash = Get-OpenScienceHash $mockContext.GuardPath
    foreach ($attempt in @(@{}, @{ RequiredTool = 'caelab_experiment_run' }, @{ NoTools = $true })) {
        $rejected = $false; try { Set-OpenScienceExpectedTools -Context $mockContext @attempt } catch { $rejected = $true }
        Assert-OpenScienceCondition ($rejected -and (Get-OpenScienceHash $mockContext.GuardPath) -ceq $pausedHash -and
            (Read-OpenScienceJson $mockContext.GuardPath).stopping) 'A schema update/default restoration reopened a stopping profile.'
    }
    $checks.Add('stopping_refuses_schema_updates_and_default_restore_without_mutation')
    $rejected = $false; try { Reset-OpenScienceToolGuardForFreshStartup $mockContext } catch { $rejected = $true }
    Assert-OpenScienceCondition ($rejected -and (Get-OpenScienceHash $mockContext.GuardPath) -ceq $pausedHash) 'Fresh startup reset reopened a stopped guard.'
    $checks.Add('fresh_startup_refuses_stopping_guard')
    Write-OpenScienceJson $mockContext.OwnerPath @{ state = 'stopped'; run_name = $RunName; repo_root = $RepoRoot } -CreateNew
    $rejected = $false; try { Reset-OpenScienceToolGuardForFreshStartup $mockContext } catch { $rejected = $true }
    Assert-OpenScienceCondition ($rejected -and (Get-OpenScienceHash $mockContext.GuardPath) -ceq $pausedHash) 'Fresh startup reset ignored historical ownership.'
    $checks.Add('fresh_startup_refuses_historical_owner')
    $historyDirectory = Join-Path $root 'server-runs'; New-Item -ItemType Directory -Path $historyDirectory -ErrorAction Stop | Out-Null
    Write-OpenScienceJson (Join-Path $historyDirectory 'prior-mock-launch.json') @{ provider_calls = 0 } -CreateNew
    $historyContext = $mockContext.PSObject.Copy(); $historyContext.OwnerPath = Join-Path $root 'absent-owner.json'
    $rejected = $false; try { Reset-OpenScienceToolGuardForFreshStartup $historyContext } catch { $rejected = $true }
    Assert-OpenScienceCondition ($rejected -and (Get-OpenScienceHash $mockContext.GuardPath) -ceq $pausedHash) 'Fresh startup reset ignored prior launch artifacts.'
    $checks.Add('fresh_startup_refuses_prior_launch_evidence')
    $helperInfo = New-OpenScienceLocalProcessInfo $mockContext @('--version', $prompt)
    Assert-OpenScienceCondition ($helperInfo.ArgumentList[0] -ceq $mockContext.LauncherPath -and $helperInfo.ArgumentList[2] -ceq $prompt -and
        -not $helperInfo.UseShellExecute -and $helperInfo.CreateNoWindow -and $helperInfo.Environment['OPENSCIENCE_EXPERIMENTAL_OUTPUT_TOKEN_MAX'] -eq '4096') 'Actual process helper changed multiline arguments, flags or safe task output setting.'
    $unexpectedEnv = @(Get-OpenScienceRemovedEnvironment @($helperInfo.Environment.Keys) | Where-Object { $_ -notin @($mockContext.Environment.Keys) })
    Assert-OpenScienceCondition ($unexpectedEnv.Count -eq 0) 'Actual process helper retained inherited credential/config keys.'
    $checks.Add('actual_process_helper_multiline_and_environment')
    $connections = @([pscustomobject]@{ LocalAddress = '127.0.0.1'; LocalPort = 4098; OwningProcess = 7002 })
    Assert-OpenScienceReadiness $mockContext 'http://127.0.0.1:4098' 7002 $mockNative $connections @{ healthy = $true; version = '2.0.146'; runId = 'owned' } 'owned'
    $rejected = $false; try { Assert-OpenScienceReadiness $mockContext 'http://127.0.0.1:4098' 8002 $mockNative $connections $null $null } catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'Foreign readiness PID was accepted.'; $checks.Add('foreign_ready_pid_rejected')
    $foreignSocket = @([pscustomobject]@{ LocalAddress = '127.0.0.1'; LocalPort = 4098; OwningProcess = 8002 })
    $rejected = $false; try { Assert-OpenScienceReadiness $mockContext 'http://127.0.0.1:4098' 7002 $mockNative $foreignSocket $null $null } catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'Foreign socket PID was accepted.'; $checks.Add('foreign_socket_pid_rejected')
    $publicSocket = @($connections) + @([pscustomobject]@{ LocalAddress = '0.0.0.0'; LocalPort = 4999; OwningProcess = 7002 })
    $rejected = $false; try { Assert-OpenScienceReadiness $mockContext 'http://127.0.0.1:4098' 7002 $mockNative $publicSocket $null $null } catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'Public owned socket was accepted.'; $checks.Add('public_socket_rejected')
    $rejected = $false; try { Assert-OpenScienceReadiness $mockContext 'http://127.0.0.1:4098' 7002 $mockNative $connections @{ healthy = $true; version = '2.0.146'; runId = 'foreign' } 'owned' } catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'Foreign health run ID was accepted.'; $checks.Add('foreign_health_run_id_rejected')
    $rejected = $false; try { Assert-OpenScienceProcessIdentity $mockLauncher ([pscustomobject]@{ Pid = 7001; CreationUtc = 'reused-pid'; ExecutablePath = 'mock-node.exe'; CommandLine = $mockLauncher.CommandLine }) } catch { $rejected = $true }
    Assert-OpenScienceCondition $rejected 'PID reuse was accepted.'; $checks.Add('pid_reuse_rejected')
    $roundTripIdentity = [pscustomobject]@{ Pid = 7001; ParentPid = 7000; CreationUtc = '2026-09-30T10:20:30.1234567Z'
        ExecutablePath = 'mock-node.exe'; CommandLine = "mock-node.exe mock-launcher run -- `"first`nsecond`"" }
    $roundTripPath = Join-Path $root 'process-identity-roundtrip.json'
    Write-OpenScienceJson $roundTripPath $roundTripIdentity -CreateNew
    $roundTripActual = Read-OpenScienceJson $roundTripPath
    Assert-OpenScienceCondition ($roundTripActual.CreationUtc -is [string] -and $roundTripActual.CreationUtc -ceq $roundTripIdentity.CreationUtc -and
        $roundTripActual.CommandLine -ceq $roundTripIdentity.CommandLine) 'Runtime JSON read changed exact UTC creation or multiline command text.'
    Assert-OpenScienceProcessIdentity $roundTripIdentity $roundTripActual
    $checks.Add('json_identity_roundtrip_preserves_exact_utc_string')
    $fallbackDocument = [Text.Json.JsonDocument]::Parse((Get-Content -LiteralPath $roundTripPath -Raw))
    try { $fallbackIdentity = ConvertFrom-OpenScienceJsonElement $fallbackDocument.RootElement } finally { $fallbackDocument.Dispose() }
    Assert-OpenScienceCondition ($fallbackIdentity.CreationUtc -is [string] -and $fallbackIdentity.CreationUtc -ceq $roundTripIdentity.CreationUtc) 'Compatible JSON parser changed a UTC string.'
    Assert-OpenScienceProcessIdentity $roundTripIdentity $fallbackIdentity
    $fallbackDocument = [Text.Json.JsonDocument]::Parse('{"dates":["2026-09-30T19:20:30.1234567+09:00"],"empty":[],"null":null,"boolean":false,"integer":7001,"float":0.6}')
    try { $fallbackTypes = ConvertFrom-OpenScienceJsonElement $fallbackDocument.RootElement } finally { $fallbackDocument.Dispose() }
    Assert-OpenScienceCondition ($fallbackTypes.dates.Count -eq 1 -and $fallbackTypes.dates[0] -is [string] -and
        $fallbackTypes.dates[0] -ceq '2026-09-30T19:20:30.1234567+09:00' -and $fallbackTypes.empty -is [array] -and $fallbackTypes.empty.Count -eq 0 -and
        $null -eq $fallbackTypes['null'] -and $fallbackTypes.boolean -ceq $false -and $fallbackTypes.integer -eq 7001 -and
        $fallbackTypes.float -eq 0.6) 'Compatible JSON parser changed arrays, nulls, scalars or date strings.'
    $checks.Add('compatible_json_parser_preserves_dates_arrays_and_scalars')
    $abort = Invoke-OpenScienceSessionAbort $mockContext 'ses_exact123'
    Assert-OpenScienceCondition ($abort.Confirmed -and $abort.StatusCode -eq 200 -and $abort.SessionId -ceq 'ses_exact123') 'Abort receipt lacks confirmation.'
    $stop = Stop-OpenScienceOwnedLauncher $mockContext $mockLauncher
    Assert-OpenScienceCondition (($trace -join ',') -ceq 'abort:ses_exact123,stop:7002,stop:7001' -and $stop.StoppedPids.Count -eq 2) 'Abort-before-owned-stop order changed.'
    $checks.Add('exact_session_abort_before_owned_stop_no_delete')
    $checks.Add('lifecycle_abort_with_disconnected_mcp')
    $checks.Add('lifecycle_abort_and_owned_stop_under_Core_HEAD_plugin_drift')
    $httpScenario = 'stopgate'; $mockHttpState.Aborted = $false
    $idleGate = Confirm-OpenScienceSessionsIdleForStop $mockContext
    Assert-OpenScienceCondition ($idleGate.state -eq 'IDLE_CONFIRMED' -and $idleGate.cancelled_sessions.Count -eq 1 -and
        $idleGate.cancelled_sessions[0].Confirmed -and $idleGate.cancelled_sessions[0].SessionId -ceq 'ses_stop123') 'Stop did not preserve confirmed active-session cancellation before idle.'
    $checks.Add('active_stop_aborts_exact_owned_session_and_waits_idle')
    $httpScenario = 'stoprefusal'; $mockHttpState.Aborted = $false; $stopsBefore = @($trace | Where-Object { $_.StartsWith('stop:') }).Count
    $rejected = $false; try { Confirm-OpenScienceSessionsIdleForStop $mockContext | Out-Null } catch { $rejected = $true }
    Assert-OpenScienceCondition ($rejected -and @($trace | Where-Object { $_.StartsWith('stop:') }).Count -eq $stopsBefore -and
        (Read-OpenScienceJson $mockContext.GuardPath).stopping) 'Unconfirmed stop cancellation terminated a process or reopened model forwards.'
    $checks.Add('unconfirmed_stop_abort_refuses_termination')
    $proxyPath = Join-Path $root 'mock-guard.mjs'; [IO.File]::WriteAllText($proxyPath, (Get-OpenScienceProxySource), [Text.UTF8Encoding]::new($false))
    $nodeName = $(if ($IsWindows) { 'node.exe' } else { 'node' }); $node = (Get-Command $nodeName -ErrorAction Stop).Source
    $git = (Get-Command $(if ($IsWindows) { 'git.exe' } else { 'git' }) -ErrorAction Stop).Source
    $nodeOutput = @(& $node $proxyPath --self-test (Join-Path $root 'proxy-mocks') $git)
    Assert-OpenScienceCondition ($LASTEXITCODE -eq 0) 'Embedded transparent schema-guard mock failed.'
    $proxyChecks = $nodeOutput[-1] | ConvertFrom-Json
    Assert-OpenScienceCondition ($proxyChecks.status -eq 'PASS' -and $proxyChecks.provider_calls -eq 0) 'Mock proxy did not confirm absence of provider calls.'
    foreach ($check in $proxyChecks.checks) { $checks.Add($check) }
    $record = [ordered]@{ status = 'PASS_MOCK_RUNTIME_CHECKS'; provider_calls = 0; backend_calls = 0; checks = @($checks); cancellation_trace = @($trace)
        source_sha256 = Get-OpenScienceHash $script:OpenScienceServerScriptPath; artifact_root = $root; completed_utc = [DateTime]::UtcNow.ToString('o') }
    Write-OpenScienceJson (Join-Path $root 'self-test.json') $record -CreateNew
    [pscustomobject]$record
}

. (Join-Path $PSScriptRoot 'openscience-chatgpt-functions.ps1')
. (Join-Path $PSScriptRoot 'openscience-native-provider.ps1')
if ($Library) { return }
$ErrorActionPreference = 'Stop'
if ($Mode -eq 'ServeInternal') { Invoke-OpenScienceServeInternal $ContextPath $LaunchToken; return }
if ($Mode -eq 'SelfTest') { Invoke-OpenScienceRuntimeSelfTest $RepoRoot $RunName; return }
if (-not $OwnerPath) {
    $OwnerPath = if ($Transport -ceq 'ChatGPT') { Join-Path $env:LOCALAPPDATA "AutonomousCAELab/profiles/$RunName-$ProfileTag-research/runtime-owner.json" }
        else { Join-Path ([IO.Path]::GetFullPath($RepoRoot)) "artifacts\$RunName\profiles\$ProfileTag\runtime-owner.json" }
}
switch ($Mode) {
    'Status' { Get-OpenScienceLocalRuntime -OwnerPath $OwnerPath }
    'Stop' { Stop-OpenScienceLocalServer -OwnerPath $OwnerPath }
    'Start' {
        $context = New-OpenScienceLocalContext -RepoRoot $RepoRoot -RunName $RunName -ProfileTag $ProfileTag -StoreRoot $StoreRoot -RuntimePrefix $RuntimePrefix `
            -ModelId $ModelId -Transport $Transport -AuthProfileRoot $AuthProfileRoot -WslDistro $WslDistro -WslPython $WslPython -AllowedTools $AllowedTools -OutputTokens $OutputTokens -Steps $Steps -ProviderTimeoutSeconds $ProviderTimeoutSeconds
        Start-OpenScienceLocalServer $context $Port $StartupTimeoutSeconds
    }
}
