# Official managed-project identity is distinct from the external CAE source.
# Loaded by the existing controller; no independent server/model entrypoint.
function ConvertTo-OpenScienceProjectBinding {
    param([Parameter(Mandatory)][Collections.IDictionary]$Binding,
        [Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)][string]$DataRoot)
    $keys = @('schema','kind','project_id','project_directory','source_directory','grant_id','working_root','access')
    Assert-OpenScienceCondition ($Binding.Count -eq $keys.Count -and @($keys | Where-Object { -not $Binding.Contains($_) }).Count -eq 0) 'Managed project binding has an unknown shape.'
    Assert-OpenScienceCondition ($Binding.schema -eq 1 -and $Binding.kind -ceq 'autonomous-cae-lab.openscience-project-binding' -and
        $Binding.project_id -cmatch '^prj_[A-Za-z0-9]+$' -and $Binding.grant_id -cmatch '^fsg_[A-Za-z0-9]+$' -and
        $Binding.access -ceq 'write') 'Managed project identity/grant is invalid.'
    foreach ($key in @('project_directory','source_directory','working_root')) {
        Assert-OpenScienceCondition ($Binding[$key] -is [string] -and [IO.Path]::IsPathRooted($Binding[$key]) -and
            [IO.Path]::GetFullPath($Binding[$key]) -ceq $Binding[$key]) 'Managed project paths must be exact absolute paths.'
    }
    Assert-OpenScienceContainedPath $Binding.project_directory (Join-Path $DataRoot 'projects') | Out-Null
    Assert-OpenScienceCondition ($Binding.source_directory -ceq [IO.Path]::GetFullPath($RepoRoot) -and
        $Binding.working_root -ceq $Binding.source_directory -and $Binding.project_directory -cne $Binding.source_directory) 'Managed working root must be the exact external CAE source.'
    $result = [ordered]@{}
    foreach ($key in $keys) { $result[$key] = $Binding[$key] }
    return $result
}

function Get-OpenScienceProjectDirectory($Context) {
    if ($Context.ProjectBinding) { return $Context.ProjectBinding.project_directory }
    return $Context.RepoRoot
}

function Get-OpenScienceProjectHeaders($Context) {
    if ($Context.ProjectBinding) {
        return @{'x-openscience-project' = $Context.ProjectBinding.project_id;
            'x-openscience-directory' = $Context.ProjectBinding.project_directory}
    }
    return @{'x-openscience-directory' = $Context.RepoRoot}
}

function Assert-OpenScienceOwnedSessionMetadata($Context, $Session, [string]$SessionId) {
    Assert-OpenScienceCondition ($Session.id -ceq $SessionId -and
        [IO.Path]::GetFullPath($Session.directory) -ceq (Get-OpenScienceProjectDirectory $Context)) 'Session is not in the exact owned project directory.'
    if ($Context.ProjectBinding) {
        Assert-OpenScienceCondition ($Session.projectID -ceq $Context.ProjectBinding.project_id) 'Session is not in the immutable managed project.'
    }
}

function Get-OpenScienceProjectWorkspaceUrl($Context, [string]$RuntimeUrl) {
    if ($Context.ProjectBinding) { return "$RuntimeUrl/$($Context.ProjectBinding.project_id)/session" }
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Context.RepoRoot)).TrimEnd('=').Replace('+','-').Replace('/','_')
    return "$RuntimeUrl/$encoded/session"
}

