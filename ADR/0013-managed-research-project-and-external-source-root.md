# ADR 0013 — Managed research project and external CAE source root

Status: accepted design, implementation acceptance pending,2026-10-01.

## Problem and decision

The legacy launcher equates session.directory with RepoRoot. Official OpenScience
Home does not surface the external legacy research, although its actual5365 CAD
loop passed. The separate Lab8766 displays real Core records but is not official
OpenScience. Use the documented managed-project workflow with an external source
folder; preserve the existing repository, pinned fixture implementation and stores.

Freeze the managed project ID/owned identity directory, exact source write grant,
selected working root and RepoRoot in the native research context before startup.
Bind the server cwd to the managed identity root. The pinned run --attach client
has no directory/project selector; headerless requests resolve from server cwd.
Explicit project/session/MCP/status/abort API requests use the exact managed ID
and its identity directory. CLI output relay uses the same identity directory.
MCP command, Python import root, repository source pin and Core store remain
bound to the external RepoRoot. A project identity is not a CAD/model revision.

Native schema2 plugin settings include that immutable binding. Public plugin
initial project/directory/worktree must match it. Before each managed logical
stream or tool call, read the actual session through the bound public v1 SDK and
the official filesystem endpoint: exact session/project/identity, effective source
root and active exact write grant must match. GUI isolated sessions and explicit
project/legacy sessions are supported; there is no invented managed workspace mode.
Source/model/tool/stage/stopping gates remain. Policy denials are non-transient.
Project/grant/root drift blocks new inference/tools. Independently owned exact
abort/idle/Stop remains available without current MCP/grant/config/source admission.

Create only project/grant metadata through supported endpoints while the previous
owned runtime is paused. Preserve its immutable owner; do not retrofit its context.
Use a new committed-source research profile/store and the already authorized
openai-codex/gpt-5.6-sol/auth data. Metadata creation is not research acceptance.

## Alternatives and impact

Copying/rebuilding the repository inside OpenScience data, changing the native
binary/frontend, inventing CLI project flags, widening tools, rewriting old owner
or routing the user exclusively to Lab are rejected. Legacy explicit transport
keeps its historical context/headers. No Core schema, engineering rule, numerical
threshold, optimizer, operation contract or editable CAD behavior changes.
Advances R03/R10–R13/R21/R25/R43/R51/R52; all52 ledger requirements stay in scope.
UNKNOWN/NOT_RELEASED and credential exclusion remain. Windows warn fallback is
application permission enforcement, not OS containment; OAuth wire limits remain.

## Required evidence

Synthetic source checks must cover both contexts, immutable binding drift, foreign
project/session/root/grant refusal, GUI isolated selection and managed lifecycle
headers. A fresh actual run must verify resident source identity, unchanged valid/
rejected CAD/results/interpretation in a new store, the same official GUI session,
and observed-busy abort/idle/output/store preservation plus controlled owned Stop.
Record exact source/run IDs and failed attempts; CI/source checks alone cannot
close P1.1. Prior5365 research remains separately attributed.

Official source pin4082a2ecb73e166d4503963798228ba700f3840f:
[project workflow](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/frontend/docs/src/content/openscience/projects.mdx),
[attached CLI](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/cli/cmd/run.ts#L836),
[server selection](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/server/server.ts#L378),
[filesystem contract](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/session/filesystem.ts#L98),
[plugin input/client](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/plugin/index.ts#L56).

## Windows actual metadata correction

The official explicit data root resolves fs.realpath(requested). Windows MSIX
AppData virtualization can return a physical private LocalCache path for the
same authorized logical directory. Read-only OS directory handles verify that
alias; do not infer a Packages path, change auth/environment/owner, or broaden
common lexical containment. Check existing logical ancestors before and after
resolution, physical ancestors after resolution, and unchanged projects root
across the returned-project read. Links, missing paths and foreign roots refuse.

The official connected project grant generator emits fsg_ + crypto.randomUUID().
Accept the current RFC4122 v4/variant/hex syntax and legacy bounded alphanumeric
fixtures with complete-string matching. Exact grant identity/path/access/root
comparison remains. This is narrower than the upstream prefix-only grant schema.
Actual metadata/old owned Stop acceptance does not establish managed research.

[official data root](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/global/data-root.ts#L68),
[official connected grant](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/session/filesystem.ts#L402),
[Microsoft AppData virtualization](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes#appdata-operations-on-windows-10-version-1903-and-later),
[directory final path API](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew).
