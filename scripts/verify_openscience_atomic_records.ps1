# TEST_ONLY Windows file-I/O controls. No runtime/profile/authentication imports.
[CmdletBinding(DefaultParameterSetName='Main')]
param(
    [Parameter(ParameterSetName='Main')][string]$OutputRoot,
    [Parameter(Mandatory,ParameterSetName='Child')]
    [ValidateSet('hold-parser','hold-stream','writer','read-once','read-loop')][string]$ChildMode,
    [Parameter(Mandatory,ParameterSetName='Child')][string]$RequestPath
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'These controls require actual Windows file replacement semantics.' }
$taskAtomicSource = Join-Path $PSScriptRoot 'openscience-server-local.ps1'
$taskAtomicSourceSha = (Get-FileHash -LiteralPath $taskAtomicSource -Algorithm SHA256).Hash.ToLowerInvariant()
$tokens = $null; $errors = $null
$taskAtomicAst = [Management.Automation.Language.Parser]::ParseFile($taskAtomicSource, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'The actual runner source failed to parse.' }
foreach ($name in @('Assert-OpenScienceCondition','Write-OpenScienceJson',
        'ConvertFrom-OpenScienceJsonElement','Read-OpenScienceJson','Assert-OpenScienceContainedPath')) {
    $definitions = @($taskAtomicAst.FindAll({param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name
    }, $false))
    if ($definitions.Count -ne 1) { throw "The actual helper is ambiguous: $name" }
    . ([scriptblock]::Create($definitions[0].Extent.Text))
}

function Assert-AtomicTest([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "TEST_ONLY control failed: $Message" }
}
function Wait-AtomicMarker([string]$Path, $Process) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while (-not [IO.File]::Exists($Path) -and $watch.ElapsedMilliseconds -lt 10000) {
        if ($Process -and $Process.HasExited) { break }
        [Threading.Thread]::Sleep(10)
    }
    Assert-AtomicTest ([IO.File]::Exists($Path)) 'a child did not publish its ready marker'
}
function Write-AtomicTestMarker([string]$Path) {
    $stream = [IO.FileStream]::new($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $stream.WriteByte(1); $stream.Flush($true) } finally { $stream.Dispose() }
}

