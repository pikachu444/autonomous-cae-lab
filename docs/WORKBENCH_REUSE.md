# Workbench reuse decisions

2026-10-07. Bounded W1/W2/W4 source investigation; this note does not certify native
solver execution, model access, literature retrieval or the whole redesign.

## W1: retain the existing CAD-free adapter boundary

- `caelab/contracts.py`: `ModelAnalysisAdapter.solve(output: Path, settings: dict)`
  already separates declared-model execution from CAD. Its parameterized extension
  exposes `describe_inputs(settings)`, `bind_inputs(settings, values)` and
  `input_runtime_identity()`. Reuse these for recorded native runs; add prepared
  in-memory evaluation as an optional boundary, rather than another solver manager.
- `Lab.run_model_analysis` / `declared_model.py` own recorded native execution.
  `Lab.__init__` currently imports CAD modules and constructs native adapters
  eagerly. Lazy discovery and solver-independent saved JSON/NPZ readers are needed
  for an installation containing only core dependencies.
- Keep a prepared model/history per worker, reset initial state per candidate,
  and reuse a response for objective and constraints. Plain callable evaluations
  need no registry, CAD-effect check, disk record, AI or MCP. Keep native artifacts
  and optional runtime admission in their existing adapter paths.

## W2: numerical reuse and the necessary small changes

| Function | Existing implementation | Action |
| --- | --- | --- |
| LHS | `optimizers/scipy_lhs.py:sample(variables, *, count, seed)` and `ScipyLatinHypercube` | Reuse SciPy sampler; replace CAD registration checks with ordinary numeric declarations for direct calls. |
| Single-objective/constraints | `ScipyDifferentialEvolution.run(variables, evaluate, *, seed, max_generations, population_size, initial_values, constraint_count)` | Reuse feedback `{'objective': float or None, 'constraint_residuals': list}`; invalid feedback remains invalid. `_validated_variables` currently requires registered `PASS` input/geometry effects. Separate numeric validation; never invent successful effect evidence. |
| Statistics/regression/surrogate/Pareto | `campaign_analysis.summarize(samples, variable_definitions, response_definitions, *, seed=13)` | Already a pure NumPy calculation. Bridge common candidate rows to `{id, values, responses, usable}`; responses contain `{value, unit, valid, reason?}`. Variable declarations use `{parameter_id, unit, lower_bound, upper_bound}`. |
| UQ | `probabilistic_analysis.declare_samples(request)` and `.analyze(declaration, rows, thresholds)` | Already pure; currently independent continuous uniform marginals only. Preserve assumed/measured/published origin and complete failed rows. |
| Epsilon multiobjective | `multiobjective.create(... objectives, primary_index, threshold_grid, child_budget, seed, total_evaluation_budget)` and `optimizers/epsilon_campaign.py` | Retain epsilon child searches and common Pareto analysis. Current orchestration binds saved native plans/receipts. Do not introduce a handwritten MOEA; make common direct evaluation usable by existing child searches. |

`campaign_report.py` is persistence orchestration, not the direct analysis API: it
requires a completed saved campaign and verified plans. Its pure calculation
modules can accept external or in-memory candidate tables without that condition.
Current `campaign_analysis` limits are 2–512 rows and 1–16 variables/responses;
these are implementation bounds, not product/example restrictions. Its sensitivity
is normalized multivariate least squares, not Sobol indices. Its surrogate uses a
seeded 75/25 split, declared-bound normalization, and training-only affine/quadratic
degree selection; expose prediction and out-of-range labeling around that fit.

Installed SciPy **1.17.0**, NumPy **2.3.5** APIs were inspected directly:

```python
least_squares(fun, x0, jac='2-point', bounds=(-inf, inf), method='trf',
              x_scale=None, loss='linear', f_scale=1.0, max_nfev=None,
              callback=None, workers=None, ...)
differential_evolution(func, bounds, ..., rng=None, updating='immediate',
                       workers=1, constraints=(), x0=None, vectorized=False)
qmc.LatinHypercube(d, *, scramble=True, strength=1, optimization=None, rng=None)
RBFInterpolator(y, d, neighbors=None, smoothing=0.0,
                kernel='thin_plate_spline', epsilon=None, degree=None)
```

Use bounded `least_squares` on actual mapped curve residuals, with per-curve scales
and weights explicit. `workers` parallelizes numerical differentiation, not an
arbitrary independent candidate study; process evaluation needs a serializable
factory and worker-local preparation. DE worker/vectorized modes use deferred
updating. Preserve existing numerical callbacks and availability handling.
SciPy/NumPy use BSD licenses; additional RBF dependency is unnecessary.

Optional **SALib 1.6.0** (MIT, Python >=3.10) supplies
`sample.sobol.sample(problem, N, calc_second_order=False, scramble=True, seed=...)`
and `analyze.sobol.analyze(problem, Y, calc_second_order=False, seed=...)`.
First/total-order plans need `N*(D+2)` actual responses in original order;
second-order plans need `N*(2*D+2)`. Do not pass ordinary LHS or delete failed rows.
Dependencies include NumPy>=2, SciPy>=1.9.3, pandas, matplotlib and multiprocess;
keep it an optional global-sensitivity extra.

## Actual two-parameter material evaluation

Recommended optional library: **FELUPE 11.1.3**, released 2026-09-28, Python >=3.10,
pure `py3-none-any` wheel, base dependencies only NumPy/SciPy, **GPL-3.0-or-later**.
Keep its dependency/license visible in material installation and distribution
documentation. It is not installed in the project venv at this investigation.

