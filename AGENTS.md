# Autonomous CAE Lab — development instructions

## Product and current direction

Build a lightweight engineering research workbench, not a CAD-demo framework or
an enterprise simulation-management system. Material evaluation, parameter
identification, PDE, structural/explicit analysis, data-only research and solver
experiments are first-class uses. CAD is optional. Python/API and CLI use must
not require an AI provider, OpenScience or MCP. Expert assistance, knowledge
retrieval, literature tools and MCP are optional integrations.

Read `docs/WORKBENCH_REDESIGN.md` for the W1–W5 design. Read
`docs/WORKBENCH_USE_CASES.md` for concrete research questions, inputs, outputs,
limitations and the final implementation handoff. The latter is a use-case
appendix, not a replacement architecture or a new profile system. Then inspect
relevant code, tests and current Git state. Do not preload all ADRs or cumulative
status histories. Search those records only for the behavior being changed.

The owner's current instructions take precedence over historical project
policies. Old `PROJECT_SCOPE.md`, `HANDOFF.md`, `CURRENT_STATE.md`, ADRs and
OpenScience contracts are historical references, not an instruction to keep
obsolete profiles, prompt bytes, exact model choices or development ceremonies.
They remain useful sources for earlier requirements and numerical observations;
this redesign does not certify or erase those observations.

## Development setup and orchestration

Read `docs/CODEX_WORKFLOW.md` for model/reasoning, usage control, task ownership,
W1–W5 integration and session handoff. Read `docs/DEVELOPMENT_SKILLS.md` for the
existing skills, their sources, dependencies and explicit invocation conditions.
These documents supplement, not replace, the product design and use cases.
The tracked launch instruction is `CODEX_START.txt`; do not depend on chat history
or an older attached prompt for missing decisions.

Use `.codex/config.toml` and `.codex/agents/` as project development defaults,
subject to the actual client, account, trust and user overrides. Verify effective
settings once; do not claim repository files have changed the user's running app.
The normal lead is Astra High, helpers are Sol High, and at most two helper
threads are open. Use Extra High only for a difficult bounded decision. Do not
spawn recursively or auto-enable paid speed modes, purchases or API fallback.

The vendored `research`, `grill-me` and `grilling` are explicit-use development
skills under `.agents/skills/`. Select `research` for substantial reuse/API
questions. Select the interview skills only for genuinely unsettled user
choices. Do not restart the agreed product interview. Follow the skill-use
catalog rather than installing every previously mentioned tool.

Keep one current progress record. After a feature bundle, return to the whole
W1–W5 and use-case outcomes. Close finished helpers and carry forward the next
implementation location, not another full audit or duplicated history document.

## How to work

- Begin a substantive bundle with the user-visible outcome and its place in the
  whole workbench. Track material identification, CAD-free numerical research,
  existing-result analysis and defect/expert consultation together. Do not let
  the easiest fixture or smallest validation issue replace those outcomes.
- Reuse implemented CAD-free APIs and SciPy integration before introducing
  replacements. Do not substitute another example for a feature. Example case
  IDs, numbers, material names and sample counts are not product restrictions.
- Before building reusable infrastructure, inspect the repository and relevant
  maintained libraries/tools. Compare integration cost, runtime overhead,
  deployment, license and exit cost. Reuse, wrap, simplify or build according to
  fit; neither a large framework nor custom code is the default. Small fixes do
  not require an elaborate research ceremony.
- Existing development skills may help challenge assumptions, search for reuse
  or review complexity. Inspect their actual source and dependencies first.
  Do not create a new skill or install an entire harness by default. Development
  aids such as grill-me or Ouroboros are not product runtime requirements.
- Complete coherent feature bundles with their input, real calculation/tool
  use, output and consuming UI/API. Review architecture before shared-interface
  changes; do not demand a new approval, ADR or duplicated report per small edit.
  Use independent review when useful; do not claim unavailable reviewers ran.
- If assigned the whole redesign, continue beyond W1 through the dependencies
  of W2–W5. Record missing native runtimes or model accounts accurately and keep
  independent implementation moving. Do not relabel missing live verification
  as complete, or restart a full audit for each blocked connection.
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
  If measured overhead is already small, report that result and continue to the
  next user function. Do not force endless micro-optimization to invent a gain.
- Use one implementation of a behavior through Python, CLI, GUI and optional
  transports. Never require an OpenScience session for ordinary computation.
- Browser teaching calculations and rule-based expert examples are explanatory
  artifacts, not production backends or proof of live agent execution. Reuse
  established numerical/retrieval/agent libraries for the product.

## Accuracy, data and completion

Never invent solver runs, timings, tests, physical validation or successful
cleanup. A numerical result, a software check and approval for an actual design
are different claims. Do not relax a scientific reference just to make tests pass.
Exploratory work may retain assumptions and unresolved checks without pretending
that it has been approved for production. Expert agreement is not causal proof;
preserve opposing evidence and the test needed to distinguish hypotheses.

Protect credentials, company data, user edits and uncommitted work. This repository
is public. No silent model/provider fallback or transfer of private content.
Do not delete user-owned raw data or adopt unknown running processes. Use isolated
branches and work directories; no force-push or merge without authorization.
Hashing may identify important inputs/results; it must not freeze ordinary
prompts or policies indefinitely. Describe records to the user as execution
history, source, validation basis and result files rather than unexplained jargon.

Finish each bundle with what the user can now do, an actual input/run/result,
changed or removed responsibilities, checks actually run, limitations and the
next coherent outcome. Update current documentation only where needed. Do not
copy progress into several historical documents. A plan is not a feature, and
passing a narrow test is not whole-system proof. W1–W5 complete the defined first
workbench, not every physical model, solver card, coupled system or device.