function Assert-OpenScienceManagedFilesystem($Binding, $Filesystem, [string]$SessionId) {
    Assert-OpenScienceCondition ($Filesystem.version -eq 1 -and $Filesystem.projectID -ceq $Binding.project_id -and
        [IO.Path]::GetFullPath($Filesystem.directory) -ceq $Binding.project_directory -and
        [IO.Path]::GetFullPath($Filesystem.toolDirectory) -ceq $Binding.source_directory -and
        $Filesystem.workingRoot -is [string] -and [IO.Path]::GetFullPath($Filesystem.workingRoot) -ceq $Binding.working_root) 'Managed filesystem identity or effective source root changed.'
    if ($SessionId) { Assert-OpenScienceCondition ($Filesystem.sessionID -ceq $SessionId) 'Managed filesystem session changed.' }
    $grant = @($Filesystem.grants | Where-Object { $_.id -ceq $Binding.grant_id })
    Assert-OpenScienceCondition ($grant.Count -eq 1 -and $grant[0].access -ceq 'write' -and $grant[0].scope -ceq 'project' -and
        [IO.Path]::GetFullPath($grant[0].path) -ceq $Binding.source_directory -and $null -eq $grant[0].time.revoked) 'The exact source write grant is absent, downgraded or revoked.'
}

function Assert-OpenScienceSessionWorkspace($Context, $Filesystem, [string]$SessionId) {
    if ($Context.ProjectBinding) {
        Assert-OpenScienceCondition ($SessionId -cmatch '^ses_[A-Za-z0-9]+$') 'Managed workspace needs the exact requested session ID.'
        Assert-OpenScienceCondition ($Filesystem.workspace.mode -cin @('legacy','isolated')) 'Managed session workspace mode is unknown.'
        Assert-OpenScienceManagedFilesystem $Context.ProjectBinding $Filesystem $SessionId
    } else {
        Assert-OpenScienceCondition ($Filesystem.workspace.mode -ceq 'legacy') 'Project workspace was not honored; no inference is allowed.'
    }
}

function Assert-OpenScienceManagedWorkspace($Context, [string]$RuntimeUrl) {
    $headers = Get-OpenScienceProjectHeaders $Context
    $projectResponse = Invoke-OpenScienceHttp "$RuntimeUrl/project/current" -Headers $headers -TimeoutSeconds 15
    Assert-OpenScienceCondition ($projectResponse.StatusCode -eq 200) 'Managed project metadata is unavailable; inference refused.'
    $project = $projectResponse.Content | ConvertFrom-Json -AsHashtable -ErrorAction Stop
    Assert-OpenScienceCondition ($project.id -ceq $Context.ProjectBinding.project_id -and
        [IO.Path]::GetFullPath($project.worktree) -ceq $Context.ProjectBinding.project_directory) 'Managed project ownership changed.'
    $fsResponse = Invoke-OpenScienceHttp "$RuntimeUrl/project/current/filesystem" -Headers $headers -TimeoutSeconds 15
    Assert-OpenScienceCondition ($fsResponse.StatusCode -eq 200) 'Managed project filesystem is unavailable; inference refused.'
    Assert-OpenScienceManagedFilesystem $Context.ProjectBinding ($fsResponse.Content | ConvertFrom-Json -AsHashtable -ErrorAction Stop)
}

