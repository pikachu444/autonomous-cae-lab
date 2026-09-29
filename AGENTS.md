# Autonomous CAE Lab — instructions for every agent session

## Recover state before editing

Read these repository files, in this order, before planning implementation:

1. `PROJECT_SCOPE.md` — the user's complete 52-section requirement ledger and acceptance inventory.
2. `HANDOFF.md` — verified checkpoint, local setup, blockers and next work.
3. `CURRENT_STATE.md` — recovered implementation history and unresolved assumptions.
4. `ARCHITECTURE.md` and all `ADR/*.md` — platform boundaries and accepted decisions.
5. `openscience/contract.md` and the relevant acceptance/backend documents under `docs/`.

Then inspect `git status`, recent commits, the pinned submodule and applicable
code/tests. Check CI for the **exact source commit** under discussion. A later
documentation commit is not a new solver verification. Do not assume cloud
processes, downloaded CI ZIPs, installed dependencies or another session's chat
are available on this computer. State missing evidence explicitly.

Treat the ledger as the continuing project scope. A new session or short prompt
does not erase earlier authorized work. Do not restart implemented features or
ask the user to decide a question already answered in an ADR. When historical
transcripts are unavailable, use recovered files/code/tests and mark the gap;
do not invent the missing conversation.

## Non-negotiable architecture

- OpenScience is the research control plane: questions, hypotheses, campaign
  choices and interpretation. Core exposes solver-independent operations.
- Deterministic numerical engines generate DOE/search candidates. An LLM is
  not the default numerical optimizer.
- Core owns common schemas, research parameter mappings, execution gates,
  artifacts, evidence, validations and provenance. Domain plugins own
  engineering rules. Adapters own all backend syntax and native CAD paths.
- Reuse the pinned `plugins/fixture_design/upstream` implementation through
  adapters. Read its code before changing the integration; do not copy or
  replace its tested behavior casually.
- Human GUI inspection and headless execution must refer to the same native
  model/revision and artifacts. Preserve editable CAD.
- Validation is a verdict; evidence is its basis. Unknown machine, material,
  strength, physical and durability requirements stay `UNKNOWN` and prevent
  release. Solver exit success and CI success are not engineering approval.
- Invalid parameters/CAD must block export and downstream solver execution.
  Preserve old results; append a new experiment/revision for a new run.
- Never loosen a numerical threshold or substitute a different response just
  to make acceptance pass. Explain failures and retain invalid metrics.

## Work, review and checkpointing

One owner changes common schema/Core/registry/provenance interfaces. Use
sub-agents for independent research, bounded implementation or verification
when supported and useful, as requested by the project owner. Root reviews
their evidence and owns integration; record important findings in the repo.
Avoid concurrent edits to the same shared interface or file.

For a material architecture change, record reasons, alternatives, requirement
impact, ADR, relevant tests and OpenScience contract impact. Verify with a
meaningful acceptance/benchmark, not merely an exit code. Canonical benchmarks
require an analytical/reference/cross-solver comparison and clear limitations.

Commit meaningful, verified units. Check the staged diff and working tree,
preserve user edits, and push only through authorized access. Do not force-push
or erase history. If push is blocked, keep a local commit and report that it
is unpushed. Do not claim work is durable remotely before confirming it.

At every meaningful checkpoint, update `CURRENT_STATE.md`, the applicable
acceptance record and `HANDOFF.md`; update `PROJECT_SCOPE.md` statuses without
silently removing requirements. Record exact commit/run IDs, versions,
assumptions, failed attempts, artifact hashes/retention and next acceptance
gates. Important knowledge must survive outside the conversation.

Use new store paths/experiment IDs when reproducing acceptance. Never overwrite
historical experiments. Keep credentials, company CAD/data and environment
secrets out of commits; the supplied repository is currently public. Corporate
license/security approval remains an open deployment requirement.
