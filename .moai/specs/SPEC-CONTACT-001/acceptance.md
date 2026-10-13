# User completion and verification timing

## AC-C01 — author and reopen

Given two user bodies and named face sets, select A/B from native 3D or the table,
choose law/friction/gap policy and step, preview orientation and save/reopen.
The same editable geometry and declarations remain. Missing fields remain
editable/saveable but cannot export/run. Undo/Redo acts on the contact transaction.
Check this during implementation with small native-owner/UI cases.

## AC-C02 — changed geometry

Given a saved pair and older result, split an A face and reverse a candidate
normal. Preview old/new sets and area/centroid/normal differences. Cancel leaves
the pair unresolved; explicit selection and Apply produce a new draft reference.
The old source/result still opens. Never silently repair by face number or nearest
position. The old mesh remains stale after a geometry/face repair until remeshing
or explicit mesh admission validates the new bindings. Use a small save/reopen case during development, then native interaction
after the feature exists.

## AC-C03 — supported model execution

Given a supported native two-body model, generate or explicitly admit its contact
mesh, including independent interface DOFs, body/material/load ownership and
valid multi-face mappings. With frictionless or Coulomb contact and a configured
free solver, export the exact selected model and submit through
Runner. Inspect frozen surfaces, cards, units, step and outputs; cancellation or
failure returns to that setup and retains the previous attempt. Unsupported
law/mesh/gap/output reasons appear before submission without changing the draft.
Inspect that normal/sliding/step choices have an effective card/surface mapping
or an explicit refusal. Native property persistence alone does not meet this check.
During development inspect writer output and adapter units; defer the actual
two-model contact comparison until editor/export/reader implementation is ready.

## AC-C04 — actual result and connected research

Given actual retained contact outputs, select pair and time, inspect pressure,
forces, gap/penetration/slip and source association/sign, and take an existing
Post measurement to Numerical. Unavailable channels explain whether output was
not requested, parsing is unsupported, or contact was absent. Failed frames stay
failed. Save/reopen returns to the exact result. Do not substitute "parser
unsupported" for unfinished required output support.
Preserve original slave-node/integration-point values, basis and signed derivations separately
from display projections. Missing contact rows must not fabricate gap or zero force.
Final connected verification includes at least two user-model geometries and independent numerical references
with original tolerances; model execution alone is not engineering approval.

## Implementation evidence and remaining work

The editor and native save/reopen portion of AC-C01/C02 is implemented and has
focused Qt/owner checks plus a real FreeCAD multi-face example. Native GUI mesh
generation now produced separate Base (1,147 nodes/532 volumes) and Bridge
(2,256 nodes/1,122 volumes) meshes while retaining the contact references. This
was programmatic execution in FreeCAD, not mouse/keyboard usability acceptance.

Pro `8d350ab` adds the AC-C03/C04 export, Runner and retained Post source path.
At its first Windows checkpoint, 16 contact/output tests passed and three
snapshot tests failed because their fixture used Windows line endings. Astra
also identified Force table unit conversion, stale named support-group mapping
and closed-session source reopening defects. Pro `b19c8f1` corrects these;
66 changed-path unit tests passed on Windows. Real native multi-face Force
export retained a 100 N resultant after correction (11.484 seconds). Real
FreeCAD export completed for the two-body prescribed-displacement example,
including comparison with the installed native contact writer and retained
editable model/deck/manifest; the corrected run additionally exercised Force export.
Subsequently, the actual installed CalculiX 2.22 completed this retained input
through the product adapter in 41.703 seconds, with ten parsed increments.
This is direct adapter execution, not Runner UI submission or qualification.
Actual ParaView opening initially failed on ASCII nonfinite GeomGap values;
raw FRD/DAT and the failed Post files remain retained. Pro's `5744079` correction
was integrated as `b97ae6b`, with ten changed-path unit checks passing. Post-only
regeneration and native reading of all ten frames succeeded without rerunning
the solver. Exact registered input opened, CPRESS at static load parameter 1.0
was selected and saved, and a new pvpython process restored that selection and
3,403 points/1,654 cells. Pair-focused native interaction and the connected
measurement/Numerical user workflow remain separate work; AC-C04 is not complete.
Pro's pair/side/increment inspection and force measurement integration
(`1edd036` through `5cb083c`, local product `b6dc2d6`) adds the native overlays,
Qt result/force-history view, and existing Data/Numerical Plan handoff. The first
four changed-path test files passed 33 checks; subsequent initialization and
partial-repair corrections passed 17 focused guard checks in 0.82 seconds.
Native reader/display initialization and enum-label differences were found and
corrected without weakening the native-edit guard or rerunning physics.

On the installed ParaView 6.2, the unmodified final product and native check
selected the actual CPRESS contact surfaces at static load parameter 1.0,
created a ten-row CFN Z measurement, saved, then reopened in a separate
pvpython process with the same rows and no restore issues. The local receipt is
`runs/product-development/20261013/contact-inspect-bb998593/checked-enum-inspection.json`.
The Qt view was separately rendered with actual 194-node contact data and ten
increments; its command transport was a labelled double. These results do not
claim native mouse/keyboard/DPI acceptance, Runner UI submission, a complete
native-to-Qt broker round trip, or the two-model engineering reference comparison.
AC-C04 is consequently still partial. CURRENT_STATE owns the current assignment.
