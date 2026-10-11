# ADR0062 — Connected research owners and retained physical fields

Date: 2026-10-11. Status: implemented in Pro r2/r3/r4/r5, published at
`1de8a69462eaf6c0c32d8f7bfcf19a85ff6183d3`; bounded acceptance and known
correction work remain open. PR7 is draft and not merged.

## Reason and decision

Independent editing and a real research workflow need saved domain inputs,
reusable evaluations, candidate results and research judgments that survive
closing a window. A Data or PDE editor cannot be a CAD mode, an Expert reply
cannot silently execute a Plan, and a successful solver process cannot substitute
for comparison, field delivery or engineering qualification.

Extend the existing service-owned document lifecycle to PDE, Discussion,
Simulation, EvaluationDefinition and Study documents. Each owns its draft,
validation, Undo and saved revisions. GUI, HTTP and optional MCP use these same
commands. Existing readers, evaluators, JobManager, numerical engines and native
brokers remain the execution and transport boundaries.

EvaluationDefinition composes exact saved Material/PDE/Simulation inputs in an
ordered evaluation. Advertised typed ports declare field meaning, units, mesh,
frame and time. The initial physical transfer is an exact same-mesh Kelvin
temperature field; it does not infer a projection or relabel dimensionless PDE
values. Explicit lagged feedback and declared convergence checks remain separate
from a simultaneous nonlinear solve. Every attempted stage and its actual files
are retained when a later stage fails or is cancelled. Explicit reuse refers to
the retained successful prefix; it is not an implicit retry of a whole job.

Numerical plans use the existing engines to vary advertised domain inputs and
retain candidate-stage results. Multi-owner adoption creates changed domain
branches before adopting their reference set through the original Evaluation
owner. The source domain documents and previous results remain available. Study
editing holds questions, hypotheses, supporting/conflicting evidence, judgments
and proposed observations; it does not replace the legacy experiment registry
or promote `NOT_RELEASED`. Discussion and Study remain independently usable.

Native Post owns multi-source filters, extraction, comparison and display
recipes. Applied results retain their historical upstream inputs; current input
staleness is distinct from corruption of an old result. Repair and partial
recovery must preserve healthy sources and original results. Managed save must
pin the files actually consumed by the restored native readers.

R5 connects existing MFront Elasticity/SVK/Maxwell evaluators to Material owners,
explicit protocol/coefficient editing and advertised research bindings. Retained
native node/Gauss/direct responses are selectable by their actual physical
meaning and location; numerical candidate and observation references survive
temporary job cleanup through saved document assets. Existing Simulation paths
remain available. This is not a generic law-state port or new optimizer.

Native Pre uses the same live FreeCAD document and installed Assembly/FEM APIs
for dimensions, preview, conditions and mesh. Preview restores design placement
before an operation consumes design geometry; pose adoption is an explicit edit.
Managed `.caepre` revisions package editable `.FCStd` dependencies and the
research/result references. A separate flattened replacement CAD representation
or a mesh regenerated implicitly at solve time would break the shared native
revision contract and is not introduced. The existing one-solid C3D10 static
linear freeze/CalculiX path retains its admission and Jacobian gates.

## Alternatives and constraints

One mutable universal project, a second scheduler/optimizer, automatic adoption
of Expert prose, inferred physical units and rebuilding old results on reopen
were rejected. The chosen implementation reuses existing owners and algorithms
and makes the missing cross-document relationships explicit. It adds no default
LLM numerical search, unrestricted user code or new provider credentials.

The new physical adapter is bounded to steady isotropic heat conduction and
small-strain 2D plane-stress elasticity on serial triangular P1 rectangles with
explicit SI inputs. Same-mesh thermal transfer and lagged conductivity do not
establish general multiphysics, contact, plasticity or physical validity. Native
source/HDF5 records remain distinct from derived VTU/PVD display files.

## Requirements, contract and verification

This implements the independent and connected workflows of ADR0060 and the
whole-product plan, including PDE/Expert use without CAD, explicit adoption,
retained results, reusable evaluations and Study evidence. Core/common records,
Domain engineering rules, adapter syntax, unknown requirements and original
numerical thresholds retain their owners. Optional MCP adds thin document,
progress/result, follow-up and native Post wrappers; editing and reading do not
execute providers or calculations. The exact operations are in
`openscience/workbench_mcp.py` and the current OpenScience contract.

Root verified actual HTTP/Qt edit/save/restart workflows, retained numerical
analysis, real Windows installation/storage overlap and native ParaView history/
repair. The real FEniCSx thermal/free-expansion fields match independent
analytical/P1/Fourier calculations and raw HDF5. Evaluation failure/cancel/reuse,
candidate adoption and Study handoff were exercised with a labelled controlled
stage boundary; they are not additional native solver verification.

R5 actual ParaView verifies corrected ID handling, analysis/history, partial
Owner Save, repair and separate-process reopen. Independent portable checks
cover retained reader pins and declared clocks. Actual HTTP Heat-to-Structure
publishes native temperature/displacement/stress exactly; default cold stage
reads still time out. Actual Qt/SDK stdio checks close pending-edit/fieldless
error handling and preserve specific HTTP refusal guidance. Controlled Material
evaluation/candidate/comparison checks are not native constitutive evidence.

Remaining defects include Windows managed Pre publication, external-dependency
dirty tracking, human Post partial Save, original native-reader compatibility,
picker completeness and other-method draft preservation after Plan Save. Local
FreeCAD and the exhausted cloud trial remain stopped. Relevant focused checks
and original failures are retained in
`docs/WORKBENCH_PROGRESS.md` and
`benchmarks/records/20261011-connected-research-r4.json` and
`benchmarks/records/20261011-connected-research-r5.json`. Neither this ADR nor a
later documentation commit qualifies physics or completes the product.
