# Resume Autonomous CAE Lab locally or in a new session

## Start here

Repository: [pikachu444/autonomous-cae-lab](https://github.com/pikachu444/autonomous-cae-lab).
Continue from its current `main`; do not rebuild the project from the original
prompt. Read `AGENTS.md`, `PROJECT_SCOPE.md`, `CURRENT_STATE.md`,
`ARCHITECTURE.md`, ADRs and `openscience/contract.md` before editing.

The same code and project state can be resumed on a new computer/session using
Git. The running cloud shell, in-memory Python state, live agent tasks and
installed binaries are not transferred by cloning. This file is a durable
handoff record, not a claim that the model retains every past chat forever.

## Verified checkpoint

- Last fully verified **code** commit:
  `dad581fea4fb8e20d26d329ed53592f2897dfd05`.
- [CI 36641675306](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36641675306):
  core, native FreeCAD, structural and DOE all succeeded.
- Local Core tests: **32 passed**. Native/mesh/solver execution occurred in
  Ubuntu CI; FreeCADCmd/Gmsh/CalculiX are absent from the cloud development
  container. Do not report those solver runs as local execution.
- Evidence recording commit:
  [691d639](https://github.com/pikachu444/autonomous-cae-lab/commit/691d639af25a71a09a0c3474d1c4d1d5abbb7437).
  Later documentation commits do not alter that numerical proof reference.
- Pinned fixture dependency:
  `plugins/fixture_design/upstream` at
  `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
- Canonical 38 mm support: 3→2 mm displacement change **2.3361%**.
  Three valid seeded DOE proposals: **1.8660%, 1.3669%, 3.8451%**.
  All pass the unchanged 5% preliminary displacement screen and signed
  reaction checks. One invalid CAD proposal was blocked before a solver child.
- Overall decision: **`NOT_RELEASED`**. Material/load/fixed base are assumptions;
  stress is invalid for strength release; machine/physical/fatigue checks are
  unknown. DOE is not an optimization optimum.

Machine-readable evidence is committed in
`benchmarks/records/20260930-area-load.json`. Detailed earlier runs and the
failed CLOAD parser attempt are in `docs/STRUCTURAL_SCREEN.md`,
`docs/DOE_CAMPAIGNS.md` and ADR 0004. Do not overwrite or relabel older runs.

## Code ownership and implemented operations

- `caelab/`: common schema, Lab engine/API, CLI, parameter registry, append-only
  stores/ledgers, campaign journal and typed contracts.
- `caelab/adapters/`: CadQuery/FreeCAD bridges, fixture CalculiX child-run and
  saddle-load implementation. Fixture assumptions stay behind adapters.
- `caelab/optimizers/scipy_lhs.py`: deterministic continuous Latin hypercube
  sampling with recorded seed/version. No actual numerical optimizer yet.
- `plugins/fixture_design/upstream`: tested fixture source, native worker,
  domain rules, browser GUI and exporters; pinned submodule, not copied code.
- `openscience/`: common research operation contract and local stdio MCP.
  Transport round trip is tested; live OpenScience agent loop is unverified.
- `schemas/`, `tests/`, `scripts/`, `docs/`, `ADR/`: contracts, regressions,
  acceptance execution, evidence/research and decisions.

Public operations currently include study create/inspect; native new/import/
inspect/select-final; parameter discover/register/list/refresh; CAD experiment
run/inspect/summary/compare; structural child run; DOE plan/run/inspect. API,
CLI and MCP use the same Core. The basic `report` CLI returns a research
summary. Full research-report generation, PDE/optimization/unified UI/HPC/
physical operations remain scope requirements, not completed capabilities.

## Local checkout and core verification

These commands create a new checkout and isolated Python environment. For an
existing checkout, first inspect/preserve local changes, fetch/pull normally,
and update submodules; do not reset work blindly.

```bash
git clone --recurse-submodules https://github.com/pikachu444/autonomous-cae-lab.git
cd autonomous-cae-lab
git submodule update --init --recursive
python3.12 -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS, or
`.\.venv\Scripts\Activate.ps1` in PowerShell (use an installed Python 3.12,
for example `py -3.12 -m venv .venv`, on Windows). Then:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/verify_mcp.py
python -m caelab --store runs/local-demo demo
python -m caelab --store runs/local-demo inspect --experiment E-demo-width38
```

`runs/local-demo` must be new. On rerun use a new directory/experiment ID;
existing immutable IDs intentionally cannot be overwritten. Dependency setup
needs package network access. Python/Core success on a new OS does not prove
native/solver deployment on that OS.

For native acceptance, configure a working `FREECAD_CMD` (see the adapter and
`docs/NATIVE_ACCEPTANCE.md`). The CI workflow provides a pinned FreeCAD 1.1.4
Linux AppImage/wrapper with a checked SHA-256. Do not assume that wrapper is a
Windows/macOS installation recipe. With the prerequisite configured:

```bash
python -m scripts.verify_native --store artifacts/local-native
```

With `gmsh` and `ccx` executables installed and available, run fresh stores:

```bash
python -m scripts.verify_analysis --store artifacts/local-linear
python -m scripts.verify_doe --store artifacts/local-doe
```

Reference installation/execution details are in
`.github/workflows/caelab-ci.yml`. Latest verified Ubuntu CI observed Gmsh
4.12.1 and CalculiX 2.21. A different version/platform needs its own recorded
acceptance. Install only the prerequisite for the next benchmark; keep Core
and adapter boundaries intact.

## Evidence transfer and retention

Git carries source, ADRs, scope/state and committed benchmark summaries.
Generated experiment stores, native CAD, meshes and raw results are **not
automatically in a clone**. CI keeps them as downloadable artifacts with
30-day retention. The verified structural and DOE ZIPs expire around
**2026-10-29 UTC**; IDs, precise expiry and SHA-256 are in the benchmark record.

To inspect those exact historical runs locally, download their artifact ZIPs
from CI before expiry, verify the recorded SHA-256, extract each into its own
store and use `Lab.inspect_experiment`/`Lab.inspect_doe` to verify ledgers and
individual artifact hashes. Alternatively rerun acceptance to create **new**
evidence and record the new commit/versions/run IDs; a regenerated STEP may
contain different serialization timestamps, so do not claim byte equality
across distinct runs. Each child must match its own immutable parent's STEP.

Open work: archive important raw evidence in a durable artifact store, with
retention/provenance references. Do not silently embed potentially proprietary
CAD/results in this currently public Git repository.

## Next concrete work, in order

1. **Finer saddle-load verification:** extend the canonical benchmark with a
   1.5 mm mesh, retaining the same CAD revision, material, load patch, 100 N,
   fixed-base definition and unchanged numerical limits. Record patch area,
   lip fraction, max loaded-node response, signed reactions, artifact hashes
   and reference/approximation limits. If it fails, diagnose rather than
   relax the screen. Current piecewise linear surface integration is not an
   exact quadratic boundary rule or physical roller contact.
2. **Actual numerical optimization:** define reproducible objective/constraint
   semantics, invalid-design/failure policy and restartable optimizer state;
   run a bounded fixture acceptance through existing CAD/analysis Core.
   Keep LLM research reasoning separate from numeric candidate generation.
3. **General PDE slice:** select/test a canonical user weak form via a real
   FEniCSx or evidence-supported adapter; verify analytical/reference error
   through the same common result/evidence contract.
4. In parallel where supported: live OpenScience MCP agent acceptance;
   arbitrary GUI-edited FCStd refresh/index drift and registration transaction
   review; durable raw-artifact retention and corporate license/security review.
5. Then Code_Aster nonlinear reference benchmarks, OpenRadioss explicit
   preprocessing/impact and the advanced research/physical phases listed in
   PROJECT_SCOPE. Do not declare those phases complete from a research table.

## Blockers and unresolved assumptions

- Earlier full Project chats were unavailable; the original OpenScience
  identity is not confirmed. Synthetic Sciences OpenScience is a provisional
  researched target. Its CLI v2.0.145 failed a PID `/proc` identity check here.
  Verify the actual local product/config/tool trace rather than implying the
  local MCP test was a live agent success.
- Native template acceptance does not cover arbitrary imported FCStd topology,
  Sketcher dimension index changes or cross-file atomic registry transactions.
- Idealized linear fixture screen does not validate bolts/roller contact,
  material allowables, stress convergence, fatigue or physical load tests.
- Upstream root license is missing; corporate redistribution/linking and
  backend license/security reviews remain incomplete. Supplied repo is public.
- Local dependencies/solvers/credentials must be established on the user's
  computer. This cloud agent currently cannot manipulate that local computer.

## Prompt to start the new local session

The continuity documents were independently reviewed, read-only, against the
CLI, CI workflow, benchmark record and existing architecture/acceptance notes.
The question was whether any retained requirement, progress claim or resume
command materially misrepresented the project. No blocking issue was found.
Root also checked that all 52 original section IDs occur once in order and
that relative document links resolve. This is document verification, not a
new numerical benchmark; the code proof remains the checkpoint above.

> Continue Autonomous CAE Lab from this repository. First read AGENTS.md,
> PROJECT_SCOPE.md, HANDOFF.md, CURRENT_STATE.md, ARCHITECTURE.md, all ADRs and
> openscience/contract.md; inspect git history/status and current CI. Preserve
> the original 52-section scope and reuse the pinned fixture implementation.
> Report the recovered checkpoint briefly, then continue the next acceptance
> gate in HANDOFF.md with meaningful commits. Do not rebuild completed work,
> treat UNKNOWN as PASS, or substitute solver success for engineering release.

After each meaningful unit, commit/push authorized changes and refresh this
handoff/state/evidence. Repository instructions plus this explicit startup
prompt make recovery checkable; they do not create an absolute memory guarantee.
