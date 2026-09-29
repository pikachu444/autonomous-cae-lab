# Autonomous CAE Lab

OpenScience is the intended research control plane. This repository contains the solver-independent experiment core and a first **real CAD vertical slice** backed by the pinned `auto-fixture-design` repository.

Current scope: a solver-independent Core/API/CLI/MCP, CadQuery and native FreeCAD fixture parameter discovery/registration/regeneration, immutable artifact/evidence ledgers, a real linear Gmsh/CalculiX child-run screen, and seeded numerical DOE with CAD gates and resumable journals. No mechanical strength, optimization optimum or physical fixture release is asserted. The full platform scope extends beyond these executed slices.

For a new/local session, start with [AGENTS.md](AGENTS.md), the [52-section requirement ledger](PROJECT_SCOPE.md), and [HANDOFF.md](HANDOFF.md). The handoff records the verified commit, local setup, evidence retention, unresolved assumptions and next acceptance gates. A [Korean phase-by-phase status report](docs/STATUS_20260930.md) summarizes progress against the initial plan.

The first structural child-run API, `Lab.run_analysis` / `caelab solve` / `analysis_run`, verifies a finished CAD experiment and preserves its exact STEP as the input to a separate Gmsh/CalculiX run. Its [linear screen](docs/STRUCTURAL_SCREEN.md) passed a [real solver CI run](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36634609802) with explicitly assumed loads and material. Code_Aster remains the nonlinear implicit target. No stress-based strength release is claimed.

For an editable native design with FreeCADCmd installed: `python -m caelab --store runs model native-new --template roller_support` (or `model native-import --path existing.FCStd`), use `model native-inspect --model <design-id>` and `model native-final --model <design-id> --final <object>` if the imported document has no selected final solid, then discover with `--backend fixture.freecad --model <design-id>`, register the selected `object|property|dimension` or Sketcher key, and regenerate using the returned design ID. The adapter delegates to the upstream worker; its output includes editable FCStd. The new Core bridge passed a [native GitHub Actions acceptance](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36632876593); FreeCADCmd is absent in the local container.

```bash
git submodule update --init
python -m pip install -r requirements-core.txt -r requirements-mcp.txt
python -m pip install -r plugins/fixture_design/upstream/requirements.txt
python -m caelab --store runs demo
python -m caelab --store runs inspect --experiment E-demo-width38
```

The demo requires a fresh store (or a new directory) because experiment IDs cannot be overwritten. API, CLI and MCP call the same engine. `python -m pytest -q` runs Core acceptance tests after installing `pytest` and upstream dependencies. `python scripts/verify_mcp.py` checks an actual local stdio MCP tool round trip. To run the original fixture GUI, execute `python -m fixturelab serve` from `plugins/fixture_design/upstream`. That GUI does not yet list CAE-Lab experiment IDs; open stored CAD source or FCStd and reports by path.

With Gmsh and CalculiX executables installed, `python -m scripts.verify_analysis --store artifacts/linear-lab` runs the canonical CAD-to-solver acceptance. It creates a new store; it does not modify the CAD-only demo. The same operation is available through `python -m caelab --store <store> solve --parent <cad-experiment> --experiment <new-run> --backend fixture.calculix --settings '<JSON material/load/mesh>'`.

The first [seeded DOE campaign](docs/DOE_CAMPAIGNS.md) freezes registered CAD variable samples, journals each iteration, and runs optional structural children only after valid CAD. In the latest [CI run 36641675306](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36641675306), the area-weighted saddle load produced three Gmsh/CalculiX children that passed the unchanged 5% displacement mesh screen; one invalid CAD proposal was blocked before solver. Core, native FreeCAD, structural and DOE jobs all passed. The public operations are `Lab.plan_doe/run_doe/inspect_doe`, `caelab doe plan/run/inspect` and MCP `doe_plan/doe_run/doe_inspect`. It is sampling, not a numerical optimization result; the campaign decision remains `NOT_RELEASED`. Earlier equal-node-load results remain as historical evidence with their boundary-discretization limitation documented.

Read [CURRENT_STATE.md](CURRENT_STATE.md), [ARCHITECTURE.md](ARCHITECTURE.md), [ADR 0001](ADR/0001-platform-boundaries.md), [acceptance record](docs/ACCEPTANCE_20260930.md), and [the OpenScience contract](openscience/contract.md) before adding adapters.
