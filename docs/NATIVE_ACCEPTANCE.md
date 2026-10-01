# Native FreeCAD Core acceptance

## Latest actual P1.2a failure and fixture correction

Source c141ae0/run01 passes imported Part and named radius/new X selection,
then fails the unchanged centroidY=0 reference after temporary Y deletion:
the actual free coordinate remains-3. Exact CI36821642536 also nativeFAIL,
other7jobsPASS. Preserve failed metrics/result and161files/5,172,603bytes.
Independent official investigation and a copy-only actual moveGeometry probe
confirm the needed explicit origin input setup. Production adapters and every
reference/tolerance remain unchanged; unsupported legacy movePoint probe stays
failed. New clean-source run02 remains required. See coordinate-correction
record and ADR0014; engineering UNKNOWN/NOT_RELEASED remain.

## Current P1.2a source checkpoint (actual new-source acceptance pending)

Clean Main671b818/fixture3e48 locally re-executed the existing public Lab native
acceptance in a fresh store: Part width38, radius6, editable reopen, invalid
bore rejection and ineffective-height refusal. The new imported/edited red
case then reproduced a real discovery gap: inserted driving center_x at0 was
omitted when registered named radius moved to1. Stale execution correctly
blocked; the failed case and original CAD/result bytes remain preserved.

ADR0014 keeps the upstream pin/geometry algorithms and adds an adapter-owned
worker for current identity checks and opaque new sketch selectors. Legacy
registered keys stay stable. 48 offline checks pass; an actual read-only
installed FreeCADCmd console probe passes and preserves the old FCStd hash.
This is source/transport admission, not full corrected P1.2a acceptance.
The new `scripts.verify_native_edits` checks native/Core/STEP analytical
bounds, volume and signed centroid, insertion/deletion/reordering, refresh,
invalid identities and all historical experiment file hashes/sizes.
Exact new clean-source run/CI and independent output review remain required.
See `benchmarks/records/20261001-native-edits-source.json`. Engineering
UNKNOWN/NOT_RELEASED and solver NOT_RUN remain. P1.2b transactional recovery
and P1.3 general research planning stay queued.

## Earlier native acceptance and discovery limitation (historical source)

The pinned fixture repository's earlier FreeCAD CI tested its worker directly.
The new workflow `.github/workflows/caelab-ci.yml` invokes
`python -m scripts.verify_native` through **CAE-Lab's public `Lab` API**. It
downloads the same SHA-256-pinned FreeCAD 1.1.4 AppImage used by the upstream
acceptance. The local development container has no FreeCADCmd; the new native
bridge ran successfully in [Actions run 36632876593](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36632876593)
at commit `252d58b9d29dd5545b7e1269837a48cd705b86ba`.

The run's preserved artifact (SHA-256
`0ccf9dadcfe56cc2393be75ae2fb43600ec3cfb0605b6a03bd844c8cff501ec8`)
was opened after the job: `native_acceptance.json` reports Part width
`[38, 40, 26]` mm, Sketcher bounds `[12, 12, 8]` mm, successful reopening of
the editable FCStd and rejection of the ineffective dimension. The valid Part
and Sketcher results each record 12 artifacts and `NOT_RELEASED`; the bore
radius 5 mm result records `REJECTED`, `cad_revision=null` and a
`bore_1_edge_land` FAIL, without exported geometry in that experiment. The Core
job passed eight tests and a local-client MCP round trip. The earlier
[run 36632462887](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/36632462887)
failed before native execution because a file-path invocation could not import
`caelab`; the subsequent module invocation fixed it.

The script records a study, discovers actual Part and Sketcher dimensions,
registers research names/bounds in both the Core and FCStd, executes 32→38 mm
support width and Sketcher radius 4→6 mm, reopens the generated editable FCStd,
and verifies the hash-checked result. A 5 mm bore radius must fail its edge-land
rule without STEP/STL/3MF/FCStd export. An ineffective cutter height must fail
registration. `static_strength`, physical tests, machine interface,
manufacturability and general domain clearance remain `UNKNOWN`; the CAD
operation does not authorize release.

The FreeCAD adapter additionally compares each proposed changed dimension's
final STEP solid with a counterfactual in a temporary directory. This prevents
one changed dimension from hiding another dimension with no final shape effect.
An invalid proposal still goes to the fixture validator for its exact rejection
reason. A domain-invalid counterfactual yields `UNKNOWN` for that individual
effect; it never becomes a fabricated `PASS`. The local regression uses actual
CadQuery STEP geometry with a synthetic no-op parameter to test the comparison
logic without claiming native FreeCAD execution.

Registered Sketcher values are resolved by the FreeCAD constraint name, which
survives ordinary index shifts. The adapter filters a renamed registered
dimension from new discovery candidates even if its positional index changes.
At this earlier source, the pinned upstream worker could suppress a newly inserted
dimension at the old index. This discovery limitation requires an upstream
worker change or adapter correction and a reorder benchmark before arbitrary sketch edit/reimport
is treated as fully round-trip-safe. A Core registry refresh rechecks the named
registered dimension, and an altered FCStd source is blocked until refresh.

Registration writes the native FCStd before the Core registry file. If the
subsequent filesystem write fails, the registered native definition can be
recovered by rediscovery and registration or by importing a fresh FCStd revision;
cross-file transactional registration remains a follow-up.
