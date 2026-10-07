## Current workbench launcher — 2026-10-08

Run `scripts/cae-research-local.ps1` from PowerShell. It reads the private
`%LOCALAPPDATA%/AutonomousCAELab/workbench-local.json` deployment settings and
starts the shared HTTP workbench; CLI and MCP use that same controller/store.
The configured installation uses WSL Ubuntu, the existing Python 3.12 venv,
port 8776 and the private `runs/workbench-service-20261008-01` store. The source
is the isolated `workbench-local-integration` worktree, preserving primary edits.
Windows source paths are translated with `wslpath`; Linux runtime/store paths
are retained. `scripts/local.ps1` supplies separately installed native runtimes.
Stop the foreground controller with Ctrl+C and use the same launcher to resume.

The operator workbench configuration registers trusted external programs,
approved local input roots, expert roles and optional model policy. It contains
no credential copied from a development session. The optional OpenScience
provider uses the existing official signed-in CLI profile. Native readiness and
live expert acceptance are separate; current evidence and gaps are tracked in
[WORKBENCH_PROGRESS.md](WORKBENCH_PROGRESS.md).

MFront preparation additionally reads the operator's private
`native-environment.json`: only `CAELAB_MFRONT_PREPARED_LIBRARY` and
`CAELAB_MFRONT_PREPARED_LIBRARY_SHA256` are accepted there. The library is copied
and verified inside each owned preparation. Never set a request's output path.

The sections below are earlier deployment records. Their old launcher options,
stores and READY claims do not describe the current workbench launcher.

## Historical native CAD mechanics — local optional runtime and flow

The existing Python3.12 WSL environment now also has gmsh==4.12.1 from requirements-native-mechanics.txt. FreeCAD1.1.4 and CalculiX2.21 were reused. On a fresh local environment Root installs that optional dependency and existing native tools; user Git/SHA work is not required.

Start the approved connected service with `./scripts/cae-research-local.ps1`. In Design choose an FCStd and create an editable CAD revision; in Simulation load its verified targets, choose CalculiX user CAD, enter explicit material/partial DOFs/face vectors, save conditions and run a new experiment. Reopen Results or the same Simulation field; report/evidence exports belong to that exact experiment. Current native scope is one solid, isotropic linear static, no contact; arbitrary assembly qualification is open.

NEXT: connect the same native records to approved OpenScience, then general CAD numerical/observation research and original assembly/remaining Phase2-7 gaps. Whole52/entirePhases are incomplete. Physical UNKNOWN/NOT_RELEASED, original meshes/fine UNKNOWN and separate R2 stash remain. Goal ACTIVE. Full-record verification latency11-19s and provider reconnect are open; no new per-fix Astra gate.

---
# Current approved CAE research launcher — bounded actual connection verified

Root prepared the existing approved local settings outside this public repository.
The source-reviewed foreground entry point is:

```powershell
.\scripts\cae-research-local.ps1
```

It reuses approved ChatGPT/`openai-codex/gpt-5.6-sol`, existing OpenScience2.0.146,
canonical FixtureRefinement/schema7/fourteen tools, new store/profile, and the same owned Research+Lab binding.
The owner-bound Lab also forwards the existing Windows PowerShell7 executable into WSL; its ProgramFiles default is not assumed.
Default local path settings: `%LOCALAPPDATA%\AutonomousCAELab\cae-research-settings.json`;
schema1 has only runtime_prefix, auth_profile_root and project_binding_path. No credentials belong in Git.
No new login/model/provider is selected. A reused output path is rejected. Ctrl+C is the intended foreground exit.
Clean c94/new run02 actually completed one CAD-discovery question, eight returned variables,
same resident/store IDLE cleanup and idle Ctrl+C/owned STOPPED. Question latency310.124764s,
cause NOT_ISOLATED. These gate services were stopped deliberately; this document is not current READY status.
Active-job/native cancellation, durable restart, complete field GUI and U1 remain OPEN.
Record: `benchmarks/records/20261005-cae-usability-live-r03.json`.
`-ValidateOnly` performs path/project/schema admission and explicitly returns NOT_CHECKED readiness.
A model answer/exit0 cannot qualify engineering. Read `docs/CAE_RESEARCH_EXECUTION_PLAN.md` before use.
The default research plan no longer requires whole-model mesh-convergence sweeps; ADR0035
keeps purpose-specific checks, targeted optional sensitivity and historical benchmark limits.
The actual fixture adapter still requires2–8 mesh levels; opt-in selected-mesh support is a pending software unit.

---

# Primary Windows / WSL execution — 2026-09-30

## Optional local backend diagnostics — 2026-10-08

In the WSL Python 3.12 environment, `python -m caelab doctor
--backend <name>` reports discovery and runtime identity without calling a
solver. Add `--execute --output <new-directory>` to run the backend's fixed
smoke input in a fresh directory. The result separates `discovery`,
`dependencies`, `execution`, and `numerical_status`; only the latter two are
actual solve evidence. Existing directories are refused to preserve history.
Discovery is intentionally narrow to the installed DOLFINx, OpenRadioss,
Code_Aster and MFront native runtimes; unsupported backend names say so.

Actual doctor runs in this local WSL session: OpenRadioss freeflight at
`/home/pikachu444/.local/share/autonomous-cae-lab/runs/workbench-doctor-explicit-20261008-01`
and Code_Aster affine block at
`.../runs/workbench-doctor-aster-affine-20261008-01`, plus MFront/MGIS
Elasticity at `.../runs/workbench-doctor-mfront-20261008-01`, all reported
`execution=COMPLETED,numerical_status=COMPLETED`. PDE discovery reported the
system DOLFINx 0.11.0.post0/PETSc environment; its actual manufactured
transient solve is retained separately at
`.../runs/workbench-native-local-20261008-02`. Its response reader retrieved
33 nodal samples. The same run's explicit solve supplied 200 velocity samples;
the saved-response reader also reproduced bounded slices after native runtime
environment variables were removed. These are numerical/local readiness
checks, not physical or release qualification.

