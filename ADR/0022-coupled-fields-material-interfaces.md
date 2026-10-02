# ADR0022: Coupled scalar fields across a conforming material interface

Date2026-10-03. Status accepted for bounded implementation; not numerical or
physical qualification. Implements next D3.4 after vector source6c8b2ba.

## Decision and requirement impact

Add pde.fenicsx.coupled through the existing declared PDE/Core/Results contract.
A two-component scalar cross-diffusion system uses region-specific symmetric
SPD2x2 diffusion and common symmetric PSD reaction on one real serial blocked
P1 rectangle with a straight conforming midpoint interface. D acts on component
rows of grad(u). Tagged region/side integration and complete region/trace input
binding retain heterogeneous physics instead of collapsing it into one source.
No shared schema, new scalar AST, wire tool, provider/model/auth or optimizer.
R16/R28 advance coupled weak-form/material-interface capability; R10/R12 and
R19-R21 retain declaration/revision/artifact/evidence and same-record inspection.
All52 remain; general forms/import/MPI/time/nonlinear and physical coverage open.

Root extracts the existing pure grid/triangle portion of rectangle _field_check
into _mesh_topology. Old response/side/verdict checks remain, and existing
rectangle/transient/vector tests are required. New Domain reuses ORIGINAL mesh
geometry and owns split-boundary/interface/component checks. No synthetic zero
solution is substituted into the acceptance checker. This narrow helper change
has a new source hash; past immutable native stores keep their original pins.

## Reasons and alternatives

A common CG space encodes value continuity; the manufactured normal operator
flux cancels internally, so no artificial interface/dS load is added. Separate
meshes/mortar or a generic symbolic PDE language would expand unsupported scope.
Reusing Lamé or one global RHS binding would change equations or discard two
interface traces. Copying the full tested grid checker would duplicate fragile
invariants; a geometry-only extraction reuses them without pretending different
responses passed. D and R are native Constants; no clipping/symmetry repair.

## Evidence and limits

Freeze PDE_COUPLED_PACKET before implementation/output: exact shapes/tags,
region/interface/trace identities, manufactured derivatives, fixed thresholds
and six positive/three numerical-negative/eight preflight controls. Root owns
independent full-field polynomial integration and clean-source runner. Source
and native qualification, official Research admission and same-record field GUI
are separate. Actual P1 flux may jump; zero pointwise computed flux jump is not
a gate. Operator Neumann input is not physical Fick flux or strength evidence.
UNKNOWN/NOT_RELEASED remains. Corporate approval/material/physical data are open.
