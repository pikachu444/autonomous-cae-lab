# S3 HTTP 실행 중단·재시작 복구 계획

현재 R1_BOUNDED_HTTP_PASS / R2_OPEN입니다. HTTP-only journal/fence를 구현하고 재시작 후 완료 J-id/답변 보존, 미해결 작업 차단, 실제 metadata HTTP controller 강제 종료, 동일 원본 연구의 읽기 전용 필드 열람을 확인했습니다. [검증 기록](../benchmarks/records/20261005-http-job-recovery-r01.json). MCP/Core 경로의 전체 저장소 single-writer나 실제 native 재연결/취소 권한을 주장하지 않습니다. 다음은 기존 R2의 exact session/resident/native ownership과 실제 취소·종료 확인입니다.

아래는 구현 전에 작성한 역사적 SOURCE_READONLY_PLAN입니다. 그 원문의 NOT_RUN은 당시 조사 범위를 뜻하며, 현재 R1 판정은 위 기록을 따릅니다.

Source report SHA a4ca701329802d844ccdf8150ad22a07ec47bbc7773220c2cbef1dd9d689987d; manifest SHA 6aa6fd0cf7f82a806db9bad51853418b123fe38f2eb3e302d256be6806e21e8f; receipt SHA 1314dc69bf83a4501b469d9bbb54cee46b500ef0e8a236c3b974523442968c23. 원문 LF 사본이며 raw private packet은 LOCAL_ONLY입니다.

---

# Bounded S3 source recovery packet — read only

Date: 2026-10-05. Owner of this investigation: cae_research_launcher. Implementation, public records, integration and Git remain Root-owned.

The demonstrated gap is HTTP job durability. A fresh LabService forgets the old J-id, active worker and cleanup gates, then locally reports IDLE and accepts a new HTTP job. Existing Research/PowerShell command and MCP-resident guards still constrain execution. This source trace does **not** demonstrate a second native solve, an orphan currently running, process absence, restart success or a deadlock.

This packet implements the minimum already accepted in docs/CAE_RESEARCH_EXECUTION_PLAN.md S3: retain a job before execution, recover unresolved records as RECOVERY_REQUIRED/UNKNOWN, preserve past-result reads and block new execution through that HTTP store. It does not propose a scheduler or a global store writer lock.

## Source and investigation boundary

Initial source checkpoint was 67caf04f85bfdfe93446a080bb093f5ebdee5941. At the closing read, Primary Main was e5000f119d2eb6e82cfc4f8089eacb06028510bc, a documentation/live-GUI record commit. Read-only git diff showed no committed change between those commits in the nine specifically compared lifecycle files: research.py, service.py, server.py, openscience/jobs.py, openscience/mcp_server.py, execution_control.py and the three PS lifecycle helpers. No raw Git/worktree EOL equivalence is inferred. Pinned fixture upstream is 3e48bf6138f495299f45b1af254bfb4aaff307b8.

At the initial snapshot, the only observed working-tree modifications were the concurrently owned fixture-field-viewer.js and style.css. At the closing observation, tests/test_fixture_field_viewer.js was also modified by that owner. None was edited, inspected for correction or copied here. The independent GUI pixel correction is outside this packet.

SOURCE-SNAPSHOT.json records actual local bytes/SHA256 for 34 consulted source, test and recovery files, totaling 1,482,197 bytes, at 2026-10-05T10:13:05.5272056Z. CLOSURE.json rechecks all22 listed source/test/status files at 10:20:13.4956221Z: every raw SHA256 is unchanged, with the same e5000f HEAD and only the three separately owned GUI modifications. These are read-only source observations, not a runtime or source freeze. Recovery context was read in the required PROJECT_SCOPE → HANDOFF → CURRENT_STATE → ARCHITECTURE/ADRs → contracts order before the source trace. The later documentation delta was also read; ADR0018, ADR0033 and ADR0036 and the focused S3/Astra plan sections were rechecked.

Only PowerShell file reads, rg source searches, Get-FileHash/.NET metadata and read-only Git inspection were used. No Python/application import, test, provider/HTTP/browser call, runtime/native execution or process inspection was performed. No tracked file, Git/index, old artifact, credential, Goal or automation was changed. New private report files only are written in this folder. Exact-commit CI was not queried under this bounded assignment; Root owns that evidence. A later documentation commit does not inherit solver qualification.

