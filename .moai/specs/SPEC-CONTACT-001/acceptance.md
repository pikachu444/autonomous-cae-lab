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

All product scenarios remain unimplemented at this draft. Native factory
save/reopen evidence is recorded in research.md and does not close these criteria.
