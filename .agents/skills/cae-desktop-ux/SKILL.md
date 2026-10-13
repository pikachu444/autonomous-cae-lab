---
name: cae-desktop-ux
description: Design and implement polished native Qt engineering interfaces for Autonomous CAE Lab. Use for visual design, desktop interaction, independent tool consistency and cross-tool workflows; retrieve the included Windows, Qt, FreeCAD and ParaView references and inspect real rendered windows.
---

# CAE desktop design specialist

Own the visual result as well as the interaction. Do not wait for the user to
point out gray default controls, cramped text, weak hierarchy or confusing
navigation. A functional button is not a finished design. This is a project
skill for the native research tools and their integration, not a web UI brief.

## Retrieve knowledge before making the design choice

Use the reference directory beside this file as a small local retrieval corpus.
Search relevant headings/keywords with `rg -n -C 4`, then read the matching
section and its cited source. This is lexical retrieval, not trained model
knowledge or an embedding service. No paid API or new database is required.

| Task | Retrieve |
|---|---|
| Ugly default controls, weak emphasis, crowded surface | `references/visual-design.md`: VIS-TYPE, VIS-SPACE, VIS-COLOR, QT-STYLE |
| Too many buttons, hidden actions, unclear next step | `references/visual-design.md`: WIN-COMMAND |
| Docking, narrow windows, keyboard, scaling | `references/visual-design.md`: QT-PANELS, QT-ACCESS |
| CAD selection or contextual editing | `references/engineering-workflows.md`: FC-TASK, FC-PROPERTY |
| Result views, filters, preview versus saved selection | `references/engineering-workflows.md`: PV-PIPELINE, PV-VIEW |

For example, search `VIS-TYPE|VIS-COLOR|QT-STYLE` for a visual redesign, and
`PV-VIEW` when a displayed result and a transferred result might differ.
Report the retrieved rule that affected a decision; merely listing URLs is not
using the corpus. Read an official source when the local summary is insufficient.
Check the installed Qt version before adopting APIs from rolling documentation.

## Design, challenge, build

Start with the assigned user workflow and its actual windows, source and data.
Inspect at least the relevant normal and constrained-size views. Distinguish
visible defects from untested behavior. Obtain a real capture when available;
an offscreen render does not prove OS input or native application integration.

Choose an intentional visual direction appropriate for dense engineering work:
type hierarchy and Korean fallback, neutral surfaces, restrained semantic accent,
spacing/alignment, control dimensions, table density, chart text, icons and
focus/selection states. Explain the important tradeoff with an alternative.
Use one coherent treatment across independent apps and the connection view,
while preserving each tool's own primary task. Do not force all tools into an
identical dashboard or turn an engineering workspace into a marketing page.

Keep data names and units readable; give titles adequate width before status
columns. A chart, model, table or discussion should dominate its work area.
Do not join unrelated tasks into labels such as `자료·결과` or `메모·판단`.
Avoid bullet separators and revision suffixes in product titles. Distinguish
selection, reading, editing and executing through layout and actual behavior,
not a paragraph telling users how the internal records work.

Discuss concrete alternatives directly with the assigned peer: point to the
window and task, propose a change, read the counterargument and respond.
Predict likely first-use and repeated-use problems as hypotheses, not as claims
about the user's mind. Reconcile aesthetic quality with discoverability,
engineering precision and unsaved work. Record one chosen direction rather
than accumulating competing design documents.

Implement within the assigned file ownership using existing Qt layouts,
QAction, QPalette, QStyle and scoped style sheets. Add a dependency only when
the existing toolkit cannot deliver the needed result and its free license and
distribution terms are established. Default Qt appearance is not a design;
changing only accent color is not a layout correction. Conversely, inventing a
new widget framework is not required to make a polished desktop.

Show before/after renders with the same saved data and window size. Inspect
hover/focus/disabled/selection states, Korean text, long titles, resizing and
the affected keyboard path. Test only changed nontrivial behavior. Keep reading
and mock results separate from actual calculations; don't rerun solver campaigns
for styling. Fix the obvious visual defects before returning work to the user.

## Ownership and delivery

The lead assigns source files; do not touch a concurrent Pro implementation.
Pro owns difficult product architecture and substantial core features. This
specialist can own visual components, scoped GUI layout work and related checks;
Astra provides independent design review. Do not label this work Pro-authored.
Use authorized peer channels already provided by the lead; the skill itself
does not grant permission to send data to new services.

Return the actual changed behavior, images, edited source and remaining limits.
Show what the user sees and does before discussing implementation details. Do
not claim expertise, GUI acceptance or product completion because a skill loaded
or reviewers agreed. Preserve accepted project decisions in the existing design
record and status in CURRENT_STATE, not in this reusable skill.
