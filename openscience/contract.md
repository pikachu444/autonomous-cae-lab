# OpenScience ↔ CAE-Lab contract v1

OpenScience owns the research request and interpretation. The CAE-Lab process owns execution and evidence. A request names a `study_id`, `experiment_id`, generic `model` reference and **registered research IDs** in `values`; it never passes FreeCAD property syntax or a solver deck. The current adapter supports `fixture.cadquery` and trusted registered model `roller_support` or another source model in the pinned fixture plugin.

1. `study.create(id, name, research_question, hypothesis, objective)` → persisted study.
   `study.inspect(id)` resumes a prior study.
2. `parameters.discover(backend, model)` → candidate native metadata for human registration; OpenScience should display user-facing labels. Discovery is read-only.
   For native FreeCAD, `model.native_new(template)` creates an editable trusted template, or `model.native_import(file_name)` copies a named FCStd from the configured `CAELAB_IMPORT_ROOT` folder. `model.native_inspect(model)` exposes feature/dimension candidates and `model.native_select_final(model, final)` selects the final solid when needed. These operations require FreeCADCmd; it is configured and locally verified in the primary WSL runtime.
3. `parameters.register(study_id, backend, model, native_path, parameter_id, display_name, lower, upper, mode, kind)` → mapping plus geometry-effect probe. Native path appears only at the registration boundary, not in subsequent experiments.
   `parameters.list(study_id)` returns the versioned mapping.
   `parameters.refresh(study_id, backend, model)` rechecks existing mappings after a native CAD source revision and writes new registry history.
4. `experiment.run(study_id, experiment_id, backend, model, values, hypothesis_id?, settings?)` → persisted result. Duplicate IDs are refused, and `FAIL` prevents later work.
5. `experiment.inspect(experiment_id)` → full schema including artifact hashes. `experiment.summary(experiment_id)` → concise outcome, metric values, failed and unknown validation types and result reference. `experiment.compare(ids)` → summaries.
6. `analysis.run(parent_experiment_id, experiment_id, backend, settings)` → a new append-only solver experiment after verifying its CAD parent's hash and revision. The initial `fixture.calculix` adapter requires explicit material provenance, per-support load in N with a source and mesh sizes in mm. The adapter owns mesh/deck/result syntax. The parent CAD result is never rewritten. `experiment.inspect` and `experiment.summary` work for both records and preserve `NOT_RELEASED` until independent engineering evidence exists.
7. `doe.plan(study_id, campaign_id, backend, model, parameter_ids, sample_count, seed, engine?, analysis_backend?, analysis_settings?)` → a persisted numerical design using **registered research IDs** and a named engine. `doe.run(campaign_id)` executes the frozen plan with CAD rejection gates and optional solver children; `doe.inspect(campaign_id)` returns checked partial progress or the completed campaign. The current SciPy Latin hypercube engine samples continuous variables and stores every value, seed and version. OpenScience interprets the returned metrics and unknown validations; it does not choose each numeric point or assume that a failed CAD candidate has a solver metric.
8. `optimization.plan(study_id, campaign_id, backend, model, parameter_ids, objective, constraints, seed, max_generations?, population_size?, initial_values?, analysis_backend?, analysis_settings?, required_validations?, engine?)` → a frozen adaptive search plan. A metric selector declares CAD/analysis source, name, exact unit and direction or operator/limit/scale. Only valid finite scalars from numerically usable results enter feedback; required checks must pass. Core freezes registry/Core/plugin/adapter/algorithm identities and the explicit seeded population. `optimization.run(campaign_id)` evaluates or exactly replays candidates through CAD/analysis; CAD rejection skips solver, numerical rejection gives null feedback and execution failure stops. `optimization.inspect` checks partial journals/checkpoints or immutable completion. The best observed feasible candidate is `NOT_RELEASED`; budget exhaustion is not an optimum proof. See ADR 0005.
9. `pde.run(study_id, experiment_id, backend, settings, hypothesis_id?)` → a common append-only mathematical experiment. The bounded `pde.fenicsx` settings declare scalar weak-form coefficients/RHS, whole-boundary Dirichlet value, analytical reference, mesh sequence and numerical limits on the dimensionless unit square. No backend Python/UFL code crosses this interface. It has no CAD parent and retains `cad_revision=null`, model revision, fields/forms/logs and analytical evidence. Numerical failures retain invalid metrics; invalid expressions are blocked before solver; process errors are `FAILED_EXECUTION`. Model/physical qualification remains `UNKNOWN` and decision `NOT_RELEASED`. See ADR 0006.

