# ADR0045 — Cancelled results and consistent research read semantics

Status: implemented; source controls and fresh actual acceptance tracked separately.

## Trigger and decision

Clean8731's real numerical campaign completed nine CAD/CalculiX children with
revision-owned conditions. Its AI reader chose the existing full experiment
inspection rather than the summary. Only summaries carried adapter-owned response
definitions, and the answer incorrectly called loaded-saddle maximum |UZ| a
whole-field |U| maximum. The original answer and numerical records are retained.

The existing full MCP inspection now uses Core research_inspection: the canonical
verified result plus the same optional verified conditions, observation context
and adapter-owned metric_semantics as the summary. inspect_experiment remains the
canonical stored-result reader. Transport context is not persisted, used as the
result hash, or admitted as replacement solver evidence. No new tool, arguments,
profile, provider, model or numerical response is introduced.

The same actual run cancelled a live owned CalculiX child and retained its output
and CANCELLED receipt. HTTP reported cancellation while Core's broad exception
handler reported FAILED_EXECUTION. Core now distinguishes ExecutionCancelled from
execution failure across CAD, parent analysis, declared models and PDE. The common
result status enum adds CANCELLED; all old statuses and historical records remain.
Cancelled native analyses report solver_status CANCELLED, no convergence verdict
or completed metrics, retained partial artifacts, unresolved qualification and
NOT_RELEASED. CAD cancellation leaves solver NOT_RUN. Declared inputs may prepare
a new experiment; partial responses cannot serve as a completed CAD/solver parent.

ExecutionCleanupFailed propagates without a completion seal. A pending live child
cannot release ownership or finalize an artifact manifest that it may still write.
Saved PIDs/receipts grant no kill, adoption, replay or reconnection authority.

## Alternatives, scope and verification

Changing metric IDs/numbers, rewriting old answers or requiring the AI to choose
only one read tool would hide the integration defect. Mapping cancellation to
REJECTED or FAILED_EXECUTION conflates user intent with model/numerical failure.
The additive lifecycle state preserves those distinctions; strict external
consumers must accept the added enum before consuming newly cancelled records.

Portable fixture stress controls mock the owned-command boundary and forbid real
child creation; they remain TEST_ONLY rather than physics evidence. Lifecycle
controls launch owned Python children and exercise all four Core routes, partial
output, parent immutability and unconfirmed cleanup. Research read controls check
the shared response definition and reject changed condition artifacts. Fresh
approved-provider reading and actual native cancellation are separate gates, with
their exact producer/reader commits, outcomes and raw evidence recorded.

R09–R13/R19–R21/R43/R48/R51 are advanced within the larger G3/G4 bundle. General
CAD FEA, assembly mechanics, broader Phase1–7, provider reconnection and deployment
remain open. Physical UNKNOWN, invalid stress and NOT_RELEASED are unchanged.
