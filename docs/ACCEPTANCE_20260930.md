# Phase 0–1 acceptance record — 2026-09-30

Run against repository commit `47e0d472459d1dc9ebbbe2abbd6d6ac60cfa45a9`, with fixture submodule `3e48bf6138f495299f45b1af254bfb4aaff307b8`. The current documentation/MCP additions after that commit do not change the hashed Core source tree used in the stored result. Run directory: `../acceptance_runs` in the accompanying deliverable.

| Check | Observed result |
| --- | --- |
| Upstream fixture tests | 58 passed in independent clean checkout; upstream CI run 36582605853 succeeded, including native FreeCAD, browser and preliminary structural screen. |
| Core regression | `python -m pytest -q`: 6 passed; one CQGI Python AST deprecation warning. |
| CAD experiment | `python -m caelab --store ../acceptance_runs demo`: `E-demo-width38` returned bounds `[38,40,26]` mm, volume `36783.829878355966` mm³, 12 registered artifacts including editable Python source, STEP/STL/3MF, preview, reports and ZIP. Source and result hashes are in `result.json` and the separate ledger. |
| Invalid design | `E-demo-clearance-reject` proposed bolt pitch 30 mm inside the numeric range but failed the upstream `cad_source_relation`. Status `REJECTED`, CAD revision `null`, and the rejected bundle contains reports but no STEP/STL/3MF. |
| Geometry-effect guard | A registered source parameter with no geometry effect was refused. A conditional model whose chosen value left the final BREP unchanged was rejected **before** export. Symmetric hole movement was accepted through a BREP symmetric-difference check. |
| Versioning/integrity | A changed CAD source required registry refresh and new revision. A modified report artifact and modified result JSON were detected by separate hash checks. Backend exception returned `FAILED_EXECUTION`, not a design verdict. |
| MCP transport | `python scripts/verify_mcp.py` completed stdio initialization, tool listing, study/variable registration, valid CAD execution and summary retrieval using MCP Python SDK 1.30.0. This was a local client, not an OpenScience session. |

The final engineering release is `NOT_RELEASED`. Machine interface, static strength, physical load test and fatigue/durability are `UNKNOWN`. Native FCStd adapter code uses the same upstream FreeCAD worker and preserves editable FCStd, but the new bridge was not executed because FreeCADCmd was absent. Existing upstream CI verifies its own native worker. No new solver result was produced for this parameter-modified CAD revision. The OpenScience CLI could not load project configuration in this container because `/proc` did not expose its own process ID consistently; the MCP bridge itself was tested separately.
