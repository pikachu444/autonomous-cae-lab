# OpenScience local runtime acceptance — 2026-09-30

Outcome: **PASS_READINESS_AND_OWNED_CLEANUP_ONLY**. This is a launcher/controller
unit. It is not a new autonomous research, CAD, solver or release acceptance.

Implementation workspace:
C:\Users\pikac\.codex\worktrees\openscience-runtime\autonomous-cae-lab.
Execution source base: 0e7209afe2ae385bcebdfe57b71c598133000071 plus the reviewed
owned-file diff. No GitHub CI run was found for that exact base when recovered.
Root's later Main CI results belong to their own source and are not substituted.
The implementation commit is the Git commit introducing this record; publication
and integration remain Root-owned.

## Scope and design

Owned changes are openscience-local.ps1, verify_openscience_live.ps1,
new openscience-server-local.ps1, openscience.json.example, OPENSCIENCE_USE.md
and this distinct record. Core, MCP transport, schemas, registry, numerical
engines and existing configure-openscience-local.ps1 were not edited.
The pinned fixture submodule was initialized at
3e48bf6138f495299f45b1af254bfb4aaff307b8 without implementation changes.

The official 2.0.146 JS launcher is called through Node with exact argument arrays,
using ProcessStartInfo.ArgumentList for the task-owned relay. The relay gives the
CLI direct stdout/stderr file descriptors. It keeps logs alive after a caller
returns or exits on unconfirmed cancellation; relay-final.json pins final bytes.
Live command.json hashes are explicitly diagnostic snapshots. A pending command
without a confirmed exit prevents another CLI model request on that profile.
The server and CLI share one explicit task profile and MCP store. The controller
proves recorded PID, creation UTC, executable/command, child lineage, loopback
socket, pinned health run/version, configuration hash and current MCP connection.
It refuses foreign processes, used ports, altered/unmarked profiles and public binds.

Before inference the CLI checks current readiness, an exclusive profile command
lock and idle sessions. It creates/verifies an exact project session via the
official API, then passes --attach and --session. This avoids the official CLI's
new-session workspace-mismatch DELETE branch. No sessions/DBs/results are deleted.

Only the nine known CAE tools are allowed, including nested MCP permission rules.
A loopback guard verifies actual function schemas and required/no-tools stage
intent before forwarding unchanged request bytes to Windows local Ollama.
It never forces tool_choice or synthesizes tool arguments. Successfully completed
CLI stages restore the ordinary Workspace guard, and restoration failure fails
the command/acceptance. Timed-out stages never restore it. Inference failures retain their
guard, session and process diagnostics rather than claiming completion.

The existing 16k alias and weights are reused. Defaults are temperature 0.6,
top_p 0.95, reasoningEffort low, output 4096, steps 3, provider 260 seconds and
external CLI 300 seconds. Title/durable jobs/autocompaction and generic/delegation
tools are disabled. Timeout abort uses the exact official session route with
x-openscience-abort-source: runner_timeout before verified CLI stop.
Unconfirmed cancellation refuses termination. Server Stop blocks new forwards,
confirms active-session abort/idle first, and rechecks idle before its owned kill.
Guard setters and Stop use one exclusive mutation lock. A stopping guard cannot
be restored or changed by a finishing/new CLI. Historical runtime profiles require
a fresh RunName rather than reactivating old guard state.

Acceptance resume pins original source HEAD and tracked/submodule byte hashes,
configuration, model manifest digest, profile/store/runtime owner and requested
CLI arguments. Each stage and the final verdict recheck current provenance.
Historical receipts cannot be relabeled as a new-source verification.

All task HOME/profile/config/data/XDG/TEMP/TMP paths are explicit.
Credential environment names are filtered without printing their values.
No user profile/model installation, account login, paid provider call, public proxy
or auth/bind weakening was performed. Windows warn fallback is not OS containment;
corporate license/security approval remains UNKNOWN.

## Verification

- Launcher checks: **31 PASS**, real no-provider Node child processes and scope-local
  HTTP mocks. Multiline/Unicode ArgumentList, readable live stdout, exact session
  preallocation, abort-before-stop, unconfirmed abort refusal, hash preservation,
  credential-name filtering, active-session/concurrent-command/foreign-owner gates
  successful bare-stage Workspace guard restoration, restoration-failure propagation,
  continued live logs after unconfirmed cancellation, pending-command rejection,
  original-provenance matching and changed-source/config/model/store/prompt rejection
  were exercised. Configured model digest matching/unknown/ambiguous cases were mocked.
