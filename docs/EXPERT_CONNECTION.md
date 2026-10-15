# Expert connection

This is setup for the independent native Expert window. It uses the existing
local service, discussion documents, source archive, bounded rounds and
Numerical/Study return actions. It creates no model answer during setup.

## First connection

The maintained Windows installer now includes the existing pinned MCP package
with either -ResearchUI or -Expert, and checks its import. The supported
OpenScience host needs that package internally; an ordinary MCP client
registration is not required. -Expert prepares these packages without Qt;
the native Expert window uses -ResearchUI (also prepared by its normal launcher).
For an existing private runtime, rerun its normal installer with the same
RuntimeRoot and -ResearchUI. The existing receipt/extras checks detect a runtime
that lacks the required package. This does not configure or invoke a provider.


1. Open Expert directly: Start-CAE-Lab.cmd -Tool expert. You can already write
   a question, import/read local sources and save a discussion without a model.
2. Choose **Connection… → 기존 OpenScience 설정 사용**. Select the existing
   owned OpenScience profile and its installed pinned runtime. **Browse…** selects existing directories;
   nothing is downloaded, installed or signed in by this dialog.
3. Choose the configured model hint or enter its exact openai-codex/model name.
   The model remains **UNVERIFIED** until an actual authorized request succeeds.
   The dialog does not treat a catalog entry, login file or developer Pro
   subscription as product inference entitlement.
4. If there are no roles, choose **Use example roles** or **Choose roles…**.
   These load the existing editable role-definition format. The role table
   permits an explicit model override on the existing ChatGPT login route.
   Select a row and choose **역할 상세…** to read its actual instructions,
   source collection names, configured tools and selected model.
5. In **Transmission**, explicitly allow question transmission if desired.
   Sources require individually allowed collections and the discussion's exact
   selected revision grants; results require both operator permission and the
   discussion's exact attachment grant. None is enabled automatically.
6. **Apply connection** saves the local operator settings and applies them to
   this same service when its current jobs/requests finish. Leave the dialog
   open for a deferred apply, or reopen and retry later. It never stops jobs.
   Cancel before Apply changes neither configuration nor discussion.
7. Back in the discussion, select the roles and explicitly enable the desired
   per-question scope. **Request round** is still the action that invokes a
   bounded model round. Setup does not request a test answer.

**Check local setup** verifies profile ownership, provider policy, executable
pin and the existing PowerShell 7 host path. Python package import readiness,
local file verification, authentication, model entitlement and inference are
separate rows. Missing authentication/entitlement remains UNVERIFIED; an
unavailable runtime is not replaced by a paid API or another provider.

OpenScience is the open-source execution tool, not a separate subscription
being requested by this checkbox. This supported setup uses the existing
ChatGPT login route through OpenScience 2.0.146 and openai-codex. Authentication
and access to a particular model still depend on that existing account.
No API key field, API fallback, account change or subscription purchase is added.
The profile's credential store is not read by setup. Its auth-only configuration
and binary pin retain the existing host's checks.

## What a displayed role contains

The materials/testing entries supplied in examples/workbench_experts.json are
editable examples: short instructions, collection names, tool choices and answer
sections. Their names do not establish trained expertise, an included specialist
corpus or a passed domain evaluation. The shipped definitions are unchanged.

The Connection table marks a definition as **예제** only when the whole selected
definition matches a shipped example; an ID/name alone is insufficient.
The main Expert participant list marks the same examples and offers
**역할 상세…** beside **Refresh roles**. Double-clicking a role also opens details.
The view shows the actual instruction text and lists collection names under
**자료 분류 (내용 미확인)**. Use **Sources** to inspect actual attached material.
The tool list is the role's configured list; request authorization and budgets
still govern use. The Connection detail uses the pending model override/default;
the main window reads the current service's role model. Neither action applies
settings, checks entitlement, submits a round nor changes the question.

