# What this laboratory verifies

The established solvers' published verification cases and documented limits
are upstream evidence. Reuse that evidence for the applicable solver version,
formulation and feature; the Lab is not a replacement certification programme
for every solver algorithm. Code_Aster provides a dedicated validation manual;
CalculiX distributes solver test examples and theory/user documentation:
[Code_Aster validation](https://code-aster.org/doc/v16/index.html),
[CalculiX official solver documentation and test examples](https://www.dhondt.de/).

Keep these scopes distinct in work plans and acceptance records:

| Scope | What is established | Required local evidence |
| --- | --- | --- |
| Upstream numerical verification | Published cases exercise specified algorithms/formulations under their stated conditions. | Exact reference, version/conditions and documented limits; do not infer all-feature approval. |
| Installed adapter/integration verification | The Lab's actual version, input conversion, execution and result reader reproduce the intended problem. | Representative applicable reference case, actual inputs/units/materials/loads/boundaries, native outputs, independent response comparison and complete provenance. |
| Research model assessment | The chosen geometry, mesh, contact/joints, material and idealisations are adequate for the stated research question. | Problem-specific assumptions, meaningful mesh/time-step sensitivity, equilibrium/convergence and analytical/reference/cross-solver comparison where available. |
| Physical/engineering qualification | The prediction is adequate for the intended real specimen, machine, strength/durability and deployment. | Required measured data, physical comparison and approval; missing evidence remains UNKNOWN/NOT_RELEASED. |

A solver's normal exit does not prove correct input mapping, correct parsing,
an adequate engineering model or release. Conversely, a reference mismatch is
not automatically an upstream solver defect: retain the native data and
separate modelling, discretisation, adapter, environment and algorithm causes
until evidence identifies them.

Use established representative benchmarks to qualify the connection, then
reuse the passing source/run evidence. Recheck the affected integration or
model when its source, runtime, formulation, mesh/conditions or admitted
feature changes. Do not rerun the complete upstream suite or unchanged native
experiments solely to create another checkpoint. Artifact-integrity checking
when consuming a retained result is a separate operation from a solver rerun.

The original-fixture assembly work in ADR0032 is CAD-parent integration:
captured parametric input/source, native component/face/interface identity,
pre-export rejection, same-revision artifacts and human inspection. Initial
geometric contact distance is not a solved pressure/gap or preload result.
Its nonlinear fixture mechanics and whole OpenScience campaign remain later
gates. Numerical engines retain search ownership; OpenScience asks questions,
selects campaigns and interprets qualified evidence through the common Core.
