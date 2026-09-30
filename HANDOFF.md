# Resume Autonomous CAE Lab locally or in a new session

## Declared-input route continuation

The additive model-input implementation passed a fresh clean-source native
campaign at `9330055`. `scripts.verify_model_optimization` ran in a new store:
Code_Aster E in 100000–300000 MPa, measured axial displacement objective,
unchanged numerical gates, seed13/population5/one generation/at most10 unique
evaluations. The script preserves an interrupted first two candidates, resumes
without rerunning them, and verifies completed reuse with no live adapters.
The 224 regression tests and 26-tool MCP checks passed. Actual native acceptance
passed nine candidates / eighteen mesh solves and exact two-evaluation replay,
with MAX_GENERATIONS and no convergence claim. Independent native inspection
and the new integrated-source CI are pending. HTTP bindings passed fifty server
tests. Continue the remaining optimization/PDE/contact/inverse gates.

## Start here

Repository: [pikachu444/autonomous-cae-lab](https://github.com/pikachu444/autonomous-cae-lab).
Continue from its current `main`; do not rebuild the project from the original
prompt. Read `AGENTS.md`, `PROJECT_SCOPE.md`, `CURRENT_STATE.md`,
`ARCHITECTURE.md`, ADRs and `openscience/contract.md` before editing.

The same code and project state can be resumed on a new computer/session using
Git. The running cloud shell, in-memory Python state, live agent tasks and
installed binaries are not transferred by cloning. This file is a durable
handoff record, not a claim that the model retains every past chat forever.

## Current continuation

Latest exact remote execution proof is main `0535e37`,
[CI 36694913981](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36694913981),
all eight jobs successful, including J2/MFront/OpenRadioss. Downloaded full
archive inspection is underway. Previous completed archive proof is `7c66006`,
[CI 36686065707](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36686065707),
seven successful jobs / 513 tests. Its Code_Aster archive fully verifies three
experiments / 144 artifacts with hidden cache files. Fresh clean HTTP repair
also passed at d0473e4, including the 71.001909-second optimizer inspection and
six full evidence ZIPs. Older failed/incomplete attempts remain preserved.

New material-point, J2 plasticity and explicit adapters are integrated after
independent native/source reviews. Defaults, CLI/MCP common model operation,
HTTP presets and launcher are connected; 69 integration regressions plus four
actual HTTP backend admission tests pass.
Their exact-source CI at `0535e37` passed. Explicit flight passes; both ideal
wall histories remain REJECTED. Never promote PARTIAL contact to Phase6 success.
Review docs/MATERIAL_POINT_ACCEPTANCE.md, PLASTICITY_ACCEPTANCE.md and
EXPLICIT_DYNAMICS_ACCEPTANCE.md for exact native source identities and limits.

Continue Root's declared-input numerical campaign, nonlinear manufactured PDE,
separate compliant-stop reference and synthetic-reference material inverse
benchmark. Keep common interfaces Root-owned and source frozen during campaign
tests/native acceptance. Sixteen worker raw stores are retained in
`artifacts/integrated-20260930-worker-evidence/`; all 2,268 payload files and the
15 final common experiment records passed inspection. Originals remain untouched.

Official OpenScience live05 and its served GUI now show actual MCP execution and
AI interpretation. The local Lab is a direct execution UI; it has no AI chat.
Live05 used a supported persistent server/attached CLI and the unchanged local
model; its staged workflow and mixed-source identities are explicitly recorded.
Physical, material, strength, durability, full contact and HPC gates stay open.

## Earlier verified checkpoint (historical)

**Latest source and active work:** main `03bfd7115ca3933cb18af17c55cc751839e91c98`
passed [CI 36676495776](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36676495776)
(seven jobs, 506 tests) and fresh local clean Code_Aster acceptance (three
experiments). Independent raw archive inspection found two missing hidden cache
files, so full CI archive integrity is 43/45 experiments plus three campaigns.
The upload correction and campaign inspection performance repair have focused
verification, but their new exact-source CI and fresh HTTP proof are pending.
HTTP clean-01 failed the unchanged 180-second optimization campaign request;
do not label it complete. Read
[the repair record](benchmarks/records/20260930-connected-inspection-repair.json).
Continue fresh corrected HTTP acceptance, actual material/plasticity/explicit
gates, declared-model numerical optimization, then remaining phases. Worktree
native failures are preserved; no material/contact/strength release is implied.

`d0473e4` CI 36683183680 failed due to synthetic test campaigns leaking into the
shared overview fixture (512 tests passed; six native jobs skipped). The test
isolation repair requires new exact-source CI. HTTP clean-02 runs independently
against frozen d047; do not change main until that acceptance finishes.

**Primary work continues across all 52 requirements.** The checkpoint below
is not a stopping condition. Root resumed actual OpenScience and independent
Code_Aster/model-Core work after correcting an earlier premature stop. Read
[CONNECTED_CONTINUATION](docs/CONNECTED_CONTINUATION.md) and ADR 0007 for the
runtime, failed drafts, tested contracts and next actual gates. Installation,
transport and exit codes alone do not establish a new research/numerical proof.

**Current primary priority:** after the user's challenge about Code_Aster
over-concentration, connect the existing research/CAD/solver/numerical/PDE
operations in `apps/lab/` and verify common reports/bundles. Read ADR 0008 and
`apps/lab/CONTRACT.md` for bounded ownership and actual HTTP/browser gates.
Native semantic-guard static review passed; only one revised actual acceptance
was run and passed as dirty draft-05. No OpenRadioss/material/HPC/full-physics completion
is implied. Root freezes Core/adapter source before adaptive campaign tests.

Read [CONNECTED_ACCEPTANCE](docs/CONNECTED_ACCEPTANCE.md) for the actual new
HTTP CAD/PDE/library/export proof, analytical model proof and narrow report-path
correction. These draft runs do not replace the older clean-source checkpoint
until the new commit's CI and clean reproduction pass. The bounded Lab browser
flow passed separately; official OpenScience GUI remains unverified.
Live OpenScience04 is partial: actual study/discovery succeeded,
registration made no tool call, registry revision0 and no experiments. Do not
repeat model/install loops or label CLI completion as research acceptance.
The user's OpenScience usage question did not request a UI redesign. Read
[OPENSCIENCE_USE](docs/OPENSCIENCE_USE.md) before explaining the Lab screen.

**Latest numerical code checkpoint:**
`41a9858bad7ebeb72de0db0d75d1f910a4a50dc4`;
[CI 36656020195](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36656020195)
passed all six jobs. The primary local session passed 217 tests, expanded MCP
and fresh clean-source finer/structural-optimization/PDE acceptance. Last-pair
mesh change is 0.881709%; optimization evaluated 9 candidates/8 solver children
with 23.3750% best observed volume reduction; Poisson L2 is 0.00135043625 with
finest rate 1.99349. One-generation optimization is unconverged, and all results
remain `NOT_RELEASED`. Read [NUMERICAL_CONTINUATION](docs/NUMERICAL_CONTINUATION.md),
ADRs 0005/0006 and their records for exact settings/hashes/limits/review.
Later evidence/documentation commits do not create new solver proof. Dirty
drafts and older cloud records below remain historical evidence.

**Primary local restoration:** the checkout now exists at
`C:\SourceCodes\autonomous-cae-lab`; the current session directly completed
Core 32 tests, upstream 58 tests, MCP, CAD demo and native/structural/DOE
acceptance on Ubuntu 24.04.4 WSL2 / Python 3.12.3. The restored source was
`16fba8cbff0ab8619ea50c6591121992f07fd32c`, with exact-source CI 36644400011
also successful. Versions, fresh store paths, repairs and artifact/ledger
verification are in [LOCAL_EXECUTION](docs/LOCAL_EXECUTION.md) and
[the environment record](benchmarks/records/20260930-local-environment.json).
`scripts/local.ps1` starts the configured WSL environment from PowerShell.
The following older checkpoint records the previous cloud execution.

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
- `caelab/optimizers/`: deterministic SciPy Latin hypercube and bounded adaptive
  differential evolution; exact numeric generation stays inside the engine.
- `caelab/optimization.py`: source/registry/plugin-frozen search plans,
  scalar/unit/check gates, journals/checkpoints and exact interruption replay.
- `caelab/pde.py` plus FEniCSx adapter/worker: common PDE records with no CAD
  parent, bounded weak-form input, isolated system Python and analytical checks.
- `plugins/fixture_design/upstream`: tested fixture source, native worker,
  domain rules, browser GUI and exporters; pinned submodule, not copied code.
- `openscience/`: common research operation contract and local stdio MCP.
  Transport round trip is tested; live OpenScience agent loop is unverified.
- `schemas/`, `tests/`, `scripts/`, `docs/`, `ADR/`: contracts, regressions,
  acceptance execution, evidence/research and decisions.

Public operations currently include study create/inspect; native new/import/
inspect/select-final; parameter discover/register/list/refresh; CAD experiment
run/inspect/summary/compare; structural child run; DOE and optimization
plan/run/inspect; declared PDE run. API, CLI and MCP use the same Core. The
basic `report` CLI returns a research summary. Full research-report generation,
general nonlinear/coupled PDE, wider optimization engines, unified UI/HPC and
physical operations remain scope requirements.

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

## Completed continuation and next concrete work

1. **Completed — finer saddle-load verification:** extended the canonical benchmark with a
   1.5 mm mesh, retaining the same CAD revision, material, load patch, 100 N,
   fixed-base definition and unchanged numerical limits. Recorded patch area,
   lip fraction, max loaded-node response, signed reactions, artifact hashes
   and reference/approximation limits. On future reproduction failure, diagnose rather than
   relax the screen. Current piecewise linear surface integration is not an
   exact quadratic boundary rule or physical roller contact.
2. **Completed bounded slice — actual numerical optimization:** defined reproducible objective/constraint
   semantics, invalid-design/failure policy and restartable optimizer state;
   executed a bounded fixture acceptance through existing CAD/analysis Core.
   Keep LLM research reasoning separate from numeric candidate generation.
3. **Completed bounded slice — PDE:** tested a canonical user weak form via a real
   FEniCSx adapter; verified analytical/reference error
   through the same common result/evidence contract.

The three scripts are `scripts.verify_finer_mesh`, `scripts.verify_optimization`
and `scripts.verify_pde`; use `--store` with a new path for reproduction.
Their latest local proof is in `benchmarks/records/20260930-local-{finer,optimization,pde}.json`;
exact CI/raw archive references are in `20260930-numerical-ci.json`. Raw stores
remain local/ignored; new CI archives expire on 2026-10-30 UTC.

4. **Next independent acceptance work:** live OpenScience MCP agent acceptance;
   arbitrary GUI-edited FCStd refresh/index drift and registration transaction
   review; durable raw-artifact retention and corporate license/security review.
5. **Next physics benchmark:** Code_Aster elastic analytical/reference baseline,
   then material/geometric nonlinearity and contact with canonical references.
   Install only its required runtime, retain exact versions/native inputs/raw
   MED/solver evidence and use common contracts. Continue OpenRadioss explicit
   preprocessing/impact and the advanced research/physical phases listed in
   PROJECT_SCOPE. Do not declare those phases complete from a research table.

Wider fixture optimization (convergence/active constraints), arbitrary PDE
domains/nonlinear/coupled equations and MPI/HPC need separate acceptance. Do
not promote this single generation or scalar unit-square proof to those scopes.

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
- Local dependencies/solvers and GitHub access were restored by the primary
  Windows/WSL session; deployment on a different computer still needs its own
  setup and acceptance. Native Windows and arbitrary GUI CAD execution remain
  unverified.

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