## What Apply changes

The local native dialog edits the existing operator JSON file using a hash
check and atomic replacement. The usual Windows path is
%LOCALAPPDATA%/AutonomousCAELab/workbench-config.json. For a service started
with another explicit config, select that same file via **Status → Choose
service config…**. A path returned by HTTP is not used blindly as a write target.

Only the Expert runtime and inline role definitions are changed. Other operator
settings are preserved. The replacement ExpertRuntime reuses the existing
KnowledgeStore, literature store, callbacks and saved sessions. All document
owners, the Workbench session, unsaved Qt question buffers and existing jobs
remain. Role availability is refreshed without reopening the discussion. If a legacy
roles file is missing, Connection still lets you explicitly choose replacement
roles. Initial activation builds the replacement without trying to open that
missing old file. A rejected configuration-file choice disables Apply until
the actual service file has been read successfully again.

A service-side reload request accepts only the hash of the already saved,
CLI-bound local file. It accepts no runtime, model, policy, executable or path.
Model/HTTP callers cannot write or redirect that file through this endpoint.
Changing other operator keys requires an explicit ordinary restart; this dialog
does not force-stop a service. Unknown prior process cleanup also blocks reload.

Reload and final job admission share a short lock. Direct assistance calls
increment/decrement an active count but run outside that lock so scoped tools
can submit work on another thread. A cleanup-unknown exception blocks subsequent
reload. Active queued/running jobs are deferred, not cancelled.

The launcher still checks process/listener/store/source/dependency ownership.
After a hot apply it can reconcile only the config hash, requiring the same
service session and the exact in-memory applied file hash on every reuse.
This also rejects restoring an older file on disk without applying it, even
when that older file matches the launch receipt. A file merely saved on disk
does not satisfy that check. First launch binds the operator file path
even when it is initially absent. Windows receipt readers explicitly decode
UTF-8, including older receipts without a BOM; the rewritten launch receipt
matches the initial Windows PowerShell UTF-8 BOM format. Identity checks remain
exact after the second and third launcher invocation.

## Native Windows host

The existing bounded OpenScience host now invokes an installed PowerShell 7
directly on Windows. It does not run wslpath there. The existing WSL route keeps
its path conversion. Neither path installs a shell or invokes a provider during
setup. The existing pinned executable, ephemeral MCP tool allowlist, bounded
steps, source permissions and cancellation checks remain in the host.

Role-specific OpenScience model choices are now used by both the original call
and bounded correction call. Nested consultations select the target role's
model while retaining the common operator transmission policy and budgets.

## Focused verification and limits

### CoSTORM public literature retrieval — 2026-10-16

The saved materials/testing role names are instructions and tool permissions,
not separately trained CAE models. The actual pinned Stanford CoSTORM runner
coordinates perspectives, questions, evidence-backed turns, user interventions,
the mind map and reports. OpenScience runs the selected model and scoped tools.
The earlier actual OAuth clamp question was a **single-role response without
retrieved sources**; that successful answer did not establish RAG or CoSTORM.

In this adapter, the first configured participant selects the effective model.
The configured participants' instructions are combined in **one Completion/LM**,
reused by CoSTORM's question, answer, discourse, polishing, outline and knowledge
components. Generated perspective names/backgrounds and discussion histories are
saved runner state; they are not separate model processes, separately trained
specialists or independent authority. Configured roles retain their IDs,
collection lists and tool lists. Local retrieval uses their collection
intersection; every role must permit the relevant local/public/result reading
capability. A generated persona cannot widen those grants or select another
provider. Different configured role model overrides do not create separate
CoSTORM persona models through this adapter. A specialist corpus is still
supplied by explicit user-selected source revisions, not by the role name.

