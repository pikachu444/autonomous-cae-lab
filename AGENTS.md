# Autonomous CAE Lab — development instructions

## Product and current direction

Build a lightweight engineering research workbench, not a CAD-demo framework or
an enterprise simulation-management system. Material evaluation, parameter
identification, PDE, structural/explicit analysis, data-only research and solver
experiments are first-class uses. CAD is optional. Python/API and CLI use must
not require an AI provider, OpenScience or MCP. Expert assistance, knowledge
retrieval, literature tools and MCP are optional integrations.

Read `docs/WORKBENCH_REDESIGN.md` for current decisions, verified findings and the
next implementation bundle. Then inspect relevant code, tests and current Git
state. Do not preload all ADRs or cumulative status histories. Search those
records only for the specific behavior being changed.

The owner's current instructions take precedence over historical project
policies. Old `PROJECT_SCOPE.md`, `HANDOFF.md`, `CURRENT_STATE.md`, ADRs and
OpenScience contracts are historical references, not an instruction to keep
obsolete profiles, prompt bytes, exact model choices or development ceremonies.
They remain useful sources for earlier requirements and numerical observations;
this redesign does not certify or erase those observations.

## How to work

- Begin a substantive bundle with the user-visible outcome and its place in the
  whole workbench. Reuse implemented CAD-free APIs and SciPy integration before
  introducing replacements. Do not substitute another example for a feature.
- Before building reusable infrastructure, inspect the repository and relevant
  maintained libraries/tools. Compare integration cost, runtime overhead,
  deployment, license and exit cost. Reuse, wrap, simplify or build according to
  fit; neither a large framework nor custom code is the default. Small fixes do
  not require an elaborate research ceremony.
- Existing development skills may help challenge assumptions, search for reuse
  or review complexity. Inspect their actual source and dependencies first.
  Do not create a new skill or install an entire harness by default. Development
  aids such as grill-me or Ouroboros are not product runtime requirements.
- Complete coherent feature bundles. Review architecture before shared-interface
  changes and integrate/test the whole bundle; do not demand a new approval,
  ADR or duplicated status report for every small edit. Use independent review
  when it materially helps; do not claim unavailable reviewers ran.
- Remove obsolete code and tests when their contract is intentionally replaced.
  State the removed behavior and the replacement checks. Prototype API and
  development-record compatibility are not unconditional requirements.

## Technical boundaries

- Numerical libraries/solvers perform numerical search and physics. LLMs plan,
  retrieve, interpret and request tools; do not invoke an LLM per objective call.
- Keep domain meaning and backend syntax distinct, without inventing a universal
  schema for every solver. Preserve native input/result files when useful.
- Keep expert knowledge, installed capability, execution resources, authorization
  and scientific checks separate. Do not encode them as copied scenario profiles.
- Separate fast in-memory/batch evaluation from recorded long-running jobs.
  Measure direct-library overhead, I/O, memory and concurrency before claiming
  speedups. Protect short record updates without serializing independent solves.
- Use one implementation of a behavior through Python, CLI, GUI and optional
  transports. Never require an OpenScience session for ordinary computation.

## Accuracy, data and completion

Never invent solver runs, timings, tests, physical validation or successful
cleanup. A numerical result, a software check and approval for an actual design
are different claims. Do not relax a scientific reference just to make tests pass.
Exploratory work may retain assumptions and unresolved checks without pretending
that it has been approved for production.

Protect credentials, company data, user edits and uncommitted work. This repository
is public. No silent model/provider fallback or transfer of private content.
Do not delete user-owned raw data or adopt unknown running processes. Use isolated
branches and work directories; no force-push or merge without authorization.
Hashing may identify important inputs/results; it must not freeze ordinary
prompts or policies indefinitely. Describe records to the user as execution
history, source, validation basis and result files rather than unexplained jargon.

Finish with changed behavior, checks actually run, limitations and the next
coherent outcome. Update the current plan only where its status changed; do not
copy the same progress narrative into several historical documents. A plan is
not an implemented feature, and passing a narrow test is not whole-system proof.
