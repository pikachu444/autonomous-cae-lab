# Current workbench implementation

## Verified live research chain — 2026-10-08

The optional OpenScience 2.0.146 provider uses the existing approved ChatGPT
OAuth profile and `openai-codex/gpt-5.6-sol`. It now connects through the official
SDK's authenticated, ephemeral loopback Streamable HTTP MCP server. A Windows
stdio host startup race was reproduced; the installed runtime was not patched
or its process ownership checks bypassed. Temporary configuration exposes only
scoped tools and disables unrelated deliverable/acceptance/review continuation
harnesses. Exact result/document scope remains enforced by Core callbacks.

- D: GUI expert job `Jba9efaca329c4ba7a5baae3213de7d99` read the selected local
  document and one actual public abstract (doi:10.2478/sgem-2025-0008), inspected
  registered inputs, and proposed DOE8 through five real tools. The operator
  edited mass to 1.2 kg, stiffness upper bound to 130 N/m and seed to 41 in the
  form, then ran `Jaad26b66365245399a1fb91113c779b8` (8 real external DOP853
  evaluations). Analysis `J29e8f4c5acc747b28312a62886ebcfc7` computed force
  abs_max 0.5044949266–1.1935027409 N, normalized stiffness/damping regression
  coefficients 1.0000000000 / 3.14e-16, and two-point holdout RMSE 2.15e-16 N.
- E: `Jd9657039f35a4b9099c58c1cbcec0825` actually read both saved results and
  consulted the authorized testing expert once. It explained the initial-force
  confound, limited holdout and lack of causal/physical proof, then proposed
  the same DOE with initial velocity 0.05 m/s. After bounded GUI authorization,
  `J50df681fd4aa42e79a44cd7e6e8a9ec9` submitted the actual eight-evaluation
  job `J8bbbc7942c9046f9aed41babedbb9193`. Analysis
  `Jcabf6666d9e24925b5135d747fe43ab7` computed force range
  0.7353048127–1.3527743352 N, stiffness/damping coefficients
  1.0990343106 / 0.1465053562, and two-point holdout RMSE 0.00370097494 N.
  These are conditional sample statistics, not invented model influence scores.
- F transport/recovery: after service restart, the same conversation
  `f18e42c48dfd43f187f45ef54ab1528f` used the actual external OpenScience host
  to read the generated DOE through its persisted grant, without adding it to
  the new selected list. `Jdf79a382e204427c99cc833672c71186` made six real
  status/result calls. Its final answer lost useful claims during strict
  citation repair; this failed interpretation is retained. Follow-up
  `J6cd084f4d2cf435db9c7f5f3e1b28a7c` copied the true numbers but wrongly
  claimed mass had changed. Selecting the original DOE as well let
  `J757e599719804e189c3bf5ec11d310bd` reread both conditions and correct
  that claim: both mass1.2 kg, identical eight candidate pairs/seed41, only
  initial velocity0→0.05 m/s changed. Five real tool calls, no new calculation
  or consultation, accepted exact citations and correct coefficient/RMSE
  comparison. SDK-only tests are separate from this actual external-host proof.
- Current remote-host cancellation: GUI job
  `Jaad4a1c294ef496796531e4fbf3adf9c` transitioned RUNNING → CANCEL_REQUESTED
  → CANCELLED (18:06:22–18:06:36 UTC). Owned Windows CLI PID101776 was observed
  before cancellation and absent afterwards; structured host cleanup was
  confirmed. Receipt: local `output/gui-model-cancel-remote.json`.
- B rerun with the newly qualified OpenCourant pin: fresh
  `workbench-native-flow-20261008-06` passed actual PDE33 and explicit200
  selected samples, changed-gravity comparison, PDE self-comparison and
  solver-free restart. PDE `Jcd0169062ba04feb84d0eda001631d98`, explicit
  `Je927911d3989472995e531034a9c9387`, changed gravity
  `Je159c0b46d074f47a3eeb1ee3acd0904`. Previous OpenRadioss22-channel output
  remains readable; the new runtime's23-channel format is separately admitted.
