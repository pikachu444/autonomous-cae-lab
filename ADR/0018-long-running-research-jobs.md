# ADR 0018 — Long-running operations and separate verification scheduling

Date: 2026-10-02. Status: implemented, focused source/transport checks passed;
native lifecycle and numerical acceptance remain open.

## Decision and reason

The owner asks for remaining development/integration first, in phase order,
with full benchmarks consolidated separately. A slow solve is not numerical
failure. The historical CPU120/wall180 defaults interrupted the roof solve;
an uncommitted CPU300/wall420 replacement is preserved as a rejected proposal.
Neither increasing that short fixed cap nor repeating the same solve is the
current development task. Preserve the original failures and all thresholds.

Reuse apps.lab.service.LabService for three additive MCP operations:
research_job_start(operation, arguments), research_job_inspect(job_id), and
research_jobs_list(). The existing allowlist, argument checks, selected store,
single writer, result and error retention apply. One lazy resident binds the
exact configured store for its lifetime. Existing synchronous MCP writers share
admission with asynchronous submission; readers remain available. No second
numerical engine, experiment store, persistent queue or engineering rule is added.

All three Code_Aster adapters read local execution policy once per solve,
separately from physical settings/model declarations. Environment options are
CAELAB_CODEASTER_TIME_LIMIT_SECONDS (positive native time_limit, default86400)
and CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS (positive wall budget; absent=None).
The86400 default follows the pinned17.4 runner; it is not unlimited. Zero is
refused: the official runner clamps its CPU ulimit to at least one second.
The existing memory/mesher/probe controls remain. Record the resolved policy
before external processes; freeze it in parameterized-model runtime identity.

The shared native process helper retains live stdout/stderr, actual child PID,
RUNNING and terminal execution state. A requested wall budget stops the owned
Linux session/process group and preserves partial files as BUDGET_EXHAUSTED.
Observed native CPU-limit markers are distinguished from other nonzero exits.
Core keeps its existing FAILED_EXECUTION compatibility and unavailable metrics;
resource exhaustion is not a strength/physical verdict or a numerical PASS.

## Alternatives and boundaries

A new job engine would duplicate the existing local service. Daemon-thread
termination is not safe solver cancellation. Cancellation, restart recovery,
cross-process coordination, native Research profile admission and lifecycle
ownership for background jobs therefore remain explicitly unsupported/open.
Keep the resident alive while its jobs run; a job ID is not restart durability.
The new tools are source/local-stdio capabilities, not a live native OpenScience
acceptance. Do not broaden historical guarded profiles merely from this ADR.

Develop subsequent capabilities in phase order while retaining their numerical
verification queue. Essential changed-code rejection/concurrency checks remain
mandatory. A missing prerequisite blocks dependent invalid execution and PASS/
release claims, while independent feature development continues.

## Evidence and requirement impact

Focused local Python3.12 checks:197 execution/structural/plasticity/job checks,
103 elasticity/resident-identity checks and one actual stdio job round trip,
301 total PASS. Tiny local subprocesses test supervision; native field tests
are synthetic. No new native solver/provider calls or benchmark qualification.
A supplemental broad model suite was deferred after84 passes and an explicit
Root-scoped interruption; its unfinished cases remain queued, not PASS.
The source review found no required P1/P2 corrections; cancellation/lifecycle
limits above remain. Exact new-source CI is reported separately after publication.

R02/R08/R09/R11/R21/R25/R43/R45/R51/R52 advance through reusable execution and
transport controls. All52 descriptions, Domain/Core/adapter boundaries, pinned
fixture behavior, model/auth choice, physical inputs and thresholds remain.
Record: benchmarks/records/20261002-long-running-jobs-development.json.

## Pinned source references

[run_aster default](https://gitlab.com/codeaster/src/-/blob/50ebc13c70ee9df62faf93ddcb746a3757b3042a/run_aster/run_aster_main.py#L415),
[time_limit to tpmax](https://gitlab.com/codeaster/src/-/blob/50ebc13c70ee9df62faf93ddcb746a3757b3042a/run_aster/export.py#L488),
[CPU ulimit](https://gitlab.com/codeaster/src/-/blob/50ebc13c70ee9df62faf93ddcb746a3757b3042a/run_aster/run.py#L217).