Read-only lookups initially used nonexistent guessed filenames for two Core/PS helpers and two ADR titles; rg resolved the actual engine.py, openscience-local.ps1, ADR0033-lab-question-handoff.md and ADR0036-explicit-selected-mesh-research-scope.md. These lookup failures are not product/test failures. Some broad batched output was truncated; lifecycle conclusions below use subsequent focused ranges.

## Current HTTP admission and persistence

| Source boundary | Current demonstrated behavior | Recovery consequence |
| --- | --- | --- |
| apps/lab/server.py:53,133,214 | Exact loopback Host/Origin/token/JSON gates; POST /api/jobs delegates to submit; main constructs a new optional Research bridge and LabService. No journal scan. | A restarted server constructs fresh transport state. Trusted owner/PS paths remain CLI-only. |
| apps/lab/service.py:69–92 | Local store is writable; configured libraries must exist and not overlap. Fresh RLock, empty jobs/tokens/threads, active_job=None and accepting_jobs=True. | Old HTTP J-ids are absent even when Core or Research files remain. |
| service.py:440–493 | Under its process-local lock, reject shutdown/unsupported op/wrong arguments/active job/library writes; check argument signature, Research question/session and safe paths; create J+UUID and RUNNING record; create token/thread; start daemon worker. Thread-start failure marks only the in-memory job FAILED and clears active. | There is no durable admission or pre-worker failure record. Crash just before/after start cannot be distinguished on restart. |
| service.py:524–569 | Worker passes the process/thread-local CancellationToken; checks parent/campaign preflight; records returned result/error. Cleanup pending retains the active gate; otherwise completed time and active=None. | Core may have saved result.json before transport terminal publication. Transport finality and J-id/result association are still only memory. |
| service.py:571–621 | job() and cancel() look up the memory dictionary; old IDs return 404. Requested vs observed cancellation and cleanup retry are distinguished. Release requires no pending cleanup and, for cleanup retry, a dead worker. | A new controller has no token/thread/owned Popen to retry; constructing replacements would fabricate authority. |
| service.py:633–677; server.py:245–262 | Cooperative shutdown closes admission, requests tokens, joins outside the service lock and retains unresolved cleanup. Server waits for joined/no pending. | Normal interruption preserves current handles; abrupt loss cannot run this finally path. |
| service.py:107–113 | execution_status is explicitly a small resident observation: memory pending → BUSY; otherwise IDLE/idle_confirmed=True. accepting_jobs is a separate field. | Closing accepting_jobs alone would still falsely communicate IDLE during unresolved recovery. A separate recovery condition is necessary. |
| service.py:94–104,128–168,170–213 | Research status calls bridge.status before checking service admission; capabilities.callable means method/configuration presence; overview reads Core records from disk and jobs from memory. | Recovery status must be checked before starting another status facade. Method availability is not recovered-store execution permission. Existing Core/result GET reads can remain available. |

All POST-submitted operations are transport jobs, including operations classified as read-only. Some native inspection can start a child even though it does not write a Core experiment. The minimum recovery fence should therefore block new HTTP execution jobs, not only numerical writes; ordinary GET inspections of preserved results/artifacts remain available.

Selecting a configured read-only library can remain a view action if Root preserves the local recovery fence across selection. Switching back to local or restarting the server must not clear that fence. No library gets a new journal or control file.

## What Research and native ownership already retain

apps/lab/research.py:52 writes new evidence with exclusive create, flush and fsync. _request at 222–248 creates a random lab-questions/status- or run-UUID directory, exact question.txt/hash/size, request.json/hash and invocation.json **before** _start launches the fixed PS facade. The request binds the trusted owner SHA, source commit/boot, approved5.6Sol, store, run/profile/project and descriptor. It does not bind the HTTP J-id or HTTP controller incarnation.

The constructor at 60–72 resets active, cleanup, process, directory and last result; it does not scan/adopt those retained run directories. _observe at 263–327 retains the same live Popen after errors and does not infer completion from exit alone once command start evidence exists. Started terminal responses require matching request/owner hashes, cleanup confirmation, no owned launcher/relay, and confirmed same-store resident IDLE. CANCELLED additionally requires user cancellation, not timeout, and confirmed session/resident idle. Finally at 436–445 clears the bridge only when no child started or cleanup was verified. Losing the Python controller loses this in-memory handle; the underlying child may or may not continue, which was not observed here.