```python
law = felupe.LinearElastic(E=1000.0, nu=0.25)
# F = identity + prescribed displacement gradient, shape (3,3,1,n)
stress, state = law.gradient([F, np.zeros((0, 1, n))])
tangent = law.hessian([F, np.zeros((0, 1, n))])[0]
```

This is established small-strain isotropic elasticity, evaluated by the library;
history samples are prescribed states, not a claim of viscoelastic/plastic memory.
Use independent constrained axial/lateral or shear observations to identify E and
nu. Free uniaxial axial stress alone cannot identify both. Tangent is library
computed. A second existing option is
`felupe.NeoHookeCompressible(mu, lmbda)`: `.gradient([F,state])` returns **first
Piola–Kirchhoff stress**, `.hessian` its tangent, `.function` energy. Preserve
stress measure and finite-strain admissibility rather than calling every output
Cauchy stress. No custom constitutive equations are needed.

Actual research smoke: extracted FELUPE wheel in `/tmp/workbench-reuse-source/felupe`
and imported it through a temporary `sys.path`; vectorized linear and compressible
Neo-Hookean `gradient`/`hessian` calls passed. For E=1000, nu=.25 and prescribed
eps11=.001 with zero lateral strain, library sigma11=1.2 and sigma22=.4.
This is API/numerical evidence, not measured material qualification or a fit test.
Existing `material.mfront.inverse` varies E only and retains frozen native-runtime
constraints; keep it accurate rather than relabeling it as two-parameter fitting.
MGIS/FELUPE/hyperelastic were absent from the current venv. Hyperelastic 0.10.2
is another GPL3+ option but adds matplotlib and supplies no advantage for this
minimal first path.

## W4: optional Haystack and public literature

**Haystack AI 3.3.0** (released 2026-10-01, Apache-2.0, Python >=3.10) is current.
Its source provides:

```python
store = InMemoryDocumentStore(bm25_algorithm='BM25L', shared=False)
store.write_documents([Document(content=text, meta=source_metadata), ...])
retriever = InMemoryBM25Retriever(document_store=store, top_k=10)
retriever.run(query=query, filters=filters)  # returns documents
Agent(chat_generator=configured_generator, tools=tools,
      max_agent_steps=budget, exit_conditions=['text'],
      raise_on_tool_invocation_failure=True, tool_concurrency_limit=1)
Tool(name=..., description=..., parameters=json_schema, function=existing_api)
```

BM25 needs no model credentials; preserve original text/source/chunk locations
outside its reconstructible index and test Korean/English/identifier retrieval.
BM25 alone does not establish semantic retrieval quality. Agent requires a
configured generator supporting tools; tool loops are Haystack's responsibility.
Wrap existing calculation/search/job APIs and bounded expert consultation, with
actual model absence reported unavailable. No model-per-candidate evaluation.
Keep inference/model transfer explicitly configured. Haystack has a substantial
optional dependency set (OpenAI client, pydantic, HTTPX, networkx, posthog etc.);
do not place it in core or require an OpenAI account merely to use BM25.

Latest 2.x is **2.31.0**: same BM25 API; Agent instead has
`tool_invoker_kwargs`/`confirmation_strategies` and no `tool_concurrency_limit`.
Prefer current 3.3 for a new optional path unless an existing host integration
requires 2.x; use the matching version's signatures. Neither Agent nor BM25 was
runtime-tested here; both wheels were read in `/tmp/workbench-reuse-source/`.

Minimal literature provider: a thin **Crossref public REST** adapter using stdlib
urllib or existing HTTPX, `GET /works?query.bibliographic=...&rows=...` and DOI
lookup. Crossref's own README states public access needs no registration/token;
optional `mailto`/identifying User-Agent enters its polite pool. Retain DOI/title,
authors/year/URL, abstract availability, link/license metadata and retrieval time.
Metadata, an abstract and accessible full text are distinct statuses; a
`has-full-text` link is not proof that the client retrieved/read it or has reuse
permission. Preserve full-text failure/paywall and allow a user-provided article
to become local sourced knowledge. A vendor SDK/full literature framework is
unnecessary for this first provider.

Official Crossref documentation was retrieved successfully from GitHub raw.
Live Crossref, OpenAlex and Europe PMC requests, and general SciPy/Haystack docs,
were blocked by this environment's network proxy (403). This is a network
limitation, not evidence that credentials are required. No live literature
result or model invocation succeeded during this investigation.

## Primary sources inspected

- Repository code cited above; current installed SciPy source/docstrings and
  signatures (`.venv/lib/python3.12/site-packages/scipy/optimize/`, `stats/_qmc.py`).
  Official references: [least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html),
  [DE](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html),
  [RBF](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.RBFInterpolator.html).
- First-party package wheels/metadata from PyPI:
  [FELUPE 11.1.3](https://pypi.org/project/felupe/11.1.3/),
  [SALib 1.6.0](https://pypi.org/project/SALib/1.6.0/),
  [Haystack 3.3.0](https://pypi.org/project/haystack-ai/3.3.0/),
  [Haystack 2.31.0](https://pypi.org/project/haystack-ai/2.31.0/).
  Wheel sources inspected include FELUPE `constitution/linear_elasticity/_linear_elastic.py`
  and `_neo_hooke_compressible.py`, Haystack `components/agents/agent.py`,
  `document_stores/in_memory/document_store.py`, `components/retrievers/in_memory/bm25_retriever.py`,
  and SALib `sample/sobol.py` / `analyze/sobol.py`.
- [Crossref official REST documentation](https://github.com/CrossRef/rest-api-doc)
  ([retrieved raw source](https://raw.githubusercontent.com/CrossRef/rest-api-doc/master/README.md)).

Only this note was added to tracked files by the research task. No product,
configuration or environment dependencies were changed.
