# Dependency and deployment inventory

This is an inventory for review, not corporate license approval. The primary
Windows 11 / Ubuntu 24.04.4 WSL2 environment uses an isolated Python 3.12.3 Lab
runtime. Earlier cloud Python 3.12.14 records remain historical. Exact local
versions/hashes are in LOCAL_EXECUTION and NUMERICAL_CONTINUATION; inspect the
actual distributions and transitive dependencies before deployment.

| Direct package / tool | Current pin or role | License metadata / deployment issue |
| --- | --- | --- |
| CadQuery | 2.7.0, fixture CAD | Apache-2.0; its OCCT and other native dependencies require separate audit. |
| trimesh | 5.1.0, STL/3MF inspection | MIT. |
| NumPy | 2.3.5, geometry checks | BSD-style NumPy license. |
| Matplotlib | 3.10.8, preview/report | Matplotlib license. |
| Pillow | Upstream pin 11.3.0; environment observed 12.3.0 | Installed metadata MIT-CMU. Resolve pin mismatch in a clean deployment and record final lockfile. |
| jsonschema / filelock | 4.26.0 / 3.32.7, Core | MIT / MIT. |
| SciPy | 1.17.0, seeded Latin hypercube DOE | BSD-3-Clause project license; inspect the exact wheel and bundled dependency notices for deployment. |
| MCP Python SDK | 1.30.0, local stdio bridge | MIT in installed metadata. OpenScience's own terms are separate. |
| pytest / Playwright / reportlab / pypdf | Upstream dev/test/report dependencies | MIT / Apache-2.0 / BSD / BSD-3-Clause metadata. Browser and PDF tooling are not required to run the Core CAD path. |
| FreeCAD | 1.1.4 AppImage, external local runtime and editable FCStd adapter | Exact AppImage SHA/build and local acceptance recorded; bundled licenses/deployment approval still require review. |
| Gmsh / CalculiX | Local/CI 4.12.1 / 2.21, separate-process child adapter | Local and CI linear numerical screening verified; actual material/contact/strength qualification remains open. |
| FEniCSx / UFL / PETSc | Separate system Python: DOLFINx 0.11.0.post0, UFL 2026.1, PETSc 3.19.6 | Exact pinned PPA build and analytical acceptance in NUMERICAL_CONTINUATION; serial scalar coverage only. |
| Singularity / Code_Aster | 4.1.1 / vendor 17.4.0 spack-local; external pinned OCI-derived SIF | OCI and local SIF identities in ADR 0007. Installed/runtime probe verified; native model acceptance in progress, nonlinear/material/physical gates open. |
| OpenScience / Ollama | Task-owned @synsci/openscience 2.0.146; existing local Ollama 0.34.0 | Actual partial study/registry tool calls recorded; whole live research loop is unverified. Isolated profile permissions are not OS containment or corporate approval. |
| Local Lab surface | Standard-library HTTP, existing Core dependencies | No extra web framework; loopback single-user implementation/acceptance in progress, ADR 0008. |

Future backend license concerns and official project sources are in [BACKEND_EVALUATION.md](BACKEND_EVALUATION.md). OpenScience security/trace settings are in [OPENSCIENCE_INTEGRATION.md](OPENSCIENCE_INTEGRATION.md). Windows, WSL, Docker and HPC support must be tested per concrete build; a Python package being importable is not a validated solver deployment. The upstream fixture repository currently lacks a root license file, so bundling or redistribution needs the owner's licensing decision.
