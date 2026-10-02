# Classify the host checkout without changing Git pointers or configuration.
function Get-OpenScienceMcpGitTransportMode {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$RepoRoot)
    $pointer = Join-Path $RepoRoot '.git'
    if ((Test-Path -LiteralPath $pointer -PathType Leaf) -and
        ((Get-Content -LiteralPath $pointer -TotalCount 1) -match '^gitdir: [A-Za-z]:')) {
        return 'WINDOWS_MANAGED_WORKTREE_GIT'
    }
    if ($RepoRoot -match '^[A-Za-z]:[\\/]' -and (Test-Path -LiteralPath $pointer -PathType Container)) {
        return 'WINDOWS_PRIMARY_CHECKOUT_GIT'
    }
    return 'NATIVE_WSL_GIT'
}