- Controller checks: **35 PASS**, zero provider/backend calls. Actual process-info
  and log helpers, exact readiness/identity rejection, disconnected-MCP lifecycle
  cancellation, abort/idle stop gating, byte-preserving proxy/endpoint/schema guards
  JSON identity round trip/compatible date parser, serialized stop/guard writes,
  held-lock refusal and historical-profile restart refusal were exercised.
- Actual fresh run **openscience-runtime-readiness-20260930-02**, before the final
  read-only review corrections, retains its original 18bf52ad controller proof:
  public Start exited 0 on 127.0.0.1:4098, current GET /mcp was connected,
  health version was 2.0.146, and recorded native PID was 22252.
  Actual --version and debug paths through the generalized wrapper both exited 0.
  home/data/config/cache/state paths were entirely under the new task profile;
  dataManaged was false, with no AppData profile migration.
- Actual Stop exited 0/state stopped. All four recorded controller/launcher/native/
  guard PIDs were absent afterwards. Exact WSL pgrep for this worktree's MCP
  script returned no matches. No 8766 PID was stopped; Root manages that endpoint.
- Actual fresh run **openscience-runtime-readiness-20260930-03**, after those corrections:
  public Start exited 0 on 127.0.0.1:4098, current GET /mcp was connected,
  health version was 2.0.146, and native PID was 80844. The final wrapper's actual
  --version and debug paths both exited 0 with finalized relay receipts and wholly
  isolated paths/dataManaged false. Public Stop confirmed stopped; controller
  79128, launcher 74400, native 80844 and guard 48552 were all absent. Exact worktree
  WSL pgrep returned no matches. There were no sessions, chat requests or Core files.
- Actual chat requests: **0**; actual agent/Core tool calls: **0**;
  new Core store files: **0**. Model inference, new launcher full research,
  live in-flight model/tool cancellation and new GUI interaction remain **UNVERIFIED**.

Final exercised controller working-file SHA256:
6620dbcfc2acd2eba786ce357d39a5f7fafef2e3978a888611679a37436906e4.
The unowned configure script working-file hash remained
6e81f201d794c950e98268d1f2961811891144ce60cff32a0c0294c9b73bf5f8.
Hashes are of this working copy's bytes; Git line-ending conversion can legitimately
give another checkout a different script hash and its own new runtime owner.

## Failures retained and actual correction

The initial combined metadata/Start command was rejected before execution by
automatic approval review: **blocked by policy**. No more specific reason was
returned. A separate explicit invocation of the public Start script was allowed;
no permission or policy was changed. The rejected local model metadata query was
not retried, and no fresh model-byte preservation claim is inferred from it.

Fresh run **openscience-runtime-readiness-20260930-01** actually prepared a server/MCP,
but public readiness verification failed:
**Process PID/creation/command changed or is not owned.**
PowerShell 7.6.5 ConvertFrom-Json converted CreationUtc into System.DateTime.
The original JSON UTC string exactly matched actual CIM, but strict string
identity comparison correctly refused the changed representation.
The hidden controller's original Stop also refused for the same parse defect.

The old source stayed frozen during cleanup. A memory-only parser preserving JSON
date strings was used with unchanged strict PID/command/socket/health checks.
Project session/status was empty; the existing owned-launcher helper stopped only
that run's verified Node/native processes, and its controller exited/cleaned its
own guard. All four owned PIDs were absent. These failures and the fallback cleanup
remain recorded. No inference was performed.

The source fix preserves JSON strings with DateKind String on this host, and uses
a tested System.Text.Json fallback on older PowerShell 7. A real WriteJson→ReadJson
identity round-trip regression covers exact UTC type/value and multiline command.
A **fresh** second profile passed public Start and Stop; first records were not
overwritten or reclassified.