- Actual GUI displays influence statistics, conditional coefficients, heldout
  error and limitations. Report preview uses the same standalone HTML as the
  download action and includes selected study arguments. Saved local evidence:
  `output/ui/actual-influence.jpg`, `research-report-preview.jpg`,
  `followup-research-report.html`, native and file/curve screenshots.
  IAB download delivery itself was not confirmed; displayed report HTML was
  saved directly and visually checked.

The upstream OpenRadioss release URL now returns404. New official community
successor OpenCourant source/runtime pins and clean-source analytical flight
and compliant-contact qualification are documented in
`OPENCOURANT_RUNTIME_QUALIFICATION_20261008.md` / ADR0059. Two rigid-wall tests
remain rejected; unknown physics is not promoted to approval. No republished
third-party release was created. Canonical Code_Aster Fz remains rejected;
MUMPS iterative-refinement probe also failed FACTOR_57 (3.07939e-6 > 1e-6).

Full local regression during concurrent integration: 6541 passed,20 failed,
4 skipped. Failures included source drift during edits, Windows/WSL Git setup,
CRLF-only source fingerprint, a missing ignored artifact folder and process
startup timing. Focused repairs passed; final frozen-source checks and exact
PR-head CI are tracked below. Prior `acbe38c` CI `37656946351`: seven jobs
passed; explicit failed on upstream404, PDE on reaction-case preasymptotic
convergence, Code_Aster on the retained canonical reaction gate. The download
and PDE issues have been corrected without changing numerical limits. Clean
`f64584f` full vector verification passed all6 accepted,3 expected numerical
rejections and5 preflight refusals over27 meshes; exact hashes and retained
coarse failures are in `PDE_VECTOR_PACKET.md`. Independent final Astra High
review reports no remaining actionable blockers after the continuation fix.


Final review also reproduced an upstream continuation issue: the next CLI
invocation automatically resumed the cancelled internal session. The official
`harness.durable-jobs=false` overlay now gates bootstrap `resumeInterrupted()`.
A following actual turn left the still-eligible interrupted session untouched;
its own answer/tool calls completed. No runtime/auth patch or history deletion
was used. Cancellation means owned process cleanup plus no later automatic
revival through this host, not simply a CANCELLED label. The erroneous earlier
mass interpretation and initial citation-repair failure remain visible evidence
that model interpretation needs checking against source conditions.

Current targeted workbench tests: **106 passed**; UI Node tests: **15 passed**.
Committed public synthetic screenshots and standalone HTML report are under
`benchmarks/workbench/20261008/`. Raw provider logs, full result artifacts and
private configuration remain local. Frozen-source replay regressions, final
review conclusion and exact PR-head CI are recorded after they finish.

## Earlier 2026-10-08 local integration evidence

Latest-main base is `afcfd27f2ff60c7fac77bbb12c750819702391bf`; exact-base CI
`37643454243` failed. Work is isolated on `codex/workbench-local-integration`;
the original checkout's user edits are preserved. The evidence below was produced
from the dirty integration source and is not exact-commit CI or release approval.

- Actual WSL FEniCSx/OpenRadioss managed jobs, selected common responses, changed
  gravity comparison and solver-free restart passed in
  `workbench-native-flow-20261008-04`: PDE 33 samples and explicit 200 samples,
  explicit changed-gravity comparison and PDE identity comparison.
  The preceding `-01` harness status mistake and `-02` packed-outcome reader
  identity failure are retained; the reader identity defect was corrected.
- Real external SciPy DOP853 process → ASCII → two-coefficient/multiple-history
  fit, independent-history holdout, DOE8 and DE17 passed in
  `workbench-external-20261008-01`. Independent analytical history errors were
  below `3.58e-12 m`; observations are explicitly synthetic from the same law.
