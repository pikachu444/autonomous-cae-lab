# ADR 0036: Explicit selected-mesh Research scope

Date: 2026-10-05. Status: accepted design; source integrated after independent bounded Astra/high PASS (0P1/P2). Actual new-scope Research/GUI acceptance OPEN.

## Decision and requirement impact

Following ADR0035 and the user's practical full-model instruction, add the explicit
`FixtureSelected` / schema8 / `fixture-selected-mesh-v1` Research definition.
The human `cae-research-local.ps1` facade defaults to this scope; an explicit
`FixtureRefinement` option retains the historical benchmark workflow.
The lower factories still default to `FixtureScalar`. All seven historical
definition fingerprints and historical prompt instructions remain unchanged.

The new scope retains the existing fourteen tools, three admitted backends,
selected provider/model, owned source/project/store binding, cleanup, step/work
budgets and deterministic SciPy numerical engine. A new fixture analysis uses
exactly `mesh={mode:'selected',max_sizes_mm:[one finite numeric size]}`.
New numerical plans must explicitly declare `analysis_backend=fixture.calculix`
and the same selected `analysis_settings`. Missing/null backend cannot become a
CAD-only numerical plan through this new CAE scope. Historical schema1/7
CAD-only admission is unchanged; stored campaigns keep their original settings.

The copied standalone native guard embeds and checks the actual PowerShell
definition canonically. It refuses scope/shape/count/type/nonfinite mismatches
before Core. Finite scientific-invalid conditions, including nonpositive sizes
or invalid finite load/material values, remain unchanged for Domain preflight
and retained REJECTED/NOT_RUN evidence. It neither repairs inputs nor replaces
Core/Domain admission. Historical schema1/7 continues refusing any own mesh.mode.

This implements the ledger's research control-plane, explicit-condition,
deterministic-search, reuse, safety and provenance requirements. It does not
remove any of the 52 requirements or complete U1, broader Phase3-7 or release.
Core schemas, registry, metrics, numerical equations/thresholds and adapter
native syntax are unchanged by this scope unit. Adapter6's selected mode is
already separately qualified in the public Core/native record.

## Verdict and applicability

The existing bottom XYZ fixation, central24mm saddle distribution and global
CAD material axes remain explicit. No bolt/contact/rotation/original-assembly
mechanics or new solver is admitted. Declared metadata does not establish
current installation or Research readiness.

Signed all-axis reaction balance retains its1% criterion. One-mesh displacement
is observed data; mesh sensitivity remains NOT_ASSESSED/invalid null without a
displacement_mesh_trend verdict. Native converged means linear solve completion,
not mesh independence. Peak stress remains invalid and the seven engineering
UNKNOWNs/NOT_RELEASED remain. No automatic full-model mesh sweep or model/backend
fallback is introduced. Purpose-specific/targeted sensitivity is a separate
explicit choice, while canonical benchmark limits are preserved.

## Alternatives and evidence boundaries

Changing historical schema1/7 would silently widen their frozen input semantics.
Passing adapter mode through their old mesh-count hook would bypass declared
Research admission. Using a dedicated new definition preserves those contracts
and gives the human facade an explicit practical choice. Keeping CAD-only plans
in schema8 was considered, then refused after the bounded verifier owner identified
the omitted/null analysis_backend path; existing profiles retain that path.

Root controls independently verify seven canonical historical definitions,
unchanged refinement instruction bytes, lower factory defaults and actual PS/JS
syntax. The facade's45 controlled mock checks preserve approved5.6Sol, same
source/project/store, explicit refinement, unsafe-profile refusals and owned
cleanup. Dedicated source controls exercise PS/JS parity, descriptor tampering,
both analysis and numerical-plan requests, argument preservation, finite-invalid
Domain forwarding, backend/engine/work limits and source/grant/stopping gates.
These are source controls, not real authentication/Research/native/GUI proof.

Nested historical PowerShell Hashtables can reorder a serialized JSON tail across
processes. Canonical definition equality and byte-preserved instruction text are
the contract; raw fresh-factory prompt hashes are retained separately. Ordered
actual-before definitions additionally reproduce the original raw prompts.
Do not report arbitrary JSON member order as a physics/product failure or claim
unproven cross-process raw-byte stability.

Actual producer ce12037/public MCP/Core/native is separately recorded in
`benchmarks/records/20261005-fixture-selected-mesh-core-native-r01.json`.
Exact ce CI37281737051 completed7SUCCESS/3FAIL. New retained logs show official
explicit download404, Aster Fz numerical classification and vector PDE classification;
the deeper numerical causes are NOT_ISOLATED. That CI is not source8 or whole
project acceptance. Next gates are independent source review, exact clean-source
official selected Research and same-record human full-field GUI, then S3/U1.

## Source integration checkpoint

The public selected Research source record binds nine source files, historical compatibility, Root18/45 controls, worker110/89PS and66focused/343full Node PASS with11optional skips, and the authoritative72-file Root/22-file independent final seals. The exact integrated workflow also adds the separately reviewed GUI's two Node tests; a bounded independent CI-delta receipt seals that addition. GUI7 has its own source-only record/review. Actual official schema8 Research, human pixels and new-source CI remain separate next gates. No scientific criterion or Core/Domain/adapter equation changed.