scripts/lab-openscience.ps1:
- Assert-LabResearchBootstrap/Runtime at 23–70 recheck owner/context/source/project/store/model/boot/descriptor and helper hashes.
- Read-LabResearchResident at 112–165 asks the fixed diagnostic source-identity resource using an owned official session, validates the actual source/interpreter/store and PROCESS_RESIDENT scope.
- Confirm-LabResearchResidentIdle at 167–186 reuses that diagnostic session, but compares the resident **numeric PID only** at line175. Same-store/source checks remain; there is no resident birth/boot/incarnation field in the current resource.
- Run mode at 314–386 requires resident IDLE before inference, invokes the existing owned CLI and waits for session cleanup plus resident IDLE before a terminal response. Status mode returns declared READY after runtime verification without this resident/native check.
- response.json is exclusively created and flushed, and binds request/owner hashes. progress.json is mutable display evidence, not an immutable completion verdict.

scripts/openscience-local.ps1:
- Assert-OpenScienceNoPendingCommand at 159–180 checks profile runtime-command-pending.json, request/log ownership, retained relay-final exit state, stdout/stderr hashes and prior launcher absence/reuse before another command.
- Invoke-OpenScienceLocalCommand at 261 onward acquires the profile runtime-command.lock, rejects a pending command, verifies/reuses an owned official session and writes request/pending before launcher start. It retains ready/final, exact session and launcher/relay identities and cleanup/output hashes.
These existing fences must not be replaced, relaxed or used as a general orphan manager. They mean a newly admitted HTTP Research job can still refuse before inference. They do not make the HTTP J-id durable.

scripts/openscience-server-local.ps1:553–578 records and checks Windows PID, parent, creation time, executable and command line. Stop-OpenScienceOwnedLauncher at 870 onward rechecks actual identity and owned native descendants before stop. Reuse these exact-ownership helpers where applicable. Do not rebuild an owned Popen or signal a process from a journal PID alone.

caelab/execution_control.py:26–81,118–173 owns actual Popen objects through a process/thread-local token, serialized cleanup and checkpointed waits. cleanup_owners is a diagnostic PID/group/reaped snapshot, not reconnect authority. A reaped POSIX group that might be reused remains UNKNOWN rather than being signaled. These safeguards must stay unchanged.

## HTTP parent, session, resident and native are distinct

The HTTP Research worker waits on a PS facade. That facade owns an OpenScience question session/CLI/relay and checks a separate MCP diagnostic session. MCP synchronous tools execute Core/native work in the MCP process. An idle AI session or exited CLI does not alone close that Core/native work.

openscience/jobs.py:27–39 lazily creates another LabService in that MCP process. Its global RLock and synchronous_writer at 112–128 coordinate synchronous/asynchronous work **within that resident**. execution_status at 49–68 deliberately does not scan stores/OS processes; a new resident with no service returns IDLE. openscience/mcp_server.py:106–149 reports diagnostic on-disk source and PID/executable/path, without a process birth/boot/incarnation identity. Source fingerprints do not prove cached bytecode or another process's state.

Core engine.py already has a separate external registration file lock and per-registry locks for registration transactions. This is not a general HTTP job lock. Reusing/extending it around a waiting HTTP Research call would change a different contract.

A generic same-store lock held by HTTP while it waits and then acquired by its MCP child creates a circular-wait design risk. No deadlock was reproduced. The minimum HTTP journal/fence must not be acquired by MCP synchronous_writer, the default MCP LabService, Core registration or native adapters.

The observed gap is loss of transport state. Potential duplicate **direct HTTP Core** work after restart is a source-supported risk because it has no PS profile-command fence; actual duplicate work, child survival and PID reuse are unrun hypotheses. A fresh MCP's IDLE is correctly scoped to that process and cannot serve as global-native absence proof.

## Root-owned implementation packet R1: durable HTTP recovery

