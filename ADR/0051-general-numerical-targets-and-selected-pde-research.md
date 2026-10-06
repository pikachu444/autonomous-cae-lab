# ADR 0051 — common numerical targets and selected PDE research

Status: accepted for the bounded software interface; wider qualification remains open.

## Decision

Keep the existing numerical engines and add an explicit target-response objective:
source, metric, unit, target, positive normalization scale and reference origin.
The engine scores the normalized residual while preserving the raw response and
its validity. A target match does not qualify measured data or identify a cause.
Preserve equal baseline values without changing their canonical numeric encoding.

Add `selected_mesh` to the existing rectangle PDE adapter. It accepts a declared
dimensionless scalar rectangle, positive diffusion, nonnegative reaction, a
restricted source expression and four whole-side Dirichlet/Neumann conditions.
At least one Dirichlet side is required. Run one selected P1 mesh without an
analytical solution or mandatory mesh sweep. Preserve the old benchmark branch
and all of its reference values and thresholds.

Reuse Core's verified bounded-resource response reader for retained PDE fields.
Adapters own native field parsing and exact mesh/time/node/component semantics;
Core owns checksums, resource limits, selector dispatch and comparison storage.
Comparison 1.4 binds the original artifact, model revision, study, step and native
node. Node zero is valid. Coordinates, scalar/vector components and model time
retain unit `1`; no conversion to millimetres/seconds or interpolation is inferred.
Unintegrated initial values and existing rejected numerical verdicts are retained.

The local UI edits the typed problem, preserves the original settings when making
a new experiment, shows the full field and connects an exact point to an observed
value. Family-specific research questions reuse the stored comparison context.
Question preparation is separate from an actual approved-provider interpretation.

## Evidence and limits

`benchmarks/records/20261007-common-numerical-pde-research-r01.json` records two
actual FEniCSx runs, full-node affine comparisons, exact-point observation records,
negative admissions, unchanged baseline artifacts and final source checks.
The original selected-mode reference errors remain null/invalid; the independent
feature test does not rewrite their verdicts. Physical/model/material qualification
and release remain UNKNOWN/NOT_RELEASED. Other retained PDE reader families have
source tests; their new actual common-reader integration is NOT_RUN here.

The target-objective interface is source-tested and the baseline regression really
ran. The interrupted new CAD target workflow is NOT_RUN and is not a prerequisite
for Phase 4–7 development. No new CAD, assembly, mesh-import or provider run is
claimed. Follow the user's large-bundle development, Root execution/fix/integration,
then final independent review order; do not add a new Astra gate for each patch.

## Alternatives and impact

Requiring manufactured solutions or repeated mesh studies for every user question
would retain a benchmark-only entry point and contradict the requested workflow.
Treating an LLM as the optimizer would bypass the accepted numerical boundary.
Treating native values as caller-supplied response data would lose evidence binding.
These alternatives are rejected. The 52 requirements and Phase 1–7 remain intact;
this advances common numerical and PDE research, not their complete acceptance.
No new MCP tool, provider model, authentication or executable-adapter admission is
introduced. Existing approved `openai-codex/gpt-5.6-sol`/ChatGPT OAuth is unchanged.
