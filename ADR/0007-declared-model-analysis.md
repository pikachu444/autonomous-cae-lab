# ADR 0007 — common declared-model execution beyond fixture CAD

Status: accepted architecture; fresh local native elasticity acceptance passed;
clean-source reproduction and exact-source CI remain pending.
Date: 2026-09-30.

## Decision

Introduce `ModelAnalysisAdapter` and `Lab.run_model_analysis` for real declared
geometry, mesh, material, boundary, load and output inputs. No fictitious CAD
parent or fixture variable is created. The existing CAD-parent analysis contract
still applies to analyses of a verified exported CAD revision.

Move the common envelope to `caelab/declared_model.py`. PDE delegates through
its existing API/namespace/output path and retains its settings-only revision.
The new operation hashes settings plus a solver-independent model declaration.
Add optional `model_revision` to proposal/result schemas and summaries; older
stored envelopes remain valid and unchanged. New proposal/result/thread model
identities must agree. Older strict consumers need the updated additive schema.

Core owns deep copies, execution gates, append-only records, artifact hashes,
evidence, ledgers and NOT_RELEASED. Domain plugins own references, units and
numerical verdicts. Adapters own native commands and field completeness.
Invalid declarations are retained as REJECTED/NOT_RUN; unexpected failures
retain partial artifacts as FAILED_EXECUTION.

## Independent analytical case

The elasticity plugin supplies an affine uniaxial block reference. Its
Code_Aster adapter uses a new Gmsh volume mesh and imports no fixture mesher or
fixture rule. DX=0 on x=0, DY=0 on y=0 and DZ=0 on z=0 allow Poisson contraction;
a full clamp on x=0 would invalidate this reference.

With L=20 mm, B=4 mm, H=2 mm, E=210000 MPa, nu=0.3 and +X traction t=10 MPa,
exact displacement is `(t*x/E,-nu*t*y/E,-nu*t*z/E)`, stress is
`[10,0,0,0,0,0]` MPa and support resultant is `[-80,0,0]` N. Compare every nodal
component and all five TETRA10 Gauss points' six stress components. Deduplicate
support reactions and compare the native resultant. Positive Jacobians,
complete quadratic boundary groups, volume and loaded area precede solving.

Both quadratic meshes represent this constant strain. Mesh agreement is a
patch test, not a convergence-order estimate. No assembled matrix residual is
claimed. Predeclared relative displacement/stress/reaction/mesh limits are 1e-8
and absolute displacement is 1e-12 mm. Strength/material/physical/durability
qualification remains UNKNOWN.

## Runtime and alternatives

Preserve the WSL Python 3.12 Lab environment. Singularity 4.1.1 runs the
official distribution's solver-only vendor OCI image at immutable digest
`sha256:d8d19ea91989eac0d38195bc5795c54c69f530f7196f53d67697ffa57c9106d5`.
Local converted SIF SHA256:
`f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64`.
Actual solver is 17.4.0, revision spack-local, with a vendor MPI rank patch.
SIF conversions can differ; record each actual SIF separately from OCI identity.
The image's Python 3.11.14/NumPy 1.26.4 do not replace Lab's dependencies.

The existing Docker daemon is unavailable; this route leaves that installation
unchanged. SALOME's larger GUI bundle is unnecessary for this numerical gate,
but human inspection remains required. Corporate deployment approval is open.
Native APIs were checked against the
[official 17.4 table implementation](https://gitlab.com/codeaster/src/-/blob/17.4.0/code_aster/ObjectsExt/table_ext.py)
and [element definition](https://gitlab.com/codeaster/src/-/blob/17.4.0/catalo/cataelem/Elements/meca_3d.py);
the [official download page](https://code-aster.org/spip.php?rubrique21) supplies
the vendor distribution route.

## Verification and scope

This serves R01/R05/R11/R14/R21/R34/R43/R45, not whole Phase 5 completion.
Nonlinear/contact/material/explicit/HPC, wider model optimization and UI remain
required. See [connected continuation](../docs/CONNECTED_CONTINUATION.md) for
actual successes/failures, independent review and pending clean-source proof.

The corrected native import guard passed a new actual run in
`artifacts/local-20260930-codeaster-draft-05`. Canonical displacement, all nodal
components, all quadratic integration-point stresses, support reactions and
the two-mesh patch agreement passed the unchanged limits. The changed
geometry/material/load case also passed; nu=0.5 was rejected before solving.
This dirty-source draft is retained separately from the four failed drafts;
it does not establish a clean committed-source checkpoint or wider physics.
