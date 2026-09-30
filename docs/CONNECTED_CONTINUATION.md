# Connected continuation after the numerical checkpoint

The primary session continues all 52 requirements. Environment restoration
and the three acceptances at 41a9858 were a checkpoint, not project completion.
Root stopped the earlier turn by incorrectly treating those bounded gates as
the stopping condition. GitHub/authentication/numerical runtime were usable.
The user challenged that judgment and Root resumed actual work.

## Current priority and reason

The user challenged over-concentration on Code_Aster. Root acknowledges that
not all backends/features are connected. Prior verified slices are CadQuery/
FreeCAD, Gmsh/CalculiX linear screening, seeded SciPy DOE/adaptive optimization
and bounded FEniCSx PDE. Code_Aster and the live OpenScience loop are partial;
OpenRadioss, MFront material acceptance, other solver/optimizer engines, HPC,
physical work and the full report/archive policy remain open.

Root now integrates a local Research/Design/Simulation/Explore/Results surface
over those existing APIs, with read-only historical libraries and verified
portable reports/bundles. Independent owners have disjoint server/static/report
files; Root owns integration/acceptance. ADR 0008 and `apps/lab/CONTRACT.md`
record boundaries. The Code_Aster owner has only a bounded native mesh-semantic
guard repair, with no installation/rebuild/solver loop. A UI implementation is
not a claim that the missing backend or research gates have passed.

## Continuing acceptance obligations

1. Verify a real OpenScience request → MCP/Core → valid and invalid persisted
   evidence. Transport-only success does not close the control-plane gap.
2. Verify fixture-independent Code_Aster elasticity through the declared-model
   Core also used by PDE. Executable reuse precedes nonlinear/contact models.
3. Continue Phase 0–7: arbitrary native edits/refresh/GUI transactions, broader
   optimization and nonlinear/time/vector/coupled PDE, nonlinear/contact/
   material models, OpenRadioss drop/energy, MFront tangent checks, MPI/SSH/HPC,
   reports/UI/durable archive. Physical work needs an accessible authorized device.

## Code_Aster preparation and actual failed drafts

Added Singularity 4.1.1 and an external pinned vendor SIF without replacing
Python/CAD/CalculiX/FEniCSx or starting Docker. Actual probe: Code_Aster 17.4.0
(spack-local), Python 3.11.14, NumPy 1.26.4, SciPy 1.15.2. Startup reports MED
4.2.0, MFront 5.0.0, MUMPS 5.6.2 and PETSc 3.24.0p0. Library presence is not
constitutive/HPC acceptance. See ADR 0007 for image identities and reference.

- `artifacts/local-20260930-codeaster-draft-01`: fort.20 integrity was checked
  before DEBUT materialized deferred runner links. Initialization order was
  corrected and a lifecycle regression added.
- `artifacts/local-20260930-codeaster-draft-02`: DEBUT hit JEVEUX_40/ENOSPC.
  Actual container df confirmed contained /tmp is 64 MiB despite WSL 943 GiB
  and Windows 199 GiB free. A fresh task-owned scratch bind repairs capacity
  without exposing host /tmp or changing numerical limits. Failed logs remain.

Native elasticity/clean-source CI acceptance is pending. Common declared-model
and PDE contracts passed 41 tests, and elasticity plugin passed 76 tests.
These tests do not establish native numerical success. Independent review
also required native NUME_ORDRE completeness, pre-command mesh resource gates
and actual plugin-byte provenance/drift checks.

- Draft 03 progressed through actual MECA_STATIQUE/CALC_CHAMP but failed
  native-name extraction: mesh.sdj.NOMNOE returned None for this imported mesh.
  Its native logs, mesh and failed scratch are preserved. Source/API repair and
  a fresh run are required; successful linear solve is not yet benchmark PASS.
- Draft 04 reached native `DIAGNOSTIC OK` and retained MED/raw tables. Host
  coordinate sorting first failed on near-equal numbers; unique spatial
  bijection fixed that false mismatch. Independent semantic inspection then
  found the actual X0/XL groups wrong: Code_Aster 17.4's GMSH reader compares
  all tags, including geometry tags, against physical group numbers. Original
  physical IDs 2/3 collided with geometry IDs 2/3. This run is failed numerical
  acceptance despite the successful solve. The bounded repair assigns disjoint
  physical IDs 1001–1005, rejects other-tag collisions and checks native
  coordinates, boundary memberships and ordered TETRA10 corner/midside roles
  before MECA_STATIQUE. Original tolerances stay unchanged. The actual Gmsh
  MED-output probe failed because the distribution build lacks MED support;
  no unnecessary rebuild is being pursued.