function New-OpenScienceManagedProjectBinding {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$ExistingContext, [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][Guid]$OperationId, [Parameter(Mandatory)][string]$LogDirectory)
    $current = Get-OpenScienceLocalRuntime -OwnerPath $ExistingContext.OwnerPath -LifecycleOnly
    Assert-OpenScienceCondition ($current.Transport -ceq 'ChatGPT' -and $current.RepoRoot -ceq $ExistingContext.RepoRoot -and
        (Read-OpenScienceJson $current.GuardPath).stopping) 'Pause the exact owned native runtime before creating managed project metadata.'
    Assert-OpenScienceContainedPath $LogDirectory $current.ArtifactRoot | Out-Null
    Assert-OpenScienceCondition (-not (Test-Path -LiteralPath $LogDirectory)) 'Project binding evidence exists; preserve it and use a new log path.'
    New-Item -ItemType Directory -Path $LogDirectory -ErrorAction Stop | Out-Null
    $request = [ordered]@{name=$Name;operation_id=$OperationId.ToString();sources=@(@{path=$current.RepoRoot;access='write'})}
    Write-OpenScienceJson (Join-Path $LogDirectory 'create-request.json') $request -CreateNew
    # Supported public metadata endpoints only; this function never invokes a
    # session/model/tool, copies the source repository, or changes auth bytes.
    $projectResponse = Invoke-WebRequest -Uri "$($current.RuntimeURL)/global/project" -Method POST -ContentType 'application/json' `
        -Body ($request | ConvertTo-Json -Depth 8 -Compress) -TimeoutSec 30 -MaximumRedirection 0 -SkipHttpErrorCheck -ErrorAction Stop
    Write-OpenScienceJson (Join-Path $LogDirectory 'create-response.json') @{status_code=$projectResponse.StatusCode;body=$projectResponse.Content} -CreateNew
    Assert-OpenScienceCondition ($projectResponse.StatusCode -in @(200,201)) 'Official project creation failed; retained evidence is not replaced.'
    $project = $projectResponse.Content | ConvertFrom-Json -AsHashtable -ErrorAction Stop
    Assert-OpenScienceCondition ($project.id -cmatch '^prj_[A-Za-z0-9]+$' -and $project.worktree -is [string] -and
        [IO.Path]::IsPathRooted($project.worktree)) 'Official create response has no exact managed identity.'
    $projectDirectory = [IO.Path]::GetFullPath($project.worktree)
    Assert-OpenScienceContainedPath $projectDirectory (Join-Path $current.Environment.OPENSCIENCE_DATA_DIR 'projects') | Out-Null
    $headers = @{'x-openscience-project'=$project.id;'x-openscience-directory'=$projectDirectory}
    $rootResponse = Invoke-WebRequest -Uri "$($current.RuntimeURL)/project/current/working-root" -Method PUT -Headers $headers -ContentType 'application/json' `
        -Body (@{workingRoot=$current.RepoRoot} | ConvertTo-Json -Compress) -TimeoutSec 20 -MaximumRedirection 0 -SkipHttpErrorCheck -ErrorAction Stop
    Write-OpenScienceJson (Join-Path $LogDirectory 'working-root-response.json') @{status_code=$rootResponse.StatusCode;body=$rootResponse.Content} -CreateNew
    Assert-OpenScienceCondition ($rootResponse.StatusCode -eq 200) 'Official working-root selection failed; no inference is allowed.'
    $fsResponse = Invoke-OpenScienceHttp "$($current.RuntimeURL)/project/current/filesystem" -Headers $headers -TimeoutSeconds 20
    Write-OpenScienceJson (Join-Path $LogDirectory 'filesystem-response.json') @{status_code=$fsResponse.StatusCode;body=$fsResponse.Content} -CreateNew
    Assert-OpenScienceCondition ($fsResponse.StatusCode -eq 200) 'Official managed filesystem snapshot failed.'
    $fs = $fsResponse.Content | ConvertFrom-Json -AsHashtable -ErrorAction Stop
    $grants = @($fs.grants | Where-Object { [IO.Path]::GetFullPath($_.path) -ceq $current.RepoRoot -and $_.access -ceq 'write' -and $null -eq $_.time.revoked })
    Assert-OpenScienceCondition ($grants.Count -eq 1) 'Official project has no exact unique active source grant.'
    $binding = ConvertTo-OpenScienceProjectBinding ([ordered]@{schema=1;kind='autonomous-cae-lab.openscience-project-binding';
        project_id=$project.id;project_directory=$projectDirectory;source_directory=$current.RepoRoot;grant_id=$grants[0].id;
        working_root=$current.RepoRoot;access='write'}) $current.RepoRoot $current.Environment.OPENSCIENCE_DATA_DIR
    Assert-OpenScienceManagedFilesystem $binding $fs
    Write-OpenScienceJson (Join-Path $LogDirectory 'project-binding.json') $binding -CreateNew
    return $binding
}