- Actual MGIS prepared-library fit through jobs passed in
  `workbench-mfront-fit-20261008-01`: E=274.99999999999994 MPa,
  nu=0.2800000000000008, two fitted histories and separate mixed-history holdout;
  37 updates, 8.52 s preparation and 0.092 s summed candidate execution.
  The prepared product route now uses an operator-registered library/hash and
  does not rerun the fixed package-fingerprint benchmark. Current law coverage
  remains infinitesimal isotropic Elasticity with zero initial state.
- Actual two-worker prepared MFront fit/cancellation passed in
  `workbench-mfront-parallel-20261008-02`: E=275 MPa, nu=.28, 37 model calls,
  independent six-component stress error <=4.44e-16 MPa; 20.37 s fit wall.
  Active DOE cancellation retained 4 successful and 508 cancelled rows and
  closed every owned MGIS child. Five active fit resources and two DOE
  resources were isolated. Peak sum RSS was 387508 KiB (shared pages counted
  repeatedly); child maxrss was 121416 KiB. Verified saved fit/DOE reads took
  .128/.036 s. The preceding `-01` verifier watched the wrong directory and
  missed cancellation; its completed 512-candidate DOE is retained.
  `workbench-mfront-prepared-cost-20261008-01` measured 3.262 s preparation
  and A/B/A calls of 56.3/2.71/1.82 ms, with exact A reproduction.
- Actual external exchange passed in `workbench-exchange-20261008-01`:
  two real program outputs imported, one missing candidate stayed unknown;
  duplicate, changed-value and stale same-case exports were rejected. New
  manifests bind returned rows to an exchange nonce as well as case/values.
  Historical manifests remain readable with explicitly weaker legacy identity.
- Native doctor actual small calculations passed separately for OpenRadioss,
  Code_Aster affine and MFront. Vector PDE finer meshes [16,32,64] pass unchanged
  thresholds; original [8,16,32] remains rejected. Canonical Aster Fz remains
  unresolved: changing essential-condition enforcement did not repair fine-grid
  MUMPS precision or MULT_FRONT reaction balance. GCPC/LDLT_DP with tighter
  1e-12 solver residual also failed the unchanged 1e-7 reaction gate. The
  retained nodal reaction audit shows summed free-node residual explains the
  support imbalance; parser summation is not its cause. No limit was loosened.
- Actual GUI registered an external CSV, mapped units/component/location and
  plotted its 201 samples. It also streamed a Korean-named 25,239,040-byte file
  from an approved root and read 300001 samples. GUI now loads an explicit
  2000-row window, preserving unsliced arrays on disk. Actual GUI PDE run,
  node544 selection (33 samples), explicit run and edited gravity rerun passed.
  Screenshots are under local `output/ui/` (not remotely archived).
- OpenScience 2.0.146 with the existing authorized ChatGPT OAuth profile has
  executed actual MCP tools, local archive lookup and accepted citations.
  First GUI research turn timed out after real literature reads and plan
  creation because nested consultation hit a 60 s MCP timeout. This failed
  turn is preserved. Later runs exposed final-text concatenation, a rejected
  MCP root schema, and a metadata-only citation; all failed runs remain.
  Canonical DOE planning now succeeds through real tools, but full D/E are
  not yet accepted. No credentials were extracted.
- Independent Astra High review reproduced and root fixed: penalized failed fit
  reported as success; completed batch results lost on failure/cancellation;
  compact response retention breaking follow-up numerical analysis. Reviewer
  reran all reproductions successfully. Eight new regression cases pass.

All named raw run directories above are under the private local runtime's
`runs/` directory. The private deployment file selects WSL Ubuntu, the existing
py312 environment, service port8776 and `workbench-service-20261008-01`.
`scripts/cae-research-local.ps1` restarts it without manually combining paths.
Service is running; full regression is in progress. Still required: finish
D/E and external MCP-host acceptance, final GUI comparison/cancellation/report,
final independent integration review, checkpoints and verified PR integration.
Numerical checks never establish physical/material/strength/durability release.

## Prior W1–W5 record

