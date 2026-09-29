# ADR 0001: Platform boundaries

Date: 2026-09-30. Status: accepted for the first CAD vertical slice.

## Context

The existing fixture program already discovers and changes real CAD parameters, validates geometry and blocks invalid export. A broader laboratory must add CAE/PDE/optimization without moving fixture or solver syntax into a research agent or a generic Core. Human inspection and reproducible automated experiments must refer to the same artifact revision.

## Decision

- OpenScience owns hypotheses, campaign selection, interpretation and the next research question.
- CAE-Lab Core owns versioned common schemas, research-variable mapping, execution gates, immutable experiment/result records, artifact/evidence/validation registry and provenance.
- Deterministic numerical optimizers own numeric candidate generation, seeds and search state. LLM proposals are not the default optimizer.
- Domain plugins own fixture/material/drop/PDE specific engineering rules. The pinned fixture repository is the first plugin; it is neither replaced nor copied into generic Core.
- CAD, mesh, solver, PDE, postprocessing and optimizer adapters own their backend syntax and return common typed results and artifacts. No `SupportBlock.Length`, Code_Aster command or OpenRadioss card belongs in a study request.
- The engineer GUI and autonomous flow read/write the same native source and versioned artifacts. GUI release/approval is distinct from successful execution.
- Validation is a verdict; evidence is the observation supporting it. `UNKNOWN` is preserved. CAD success without strength, installed-machine and physical checks is `NOT_RELEASED`.

## Alternatives considered

Installing each solver and connecting OpenScience last loses the stable research contract. Embedding every fixture rule in Core makes cross-domain reuse illusory. Copying upstream source into the new repository duplicates tested code and obscures its revision. The pinned submodule plus adapter retains the tested implementation and exact commit. A future upstream packaging/refactor can replace the submodule without changing the Core schema.

## Consequences and verification

Core cannot run arbitrary solver decks without an adapter. A real CAD run proves the initial boundary; physical or FEA qualification remains open. Changes to common schema/adapter boundary require a new ADR, migration notes and the acceptance tests. Submodule dependency, Python environment, missing upstream license metadata and platform-specific FreeCAD installation require explicit deployment checks.
