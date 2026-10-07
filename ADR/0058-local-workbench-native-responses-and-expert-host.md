# ADR0058 — Local workbench responses and scoped expert host

Status: accepted for the R1–R5 integration; actual acceptance is recorded in
`docs/WORKBENCH_PROGRESS.md`, including failures and incomplete gates.

The W1–W5 shared job controller remains the execution owner. Direct Python,
HTTP forms and MCP use the same job/result identifiers. The optional research
agent proposes and interprets work; SciPy generates and evaluates candidates.
No second scheduler, solver profile system or numerical optimizer is introduced.

Native results retain their original outcome and files. Pure readers expose
named physical channels with units, components, location, axes, coordinate
system and source hash. A selected response is resolved only below the job's
own native directory. Selected row reads keep unrelated arrays as hashed
references. Restarted readers require retained bytes, not a working solver.
Scalar solver metrics alone were rejected as evidence of history integration.

External execution is operator registration. Candidate requests contain numeric
values and test conditions; programs and paths are not model authority. Source
decks/includes are preserved, and explicitly registered token/column patches
are the only substitutions. Native material preparation similarly receives an
operator-registered verified library and controller-owned preparation directory.
It is independent of the historical fixed qualification run. Current prepared
law coverage is Elasticity with two coefficients and a reset zero initial state.

SciPy DE dispatches objective and constraint candidate batches together. Each
worker owns its prepared resource. Completed evaluations are journaled even
when cancellation or a failure stops subsequent dispatch. Compact response
reductions support later numerical analysis without retaining every full curve
in memory. Failed incumbents cannot become successful fits through cache eviction.

The optional `openscience` provider uses the installed official CLI and its
existing authorized ChatGPT profile. It does not extract OAuth credentials or
present them as API keys. A short-lived authenticated loopback MCP bridge exposes
only the selected expert's tools. The CLI has a temporary isolated configuration,
all other tools/delegation denied, a bounded deadline and owned process cleanup.
Windows has no native sandbox backend for this route; tool allowlists, scoped
callbacks, loopback authentication and fixed operator executable identity form
the boundary. This is not arbitrary shell authority or a general remote service.

The workbench retains authorization for documents, results, public discovery,
consultation, backend, variable bounds and calculation resources. These scopes
cannot override operator policy. Calls are serialized to make budget accounting
atomic; caller input cannot rebind internal tool names. Numerical submissions
enforce the evaluation budget, including UQ. A dedicated expert orchestration
slot avoids starving child jobs in a one-slot numerical controller.

Tests cover native identity restoration, bounded reads, real parallel evaluation,
failure/budget journals and approval bypasses. Actual external calculations,
native histories and MFront independent analytical comparisons are required in
addition to these tests. A live model turn, actual host, GUI actions and restart
must be verified separately; mock generators and CI do not satisfy those gates.
These changes advance ledger research/execution/provenance requirements without
removing the 52-section scope. Physical, strength, durability and company
deployment qualification remain UNKNOWN/NOT_RELEASED.

The current bridge uses the official MCP SDK Streamable HTTP transport in an
owned loopback server thread with a per-invocation bearer secret, stateless JSON
responses and serialized callbacks. The execution cancellation context is
explicitly transferred to that thread. Host cancellation must return a valid
`cleanup_confirmed` receipt after owned process exit; a missing/false receipt
is a cleanup failure, never a confirmed CANCELLED result. Windows stdio startup
races motivated this transport choice rather than modifying the installed CLI.

For this CLI provider, `model_calls` conservatively reserves maximum agent steps
across parent, consultation and one no-tool answer repair. It is not a measured
count of billed provider requests: the host may make auxiliary title/summary
requests (`provider_auxiliary_requests_counted=false`). Evaluation/tool budgets
are enforced separately. Temporary host configuration disables unrelated
research-continuation harnesses so a structured answer can end the bounded turn.

Independent final review found that the official CLI's `durable-jobs` harness
also invokes `resumeInterrupted()` at bootstrap. A later invocation revived a
previously cancelled internal session despite confirmed prior process exit.
The per-turn overlay therefore explicitly sets `durable-jobs=false`, preserving
all tool denials and delegation-off. Old sessions/credentials are not deleted or
copied. Actual subsequent logs must verify no automatic session revival; PID
absence alone does not prove this continuation boundary.