2026-10-07. Based on PR #1 head `90952c5bc1c55da81c4c80b5e266c13339755263`.
This is the single current progress record; historical results and design files
remain intact. W1–W5 code is integrated below. Live model/host/native qualification
and remote merge status are separate from local implementation checks.

## Implemented user outcomes

| Package | Delivered behavior | Verification scope |
| --- | --- | --- |
| W1 | Lazy backend discovery; direct prepared/callable/native execution; solver-independent array records; selectable install; numeric file mapping | Actual FELUPE and text/NPZ imports; clean base wheel; retained native input-rejection contracts |
| W2 | Multi-history fit, independent holdout, DOE/search, stats/regression, UQ, RBF confirmation, matched SALib, epsilon/Pareto, curve/event comparison and identified exchange | Actual SciPy/FELUPE/SALib; explicit synthetic observations; cancellation/budget/process tests |
| W3 | One shared managed workspace through HTTP/CLI/MCP, idempotency, CPU reservations, owned cancellation, interrupted recovery; profile runtime removal | Actual official SDK stdio client queries HTTP-created job; real external process and spawned-candidate cancellation |
| W4 | Versioned original documents, BM25 retrieval, source reopening/revocation, Crossref discovery/read/import; configured experts and bounded consultation/tool loop; editable/executable numerical plans | Actual local retrieval and Haystack Agent with explicitly mocked model; live external connections remain unverified |
| W5 | Editable data/material/fit/DOE/search/UQ forms, actual results/curves/comparison/influence, jobs/cancel, sources/expert plans, fit/holdout HTML reports, optional deployment config | Actual owned Chromium workflow, reports with fit/holdout plots and masked gaps; base-wheel runtime check |

Existing parameterized native adapters join the new numerical path through
`NativeEvaluationFactory`, using the existing `model_parameters.bind` validation
and separate candidate outputs. The factory does not invent parameters for an
adapter lacking `describe_inputs`/`bind_inputs`. Runtime-unavailable single/native
studies still report their actual failure/refusal. Existing Lab/CAD workflows and
scientific reference checks remain available; the original interface uses its
retained Study records, while new workbench clients share the new job IDs.

External solver connection has three explicit modes: importing actual results,
identified candidate exchange, and registered real execution/extraction. Company
commands are operator configuration and stay local to their workspace. Unknown
values and absent returned candidates are not labeled completed. No LS-OPT
installation, LS-DYNA card, company solver execution or qualification is claimed.

## Actual example results

`examples/workbench_numerical.py` generated axial/shear/holdout histories with
FELUPE and recovered **E = 1500 MPa, ν = 0.29000000000000026**. Fit RMSE was
5.95e-15 (axial) and 7.82e-16 (shear); independent-history RMSE was 8.12e-15.
These are synthetic data generated by the same law, so they establish integration,
not identification from measured materials. The two-dimensional callable search
found x = 0.30000055, y = 0.70000237.

For the same 24 material candidates with stress and tangent output:

| Execution | Wall time | Scope |
| --- | ---: | --- |
| Direct FELUPE library | 0.00393 s | No metadata/recording |
| Prepared serial API | 0.03382 s | Metadata/response copies included |
| Two spawned workers | 1.20630 s | Process startup dominates this small workload |
| Serial record / reread | 0.02585 / 0.06954 s | Full selected response arrays; 338 files |

There is no demonstrated process speedup for this small material case. Parent
Python allocation measurements exclude native heaps and child-worker memory.
The measured JSON is retained in `examples/workbench-measured-result.json`;
full local outputs and fit/holdout PNG are under `/tmp/workbench-numerical-w2-final`.
Subsequent review fixes changed cancellation/scope handling, so these timings are
measurements of that example run, not a universal or release-build performance claim.

The reusable `scripts/verify_workbench_ui.py` also ran actual browser flows:
two different synthetic loading histories, fit plus holdout, 8-candidate DOE,
influence calculation, CSV import and downloadable reports. It recovered
E = 1499.999999999978 MPa from initial 900 MPa; the fit report contained both
actual fit and holdout figures. Browser errors: 0. Its own server stopped cleanly.
Evidence is at `/tmp/workbench-ui-reusable-check` in this task environment.