The final read-only review found live-pipe disposal after unconfirmed abort,
guard-restoration failure not propagated to acceptance, and resume traces labeled
with current rather than original provenance. These paths were corrected before
commit. A further guard/Stop race was corrected with shared locking and refusal
to reactivate historical profiles. Launcher mock attempts 07 and 08 retain the
fast-process CIM/receipt race failures; attempt 09 retains the active-file hash
sharing failure and explicit cleanup of its verified no-provider mock child.
The final mock attempts 10/11 and fresh actual run 03 passed without inference.

The earlier live-04 failure and live-05 bounded 13-tool research/Root browser
inspection remain historical evidence at their original mixed source revisions.
This launcher unit does not rewrite their verdicts. See OPENSCIENCE_USE.md.

## Local retention and hashes

All raw profiles, sessions/SQLite, logs, proxy bytes, command outcomes and failed
attempts are ignored local evidence under artifacts/. They are not published by
this commit and are not included automatically in a worktree archive/cherry-pick.
Preserve this worktree or separately retain those ignored files before archiving.

| Retained relative file | SHA256 |
| --- | --- |
| artifacts/launcher-mock-20260930-06/launcher-checks/checks.json | d34389ad26f2f90c2443ece4a8c7fa01974119a1946ef4b1320a0419f5232850 |
| artifacts/controller-mock-20260930-08/self-test.json | d89b21c6c4b69ebaac7a2bc1fa6ea1cd9425551ac50094db5d4c46718ccfaafe |
| artifacts/openscience-runtime-readiness-20260930-01/first-start-failure.json | 76420dd6f6657982f36d0dace9e4ef3aa9a1c37b5bba8321c7effdfb68e7ad25 |
| artifacts/openscience-runtime-readiness-20260930-01/cleanup-verification.json | d4d4baeb13f5a610eecbb39774ccadc8dabd68f02a00456c4372c1d6c8ce9ee0 |
| artifacts/openscience-runtime-readiness-20260930-01/automatic-review-rejection.json | 05eec15f9c15da469266087ea4823209bfff5e76da9c33a7fcb44de15ceaed76 |
| artifacts/openscience-runtime-readiness-20260930-02/readiness-proof.json | 07945c309cd46b7fc1d3ff568cfcba7fd1906469866a5684864344ed3705d811 |
| artifacts/openscience-runtime-readiness-20260930-02/final-readiness.json | a33975da391c797b949065da8b0f92c2315da5ac4ff748b3378a7641b30a2ffb |
| artifacts/launcher-mock-20260930-11/launcher-checks/checks.json | 51ddb662c72f30e66be6083e7849e576c87247f615655cec5476616480b2bf57 |
| artifacts/controller-mock-20260930-09/self-test.json | b3a0d1cac2991cb484c13f168a8a3538fad6d782ff490dd9a05f4bae9035aa1e |
| artifacts/openscience-runtime-readiness-20260930-03/readiness-proof.json | 2655b477f8ad85cbd29afb5a75b998be495c677ce8b613a96c38772022e9aae1 |
| artifacts/openscience-runtime-readiness-20260930-03/final-readiness.json | 9e6ecfd7c56eacce581d5da5a9790a9da6faec23d0fe1cbc10e4eb82430dbd72 |

Closed-run manifest: artifacts/openscience-runtime-unit-20260930/cold-files.json,
192 files, SHA256 0c16fe969b35b34931eda42c508c27cea99a4883b11a0410459cdc3f509eb168.
It covers final launcher/controller mocks and both actual startup runs, including
failed/refused cleanup receipts. Earlier mock attempts remain in their original
directories. The manifest excludes itself and mutable Main/user profiles.

Final closed-run manifest: artifacts/openscience-runtime-unit-20260930/cold-files-final.json,
513 files, SHA256 8d7c8c0cba16339d6932627ccec1942fe698126d9ff85919ddce3422a6f8b787.
Every recorded size/hash was reread successfully. It adds the final review-fix
mock attempts, their retained failures/cleanup, and fresh03 without changing the
original 192-file manifest. No ignored artifact bytes are claimed remote-durable.

Next Root gate: review/integrate the local commit, restore a persistent user runtime
with fresh task ownership, and verify the actual official served Workspace. A new
full model research acceptance must retain real tool events and immutable Core byte
gates; readiness alone cannot satisfy it. Root owns HANDOFF/CURRENT_STATE/ledger
updates and remote publication.