Suggested implementation files:
1. **New apps/lab/job_journal.py**: small standard-library append-only record/validation/projection helper. It owns only HTTP bookkeeping, not Core schema, job execution or native syntax.
2. **apps/lab/server.py:main**: create/pass an explicitly HTTP-only journal for the configured local writable store before enabling HTTP execution. Trusted startup configuration chooses it; no browser path/owner/PID input.
3. **apps/lab/service.py**: additive optional HTTP journal dependency, with the existing default off. Integrate constructor recovery, submit, _execute, cancel, _resolve_cleanup, shutdown and truthful overview/execution/research status. Keep loaded recovery state separate from live _active_job/tokens/threads.
4. **apps/lab/research.py:_request/run**: optional trusted internal journal binding callback or app-owned sidecar. Before _start, durably bind J-id/controller to the newly created request directory/request hash/question hash/owner/source/store/session. Do not silently add fields to the existing exact PS request schema or broaden browser arguments.
5. **Tests**: new tests/test_lab_job_journal.py plus focused extensions to test_lab_server.py, test_lab_cancellation.py, test_lab_research.py and test_lab_research_service.py. No new dependencies are needed.

openscience/jobs.py retains the default non-HTTP LabService path. This packet must not acquire a shared store lock in the MCP process. If Root needs an explicit no-HTTP-journal assertion there, it is a small compatibility control, not a global writer implementation.

Proposed journal shape, names subject to Root's final implementation:
- A reserved local directory such as _http_job_control. Resolved containment is bound to this server's local store, never a read-only library or a browser path.
- Immutable per-J-id admission and numbered/uniquely named event records. Schema1 and kind HTTP_JOB_CONTROL distinguish them from scientific results. Record job ID, controller UUID, HTTP scope, store/source binding, operation, canonical argument digest, UTC, stage and previous-event digest. Record actual private evidence references/hashes; do not copy authentication or token/config contents.
- Controller PID/host/boot/start identity is diagnostic unless verified by a supported ownership protocol. A fresh UUID distinguishes controllers. Native authority is not created by these fields.
- A single HTTP-only atomic claim/reservation closes two-HTTP-controller admission races. Claim has J-id/nonce/digest and remains after a crash. Only the matching durable terminal/reconciliation can release it. MCP never reads/acquires it as a prerequisite to doing this HTTP parent's work. Short journal serialization may protect publication; no lock waits across provider/native execution or worker.join.
- Use exclusive new files, flush/fsync and strict JSON/size/schema/path/sequence checks. A torn record, orphaned claim, unknown version, conflict or unresolved publication remains blocked and visible. Existing storage.save_json uses temp/replace without exclusive append/fsync semantics, so it is not by itself this primitive. State caches can be replaced; authoritative old records cannot.
- Persist a result/error envelope or stable retained output references before publishing terminal. Keep native/field bytes in their existing artifact locations. Metadata/result size limits must not silently truncate evidence; a persistence failure retains an unresolved job rather than reporting a completed one.
- Scan only the opted-in local HTTP journal, not all runs/PS profiles as an invented OS inventory. No journal in a legacy store is absence of tracked HTTP history, **not** proof that no old native job exists.

Minimal state transitions and admission order:

| Event | Durable action before allowing the next boundary | Public/admission state |
| --- | --- | --- |
| Valid submit | Complete existing argument/source/store preflight; atomically reserve HTTP claim and fsync ADMITTED/LAUNCH_INTENT before worker.start. | RUNNING can remain the compatible live status; internal launch stage is explicit. New submissions blocked. |
| Before bridge Popen | Append PREPARED binding to exact request/question/owner/source/store/session and launch intent. | No child starts if binding fails. |
| Worker/thread start failure before operation | Append FAILED_PRESTART with original error and no-execution evidence; append/release only after that record is durable. | FAILED; if persistence uncertain, RECOVERY_REQUIRED. |
| Worker begins / owned launch observed | Append observed stage and actual trusted identity available from the existing helper; keep intent if identity capture fails. | RUNNING. Crash between spawn and identity publication remains UNKNOWN. |
| Cancel | Append request before acknowledging acceptance; observed cancellation is a separate event. | CANCEL_REQUESTED. Recovered jobs do not get a fabricated fresh token. |
| Operation returns but cleanup pending | Retain outcome/error refs and cleanup owners/limitations; append CLEANUP_PENDING. | No terminal/admission release. |
| Verified terminal | Persist terminal snapshot/evidence first, then release only this matching HTTP claim. | COMPLETED/FAILED/CANCELLED preserves current meanings; no engineering PASS implied. |
| Controller starts with unresolved admission/claim | Validate/read old records; append a new recovery observation without overwriting them. | RECOVERY_REQUIRED, outcome UNKNOWN, idle_confirmed=False, accepting_jobs=False. |
| Validated terminal found after terminal-before-release crash | Append/recover matching release using the verified original terminal chain/claim. | Original terminal retained; no operation replay. |

