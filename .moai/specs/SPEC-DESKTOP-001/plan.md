# Design and implementation handoff

Follow the latest assignment in [CURRENT_STATE](../../../CURRENT_STATE.md).
The [GUI recovery plan](../../../docs/GUI_RECOVERY_PLAN_KO.md) records the current
base-code selection and executable-skeleton criteria; its publication is not GUI
implementation or acceptance. Use [the original Pro request](../../../docs/design/20261012-desktop-planning/PRO_REQUEST.md)
and existing detail plan as reusable authoring material. Keep source reuse concrete and
replace outdated 'new owner' work with the relevant UI/support extensions.

The later [whole-product GUI request](../../../docs/design/20261012-desktop-planning/PRO_UX_REQUEST.md)
contains the user's current CAD/FE–Runner–Post–Numerical and Co-STORM focus.
The isolated [Qt source](../../../docs/design/20261012-desktop-planning/pro-ux/README.md)
is a working review draft; author publication does not establish workflow acceptance.
The [screen/task map](../../../docs/design/20261012-desktop-planning/pro-ux/implementation_map.csv)
extends the existing backlog rather than replacing its feature IDs, runtime prerequisites
or numerical acceptance. The [MoAI handoff](../../../docs/design/20261012-desktop-planning/pro-ux/MOAI_HANDOFF.md)
links concrete artifacts to the current SPEC. CAD/FE → Simulation → Runner → Post →
Numerical and Expert → research result → Study are the first integrated user paths;
Material remains a parallel domain tool.

The original planning sequence was context recovery → actual Pro whole-product authorship
→ editable tool artifacts and limited Qt interaction checks → independent Astra
review plus Codex actual artifact inspection → necessary Pro correction → user
review. The user subsequently authorized implementation on 2026-10-13. Neither
that historical authorization nor the original approval gate overrides a later
stop/planning assignment. Do not restart old feature work from this plan.

No automatic `run`, goal/loop, provider/model replacement or all-solver prerequisite.
Shared schemas/Core/native command integration have one lead owner. Helpers have
explicit bounded file scope. Current assignment and connection state stay in
CURRENT_STATE; this file is not another current queue.

For assigned implementation, the backlog pins input/output contracts, existing
files/commands, dependencies and user completion per meaningful feature unit.
New/expanded backend physics verification runs when the corresponding feature is
ready; unchanged old campaigns do not gate table/dock/selection design.
