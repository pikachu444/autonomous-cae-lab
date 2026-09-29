# Dependency and deployment inventory

This is an inventory for review, not corporate license approval. The tested environment used Python 3.12.14 on Linux. Direct package licenses below are from installed package metadata; inspect the exact distributions and their transitive dependencies before redistribution or internal deployment.

| Direct package / tool | Current pin or role | License metadata / deployment issue |
| --- | --- | --- |
| CadQuery | 2.7.0, fixture CAD | Apache-2.0; its OCCT and other native dependencies require separate audit. |
| trimesh | 5.1.0, STL/3MF inspection | MIT. |
| NumPy | 2.3.5, geometry checks | BSD-style NumPy license. |
| Matplotlib | 3.10.8, preview/report | Matplotlib license. |
| Pillow | Upstream pin 11.3.0; environment observed 12.3.0 | Installed metadata MIT-CMU. Resolve pin mismatch in a clean deployment and record final lockfile. |
| jsonschema / filelock | 4.26.0 / 3.32.7, Core | MIT / MIT. |
| MCP Python SDK | 1.30.0, local stdio bridge | MIT in installed metadata. OpenScience's own terms are separate. |
| pytest / Playwright / reportlab / pypdf | Upstream dev/test/report dependencies | MIT / Apache-2.0 / BSD / BSD-3-Clause metadata. Browser and PDF tooling are not required to run the Core CAD path. |
| FreeCAD | Optional native GUI/FCStd adapter | Verify exact FreeCAD and bundled component licenses, OS binary and redistribution mode. FreeCADCmd was absent locally. |
| Gmsh / CalculiX | Upstream preliminary FEA CI | Assess exact installation licenses and whether solver is invoked as a separate process; no new FEA adapter in this repository. |

Future backend license concerns and official project sources are in [BACKEND_EVALUATION.md](BACKEND_EVALUATION.md). OpenScience security/trace settings are in [OPENSCIENCE_INTEGRATION.md](OPENSCIENCE_INTEGRATION.md). Windows, WSL, Docker and HPC support must be tested per concrete build; a Python package being importable is not a validated solver deployment. The upstream fixture repository currently lacks a root license file, so bundling or redistribution needs the owner's licensing decision.
