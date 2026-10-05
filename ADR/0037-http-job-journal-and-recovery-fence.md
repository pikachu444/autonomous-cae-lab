# ADR 0037 — Durable HTTP job records and conservative restart recovery

Date: 2026-10-05. Status: accepted, bounded R1 transport verification complete.
Record: `benchmarks/records/20261005-http-job-recovery-r01.json`.
This does not qualify native reconnection/cancellation or complete S3/R2.

## Problem and decision

The Lab's in-memory J-id, thread and cancellation token disappear with its
HTTP controller. A new controller must not describe a lost job as completed,
cancelled or idle merely because its own thread list is empty. Users also need
to read the original answer, job outcome and associated experiment after a
restart. This follows the existing S3 plan and ADR0018/ADR0033 boundaries.

Opt in an HTTP-only job journal at the trusted server entry point. Keep the
default LabService/MCP/Core paths outside that claim. A short advisory lock
serializes journal publication, not provider/solver execution. An exclusive
claim and flushed/fsynced append-only events bind the local store, HTTP source,
job, controller UUID, argument digest, sequence and previous-record digest.
Admission and launch intent precede worker start. The Research bridge records
its trusted prepared request binding before Popen without changing the exact
PowerShell request schema or browser argument allowlist.

Persist the full terminal snapshot before releasing that job's matching claim.
An intact historical terminal/release chain remains readable across source
updates; a new job gets the current source binding. Source drift never grants
authority to adopt an unresolved operation. Retain original scientific result,
field and experiment artifacts in their existing locations.

After an unresolved admission, orphan/foreign claim, torn/corrupt record or
uncertain persistence, expose RECOVERY_REQUIRED, outcome UNKNOWN,
idle_confirmed=false and accepting_jobs=false. Preserve known J-ids and
available results. A recovered record is separate from live tokens/threads;
cancel/shutdown cannot manufacture handles or infer native completion. Only
an intact terminal/claim chain may close the terminal-before-release crash
window without replay. A missing marker, PID or result file is insufficient.

The UI describes this as “실행 상태 확인 필요 · 새 작업 차단”, without a
running animation, fresh orphan-cancel button or implied completion. Past
answer/result reads remain available. The server remains the admission owner.

## Alternatives and boundaries

Replaying a lost job can duplicate scientific execution. Clearing a claim on
PID absence loses unknown outcomes and creates no cancellation authority.
A general scheduler is unnecessary for this transport repair. A whole-store
lock acquired by both the waiting HTTP parent and its MCP child could create
circular waiting; this is a design risk, not a demonstrated deadlock.
Keep the claim in the HTTP transport and retain existing resident/source/
session/native ownership checks. No HTTP journal owns Core/native processes.

R1 does not recover untracked legacy operations or qualify their absence. Exact
session, resident incarnation and owned native reconnection/cancel are the
separate R2 continuation. Store/source/PID metadata is not signal authority.
Fixed journal limits refuse admission before starting a worker and reserve
terminal/release slots. Older overflow or uncertain persistence blocks admission
without truncating history. Valid recovered cancellation intent survives another
restart but never confirms a native stop. A corrupt current claim cannot change
a separately intact, released historical completion.

## Requirements and verification

R08–R13, R21, R38, R43–R49 and R52 gain durable HTTP observation and conservative
admission. Core schemas, Domain engineering decisions, adapter syntax,
deterministic numerical engines and approved research model/auth are unchanged.
Existing invalid metrics, UNKNOWN and NOT_RELEASED remain scientific verdicts.

Verify terminal/result retention, admission-before-worker/prepared-before-launch,
start/persistence failures, tiny-controller crash and restart, terminal-before-
release, two-controller races, corruption/foreign bindings, source-update
history and safe recovered cancel/shutdown. Check the actual mounted C: store
primitive and user-visible blocked/reopened-result behavior. None of these
transport controls substitutes for a native interruption, a numerical reference
comparison, complete U1 or full Phase1–7 acceptance.