CoSTORM now connects its retriever to the existing free Crossref Literature API.
In **Connection → Transmission**, the operator must allow public search; the
discussion must separately enable its public-search scope. Every participating
role must have both `literature.search` and `literature.read`. With both search
grants, a discussion can start from a topic alone. Selected local revisions or
explicit result attachments can still support discussions without public search.
Importing the module, selecting sources, loading a saved discussion or viewing
its retained citations performs no external search or inference.

Each retrieval accepts at most two distinct queries and requests up to four
papers per query. Selected local BM25 hits and explicit calculation evidence
come before public rows. Search and each paper read consume the existing shared
tool budget; model steps retain their existing independent budget. The retriever
checks cancellation and the deadline around each operation and will not start
a new public search with 20 seconds or less left, matching the existing fetch
timeout. An in-flight existing fetch observes cancellation when it returns;
this change does not add a background network thread or a new search service.

The automatic public route explicitly reads **Crossref abstracts**, not publisher
full text. Each source retains its exact paper ID, DOI, URL, title, authors,
provider, actual read status/scope and archived segment locator; an absent
abstract is labelled bibliographic metadata only. Such titles and metadata do
not establish the paper's findings. Public empty/unavailable searches remain
visible in retrieval events and limitations. With no selected/result evidence
and no returned public evidence, the action stops without an article. Existing
Literature full-text access is a separate explicitly requested operation.

Public citation metadata and the actually read abstract survive CoSTORM turns,
mind-map citations, report references, Save and reopen. Opening a citation uses
the existing local archive reader, never a replacement DOI/network read.
Before another model step or retry reuses public text, both public-search grants
and the exact archive digest, paper identity, metadata and segment are checked
again. Withdrawal, missing archives or changed source bytes block reuse. Retry
retains each successful search/read operation immediately, even if a later
query/read is interrupted, alongside completed retrieval rows and the existing
completion journal. Replaying completed work does not search again or replace
its original abstract with newer metadata; failed/empty searches can be tried
again by explicit Retry. Replay events are labelled and do not consume another
tool operation. Source-integrity failures do not invalidate a valid model query.
The general model transmission checker does not itself treat a bare `paper_id`
as a grant: these checks are performed at the CoSTORM retrieval/restore boundary.

The focused tests use the actual vendored runner and document owner with
explicit network/model doubles: public-only start, permission/role refusal,
local/result priority, query/paper/tool/time limits, cancellation, missing
abstracts, failed searches, citations/report/save/cold read, archive corruption
and partial retry. They invoke no live model, credential store, paid search,
embedding service or vector database. This is a core connection change; no new
GUI or live public-search acceptance is claimed here.

Commands for the existing runtime:

~~~powershell
python -m pytest tests/test_expert_connection.py tests/test_expert_connection_ui.py -q
python -m pytest tests/test_server_config_encoding.py -q
python -m pytest tests/test_windows_desktop_launcher.py -k "applied_expert_config or reuse_checks_loaded_config or conflicting_owned_service" -q
python -m pytest tests/test_workbench_assist.py -k "openscience_step_reservation or openscience_host_cancellation or openscience_host_uses_utf8" -q
~~~

Tests use public pinned-file doubles, actual shared owners/HTTP/Qt where stated,
and stdlib launcher doubles. They do not execute a provider or read credentials.
They cover Cancel/Apply/reopen, local-write conflicts, unrelated-setting
preservation, pending work, question-buffer preservation, explicit permissions
and role/model selection. Existing Plan/Study workflows are reused.

Pro remote compilation, pytest, Qt, Windows PowerShell and live inference:
**NOT_RUN** (executor disconnected). Codex's Windows execution is separate
from source authoring. Neither setup nor role details establishes domain
expertise, full Co-STORM acceptance or engineering approval.

### Latest bounded integration report — 2026-10-13

Codex reported that the 81aa048 UTF-8 correction passed the three focused
Windows PowerShell checks: applied-config three-phase reuse, an older BOM-free
receipt and rejection of a loaded-config mismatch (5.13 seconds). The observed
cause was different default-versus-UTF-8 decoding of Korean store/source/config
paths. Existing identity checks remain in force.

