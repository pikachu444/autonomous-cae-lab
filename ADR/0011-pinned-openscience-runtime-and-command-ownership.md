# ADR 0011 — Pinned local OpenScience runtime and command ownership

Status: accepted for bounded local research, 2026-09-30. Full new-launcher
model research and in-flight model cancellation require separate acceptance.

## Problem and decision

The official browser and a one-shot CLI can otherwise use different profiles,
projects, sessions or imported Core code. A persistent MCP server imports Lab
at startup; capturing disk source only at the first later research request
could falsely attribute cached source A to edited source B. A CLI timeout also
does not establish that the server's model request has stopped.

Use the existing pinned official OpenScience2.0.146 installation and existing
local model through a task-owned persistent loopback server. The browser and
`run --attach --session` use the same isolated profile/project/store. The
controller records verified executable/PID/creation/lineage/socket/health/MCP
identity and captures HEAD, index, tracked working bytes, imported plugin and
recursive submodule bytes before serve. It rechecks after readiness and before
every model POST, including unchanged-body browser forwarding. Each acceptance
binds to that boot pin, with a fresh task Python bytecode-cache directory.

Source drift blocks inference. Exact owned cancellation and Stop remain
available under Core/plugin/HEAD drift; controller tampering still fails its
strict ownership check. Official session abort and idle confirmation precede
owned CLI/server termination. Unconfirmed cancellation preserves the session,
process and continuing log relay rather than manufacturing a finished receipt.
Final relay output hashes are distinguished from mutable diagnostic snapshots.
Prior commands without confirmed completion block a new CLI request.

The research model retains the existing nine-tool CAE allowlist. Source/runtime
selection, process syntax and profile paths remain in the local transport, with
no Core schema, numerical-engine or engineering-rule changes. The model plans
and interprets research; numerical engines generate optimization candidates.
No weights, user profile, global environment or unrelated listener is replaced.

## Alternatives and consequences

Independent CLI profiles would split GUI/tool/store provenance. Trusting a URL,
an arbitrary PID, an exit code or a later source snapshot would not establish
ownership or execution identity. Blind process termination, deleting sessions
and promoting readiness into model acceptance are rejected.

A source pin intentionally prevents inference after edits in its checkout.
Use a separate clean pinned serving worktree during continuing Main changes.
Preserve the old profile/store; a changed source starts a new owned run.
The permission guard does not establish operating-system containment or
corporate license/security approval. These remain UNKNOWN.

## Verification and requirement impact

Reviewed source a60b854 and its six-file packet passed independent static review.
Owner controller46 and launcher35 mock checks passed with zero provider/Core
mutations. Actual fresh04 verified readiness, MCP connection, boot-bound official
metadata and exact owned cleanup only, with zero model/Core calls. Its source
was HEAD1f6cb07 plus frozen correction before the later acceptance-document
append; it is not a clean-a60 or Main execution. Earlier failed mock/collector
attempts and all closed raw evidence are preserved. Main tests, clean integrated
startup, official GUI, actual research and cancellation are distinct gates.

Advances R03,R10–R13,R20–R21,R25,R33,R43,R45,R51–R52 while preserving all52
requirements. Numerical/physical/strength/release qualification is unaffected;
all unverified requirements stay UNKNOWN and decisions remain NOT_RELEASED.

## Managed Windows worktree Git correction, 2026-10-01

After Main source259649d was pushed, a read-only deployment probe found that
native WSL Git cannot follow the managed worktree's Windows absolute .git
pointer. Core therefore recorded unavailable commit/unknown dirty state, while
the relative fixture submodule pointer remained readable. No research was run.

Reuse the invocation-scoped host Git bridge design already in scripts/local.ps1.
For Windows-managed worktrees only, prepend the tracked LF-only
scripts/wsl-windows-git directory to the existing WSL PATH and pass the exact
host Git path to its two-line wrapper. Other checkouts retain native WSL Git.
The wrapper is in the repository boot pin; startup requires its tracked hash
and host Git executable to match the transport intent. Later bridge/source drift
is refused by the existing inference gate. Profile intent version3 requires a
new profile; no existing pointer, profile, global PATH or Git config is changed.

Running on Main alone would avoid this deployment defect but would not provide
a separate stable research runtime while integration continues. Rewriting old
worktree pointers or setting global Git/PATH would affect unrelated checkouts.
Those alternatives are rejected. Core schemas, tool permissions, numerical
thresholds and OpenScience research arguments are unchanged.

Controller52 mock gates passed, including six bridge/deployment checks;
unchanged launcher39 remains separately attributed. An actual read-only
diagnostic used the new frozen wrapper against clean Core259649d and reported
the exact commit, dirty=false and fixture3e48bf6. This diagnostic did not start
OpenScience or call a model/Core mutation. Clean new-config runtime/research/
GUI/cancellation and bounded independent source admission remain separate gates.
See the openscience-wsl-git-correction record. Advances R11/R21/R25/R43/R51/R52.

## Timeout idle enforcement correction, 2026-10-01

Clean a1 readiness/metadata/owned cleanup passed independently. Actual research
run01 failed at300s after one study tool. Exact abort200/true caused provider
client_cancelled and natural CLI exit; later idle-before-server-Stop passed.
There is no actual forced CLI termination after idle proof at this source.

Independent review found a P2: CLI timeout performed abort then owned termination
without an explicit idle query, contrary to this ADR's decision. Enforce the
existing decision by checking exact session/project metadata through lifecycle
identity and retaining bounded session-status/idle receipts before CLI stop.
Busy/unavailable/malformed/foreign state refuses termination and preserves the
continuing CLI/session/log relay. Abort confirmation and idle confirmation have
separate fields and refusal reasons. General schema/Core/research operations,
model/tools/numerical thresholds are unchanged; old receipts are not upgraded.

Trusting HTTP200/true alone or replacing retained evidence with later idle would
leave the gap. Immediate blind kill or deleting a session is rejected. Separate
unchanged controller52 and changed launcher47 mock gates pass with zero model/
Core calls, including actual helper busy-to-idle order and refusal/log retention.
Independent source admission and fresh clean research/cancellation remain open.
Requirement impact: R11/R13/R21/R25/R43/R45/R51/R52; operation contract unchanged.

Retry wallclock policy is declared before execution: provider500s/stage600s,
same output4096/steps3/model/tools/CAD inputs/numerical criteria. The old response
took181.471s and first tool about95s; exact latency cause remains UNKNOWN.
This changes waiting time, not numerical acceptance. Preserve original failure,
both raw copies/manifests and all UNKNOWN/NOT_RELEASED qualification.
