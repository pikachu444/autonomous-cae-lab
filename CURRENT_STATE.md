# Current state — 2026-09-30 (Asia/Seoul)

## Recovered decisions and sources

The Project discussions require an **OpenScience research control plane** over a solver-independent CAE-Lab, with human GUI inspection and headless automation sharing native artifacts. Numerical search belongs to a reproducible optimizer. Fixture design is the first real domain plugin. Earlier planning chose CadQuery Python source plus parameters as the generated CAD source and FreeCAD for editable native models and inspection; a STEP import does not reconstruct design intent. The exact OpenScience product identity in older turns was not retrievable from conversation history in this environment. The integration below targets Synthetic Sciences OpenScience provisionally and keeps a transport-independent JSON contract.

Sources recovered: Project prompt and visible 2026-09-28/29 discussion; `fixture_plan.md` and `auto_fixture_design_verification(1).pdf` in the user's files; `pikachu444/auto-fixture-design` main at `3e48bf6138f495299f45b1af254bfb4aaff307b8` (pinned submodule). The prior GitHub Actions run [36582605853](https://github.com/pikachu444/auto-fixture-design/actions/runs/36582605853) completed successfully.

## Actual fixture implementation and evidence

| Area | Existing code / observed result | Limit |
| --- | --- | --- |
| CadQuery discovery | `fixturelab/model_cad.py` uses CQGI and `FIXTURE_META` in `models/*.py`; new trusted local models appear without a server shape template. | Numeric `mm` parameters with source metadata; no arbitrary STEP reverse parametrization. |
| Native FreeCAD | `native_cad.py`/`freecad_worker.py` inspect Part length/distance properties and Sketcher driving dimensions; registration is stored in FCStd; perturbation checks final BREP effect. | Requires FreeCADCmd; only supported candidates are discovered; face associations are suggestions, topology can change. |
| CAD execution | `model_cad.execute` / `native_cad.execute` regenerate and block out-of-range, bad relationships, ineffective dimensions or example bore edge land; STEP/STL/3MF round-trip checks, preview and editable source. | `REVIEW_REQUIRED` means CAD checks completed, not strength/machine/release approval. |
| Tests | Local clean checkout: `58 passed` in 4.06 s. Native CI acceptance: 32→38 mm FreeCAD width, Sketcher radius 4→6, clearance rejection, ineffective cutter height rejection, FCStd reimport. Eleven fixture cases met expected decisions. | Local pytest does not execute FreeCAD or FEA. Native acceptance was verified by upstream CI, not rerun in this local environment. |
| FEA | `scripts/run_structural_screen.py` used Gmsh and CalculiX for an initial linear support screen; raw mesh/deck/FRD and mesh sensitivity recorded in upstream CI. | Legacy assembly only; not yet connected to a parameter-modified FreeCAD/CadQuery revision. Material and support conditions assumed; no strength release. |
| Browser | `fixturelab/server.py`, `ui.html`, `surface_viewer.js`: loopback GUI, face selection, parameter registration and CAD ZIP. | No integrated mesh/solver/stress viewer or autonomous optimizer. |

Local checkout did not contain FreeCADCmd, Gmsh or `ccx` binaries. The existing upstream checkout's virtual environment does contain CadQuery, trimesh and pytest. This repository runs its own first CAD experiment against the pinned upstream source. A thin FreeCAD adapter now wraps native discovery/registration/regeneration, but cannot be executed in this container. It does not claim local FEA or native FreeCAD execution.

## Code ownership decision

The upstream repository is retained as a pinned **git submodule**, called through a fixture CAD adapter. Its CAD discovery, regeneration, export and tests remain authoritative. The Core owns study/experiment schema, parameter mappings, validation state, evidence, artifact hashes and the digital thread. The fixture plugin owns source model relations, edge land/clearance, equipment limits, hand checks, GUI and FEA screen. Replacing those fixture rules with generic Core code would lose the demonstrated behavior. Core does not import `fixturelab` outside the adapter.

Refactor candidates in upstream: move `DESIGNS` away from a repository-global runtime path; separate the roller example's bore check from generic `freecad_worker.py`; expose native parameter definitions without global module patching. Legacy demo and duplicated report formats are retained upstream as provenance, not copied into Core. No license file was found at the upstream root; clarify licensing before distributing bundled code.

## Still unverified or undecided

- Live OpenScience agent/tool round trip; its exact product identity needs confirmation from the unavailable older transcript. Local MCP transport was tested; OpenScience CLI v2.0.145 could not load config in this container because its PID identity check saw an inconsistent `/proc` view.
- Local native FreeCAD execution remains unavailable, but the Core-to-FreeCAD Part/Sketcher acceptance passed in GitHub Actions run 36632876593. The result artifact was inspected; details and the remaining Sketcher index-shift discovery and cross-file registration transaction limits are in `docs/NATIVE_ACCEPTANCE.md`. Physical machine interface, printed-part strength and load/fatigue tests remain unknown.
- Code_Aster/SALOME-MECA nonlinear contact benchmark, OpenRadioss explicit preprocessing and converter coverage, FEniCSx PDE prototype, optimizer integration. These are research candidates, not implemented adapters.
- Source and dependency license obligations for corporate deployment, including bundled SALOME components and OpenRadioss AGPL.
- The user supplied [pikachu444/autonomous-cae-lab](https://github.com/pikachu444/autonomous-cae-lab), currently public. The prior local architecture/acceptance and the native verification work are reflected in its `main` branch. A company/private visibility decision remains open.

## Next acceptance gates

1. The CadQuery vertical slice is executed here: discover actual source variables, register selected variables and bounds, regenerate 32→38 mm, reject invalid inputs before export, record hashes/evidence/validation, return a research summary.
2. The sample Part/Sketcher Core bridge is now CI-executed. Verify imported, arbitrary FCStd models and edit/reorder Sketcher constraints in a GUI, then refresh registry without ambiguous discovery.
3. Attach a solver result to the **same CAD revision**, then add a numerical DOE driver and a canonical PDE benchmark. Keep every unverified release requirement `UNKNOWN`.
