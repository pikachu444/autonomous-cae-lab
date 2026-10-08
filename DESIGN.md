# Engineering desktop design direction

This replaces the rejected web visual direction. The full behavior specification remains in `docs/PLANNING_SCREENS.md`.

## Mode and references

Operate. Use the user's specified engineering desktop references, without random brand concepts, marketing cards or invented decoration. Impeccable Operate/craft-floor and frontend-design's domain grounding/copy/critique guidance apply. Their web hero, mobile-only audit, and new-brand interview/concept tournament do not fit the explicit settled brief.

## Visual tokens

Window `#edf0f3`, document `#ffffff`, toolbar `#f4f6f8`, rule `#bbc8d4`, text `#263746`, secondary `#586d7d`, selection `#cfe3f6`, active accent `#276396`, warning `#9a5b17`. Text, labels, units and shape convey state alongside color.

Malgun Gothic / Windows system sans: 12px controls, 13px conversation body, 15px document heading. No oversized page heading. Native menus, table headers, context selection, file dialogs, keyboard shortcuts and splitter handles retain familiar behavior. Standard Qt icons carry actions; no emoji icon stand-ins.

## Composition and interaction

Document commands occupy a compact first toolbar; domain commands occupy the second. App-specific menus divide real actions. The central engineering object is dominant: model/curve, execution queue/logs, field/history, procedure/design-space, conversation/article, or system connection cells. Dense tables share selection with views; irrelevant properties do not remain visible after selection changes.

Each app runs in a separate native window/process and reads its own file document. All six default windows were operated at 1480×940 and Expert was also inspected at 1100×760. Final selection/display corrections and the other five small-window inspections await restored desktop access; the latest build has not passed that complete visual gate. Resizable panes and contained scroll areas are intended to preserve controls. User-selected values, document versions, evidence provenance and actual/demo state must remain visible.

## Review standard

Assess task fitness, information/command density, independent app lifecycle, reference behavior, and actual user acceptance separately from persistence and numerical test results. Compare real captures to the supplied reference images and the rejection reasons. An internal review is not user approval.