A missing WORKER_STARTED marker cannot prove no worker/native started. A result.json or an exited/missing PID cannot substitute for a transport/native terminal. A terminal that cannot be durably saved must keep the gate closed even if the native operation returned.

A recovered J-id is a record, not a current Thread/CancellationToken/Popen. Use a separate unresolved-job collection/recovery flag so cancel(), shutdown() and cleanup retry do not index nonexistent live handles. An uncertain job can be read and cancellation intent retained; actual cancel/reconnect needs R2's verified ownership path. No automatic replay or automatic session/runtime replacement.

research_status should return the blocked recovery reason before invoking bridge.status. execution_status must return RECOVERY_REQUIRED/UNKNOWN rather than IDLE during this condition. Preserve old Core/result/artifact GET reads and transport J-id inspection. Selecting configured read-only views may be allowed, but cannot clear the local execution fence. Server startup with a stale optional Research owner currently can fail in bridge construction; starting without an owner remains the existing read-only/metadata route. Do not bypass owner validation to call execution ready.

R1's guarantee is limited to this HTTP job journal/store. Independent MCP/direct Core writers remain outside it. Cross-process whole-store exclusion is a separate accepted design/gate, and should not be implied by the R1 result.

## Root-owned display dependency, after current viewer correction

No field viewer/style correction belongs to R1. A small subsequent transport-status change is needed in apps/lab/static/app.js, research-controls.js and result-presentation.js, with their focused existing tests:
- app.js:32/68/130 recognizes only the current live/cancel/cleanup statuses; busy and overview-follow logic at 447/470 do not treat a recovered job as blocked. The file currently does not consume overview.accepting_jobs.
- Display RECOVERY_REQUIRED as “실행 상태 확인 필요 · 새 작업 차단”, with preserved result links. Block execution independently of a live-thread label. Do not label the unknown job “running” as an observed fact.
- Avoid exposing cancel/cleanup retry as an effective native action until exact ownership is available. An explicit request can remain a request, never a stopped/completed observation.
- research-controls.js:204 and result-presentation.js:133 need the same unknown/recovery interpretation. No result schema or engineering verdict change.
Root should assign this after the current three-file GUI owner freezes. Server-side admission remains authoritative even before this display patch; a full user-facing S3 PASS needs both.

## R2 prerequisite: exact reconnect/cancel identity

R1 intentionally cannot resolve an orphan by itself. Root's later shared lifecycle packet should establish a durable, launch-time binding to the exact official session/command, same source/store/boot, MCP resident incarnation and owned native execution. Reuse existing request/ready/final/command/output records and exact process helpers; append observations instead of rewriting originals.

Before accepting reconnect/idle, add a trusted MCP lifetime identifier (fresh process-start nonce plus birth/boot identity where supported) to the source-identity resource and retain the first handshake before inference. Compare the same lifetime in Confirm-LabResearchResidentIdle, not only numeric PID. An unknown/changed boot or reused PID stays UNKNOWN; do not adopt another resident even with the same source/store. This is diagnostic ownership observation, not proof of numerical qualification.

The spawn→identity crash window needs a retained launch intent/child handshake before accepting ownership; no missing after-start event implies absence. Strong owned native identity is also needed if cancelling outside the original token/Popen lifetime. The current journal PID/group diagnostic cannot authorize it. If existing helpers cannot re-establish ownership, leave recovery blocked and expose that limitation; do not add a generic process killer.

Known same-owner live work can be observed without reissuing the question or analysis. Abort must target the exact already-owned official session/command; keep original exception, cancel-request vs observed fields and timeout distinction. Confirm exact session idle, owned CLI/relay/native closure and same-incarnation resident idle separately. A native resource-closure reconciliation can release resource admission while preserving an UNKNOWN scientific outcome if Root explicitly qualifies that policy; it must never turn it into a completed numerical result.