The Python API is `caelab.Lab`. The CLI maps the same operations to `python -m caelab`. JSON schemas under `schemas/` define the common envelopes. `openscience/mcp_server.py` is a thin local stdio transport using the official MCP Python SDK; it does not implement engineering logic. The server store is selected by `CAELAB_STORE`, not an argument that a model can point at an arbitrary filesystem path. The native import tool accepts only a basename under `CAELAB_IMPORT_ROOT`, with resolved symlinks checked against that root. The `openscience.json.example` shows project configuration; its absolute paths and OpenScience identity need confirmation in a real installation.

`status=COMPLETED_REVIEW_REQUIRED` says the transaction ran and its numerical/CAD checks are recorded. `decision=NOT_RELEASED` is retained while any machine/strength/physical/durability requirements are unknown. `status=REJECTED` can be an intended invalid-design observation, not a process crash. `FAILED_EXECUTION` marks a backend error. The OpenScience agent must follow the result's evidence IDs rather than interpreting a tool exit code as engineering approval.

The additive `pde.fenicsx.nonlinear` backend uses the same `pde.run` transport
for its bounded scalar diffusion benchmark, full Newton histories and the
alpha-zero linear limit. If a PDE adapter explicitly sets
`pde_model_declaration = True` and implements the pure `describe_model` hook,
Core hashes settings plus that declaration and captures common geometry,
boundaries, source loads and fields. Other adapters retain their historical
settings-only revision even if they already expose the shared hook. Numerical gates remain
domain-owned; mathematical acceptance does not qualify a physical model.

`model_analysis.run(study_id, experiment_id, backend, settings, hypothesis_id?)`
adds declared geometry/material/boundary/load analysis without a fictitious CAD
parent. CLI `model-analysis`, API `run_model_analysis` and MCP
`model_analysis_run` use the shared declared-model Core also used by PDE.
Solver-independent metadata and common model_revision are frozen; native syntax
remains in the adapter. The first independent Code_Aster elasticity case is
bounded by ADR 0007 and retains strength/physical UNKNOWN and NOT_RELEASED.

`model_parameters.discover(backend, settings)` returns actual named scalar
inputs for adapters that implement checked bindings.
`model_parameters.register(study_id, backend, settings, input_id, parameter_id,
display_name, lower, upper, mode?)` maps a selected input to a research ID.
Its `input_effect` checks declaration round-trip only, not CAD or physical
qualification. Core freezes all other model settings and metadata.

`model_optimization.plan(study_id, campaign_id, backend, settings, parameter_ids,
objective, constraints, seed, max_generations?, population_size?, initial_values?,
required_validations?, engine?)` uses the existing deterministic numerical
engine. Metric source is `model`; run/inspect reuse `optimization.run/inspect`.
Each candidate is one real declared-model experiment with no CAD parent,
frozen runtime/source identity and an independent model revision. Only valid
measured scalars feed the numerical engine. Domain rejection retains
REJECTED/NOT_RUN; malformed binding contracts stop execution. Frozen metadata
cannot change at a later describe or inspection. See ADR 0009.

CLI additions are `model-inputs discover/register` and `optimize plan-model`.
MCP names are `model_parameters_discover`, `model_parameters_register` and
`model_optimization_plan`; the existing `optimization_run/inspect` apply.

Native runtime admission is deployment configuration, not a research input.
For `material.mfront.inverse`, the default remains the measured exact local
SIF; an operator-configured `SEALED_OCI` profile requires actual fixed bounded
image/OCI/binding/tool/source verification before the same model-input route.
No tool/model settings select a profile or trigger a fallback. Feedback still
requires the original native numerical gates; qualification stays UNKNOWN and
decision NOT_RELEASED. See ADR0010 and MATERIAL_INVERSE_RUNTIME_ACCEPTANCE.

The local persistent transport uses the installed pinned official OpenScience
2.0.146 and existing local model. Its attached CLI and official workspace share
an isolated profile/project/store and exact session IDs. The server pins tracked
Core/plugin/recursive submodule source before MCP imports Lab; every later
inference binds to this boot identity, including browser forwarding. Disk/HEAD
drift blocks inference, with exact owned abort/Stop preserved. Confirmed official
abort/idle and owned process identity precede termination; an unconfirmed command
keeps its process/session/output relay and blocks new CLI commands. Runtime
ownership does not change operation schemas or authorize broader tool access.
See ADR0011 and [runtime acceptance](../docs/OPENSCIENCE_RUNTIME_ACCEPTANCE.md).

The earlier cloud identity failure and exit0-without-tools attempt remain
historical failures. The retained staged live05 actually called thirteen tools
for study/discovery/registry/valid+invalid CAD/inspection/comparison and a corrected
evidence interpretation; its mixed source identities are recorded separately.
That does not establish a full new-launcher or arbitrary autonomous research
acceptance. Read [connected continuation](../docs/CONNECTED_CONTINUATION.md) and
[usage](../docs/OPENSCIENCE_USE.md). Real tool receipts and checked store bytes,
not transport/CLI completion or readiness, are required.
