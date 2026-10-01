# Connected structural family acceptance

Updated: 2026-10-02. Current unit: P2.2, still OPEN. ADR0017 and the frozen
`structural-families-v1.json` retain the predeclared geometry, DOFs, loads,
response/field definitions and numerical thresholds. The full MIDAS survey
remains a separate inventory; these are three independent bounded derivatives.

OpenScience owns questions, hypotheses, declared solver/condition choices,
comparison, interpretation and the next experiment. The existing common Core
owns append-only model/result/evidence/provenance operations. Domain owns the
engineering rules; adapters own native decks, mesh/field extraction and runtime.
Deterministic numerical engines own numerical search in the subsequent Phase3.

## Actual execution and preserved failures

- Native01/b7b6450 stopped before a solver at the installed ccx metadata query.
  The narrow exact-query correction is recorded in20261002-calculix-version-metadata.
- Native02/fa0b1a8 ran one coarse beamFx job/exit0, then Core FAILED_EXECUTION
  at native DAT/FRD output parsing. Actual-byte regression files,88 checks and
  independent review are recorded in20261002-calculix-native-format. That failed
  store remains unchanged; posthoc parsing does not turn it into numerical PASS.
- Native03/b598f42325ea438918f5865fb2ea6c857e0ea339 ran all three beamFx meshes
  and parsed complete fields. Core REJECTED the fixed1e-7 signed reaction gate:
  maximum observed error2.663401471566829e-7. Finest response0.0007607607mm,
  reference relative error0.0016263779527558879 and last-pair mesh difference
 0.0013362204724408691 remain invalid metrics on this rejected record.
  Moment/reference/mesh checks are not substituted for the failed force check.
  See20261002-structural-family-native03 for raw values, exact source and retention.

The rounded DAT RF cannot establish the exact unrounded native balance. Root
ran one direct output-format probe on clean ab188cd, changing only both FILE
cards to DOUBLE. Installed executable/original store/source stay unchanged;
the DAT is byte-identical. Strict correction requires supported observed ABI
and complete native DOUBLE U/RF at the same nodes, corroborating every component
against DAT printing precision. Actual restrained RF minus CLOAD supplies signed
reactions/moments; nothing is projected to balance. Native DAT stress points and
all references/thresholds remain unchanged. Historical ASCII record/metadata
equality is checked.152 staged/30 integration/1 actual-fixture tests and bounded
independent source review PASS. Record20261002-calculix-double-evidence retains
actual probe/raw hashes and earlier failed source attempts. This format proof
does not revise Native03 or establish a new Core verdict. Fresh native04,
other loads/families/cross-solver and connected research/GUI remain NOT_RUN.

## Reviewed connected research driver

`scripts/verify_structural_research_live.ps1` reuses the pinned official
OpenScience2.0.146, selected `openai-codex/gpt-5.6-sol`, approved auth/project,
existing helpers and six existing Core/MCP tools. There is no model fallback.
The companion source checker has51 cold checks and independent source review;
record20261002-structural-research-driver. These checks execute no actual
HTTP/model/Core/solver call. Publication is readiness, not research completion.

The actual acceptance requires a clean owned runtime, fresh store/attempt and
fresh current-session source resource observation before inference. It binds
owner/process/context/source/config/store/project before and after the query,
then retains and rechecks diagnostic bytes around every model stage. Store
identity is configured owner/context binding, not direct CAELAB_STORE observation;
disk/import fingerprints do not prove cached Python bytecode identity.

Nine actual model stages are predeclared: missing-input refusal, unsupported
torsion refusal, and for beamFz/cylinder pressure/roof gravity a two-solver
baseline followed by a CalculiX half-load experiment, then interpretation.
Nine experiments each retain three native mesh levels. Each baseline and
follow-up must use actual inspect/summary/comparison receipts matching frozen
Core records. Changed load creates a new model revision. Earlier results,
threads, ledgers and artifacts must remain byte-identical. All nine complete
results and exact IDs are included in the final actual prompt before a bare
interpretation stage. UNKNOWN and NOT_RELEASED persist.

## Next gates

1. Resolve native reaction evidence without manufactured balance or relaxed
   limits; retain the rejected Native03 and use a fresh clean-source native store.
2. Complete native reference/mesh/all-field/cross-solver and changed-load gates.
3. Run the reviewed actual OpenScience driver with approved model/auth/project;
   independently audit its raw fields and show the same records in human GUI.
4. Verify owned idle/Stop and artifact retention; record exact-source CI with
   failures separate from local evidence. Then continue the sequential worklist.

Original MIDAS replication, torsion/shell rotations and additional structural
families remain open. Static strength, material, physical, fatigue and model
qualification remain UNKNOWN. Native exit0, source checks and AI interpretation
never establish RELEASED or completion of the retained52 requirements.
