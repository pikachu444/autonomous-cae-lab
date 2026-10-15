# Mixed-domain API — root/Sol consumer contract

Request PRO-NUMERICAL-MIXED-DOMAINS-20261015-01. Existing Numerical entry points remain the execution authority. No new optimizer, scheduler, model setter, document owner, store or compiler is introduced.

## One declaration boundary

`caelab.variable_domains.normalize(variables)` normalizes and validates without evaluating expressions. `VariableDomains(raw)` exposes `.variables`, `.free`, `.order` (dependent topological order), `.snapshot`; it parses existing dimensioned_expression trees. GUI consumers use `variable_schema()` for fields, `normalize` for semantic diagnostics, and `capability(method, variables)` for per-method admission. Do not rebuild types in a widget or strip fields to the old continuous schema.

Common fields: `id`, `unit`, optional `kind` (continuous/integer/discrete/categorical), `mode` (free/fixed/dependent), `transform` (linear/log). Kind/mode omission means legacy continuous/free. Public Plan schema uses id/lower/upper/value; the numerical Python boundary also retains parameter_id/lower_bound/upper_bound/initial aliases, rejecting simultaneous aliases.

- continuous free: finite increasing lower/upper, initial value in range; log requires strictly positive bounds. Legacy omitted initial is the existing midpoint.
- integer free: bounded interval with at least one integral member. Explicit candidates require Python/JSON int, not bool or 1.0. Sampler/AST exact integral coordinates may be converted to int before dispatch, never rounded afterwards. Float64-exact integer bound: absolute value <= 2**53-1.
- discrete: `values` is a nonempty finite strictly increasing numeric list, at most 256 entries. No duplicates, including equal int/float representations. Optional bounds must include the entire set. Samplers output declared values, preserving their declared numeric types.
- categorical: unit `1`, no numeric bounds; `choices=[{'id':..., 'label':..., 'value':...}]`, with distinct nonempty string IDs, labels and actual string values. At most 256 choices. Numeric/string mixed enumerations are rejected. The model receives `value`, never `label`, `id`, or index.
- fixed: explicit value, no exploration coordinate. Numeric bounds may be omitted and then equal the fixed value. A categorical fixed input still refers to its advertised choices.
- dependent: numeric continuous or integer kind; expression and output bounds; no value/initial. Existing safe scalar AST, SI dimensions, maximum 2048 characters/256 nodes. Dependent categorical/discrete outputs are explicitly unsupported. Maximum 64 Plan variables. No unit scale/offset inference.

`DomainError(ValueError)` provides `code`, `path`, optional one-based line and zero-based column, and `diagnostic()`. Codes distinguish duplicate/unknown/self/cyclic dependency, bad units, unsafe expression, fractional integer, membership, division by zero and range rejection. Existing ExpressionError is wrapped with its location. Do not substitute zero for a rejected expression.

## Generation, dispatch and accounting

`VariableDomains.resolve(free_values)` constructs a new independent full assignment in DAG order. User values must match free IDs exactly; fixed/dependent overrides are errors. Explicit invalid free inputs fail admission. A dependency failure during candidate preparation is retained as a REJECTED row with `domain_error`, and no model dispatch for that row.

Existing `run_doe`, `optimize`, `epsilon_optimize` use this boundary. LHS uses SciPy qmc's existing random cube and inverse-CDF finite bins, with replacement. This preserves the existing continuous LHS sequence; it does not claim an orthogonal array over categories. DE maps discrete/category choices to integer axes and supplies public `integrality` to the existing ScipyDifferentialEvolution. Choice order is an algorithmic encoding and affects seeded search, not a physical distance; results preserve the order. No order-invariance or categorical derivative is claimed. Existing DE polishing policy is unchanged.

Result `domain_input` contains the original declaration, normalized declaration, free/dependent order, unit policy and SHA256. Each `domain_assignment` contains domain/candidate IDs, free values, full values, exact category IDs, resolved/rejected status and its seal. `domain_accounting` distinguishes requested/retained rows, unique free assignments, repeats, finite Cartesian size/coverage before dependent/domain rejection, and actual model_calls. `solver_dispatch` distinguishes library objective/constraint callback visits and exact cache hits from actual evaluator calls. Epsilon child IDs are namespaced with the preserved assignment resealed only for that ID. There is no expression re-evaluation during this identity change.