An expanded local test run reported 367 passes and two source-freeze failures
in 1246.82 s. The Code_Aster owner edited Core-source adapter files while the
long campaign tests ran; both correctly rejected changed source after planning.
Root owns that scheduling error. This mixed-source run is not a full-suite PASS;
rerun the affected tests with frozen source and exact-commit CI after integration.

## Actual OpenScience attempts

Pinned @synsci/openscience 2.0.146 is installed in a task-owned Windows runtime.
`scripts/openscience-local.ps1` sets isolated home/config/data/XDG paths before
every call. Windows Ollama 0.34.0 and existing qwen3:4b provide a local endpoint.
No paid provider/login/copied Codex credential was required. Version, model
listing and mcp list confirmed the connector was connected.

Only explicitly named study/registry/CAD/inspection MCP tools are allowed.
Generic shell/file/network/delegation tools are denied. Windows has no native
OpenScience sandbox backend; the isolated profile uses warn fallback for these
public local tests. Application permissions do not imply OS containment or
corporate-data approval.

- Attempt 01's npm .cmd shim truncated the multiline prompt. Root stopped only
  its task-owned processes and invoked the official JavaScript launcher with
  Node instead; attempt 02's user event verified the full prompt arrived.
- Attempt 02 ended completed/exit0 but emitted zero tool_use events and wrote
  no store records: research acceptance FAILED. Planning text is not execution.
  JSONL is retained under artifacts/local-20260930-openscience.
- A separate local OpenAI-compatible probe emitted a correct structured call
  in 8.95 s but did not invoke Core; it is only a model/transport diagnosis.

Observed active context was 4096 tokens. OpenScience also resumed the
interrupted session and issued concurrent title/summary requests that timed
out. Source-backed corrections use a compact primary agent, disable title/
summary and interrupted-job recovery for this profile, and create a separate
16384-token model alias while preserving the original model. Live acceptance
is still pending. The existing model template unconditionally starts a think
block, so reasoning metadata alone does not guarantee short/no-thinking output.

Attempt 03 actually called caelab_study_create and persisted S-open-live;
its tool status was completed and actual alias context was 16384. The combined
registration request used invented native paths and was correctly rejected;
tool status `completed` described transport, not successful registration. A
fresh compact one-action session then actually registered `support_width` to
`support_width_mm` and persisted geometry-effect PASS. Its later compaction/
continuation ended with CLI exit1, so only that real tool/store result is claimed.
Both live CAD cases and interpretation remain unverified. Planning text, copied
JSON or a partial study/registry result is not the Phase 1 research-loop PASS.

Later live04 used explicit task TEMP/TMP to establish actual MCP ownership.
Study creation and eight-candidate discovery succeeded. Two identical read-only
discovery calls are disclosed; mutating operations still require exactly one
actual receipt. The next registration stage ended completed/exit0 but made
zero tool calls, leaving registry0/no experiments. Its bounded result is
FAILED_OR_PARTIAL; no further model retries or installation loops were used.
Raw attempts/checkpoints/scripts are preserved. The official browser workflow
has not been exercised on this host; its documented project/model/conversation
usage differs from this repository's Lab screen. The user's usage question did
not authorize a UI redesign. See [OPENSCIENCE_USE](OPENSCIENCE_USE.md).

The revised Code_Aster import and common metadata passed new actual draft-05.
Common HTTP CAD/PDE, all 37 previous library experiments and nine bundle checks
also passed a fresh frozen draft. The report case-only collision correction,
browser work and pending clean-source/CI gates are recorded in
[CONNECTED_ACCEPTANCE](CONNECTED_ACCEPTANCE.md). Failed drafts remain unchanged.

All decisions remain NOT_RELEASED; unexecuted gates remain UNKNOWN. Raw local
ignored stores do not transfer by cloning. This progress document is not a
stop condition: record clean commits/CI/durable artifacts and continue remaining work.