The primary session uses `C:\SourceCodes\autonomous-cae-lab`. The folder was
empty before cloning current main `16fba8cbff0ab8619ea50c6591121992f07fd32c`
and the pinned fixture submodule `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
GitHub authentication and the exact-main CI run
[36644400011](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36644400011)
were checked directly; all four jobs succeeded. Older cloud records remain
historical evidence, rather than descriptions of this computer.

## Environment actually used

Windows 11 Home Single Language build 26200 hosts the existing Ubuntu 24.04.4
WSL2 distribution. Existing Windows Python 3.13.5, managed Python 3.11.15 and
Anaconda were retained. Lab executes in a dedicated Python 3.12.3 environment:
`/home/pikachu444/.local/share/autonomous-cae-lab/venv-py312`.
The working source and experiment stores remain in the specified C: folder,
visible inside WSL as `/mnt/c/SourceCodes/autonomous-cae-lab`.

Pinned project requirements were installed. `pip check` passed. The numerical
runtime contains CadQuery 2.7.0, NumPy 2.3.5, SciPy 1.17.0 and MCP 1.30.0.
Ubuntu packages provide Gmsh 4.12.1 and CalculiX 2.21. FreeCAD 1.1.4 is the
CI-pinned Linux AppImage, SHA-256
`f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434`.
Its console reported build commit `4fd3bf320d9566a27e60069fc8387448aaa3a094`.
FreeCAD's bundled Python stays separate from Lab's Python.

The first venv attempt found missing `ensurepip`; installing
`python3.12-venv` and completing the same environment fixed it. Windows Git
created CRLF shell files, so the pinned upstream wrapper was copied with LF
into the external runtime directory as `freecad_cmd.sh`. The tracked
submodule was preserved. Repository-local `core.autocrlf=true` keeps Windows
and WSL Git views consistent. The AppImage's GUI `--version` path waited
without exiting; that version-only process was stopped and `App.Version()`
was executed through the tested console wrapper instead.

`scripts/local.ps1` launches this runtime from PowerShell without shell
interpolation. It resolves the checkout path, supplies the external wrapper
and preserves the Python argument array. For future sessions:

```powershell
& .\scripts\local.ps1 -PythonArgs @('-m', 'pytest', '-q')
& .\scripts\local.ps1 -PythonArgs @('-m', 'scripts.verify_native', '--store', 'artifacts/new-native-store')
```

These are reproducibility instructions; the current session already performed
the setup and verification. Use a new store for each acceptance rerun.

## Reproduced evidence

The [machine-readable record](../benchmarks/records/20260930-local-environment.json)
lists exact experiment/result/thread hashes and the source identity captured
by each run. Fourteen experiment ledgers and all their registered artifacts
were inspected through `Lab`; both completed DOE journals were also verified.

| Local check | Observed outcome |
| --- | --- |
| Core tests | 32 passed; 116.90 seconds on the mounted Windows checkout |
| Pinned fixture tests | 58 passed; 20.26 seconds |
| MCP stdio transport | Valid CAD and seeded DOE round trip passed |
| CAD demo | 38 mm width exported; invalid pitch rejected before export |
| Native Part / Sketcher | Bounds `[38,40,26]` and `[12,12,8]`; FCStd reopened; invalid bore and ineffective dimension blocked |
| Structural 4/3/2 mm | Fine displacement 0.005707813 mm; 3→2 mm change 2.3361487%; worst signed reaction imbalance 1.4573531e-8 |
| Seeded DOE | Three solver children completed the numerical screen; one CAD proposal had no solver child |

Raw stores are `runs/local-20260930-demo`,
`artifacts/local-20260930-native`, `artifacts/local-20260930-linear` and
`artifacts/local-20260930-doe`. They are retained locally and ignored by Git.
The clone contains the compact evidence record, not those raw files. Managed
durable raw-artifact archival remains open.

Native Windows execution, direct GUI inspection of arbitrary FCStd,
live OpenScience agent execution and physical engineering qualification were
not verified. This acceptance is local **WSL** execution. Every engineering
decision remains `NOT_RELEASED`; strength, contact, material qualification,
machine interface and physical/durability evidence remain `UNKNOWN`.

## Isolated PDE prerequisite

The official FEniCS PPA was added to Ubuntu for the next acceptance. Both
`python3-dolfinx` and `python3-dolfinx-real` are installed at
`1:0.11.0.post0-2~ppa1~noble1`. Importing from `/usr/bin/python3` returned
DOLFINx 0.11.0.post0, UFL 2026.1.0, Basix 0.11.0, NumPy 1.26.4 and
PETSc 3.19.6. This interpreter is a subprocess boundary; Lab's NumPy 2.3.5
was retained. Import success is a prerequisite check, not PDE numerical proof.

Official installation source:
[DOLFINx installation](https://github.com/FEniCS/dolfinx#installation).

The prerequisite subsequently passed actual canonical/reaction/rejection PDE
acceptance at clean source `41a9858`, together with finer and real numerical
optimization acceptance. The integrated local test count is now 217; exact
source CI 36656020195 passed all six jobs. See
[NUMERICAL_CONTINUATION](NUMERICAL_CONTINUATION.md) for execution evidence,
independent review and remaining scope. The earlier restoration values above
are historical checks at `16fba8c`, not overwritten by this continuation.