## Removed and replaced responsibilities

The generated OpenScience scenario runtime was retired: `openscience-research.ps1`,
`openscience-native-provider.ps1`, `openscience-server-local.ps1`,
`openscience-local.ps1`, `native_guard.mjs`, `apps/lab/research.py` and the
`lab-openscience.ps1` owner bridge. Dependent frozen-descriptor/source/live-launcher
checks were removed. `cae-research-local.ps1` and `lab-local.ps1` now pass ordinary
workspace/configuration arguments to the shared service. The old authentication
facade only reports migration guidance; no credential/configuration files were
read, rewritten or migrated.

Replacement checks cover current result/document scope, path containment,
request idempotency, controller ownership, actual owned subprocess cancellation,
process-worker cancellation, interrupted recovery, budget/resource limits and
SDK transport. Existing native mesh/domain/process guards remain in their
adapters and existing scientific suites. Generic Git identity code/tests remain.
CI now exercises current workbench behavior in the former source-driver job;
existing native/scientific jobs retain their reference checks.

Independent Astra High review found and integration fixed: cancellation propagation
to spawned evaluators; remote observation path bypass; expert result/status/analysis
scope and transmission; effective resource limits; native thread reservations;
masked-value JSON representation; scientific report omissions; partial-failure
job status; and independent DOE candidate-ID handling for surrogate confirmation.
A further workspace-isolation check prevents external backend configuration from
leaking into another workspace. No reviewer or test establishes live native/LLM
qualification that did not run.

## Validation and external prerequisites

- Full Python regression: **6,537 passed, 10 skipped**, with one existing CadQuery
  deprecation warning (538.57 seconds).
- Workbench targeted suites: **70 passed** after the final registered-callable
  dispatch fix; that fix and its regression test followed the full-suite run.
- A non-UTF-8 locale reproduced a Korean knowledge archive decoding failure.
  Explicit UTF-8 reads now cover document archives, literature caches and expert
  sessions; all **70 workbench tests passed** with Python UTF-8 mode and locale
  coercion disabled. Hosted Windows checks are tracked separately below.
- Node suites: **877 passed**, including 9 current workbench UI tests.
- Actual existing MCP smoke: **passed**, including CAD, DOE/search and native
  preflight refusal. The earlier `report_context` comparison mismatch was fixed
  without discarding checks on the shared result fields.
- Existing HTTP CAD/result/report/ZIP workflow: **passed**. This is distinct from
  the new actual Chromium workbench check, which also passed.
- Final wheel built; a clean base-only installation imported the service, read
  a CSV, saved/reopened its result and constructed/shut down a controller without
  importing or installing CAD, FELUPE, SciPy, Haystack or MCP.
- `pip check` and `git diff --check`: passed.

Live LLM calls, a real product MCP host, external literature access, Windows
PowerShell execution and this session's native FEniCSx/Code_Aster/MFront/OpenRadioss
runs are **unverified**. Mocked model tests use the real agent/retrieval/numerical
tool interfaces but are not live model evidence. The interface reports missing
configuration rather than returning a fabricated expert answer. PDF tables,
figures/OCR, arbitrary native formats, distributed/HPC recovery and additional
constitutive laws are outside this implemented first boundary.

Reviewed implementation was pushed to PR #1's existing branch without rewriting
its earlier commits. GitHub API requests initially returned `Forbidden`; access
became available after delivery, and hosted checks were confirmed running.
Their completion and merge are verified separately from the local results above.
The environment draft preserves package-manager presets and
adds `api.github.com` and `api.crossref.org`, plus updated tested install/start
instructions. Draft persistence is confirmed; application/publication and
fresh-task restoration are not. Review/save and publication are user actions in
environment settings. No branch protection is bypassed or force push used.