The current synchronous MCP analysis path does not promise immediate solver interruption from AI session abort. Report whether cancellation waited for native completion, reached a cooperative checkpoint or actually stopped an owned child. If any closure remains unconfirmed, keep CLEANUP_PENDING/RECOVERY_REQUIRED. Retain approved ChatGPT/openai-codex/gpt-5.6-sol, descriptor, fixture source, thresholds, raw full-U and seven UNKNOWN/NOT_RELEASED throughout.

## Focused acceptance controls to implement, all NOT RUN here

Existing source tests already cover process-local single writer, partial Core experiment retention, requested/observed cancellation, same live Popen cleanup, worker join, marker I/O failure and started-terminal resident idle. Relevant anchors include test_lab_server.py:466/494, test_lab_cancellation.py:211/249/281/443, test_lab_research.py:175/192/257/399/419, test_execution_control.py:82/116/162/201 and verify_lab_research.ps1's same-resident mock. They do not qualify an abrupt HTTP-controller restart.

Use tiny TEST_ONLY children/controllers and finite latches, not a solver/provider. Kill only the test-owned controller for crash controls; retain stage logs and invocation counters.

| Control | Required observation |
| --- | --- |
| Crash after admission, before worker begins | Restart preserves J-id and UNKNOWN/recovery fence; no second method invocation. |
| Crash after worker begins or spawn, before child identity publication | Intent cannot be treated as no execution. No PID reconstruction or auto rerun. |
| Tiny child active when controller lost | A fresh controller stays blocked, old partial bytes/IDs readable; read observers cannot launch work. |
| Core/method returned, terminal not persisted | Presence of a saved result is displayed as retained evidence only; recovery remains unresolved. |
| Terminal persisted, release not persisted | Strict matching terminal/claim recovery is append-only and invokes nothing. |
| Admission/binding/terminal I/O failure | No launch before admission/binding; post-launch I/O failure retains busy/recovery and original error; cleanup failure is separately retained. |
| Startup failure before any operation vs cleanup failure after start | Distinct evidence; failure cannot clear an unproved owned process. Late cancel does not rewrite an already authoritative terminal. |
| Wrong job/store/source/owner/request digest, malformed/torn/foreign/oversize/path association | Fail closed without external writes or native calls; exact original bytes retained. |
| Same numeric PID, different boot/birth/resident nonce; different owner | No abort/signal/adoption, never confirmed idle for the old job. |
| Two HTTP controllers and two read observers | One atomic HTTP execution admission, readers see retained unknown state. Concurrent reconciliation cannot release another claim. |
| HTTP parent waits, simulated MCP child performs work | MCP default service never acquires the HTTP claim; a bounded latch proves the proposed path has no parent-child lock cycle. This tests the new design, not a reproduced old deadlock. |
| Current API guards/read-only defaults | Existing Host/Origin/token/strict JSON/body/path/signature guards and normal cancellation meanings remain. No model/provider/runtime choice from browser. |
| Recovery UI | Unknown status disables new execution, keeps exact old result links, does not display completion/active-native certainty or poll a provider. |

After independent source review and integration, Root's separate native gate should use one suitable existing mesh and new store/job/experiment IDs. No convergence sweep is needed. Freeze exact source/runtime boot and immutable original/partial records; demonstrate a **known active** owned native phase before controller loss or cancellation, reconnect the same job without another invocation/solve, and prove admission remains closed until exact closure. Check old result/field/source hashes unchanged. Capture session, resident lifetime, child identities, launch/terminal and cancellation observations. Include a wrong-owner/reused-identity refusal control without signaling a foreign process.

Historical cancellation after native completion is not active-native interruption proof. A truthful cooperative-wait result can qualify its bounded behavior, but cannot be reported as immediate kill. Native solve/reconnect/cancel/GUI and exact CI remain separate observations. UNKNOWN outcome and engineering NOT_RELEASED do not become PASS from journal repair.

## Completion of this assignment

This is a Root-owned implementation/test packet derived from the current source and accepted S3 plan. No test or runtime success is claimed. Read-only findings are demonstrated at the cited functions; child survival, actual duplicate native work, PID reuse and a lock deadlock remain unrun hypotheses. R1 can be implemented and reviewed first, with unresolved native cases deliberately blocked until R2 and the actual native gate are qualified. All wider project requirements remain in the ledger.
