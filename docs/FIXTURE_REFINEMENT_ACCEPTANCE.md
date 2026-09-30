# Predeclared multi-generation fixture refinement

Implementation baseline: `d36387b309e6e0938e53c170415d0b210c4ee2e7`, with
the unchanged fixture submodule `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
Actual native acceptance is **PENDING**. The original nine-evaluation,
one-generation proof remains unchanged; this document does not upgrade it.

This Phase 3 acceptance reuses `Lab.plan_optimization/run_optimization`, the
public SciPy differential-evolution adapter, pinned CadQuery implementation
and Gmsh/CalculiX adapter. OpenScience chooses the question, objective and
budget. The numerical engine chooses every candidate. There are no Core,
adapter, schema, registry, upstream or public-contract changes.

The predeclared seed is 13, population size 5, maximum generations 5 and initial
width 28 mm, with registered width bounds 28–42 mm. Minimize valid measured CAD
volume under `max_displacement <= 0.0065 mm`, with normalization 0.0065 mm.
Use the existing **ASSUMED_NOT_MEASURED** orthotropic material, illustrative
100 N per support, fixed bottom and central 24 mm area-weighted saddle load,
and 2/1.5 mm meshes. Require the unchanged 5% displacement trend and 1% signed
reaction gates. Gmsh and CalculiX retain 180/300-second process timeouts.

The maximum is 30 campaign CAD experiments and 29 solver children; adding one
38 mm baseline gives 31 CAD experiments, 30 children and 60 mesh solves. These
counts concern immutable public experiment IDs, including the rejected CAD
attempt; the parameter registration's fixed geometry-effect probe is additional
setup, and adapter-internal CAD checks are not counted as separate experiments.
SciPy uses one worker. The acceptance process sets two-CPU affinity and an
inherited address-space limit at most 8 GiB. An external supervisor starts a
dedicated POSIX worker/session and enforces a fixed whole 5,400-second deadline.
Its kernel PID/start-tick/session/group identity is retained and verified before
terminating only that owned group on timeout. A blocked native CAD call cannot
defer its SIGKILL. Task-local subreaping collects terminated child descendants;
bounded exit/reaping can take up to ten additional seconds. An unexpected orphan
after a zero worker exit is a supervision failure, with owned cleanup retained.
The worker also retains a cooperative watchdog for normal Python execution.
An 8 GiB store-size check runs before/after native operations and at finalization.
This is a boundary check, not an instantaneous disk quota or combined machine
memory limit. No timeout is relabeled as infeasibility.

Before actual experiment execution, retain clean Git/Core/script identity,
every tracked repository/upstream source file and its actual working bytes,
material SHA, executable paths/SHA/version output, resource settings, registry
and complete frozen plan. Recheck identities before and after each native
operation. Shared-library closure is not claimed from executable SHA alone.
Do not edit this checkout until the acceptance stops.

A retained read-only preflight probe found that the installed CalculiX 2.21
`ccx -v` prints its valid version and returns 201. The verifier records this
query return code explicitly and accepts only the bounded version-text/status
convention. Actual solves still require the original adapter's exit-zero and
raw-result/numerical checks. This version query is not native acceptance.

Interrupt immediately before the eighth actual campaign CAD experiment. Retain
the first seven complete CAD/child trees, their ledgers, all prefix candidates
(including the pending eighth), journals, checkpoints, plan and registry hashes.
Preserve exact snapshots of the mutable latest-state and optimization ledger.
Resume using a **fresh Lab instance**; require the first seven observations and
all their old bytes/trees to stay unchanged, with no repeated native calls.
Then reuse/inspect completion with all six adapter maps empty and require the
whole retained store to stay byte-identical during that reuse.

The existing X-hole relation requires
`width > bolt_pitch_x + hole_diameter + 2*edge_land = 28.5 mm`.
Equality is rejected. The analytical volume is
`40*26*width - pi*4.15^2*40/2 - 4*pi*2.25^2*26`, with the existing relative
identity limit `1e-9`. This geometric lower bound is not an admitted optimum or
a certificate that every other numerical constraint is satisfied there.

For each evaluation, check actual analytical CAD volume, exact parent/consumed
STEP SHA, two mesh policies, raw numerical limits/checks, constraint residual,
null unusable feedback, UNKNOWNs and NOT_RELEASED. Retain the independently
reconstructed incumbent volume, `width - 28.5 mm` and
`0.0065 mm - measured displacement` after every evaluation. Report actual
generations; claim multigeneration only for at least two. Report adaptive
refinement only if a later member improves the best feasible initial-population
member; otherwise report **NOT_OBSERVED**. Do not assume displacement is active,
claim a global optimum, change limits, or substitute diagnostic stress.

Execution with the existing WSL environment:

```powershell
.\scripts\local.ps1 -PythonArgs @('-m', 'scripts.verify_fixture_refinement',
  '--store', 'artifacts/local-20260930-fixture-refinement-clean-01')
```

The store and its sibling `<store-name>-supervisor` must be new. Supervisor
stdout/stderr and immutable request/ownership/result records stay in that sibling
until the worker exits, then are copied without change into
`acceptance/supervisor/`. A separate final supervision/store manifest covers
those stable logs and the original worker report; no earlier manifest is edited.
Raw editable CAD, meshes, decks, DAT/FRD, logs,
experiment/optimization ledgers, exact source snapshot, frozen plan, prefix
manifest, per-evaluation proof/history and final full-store inventory remain
there. The final manifest lists all files before its own creation and the final
acceptance report; those two have separately recorded hashes. Remote permanent
raw retention is a separate requirement.

Implementation and independent static review precede a clean local commit and
native execution. A later evidence commit records the exact execution source,
actual outcome, failure attempts, retention hashes and independent proof review.
Root owns shared status documents, integration and publication.

The initial pure witness/engine cases passed 64 tests in 2.87 seconds. The first
static review required an external process watchdog because Python SIGALRM is
cooperative during native CAD. After that correction, 67 pure witness/engine
cases passed in 4.02 seconds. A later targeted run retained one startup failure:
the kernel reported an exec-loading process in state D with transiently empty
`/proc/cmdline`; exact PID/start/session/group identity stayed owned and cleanup
succeeded. The corrected startup waits at most five seconds within the unchanged
overall deadline, requiring that same kernel identity and the exact launch argv.
68 pure witness/engine cases then passed in 4.32 seconds, including a forced
empty-argv regression, libc-sleep-blocked worker with child/grandchild cleanup,
and zero-exit orphan refusal. No native solver/CAD calculation is claimed from
these tests. Renewed independent static review is **PASS**, with no open P1/P2,
at verifier working SHA `226218feb79f09484f0e7a13168ebfb96c829c14fdf6c2b474df9e517a627d6d`
and test SHA `67ea04b10c02043f2d5430bbad6135dc667f828c324087a89940dfd1809ae4e8`.
It checked the 40 retained supervision-witness files and failure/test-log hashes
read-only; it executed no tests/native. Actual execution remains pending.

All engineering qualification remains UNKNOWN and every decision NOT_RELEASED.
This bounded acceptance advances R03/R11/R18/R20/R27/R34/R43–R52; it does not
complete Phase 3 or the seven-phase project. See [OPTIMIZATION](OPTIMIZATION.md),
[ADR 0005](../ADR/0005-adaptive-numerical-optimization.md) and
[the unit record](../benchmarks/records/20260930-fixture-refinement.json).
