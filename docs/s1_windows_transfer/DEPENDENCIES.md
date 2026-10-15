# Dependency decision and provenance

현재 Windows 설치·버전·라이선스 확인은 [Windows 확인 기록](WINDOWS_ACCEPTANCE_KO.md)을 따른다.
아래 다운로드 실패·미설치 문장은 Pro 작성 당시 환경의 기록이다. 기본 Research 설치는
`spatial` extra를 포함하며 기존 설치 receipt에 이 항목이 없으면 추가 설치한다.

Checked 2026-10-15. These references establish the API/distribution route, not a successful local or Windows solve.

| Distribution | Pin | Licence / role |
|---|---|---|
| scikit-fem | 12.0.2 | BSD-3-Clause; pure Python finite-element assembly |
| SciPy | 1.17.0 | BSD-3-Clause; existing project sparse solver, `spsolve`/SuperLU |
| NumPy | 2.3.5 | BSD-3-Clause; existing project dependency, float64 arrays |
| PySide6 | 6.9.1 | Existing `research-ui` dependency; existing Qt licence/distribution obligations remain |

Primary references:
- https://pypi.org/project/scikit-fem/12.0.2/
- https://github.com/kinnala/scikit-fem/blob/12.0.2/pyproject.toml
- https://github.com/kinnala/scikit-fem/blob/12.0.2/LICENSE
- https://scikit-fem.readthedocs.io/en/latest/api.html
- https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.sparse.linalg.spsolve.html
- https://docs.scipy.org/doc/scipy-1.17.0/dev/core-dev/index.html
- https://numpy.org/doc/2.3/license.html

The official 12.0.2 changelog (2026-06-05) includes a `models.elasticity.plane_stress` formula fix.
The worker declares the explicit reduced plane-stress Lamé coefficient and uses the library's
`linear_elasticity` assembler, not a copied generic FE engine. The isolated worker requires the
exact pins; an arbitrary installed version is not silently accepted. Official `MeshTri`,
`ElementTriP1`, `ElementVector`, `Basis`, `BilinearForm`, `LinearForm`, `condense` and existing
SciPy `spsolve` are the selected public API. No JAX, PETSc, FEniCSx, supermeshing, meshio, MPI,
CAD, AI, WSL or paid dependency is required for this capability. Existing VTU/PVD writer is reused.

The environment actually has NumPy 2.3.5 and SciPy 1.17.0. scikit-fem and PySide6 are absent.
The pip index failed DNS resolution. A direct official wheel download also failed. No vendored
replacement, substitute solver, fabricated wheel or fake installation was used. No dependency
binary is in this delivery. `evidence/dependency-download.log` retains the actual failure.

Official wheel locator (NOT downloaded or locally hash-verified):
`https://files.pythonhosted.org/packages/5b/13/d46cf943bd1b04b1b010094eb08493d6660c99c49652fa46cf7c3bf36ab5/scikit_fem-12.0.2-py3-none-any.whl`.
The source distribution is Python >=3.10; this product's Python >=3.12 requirement is unchanged.
Use the Windows commands in README_KO.md and then run the non-mocked tests. Wheel availability
and primary documentation alone do not establish actual Windows compatibility of this authored worker.
