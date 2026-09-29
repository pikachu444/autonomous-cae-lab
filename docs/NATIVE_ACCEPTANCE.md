# Native FreeCAD Core acceptance

The pinned fixture repository's earlier FreeCAD CI tested its worker directly. The
new workflow `.github/workflows/caelab-ci.yml` invokes `scripts/verify_native.py`
through **CAE-Lab's public `Lab` API**. It downloads the same SHA-256-pinned
FreeCAD 1.1.4 AppImage used by the upstream acceptance. The local development
container has no FreeCADCmd, so the native path is not locally accepted until
the new workflow succeeds and its artifact/result ledger is inspected.

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
The pinned upstream worker can still suppress a different, newly inserted
dimension at the old index. This discovery limitation requires an upstream
worker change and a GUI reorder benchmark before arbitrary sketch edit/reimport
is treated as fully round-trip-safe. A Core registry refresh rechecks the named
registered dimension, and an altered FCStd source is blocked until refresh.

Registration writes the native FCStd before the Core registry file. If the
subsequent filesystem write fails, the registered native definition can be
recovered by rediscovery and registration or by importing a fresh FCStd revision;
cross-file transactional registration remains a follow-up.