Codex also reported one actual ExpertRuntime response through the existing
OAuth profile and openai-codex/gpt-6-astra: ANSWERED in 40.359 seconds, one host
call and zero tool calls, with session/result saved. The question concerned
checks before tensile fitting when units, section area and instrumentation
were unclear; no company data, source or result attachment was sent. This is
a reported live basic-response result, not a Pro remote run, a domain
qualification, GUI-wide acceptance, retry/cancel coverage or completion of E6.

The role-detail correction adds two focused Qt tests for the actual selected
definition/model, read-only Cancel, retained live question and selection across
polling. These new tests remain NOT_RUN by Pro. For this change only:

~~~powershell
python -m pytest tests/test_expert_connection_ui.py -k role_details -q
~~~

### Initial role loading correction

The initial registry request is retained when another worker or modal is busy.
Document polling yields to that pending read. A single queued callback drains
it after the current response has scheduled any explicit Save/Ask continuation;
it does not create a general request queue or repeatedly scan profiles.
Repeated waiting requests coalesce. A completed HTTP error stays visible and
does not cause an automatic retry loop.

The focused role-details test keeps 20 ms polling active and deliberately offers
the document poll the startup slot. An additional held-read test checks that a
pending registry read follows an explicit foreground continuation, occurs once,
and preserves the unapplied question. Existing wait limits are unchanged.

~~~powershell
python -m pytest tests/test_expert_connection_ui.py -k "registered_role_details or busy_registry_refresh" -q
~~~

Execution of this correction remains NOT_RUN in Pro's disconnected environment.

### Subsequent E6 execution reported by Codex

Codex reported an actual OAuth calculations.plan proposal, an editable Numerical
document changed from E=1000 to E=1500, a real FELUPE run, attachment of that
result to the original discussion, and an AI results.read call with an authored
stress explanation. Saving and opening a separate Qt process recovered four
turns and one run. The route used API helpers and offscreen Qt. It does not
establish OS-input acceptance, the complete Study path, cancellation coverage
or engineering qualification. This report is distinct from Pro remote execution.

The E1–E4 table below is the earlier source-handoff snapshot; its then-pending
execution entries do not supersede this separately attributed integration report.


## E1–E4 source handoff — 2026-10-13

This is the bounded source-delivery record for DELIVERY-BOUNDARY-20261013,
not another current task queue. Codex owns the live MoAI tasks, SPEC status and
CURRENT_STATE. The October 15, 2026 KST first Expert delivery target is an
estimate from that handoff, not a claim that the product or live round is done.

| Task | Submitted implementation / existing path | Remaining evidence |
|---|---|---|
| E1 — distinguish setup states | Connection separates configuration, package imports, profile/runtime files, authentication, model entitlement and inference. Actual roles and selected models are shown. | Changed Windows UI/readiness execution. Auth and entitlement remain UNVERIFIED; inference NOT_RUN. |
| E2 — select existing connection | Native directory/file choosers, profile/runtime/model and role selection, explicit example roles, Cancel before Apply. Rejected config paths cannot be applied. | Changed Windows Cancel/Apply/reopen checks and ordinary first-use view. |
| E3 — persist and safely apply | Local compare-and-swap save; same-service reload deferred while work is active; existing document owners/session retained; Windows invokes PowerShell directly without wslpath. Launcher always checks the loaded config. | Focused service/launcher/Qt execution; no remote PASS is claimed. |
| E4 — explicit transmission | Operator question permission plus collection/result/public-search choices; existing per-question and exact-source grants still apply. Setup performs no inference. | Focused policy/draft checks. No automatic grant or provider fallback. |
| E5 — actual bounded round, retry/cancel | Existing Request round, budget, cancellation and retained-failure path are reused. Role models reach original, nested and repair calls in the submitted code. | Actual authorized subscription round and its retry/cancel evidence have NOT_RUN in this delivery. Controlled host tests are not live inference. |
| E6 — proposal through calculation and back | Existing proposal → editable Plan → actual Numerical result → original Expert/Study return and reopen are reused. | The complete sequence beginning with E5's actual new round remains unverified here. Prior Numerical checks do not establish this whole sequence. |

