# Autonomous CAE Lab — agent instructions

## Start from the current assignment

Read [CURRENT_STATE.md](CURRENT_STATE.md), [the product overview](docs/PRODUCT_PLAN.md)
and [CODEX_WORKFLOW.md](docs/CODEX_WORKFLOW.md) before choosing work. Then read the
relevant sections of [the detailed product plan](docs/PRODUCT_UI_MCP_PLAN.md),
applicable contracts/ADRs, code and tests. Inspect Git status, source commits,
the pinned submodule and evidence for the exact source under discussion.

CURRENT_STATE is the only current assignment/status/next-action record. HANDOFF
and CODEX_START are short entry points. Dated logs, old SYSTEM plans, R1–R5/W1–W5
instructions and PR comments are evidence or references, not competing current
queues. Do not restart their old tasks or require a full historical audit before
continuing. Preserve PROJECT_SCOPE's original requirements and read its relevant
sections with REQUIREMENTS_VALIDITY_REVIEW; 52 section numbers are not 52 equal
features or a completion percentage. Valid architecture and numerical contracts
remain effective; do not dismiss every ADR as obsolete history.

The latest direct user instruction controls scope and priority, including a new
decision in Space before it is transferred to Git. Distinguish user decisions
from Pro/Codex proposals. Recover missing context from the current records; never
invent previous conversations or assume another machine's files are available.

## Product and responsibilities

Build independently usable engineering research tools: FreeCAD CAD/FE, ParaView
Post, Data, Material, PDE, Numerical, Runner, Expert and related research documents.
Workbench is an optional connection view. Ordinary GUI, Python and CLI use must
not require CAD, AI, OpenScience or MCP when the selected operation does not need
them. Preserve material identification, CAD-free research, external results,
structural/explicit analysis, numerical methods and expert consultation. LS-OPT
is unavailable and must not become a prerequisite.

Pro writes substantial product designs, implementations, related tests/CI and docs.
Codex challenges assumptions, reviews source and actual behavior, integrates the
result and owns current-state/document synchronization. Codex performs the
assigned documentation and integration work; do not silently replace Pro as
the implementation author. Use bounded independent helpers when useful and
supported, with explicit file ownership and no concurrent shared-interface edits.
The lead owns common schema/Core/registry/provenance integration. Actual user
model choices take precedence over old agent-model recommendations.

Complete the authorized outcome. Do not repeatedly stop at plans, transmission
receipts, status reports or approval requests for routine steps already assigned.
Settle material disagreements with Pro and apply the decision. Ask only for an
unresolved user choice or genuinely missing authority; continue independent work.
Do not start unassigned provider calls, native runs or unrelated implementation
merely because an old prompt says to do so.

## User-facing desktop interaction

Use familiar engineering application menus and natural task language. Users should
be able to open their data/model, select or edit it, run the intended operation,
inspect the result and save/reopen without understanding our internal architecture.
Keep internal IDs, hashes, schema names, raw JSON and developer status codes in
optional diagnostic details, not the primary work area. Preserve necessary physical
terms, units, limitations and actionable errors; do not hide them with vague labels.
Follow the adopted application references in PRODUCT_PLAN. Do not replace working
selection/editing flows with helper paragraphs, long forms or decorative summaries.
Use concise names without appended revision tokens or bullet separators. Review
the actual rendered window and task flow before claiming GUI completion, including
readable Korean fonts, focus/selection and recovery. Apply this to every GUI change;
the user must not have to repeat this requirement in each task.

## Technical boundaries

- OpenScience/Expert plans, asks, retrieves and interprets; deterministic numerical
  libraries generate DOE/search candidates and solvers perform physics.
- Core owns shared records, schemas, mappings, execution gates, artifacts, evidence
  and provenance. Domain plugins own engineering rules; adapters own native syntax
  and paths. Reuse pinned `plugins/fixture_design/upstream` through adapters.
- Reuse the existing readers, numerical engines, JobManager and document owners.
  GUI/CLI/Python/MCP must address the same document/revision/result and commands.
  Preserve editable CAD and exact saved source/result relationships.
- Invalid drafts may remain editable/saveable, but invalid required parameters or
  CAD block export and downstream execution. New runs use new IDs/stores; preserve
  old results, failed metrics and original inputs.
- A validation verdict is distinct from its evidence. Unknown machine/material/
  strength/physical/durability requirements remain UNKNOWN and prevent applicable
  engineering release. CI, solver exit success and expert agreement are not approval.
- Never weaken a numerical threshold, replace the requested response or relabel a
  failure to obtain a pass. State supported scope and unverified behavior honestly.
- Before new infrastructure, inspect existing code and maintained tools. Record
  material architectural decisions and their contract/requirement impact; small
  fixes do not require new ceremonies, frameworks or duplicated reports.

## Integrate, record and finish

Verify the behavior affected by the change, including real user workflows when
claiming GUI completion and reference comparisons when claiming numerical validity.
Do not rerun unchanged full suites or native campaigns without a concrete reason.
Keep product implementation, actual execution, usability and engineering qualification
as separate claims. C3D10/F05 work is not the default prerequisite for product work.

Preserve user edits and untracked files. Review the staged diff, commit meaningful
verified units, use authorized Git access and confirm remote publication. Never
force-push, bypass branch protection or erase history. If publication is blocked,
retain the local commit and record that it is unpushed. This public repository must
not contain credentials, company CAD/data or environment secrets.

At a meaningful checkpoint, update CURRENT_STATE and the affected design/usage or
acceptance record. Update requirement status only when it changes. HANDOFF links
to that state instead of duplicating it. Codex updates the relevant Space summary
and links for material decisions; no automatic Git–Space synchronization is assumed.
See CODEX_WORKFLOW for ownership, document roles and fresh-session instructions.
