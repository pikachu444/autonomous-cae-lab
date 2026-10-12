# Design and approved implementation handoff

Use [the actual Pro request](../../../docs/design/20261012-desktop-planning/PRO_REQUEST.md)
and existing detail plan as the authoring packet. Keep source reuse concrete and
replace outdated 'new owner' work with the relevant UI/support extensions.

The later [whole-product GUI request](../../../docs/design/20261012-desktop-planning/PRO_UX_REQUEST.md)
contains the user's current CAD/FE–Runner–Post–Numerical and Co-STORM focus.
The isolated [Qt source](../../../docs/design/20261012-desktop-planning/pro-ux/README.md)
is a working review draft; author publication does not establish workflow acceptance.

The authorized sequence is context recovery → actual Pro whole-product authorship
→ editable tool artifacts and limited Qt interaction checks → independent Astra
review plus Codex actual artifact inspection → necessary Pro correction → user
review. Production implementation follows only a later development-start instruction.

No automatic `run`, goal/loop, provider/model replacement or all-solver prerequisite.
Shared schemas/Core/native command integration have one lead owner. Helpers have
explicit bounded file scope. Current assignment and connection state stay in
CURRENT_STATE; this file is not another current queue.

After approval the implementation backlog pins input/output contracts, existing
files/commands, dependencies and user completion per meaningful feature unit.
New/expanded backend physics verification runs when the corresponding feature is
ready; unchanged old campaigns do not gate table/dock/selection design.
