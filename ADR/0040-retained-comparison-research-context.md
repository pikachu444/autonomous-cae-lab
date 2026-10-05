# ADR0040 — Interpret the same retained observation comparisons

Status: accepted; source controls passed, actual clean-source connected acceptance pending.
Date: 2026-10-06.

## Decision and reason

Product-defect hypotheses and virtual-test planning need the research agent to
read the engineer's declared observations and the same preserved responses.
Reuse the existing `research_summary`/`experiment_summary` operation. When the
store has comparisons, add a separate `comparison_context` with reverified
records, original result/record/receipt hashes, declared scope and diagnostics.
No comparison becomes a solver metric, Domain verdict or optimizer feedback.
Without that namespace the historical summary shape is unchanged.

Only records associated with the requested experiment are included. Core
rechecks their existing source/receipt/calculation and verifies result stability
before returning. Failed records have UNKNOWN diagnostics without numerical
payload. A bounded scan/record/byte limit reports omissions; incomplete context
cannot be described as all evidence. Native time/tensor/driver/initial-state
meaning stays in ADR0039's adapter. SYNTHETIC, unqualified reported measurements,
null mismatches, physical UNKNOWN and NOT_RELEASED retain their meanings.

The Lab links verified comparison IDs and source experiment IDs into an editable
Korean research question. It preserves edited text, resets automatic continuation
and checks current store/result/ownership before preparing the draft. Sending the
question uses the existing official bridge, approved5.6Sol/OAuth and actual Core
summary tool. Research text stays separate from authoritative numerical verdicts.
The existing facade requires clean resident Core Git even when the controller
can pin a dirty development snapshot. Commit the verified implementation before
the actual probe; preserve dirty preflight refusal and do not weaken that gate.

## Alternatives, impact and acceptance

Pasting browser numbers into a prompt would not prove a current Core read.
New solver examples, new MCP readers or a replacement research provider are
unnecessary. Existing descriptors/prompts/tool universes remain unchanged; the
runtime may grant just the existing summary reader for retained interpretation.

R01–R03/R09–R13/R19–R21/R24/R43/R48/R52 gain this bounded B3 connection.
All52/Phase1–7, numerical-engine exploration, assembly mechanics, general inverse,
physical and deployment gates remain. Source controls cover original-summary
compatibility, exact context/UNKNOWN/null/axis retention, tamper/path/omission and
stale/edit-preserving human handoff. Actual approved provider reading, same-record
answer/reload, source-byte retention and owned idle/Stop are separate next gates.
Final83 Core/543 Lab Node,341 native-guard PASS/14 SKIP and56 mocked facade
controls are source evidence. Three independent metadata/aggregate findings
were corrected. The first actual question was refused before provider execution
on dirty Git; record `20261006-response-interpretation-source-r01.json` preserves
it. Original193 copied bytes and idle owned Stop are separate from interpretation.