if ($ChildMode) {
    $request = Read-OpenScienceJson $RequestPath
    Assert-AtomicTest ($request.kind -ceq 'TEST_ONLY_ATOMIC_RECORD_IO' -and
        $request.source_sha256 -ceq $taskAtomicSourceSha) 'child source/request binding'
    $taskAtomicTestRoot = [IO.Path]::GetFullPath($request.root)
    Assert-AtomicTest ($taskAtomicTestRoot.StartsWith([IO.Path]::GetFullPath($env:TEMP), [StringComparison]::OrdinalIgnoreCase)) 'child TEMP root'
    foreach ($name in @('target','ready','release','result')) {
        Assert-OpenScienceContainedPath $request[$name] $taskAtomicTestRoot | Out-Null
    }
    $watch = [Diagnostics.Stopwatch]::StartNew(); $stream = $null; $value = $null
    $outcome = [ordered]@{ kind='TEST_ONLY_ATOMIC_RECORD_IO'; mode=$ChildMode; status='SUCCEEDED' }
    try {
        if ($ChildMode -ceq 'hold-parser') {
            # Pause the real converter while Read-OpenScienceJson still owns its
            # parsed document and open stream. Publication must work before release.
            $script:taskAtomicOriginalConverter = (Get-Command ConvertFrom-OpenScienceJsonElement).ScriptBlock
            $script:taskAtomicPaused = $false
            function ConvertFrom-OpenScienceJsonElement([Text.Json.JsonElement]$Element) {
                if (-not $script:taskAtomicPaused) {
                    $script:taskAtomicPaused = $true
                    Write-AtomicTestMarker $request.ready
                    $hold = [Diagnostics.Stopwatch]::StartNew()
                    while (-not [IO.File]::Exists($request.release) -and $hold.ElapsedMilliseconds -lt 10000) {
                        [Threading.Thread]::Sleep(10)
                    }
                    Assert-AtomicTest ([IO.File]::Exists($request.release)) 'held product reader release'
                }
                & $script:taskAtomicOriginalConverter $Element
            }
            $value = Read-OpenScienceJson $request.target
        } elseif ($ChildMode -ceq 'hold-stream') {
            $share = switch ($request.share) {
                'Read' { [IO.FileShare]::Read }
                'None' { [IO.FileShare]::None }
                default { throw 'Invalid TEST_ONLY share mode.' }
            }
            $stream = [IO.FileStream]::new($request.target, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
            Write-AtomicTestMarker $request.ready
            $hold = [Diagnostics.Stopwatch]::StartNew()
            while (-not [IO.File]::Exists($request.release) -and $hold.ElapsedMilliseconds -lt 10000) {
                [Threading.Thread]::Sleep(10)
            }
            Assert-AtomicTest ([IO.File]::Exists($request.release)) 'held legacy reader release'
            $document = [Text.Json.JsonDocument]::Parse($stream)
            try { $value = ConvertFrom-OpenScienceJsonElement $document.RootElement } finally { $document.Dispose() }
        } elseif ($ChildMode -ceq 'writer') {
            Write-AtomicTestMarker $request.ready
            $ioWatch = [Diagnostics.Stopwatch]::StartNew()
            for ($generation=1; $generation -le $request.iterations; $generation++) {
                Write-OpenScienceJson $request.target ([ordered]@{
                    generation=$generation; payload=([string]($generation % 2) * [int]$request.payload_size)
                })
            }
            $outcome.io_elapsed_ms = $ioWatch.ElapsedMilliseconds
        } elseif ($ChildMode -ceq 'read-once') {
            Write-AtomicTestMarker $request.ready
            $ioWatch = [Diagnostics.Stopwatch]::StartNew()
            try { $value = Read-OpenScienceJson $request.target }
            finally { $outcome.io_elapsed_ms = $ioWatch.ElapsedMilliseconds }
        } else {
            Write-AtomicTestMarker $request.ready
            $reads = 0
            while (-not [IO.File]::Exists($request.release) -and $watch.ElapsedMilliseconds -lt 15000) {
                $value = Read-OpenScienceJson $request.target
                Assert-AtomicTest ($value.generation -ge 0 -and $value.generation -le $request.iterations -and
                    $value.payload -ceq ([string]($value.generation % 2) * [int]$request.payload_size)) 'a complete single JSON generation'
                $reads++
            }
            Assert-AtomicTest ([IO.File]::Exists($request.release)) 'reader loop release'
            $outcome.reads = $reads
        }
        if ($value -and $ChildMode -ceq 'read-loop') {
            $outcome.last_generation = $value.generation
            $outcome.last_payload_sha256 = [Convert]::ToHexString(
                [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($value.payload))).ToLowerInvariant()
        } elseif ($value) { $outcome.value = $value }
    } catch {
        $failure = $_.Exception.GetBaseException()
        $outcome.status = 'REFUSED'; $outcome.error_type = $failure.GetType().FullName
        $outcome.win32_code = $failure.HResult -band 0xffff
        $outcome.error = $failure.Message
        if ($ioWatch) { $outcome.io_elapsed_ms = $ioWatch.ElapsedMilliseconds }
    } finally {
        if ($stream) { $stream.Dispose() }
        $outcome.elapsed_ms = $watch.ElapsedMilliseconds
        Write-OpenScienceJson $request.result $outcome -CreateNew
    }
    exit 0
}

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $env:TEMP ('caelab-atomic-record-controls-' +
        [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '-' + [Guid]::NewGuid().ToString('N'))
}
$taskAtomicTestRoot = [IO.Path]::GetFullPath($OutputRoot)
$tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')
Assert-AtomicTest ($taskAtomicTestRoot.StartsWith($tempRoot+'\', [StringComparison]::OrdinalIgnoreCase) -and
    -not (Test-Path -LiteralPath $taskAtomicTestRoot)) 'a fresh directory beneath TEMP'
[IO.Directory]::CreateDirectory($taskAtomicTestRoot) | Out-Null
$taskAtomicVerifierSha = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskAtomicChecks = [Collections.Generic.List[string]]::new()
$taskAtomicChildren = [Collections.Generic.List[object]]::new()
$taskAtomicRequests = [Collections.Generic.List[object]]::new()
$taskAtomicResults = [Collections.Generic.List[object]]::new()
$taskAtomicStatus = 'FAIL'; $taskAtomicError = $null

function New-AtomicCase([string]$Name) {
    $folder = Join-Path $taskAtomicTestRoot $Name
    [IO.Directory]::CreateDirectory($folder) | Out-Null
    $target = Join-Path $folder 'record.json'
    Write-OpenScienceJson $target @{generation=0;payload=''} -CreateNew
    return $target
}
function Start-AtomicChild([string]$Mode, [string]$Target, [string]$Name, [string]$Share='',
        [int]$Iterations=1, [int]$PayloadSize=0) {
    $folder = Split-Path -Parent $Target
    $request = [ordered]@{
        kind='TEST_ONLY_ATOMIC_RECORD_IO'; root=$taskAtomicTestRoot; source_sha256=$taskAtomicSourceSha
        target=$Target; ready=(Join-Path $folder ($Name+'.ready')); release=(Join-Path $folder ($Name+'.release'))
        result=(Join-Path $folder ($Name+'.result.json')); share=$Share
        iterations=$Iterations; payload_size=$PayloadSize
    }
    $path = Join-Path $folder ($Name+'.request.json')
    Write-OpenScienceJson $path $request -CreateNew
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = (Get-Process -Id $PID).Path
    $info.UseShellExecute = $false; $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true; $info.RedirectStandardError = $true
    $info.Environment.Clear()
    foreach ($environmentName in @('SystemRoot','WINDIR')) { $info.Environment[$environmentName] = [Environment]::GetEnvironmentVariable($environmentName) }
    $info.Environment['TEMP'] = $taskAtomicTestRoot; $info.Environment['TMP'] = $taskAtomicTestRoot
    foreach ($argument in @('-NoLogo','-NoProfile','-File',$PSCommandPath,'-ChildMode',$Mode,'-RequestPath',$path)) {
        $info.ArgumentList.Add($argument)
    }
    $process = [Diagnostics.Process]::Start($info)
    $child = [pscustomobject]@{ process=$process; request=$request; name=$Name }
    $taskAtomicChildren.Add($child); $taskAtomicRequests.Add($request)
    Wait-AtomicMarker $request.ready $process
    return $child
}
function Complete-AtomicChild($Child) {
    Assert-AtomicTest ($Child.process.WaitForExit(12000)) 'bounded child exit without termination'
    $stdout = $Child.process.StandardOutput.ReadToEnd(); $stderr = $Child.process.StandardError.ReadToEnd()
    [IO.File]::WriteAllText((Join-Path (Split-Path -Parent $Child.request.target) ($Child.name+'.stdout.txt')), $stdout)
    [IO.File]::WriteAllText((Join-Path (Split-Path -Parent $Child.request.target) ($Child.name+'.stderr.txt')), $stderr)
    Assert-AtomicTest ($Child.process.ExitCode -eq 0) ('child exit: '+$stderr)
    $result = Read-OpenScienceJson $Child.request.result
    $taskAtomicResults.Add($result)
    return $result
}
function Release-AtomicChild($Child) {
    if (-not [IO.File]::Exists($Child.request.release)) { Write-AtomicTestMarker $Child.request.release }
}
function Assert-AtomicRefusal([scriptblock]$Action, [string]$Name) {
    $refused = $false
    try { & $Action | Out-Null } catch { $refused = $true }
    Assert-AtomicTest $refused $Name
    $taskAtomicChecks.Add($Name)
}

try {
    $sourceFolder = Join-Path $taskAtomicTestRoot 'source'
    [IO.Directory]::CreateDirectory($sourceFolder) | Out-Null
    [IO.File]::Copy($taskAtomicSource, (Join-Path $sourceFolder 'openscience-server-local.ps1'))
    [IO.File]::Copy($PSCommandPath, (Join-Path $sourceFolder 'verify_openscience_atomic_records.ps1'))
    $target = New-AtomicCase 'immutable'
    $value = [Collections.Specialized.OrderedDictionary]::new([StringComparer]::Ordinal)
    $value.Add('utc','2026-10-07T01:02:03.1234567Z'); $value.Add('unicode','TEST_ONLY 연구')
    $value.Add('exact',1); $value.Add('Exact',2); $value.Add('items',@(1,$false,$null,@{nested='text'}))
    Write-OpenScienceJson $target $value
    $read = Read-OpenScienceJson $target
    Assert-AtomicTest ($read.utc -is [string] -and $read.utc -ceq $value.utc -and $read.unicode -ceq $value.unicode -and
        $read['exact'] -eq 1 -and $read['Exact'] -eq 2 -and $read.items.Count -eq 4 -and $read.items[1] -ceq $false -and
        $null -eq $read.items[2]) 'exact JSON string/key/value preservation'
    $taskAtomicChecks.Add('exact_json_strings_case_keys_unicode_arrays_preserved')
    $sha = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    Assert-AtomicRefusal {Write-OpenScienceJson $target @{changed=$true} -CreateNew} 'create_new_existing_record_refused'
    Assert-AtomicTest ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ceq $sha) 'CreateNew preserved original bytes'
    $taskAtomicChecks.Add('create_new_original_bytes_unchanged')
    foreach ($case in @(@('duplicate_root','{"x":1,"x":2}'), @('duplicate_nested','{"a":[{"x":1,"x":2}]}'),
            @('malformed','{"partial":'), @('missing',''))) {
        $path = Join-Path (Split-Path -Parent $target) ($case[0]+'.json')
        if ($case[0] -ne 'missing') { [IO.File]::WriteAllText($path, $case[1]) }
        $refusalWatch = [Diagnostics.Stopwatch]::StartNew()
        Assert-AtomicRefusal {Read-OpenScienceJson $path} ($case[0]+'_json_refused')
        if ($case[0] -ceq 'malformed') {
            Assert-AtomicTest ($refusalWatch.ElapsedMilliseconds -lt 1500) 'malformed JSON is not an I/O retry'
            $taskAtomicChecks.Add('malformed_json_parse_failure_is_immediate')
        } elseif ($case[0] -ceq 'missing') {
            Assert-AtomicTest ($refusalWatch.ElapsedMilliseconds -ge 1900 -and $refusalWatch.ElapsedMilliseconds -lt 4000) 'persistent name missing remains a bounded refusal'
            $taskAtomicChecks.Add('persistent_missing_open_failure_remains_bounded')
        }
    }
    $original = [IO.File]::ReadAllBytes($target); $attributes = [IO.File]::GetAttributes($target)
    try {
        [IO.File]::SetAttributes($target, ($attributes -bor [IO.FileAttributes]::ReadOnly))
        $watch = [Diagnostics.Stopwatch]::StartNew(); $denied = $null
        try { Write-OpenScienceJson $target @{changed=$true} } catch { $denied=$_.Exception.GetBaseException() }
        Assert-AtomicTest ($denied -is [UnauthorizedAccessException] -and ($denied.HResult -band 0xffff) -eq 5 -and
            $watch.ElapsedMilliseconds -lt 1500) 'persistent access denial is not retried as sharing'
        Assert-AtomicTest ([Convert]::ToBase64String([IO.File]::ReadAllBytes($target)) -ceq [Convert]::ToBase64String($original)) 'denial retained original'
        $taskAtomicChecks.Add('persistent_access_denied_raised_without_rewrite_or_sharing_retry')
    } finally { [IO.File]::SetAttributes($target, $attributes) }
    $owned = Join-Path $taskAtomicTestRoot 'owned'; $external = Join-Path $taskAtomicTestRoot 'outside-owned'
    [IO.Directory]::CreateDirectory($owned) | Out-Null; [IO.Directory]::CreateDirectory($external) | Out-Null
    $outsideFile = Join-Path $external 'record.json'; Write-OpenScienceJson $outsideFile @{untouched=$true} -CreateNew
    $link = Join-Path $owned 'junction'
    New-Item -ItemType Junction -Path $link -Target $external -ErrorAction Stop | Out-Null
    try {
        Assert-AtomicRefusal {Assert-OpenScienceContainedPath (Join-Path $link 'record.json') $owned} 'existing_junction_guard_refuses_reader_and_writer_path'
        Assert-AtomicRefusal {Assert-OpenScienceContainedPath $outsideFile $owned} 'existing_ownership_containment_refuses_foreign_path'
        Assert-AtomicTest ((Read-OpenScienceJson $outsideFile).untouched -eq $true) 'outside bytes retained'
    } finally { [IO.Directory]::Delete($link) }

    $target = New-AtomicCase 'held-product-reader'
    $reader = Start-AtomicChild 'hold-parser' $target 'reader'
    $writer = Start-AtomicChild 'writer' $target 'writer'
    $published = Complete-AtomicChild $writer
    Assert-AtomicTest ($published.status -ceq 'SUCCEEDED' -and -not [IO.File]::Exists($reader.request.release)) 'publish while actual helper reader is still held'
    Assert-AtomicTest ((Read-OpenScienceJson $target).generation -eq 1) 'new generation visible'
    Release-AtomicChild $reader; $held = Complete-AtomicChild $reader
    Assert-AtomicTest ($held.status -ceq 'SUCCEEDED' -and $held.value.generation -eq 0) 'held helper reader saw intact old generation'
    $taskAtomicChecks.Add('real_process_actual_helper_reader_allows_atomic_replace_and_keeps_old_generation')

    foreach ($purpose in @('transient-writer','persistent-writer','transient-reader','persistent-reader')) {
        $target = New-AtomicCase $purpose
        $share = if ($purpose.EndsWith('writer')) { 'Read' } else { 'None' }
        $holder = Start-AtomicChild 'hold-stream' $target 'holder' $share
        $mode = if ($purpose.EndsWith('writer')) { 'writer' } else { 'read-once' }
        $actor = Start-AtomicChild $mode $target 'actor'
        if ($purpose.StartsWith('transient')) { [Threading.Thread]::Sleep(250); Release-AtomicChild $holder }
        $actual = Complete-AtomicChild $actor
        if ($purpose.StartsWith('transient')) {
            Assert-AtomicTest ($actual.status -ceq 'SUCCEEDED') 'sharing release permits bounded operation'
        } else {
            Assert-AtomicTest ($actual.status -ceq 'REFUSED' -and $actual.win32_code -eq 32 -and
                $actual.io_elapsed_ms -ge 1900 -and $actual.io_elapsed_ms -lt 4000) 'persistent sharing refusal is bounded'
        }
        Release-AtomicChild $holder; $closed = Complete-AtomicChild $holder
        Assert-AtomicTest ($closed.status -ceq 'SUCCEEDED') 'holder closes naturally'
        if ($purpose.StartsWith('persistent')) {
            Assert-AtomicTest ((Read-OpenScienceJson $target).generation -eq 0) 'refusal retained the old generation'
        }
        $taskAtomicChecks.Add('real_process_'+$purpose+'_bounded_sharing_control')
    }

    $target = New-AtomicCase 'concurrent-generations'
    Write-OpenScienceJson $target @{generation=0;payload=('0'*131072)}
    $reader = Start-AtomicChild 'read-loop' $target 'reader' '' 24 131072
    $writer = Start-AtomicChild 'writer' $target 'writer' '' 24 131072
    $published = Complete-AtomicChild $writer
    Release-AtomicChild $reader; $observed = Complete-AtomicChild $reader
    Assert-AtomicTest ($published.status -ceq 'SUCCEEDED' -and $observed.status -ceq 'SUCCEEDED' -and
        $observed.reads -ge 2 -and (Read-OpenScienceJson $target).generation -eq 24) 'concurrent product reader/writer preserves every complete generation'
    $taskAtomicChecks.Add('real_process_24_atomic_publications_no_partial_or_mixed_json')
    Assert-AtomicTest (@(Get-ChildItem -LiteralPath $taskAtomicTestRoot -Filter '*.tmp' -File -Recurse).Count -eq 0) 'temporary publications cleaned'
    $taskAtomicChecks.Add('no_temporary_publication_files_retained')
    Assert-AtomicTest ((Get-FileHash -LiteralPath $taskAtomicSource -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $taskAtomicSourceSha -and
        (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $taskAtomicVerifierSha) 'actual source frozen across controls'
    $taskAtomicChecks.Add('actual_helper_and_verifier_source_unchanged_during_controls')
    $taskAtomicStatus = 'PASS_WINDOWS_ATOMIC_RECORD_IO'
} catch {
    $taskAtomicError = $_.Exception.Message
} finally {
    foreach ($child in $taskAtomicChildren) {
        Release-AtomicChild $child
        $exited = $child.process.WaitForExit(12000)
        if (-not $exited -or ($exited -and $child.process.ExitCode -ne 0)) {
            $taskAtomicStatus = 'FAIL'; $taskAtomicError = 'A TEST_ONLY child did not close normally.'
        }
        $child.process.Dispose()
    }
    $receipt = [ordered]@{
        status=$taskAtomicStatus; kind='TEST_ONLY_REAL_WINDOWS_ATOMIC_RECORD_CONTROLS'; output_root=$taskAtomicTestRoot
        checks=$taskAtomicChecks.ToArray(); check_count=$taskAtomicChecks.Count; child_results=$taskAtomicResults.ToArray()
        source_sha256=$taskAtomicSourceSha; verifier_sha256=$taskAtomicVerifierSha; powershell=[string]$PSVersionTable.PSVersion
        provider_calls=0; native_calls=0; official_profile_mutations=0; process_termination_calls=0
        completed_utc=[DateTime]::UtcNow.ToString('o'); error=$taskAtomicError
    }
    $receiptPath = Join-Path $taskAtomicTestRoot 'receipt.json'
    Write-OpenScienceJson $receiptPath $receipt -CreateNew
    $receipt | ConvertTo-Json -Depth 10
}
if ($taskAtomicStatus -cne 'PASS_WINDOWS_ATOMIC_RECORD_IO') { exit 1 }
