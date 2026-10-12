# Autonomous CAE Lab — desktop UX review prototype

Request: PRO-DESKTOP-DESIGN-20261012-06. Main design and source author: ChatGPT Pro (this conversation). Separate reviews are attributed in REVIEW.md.

This folder contains an isolated, editable Qt planning prototype. It does not import or change production owners, launch native applications, execute solvers, run optimizers, contact providers, or configure MoAI. All engineering values and native views are synthetic design illustrations.

## Run with the existing Windows environment

From the repository root:

    py -3.13 docs/design/20261012-desktop-planning/pro-ux/qt_prototype.py --tool cad

Other direct entries: data, material, pde, numerical, runner, post, expert, study, evaluation, simulation, thermal, thermoelastic, workbench. No installation command is needed. Required existing modules: PySide6 QtCore/QtGui/QtWidgets. SVG editing does not require a paid tool.

Only a review workspace chosen with --workspace or a temporary review directory is written. File > Save asks for a file for the active document. File > Save review session preserves all open review drafts, exact saved documents and receipts for a fresh-process reopen with --session. This review JSON is not a proposed new production file format.

The editable source is published early; additional views, vectors, route documentation and verification evidence will be committed to the same branch. This initial source checkpoint is not a completed usability review.

## Boundaries

Pinned product source: 9a6e3083037630b45694b812b135dc1cd63cf95a. Pinned requirements: 313679843813b63dee44409de5c5abc43c8a373b. D1 read-only source: 95a2389ca534b807420a4e7dbe2397f5e60953c9. Original D1 is not edited. Production development still requires the user's later instruction.

F05 remains 3.32295e-6 > 1e-6. Engineering qualification remains UNKNOWN / NOT_RELEASED.

## UX-FIX-01 source correction (draft)

The next source checkpoint adds CAD Create / sketch dimensions / conditions and contact tasks,
Numerical typed owner-field-unit bindings, evaluator assignment, editable responses and per-method
inputs. Post array + unit + association is one undo command; its measurements, legend and cursor
read the same exact synthetic frame. Missing frames remain unavailable. Graph node labels are
painted by the node itself to address the Windows offscreen blank-label report.

Required invalid time steps, empty contact sets, stale meshes and unknown response roles block
Check / Freeze and offer an editor jump. Signed loads and a zero load remain valid. This source
has Python compilation and stdlib state checks here; the corrected Qt must be checked again in
the existing Windows PySide6 environment. The user's report verified offscreen Qt behavior of
3ab34b0 only, not OS input acceptance or this newer source.

## Engineering controls and precision checkpoint

`make_table` now uses a retained `EngineeringTextDelegate` (QLineEdit), avoiding Qt's
2-decimal floating-point delegate. Scientific notation and partial input remain editable.
Simulation has separate model/step/condition/contact/initial/failure/output settings;
CAD has sketch lines, geometry dimensions, mesh refinement, conditions and relative joint pose.
Post supports filter settings, two-point picking, measurements and response registration.
Expert Models provides draft role bindings for existing subscription OAuth, an existing local
endpoint, or no configuration. All provider/model entitlement states remain UNVERIFIED.

User-authorized temporary remote PySide6 6.9.1 offscreen checks passed nine bounded
interaction checks and 14 window startups/renders at 1440×900 on the recorded source snapshot.
No Windows OS/native-host/solver/provider acceptance is implied. The Models dialog was added
subsequently and is pending its next targeted Qt check.

Portable checks (existing interpreter, no installer in this script):

```powershell
py -3.13 docs/design/20261012-desktop-planning/pro-ux/qt_acceptance.py --source docs/design/20261012-desktop-planning/pro-ux --offscreen
```
