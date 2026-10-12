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