### ANALYZE — inspected boundaries

The existing SPEC-EXPERT-002, Expert window, RuntimeConfig/ExpertRuntime,
OpenScience host, Workbench assistance/job admission, server routes/client,
Windows launcher and focused tests were read before changing their boundaries.
The implementation uses the existing local operator file and owners.

The material choices are same-service runtime replacement instead of killing
or restarting active work; a local native config writer plus a fixed-file,
hash-only reload endpoint instead of remote configuration writes; and explicit
role model selection through the existing bounded host instead of a new provider.

### PRESERVE — behavior that the changed tests protect

The submitted tests retain unrelated operator keys, live edited questions,
existing documents and service identity; distinguish saved from applied config;
defer for active jobs; reject stale writes and the wrong config file; and preserve
the common transmission/budget restrictions through role-specific model calls.
The existing cancellation/UTF-8 host tests use an explicit host-command double
at the changed shell-selection boundary. There is no live provider in those tests.

This record does not claim a pre-change or post-change test execution in Pro's
disconnected environment. Tests are authored and published; Windows execution
belongs to Codex's integration record.

### IMPROVE — planned versus actual files and scope

Source commits are **eab4216433f192a9b6929949dff5f7625d548c2e** followed by
**c9af9f252bf38fd40bb1fbcab78cfe66e3213034** on
codex/expert-connection-20261013.

| Planned boundary | Actual files | Scope decision |
|---|---|---|
| Native setup and draft preservation | apps/research/expert_connection_dialog.py, apps/research/expert_window.py | One connection dialog, existing window/actions retained. |
| Local settings and safe current-service apply | caelab/expert_connection.py, caelab/workbench.py | One local config helper; existing assistance, stores and job admission reused. No new persistent owner/store. |
| Client/server access to current connection | caelab/workbench_client.py, apps/lab/server.py, apps/lab/workbench_routes.py | Read-only status and fixed-file hash-only reload; trusted startup binds the config path even when initially absent. |
| Existing host and role models | caelab/assist/openscience_host.py, caelab/assist/experts.py | Native Windows shell path and effective role model; existing permissions, source scope and bounded host retained. |
| Launcher reuse | scripts/start-windows.ps1 | Necessary lifecycle change: verify the service's applied config/session on every owned reuse. Existing store/source/process/dependency guards retained. |
| Changed-path checks | tests/test_expert_connection.py, tests/test_expert_connection_ui.py, tests/test_server_config_encoding.py, tests/test_windows_desktop_launcher.py, tests/test_workbench_assist.py | Setup/repair/Cancel/Apply, active work, config identity, shell seam and model routing only. No broad solver or provider campaign. |
| Feature usage | docs/EXPERT_CONNECTION.md | Expert-specific usage and this source handoff. General README, INSTALL_KO, USER_GUIDE_KO, CURRENT_STATE, SPEC and task mapping remain Codex-owned. |

The read-only correction review at c9af9f2 closed the three identified setup
issues: loaded-config reuse, missing legacy roles and rejected config-path Apply.
That is source review, not Windows execution or user acceptance.

The repository's MoAI connection/configuration documents were read. The installed
MoAI run workflow files and execution tools are not accessible in this Pro
session; the executor is disconnected and no MoAI tool is exposed. Therefore
the ANALYZE–PRESERVE–IMPROVE record above is the actual authoring discipline,
not a fabricated completed MoAI run. Codex operates the installed workflow and
live backlog. No optional improvements, general installation changes or new
dependencies were added for this handoff.