An all-fixed/dependent model produces no search axis and is evaluated through the existing evaluator. A finite domain may be exhausted before a requested DE budget; repeats are cached. DOE repeats remain separate evaluations. Process/batch cancellation and total budgets remain owned by `_Evaluators`/JobManager. A rejected dependency is not a physical failure; unsuccessful calculation, constraint infeasibility, physical objective and optimizer penalty remain separate.

## Actual bindings

`variable_binding.admit_domains(normalized, descriptors)` verifies the Plan subset against the actual advertised physical input and exact unit; Plan subsets do not rewrite physical bounds. A numeric parameter may use a Plan integer/discrete subset. A categorical parameter must match an actual enum by ID/label/value. An enum cannot be declared as numeric indices.

The existing ODE adapter advertises one new input, `solver-method`, unit 1, role `numerical_setting`, choices RK45/DOP853/Radau/BDF. This exact ID deliberately cannot collide with the ODE's identifier syntax for numeric parameters. Only adapter-owned paths are applied. The existing domain setter and model_parameters settings/declaration/mirror/effect checks remain the admission gate. ODE's already supported maximum 64 numeric parameters plus this enum are admitted; other adapters retain their 32 descriptor limit.

`actual_binding(adapter, template, bound, assignments)` records already-checked assignments, actual advertised values, template/descriptor/settings/declaration hashes and adapter version. `verify_actual_binding` uses the original pure checked bind, not the solver. Typed PDE adoption requires this receipt. Material/Simulation legacy and controlled non-native records keep their existing policy; file-native typed records require the actual binding receipt. Existing EvaluationDefinition stage compiler/setters carry enum and full dependent assignments. Its completed stage is read through the existing writer/reader before hash/progress publication so actual ndarray responses are consumed as detached lists. No B6 iteration or field-mapping algorithm is changed.

## Read-only retained input and exact owners

`verify_retained(snapshot, normalized_variables, candidate)` checks seals, original declaration/order, types/membership, fixed values, category identity and the full assignment. It parses syntax/dimensions but **never evaluates the dependent expression**. This is retained integrity, not a second numerical proof. Existing immutable result/ref hashes, C03/C2 scope, source revision, owner session/generation and CAS remain authoritative. Hashes are not signatures authenticating a maliciously resealed external record.

`verify_candidate` also matches raw declarations against the frozen submitted Plan. pde_candidate/domain_candidate use full IDs, not only free IDs, and preserve actual typed values on preview/adopt. Saved results never acquire new type interpretation from a newly edited Plan. A legacy continuous 1.5 stays 1.5.

`validate_retained_table(table)` checks retained tables without solving. `retained_candidates(snapshot, variables, candidates)` is for exact exchange or explicitly requested new evaluation: it copies preserved resolved assignments and never executes the DAG. `run_doe(..., candidates=full_retained_rows, domain_input=retained_capsule)` requires both and is a NEW execution, not resume. Normal explicit DOE accepts only free values. Public Request Plan uses existing result references; callers cannot smuggle domain_input through arbitrary input fields. Existing research_operations resolves those refs into this internal argument.

Batch export/import preserve categories as actual strings, int types, full resolved values, candidate/case/source relations and rejected rows. New free candidates are explicitly generated; exporting a saved table must use its capsule rather than recompute dependencies. No new remote Runner protocol is supplied.

`capability` permits typed doe/optimize/epsilon, exchange, empirical statistics/Pareto and read. Existing fit (including mixed DE-fit), least_squares, regression, Sobol sensitivity, UQ and global RBF are unavailable for mixed/fixed/dependent inputs. Existing continuous analyses remain unchanged. `analyze_candidates` reports UNAVAILABLE regression/holdout with sample IDs/count; it does not fit encoded categories. Direct old campaign `summarize` also rejects typed domains. Reporting old results remains read-only. GUI should disable only the unsupported method and preserve drafts/other actions; no GUI file is replaced here.

## External API basis

Official SciPy 1.17.0 documentation reviewed for this implementation:
- differential_evolution integrality, constraints, callbacks and bounded initialization: https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.optimize.differential_evolution.html
- qmc integer inverse mapping: https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.stats.qmc.LatinHypercube.integers.html
- solve_ivp supported methods and tolerance semantics: https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.integrate.solve_ivp.html

The qmc finite-bin policy is declared here rather than calling separate per-axis engines. solve_ivp is used only as an independent test reference; the product's stepwise ODE adapter remains unchanged apart from recording solver_method.
