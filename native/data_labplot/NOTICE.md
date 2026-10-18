# Donor and distribution notice

Donor: KDE LabPlot, `https://invent.kde.org/education/labplot` (GitHub mirror:
`https://github.com/KDE/labplot`), fixed commit
`ffd1eb53fcd5d033810af092a255b25cab7c93d1`.

LabPlot application sources including `src/frontend/MainWin.cpp` identify
GPL-2.0-or-later. Build scripts and some components have other SPDX licenses;
the donor `LICENSES/`, per-file SPDX notices and included third-party notices are
authoritative. A future distributed fork must include its applicable source,
license texts and notices, including its Qt/KDE/QADS and other bundled parts.
An available free build does not remove redistribution obligations.

`CaelabDataBridge.h` and `CaelabDataSettings.h` are original bounded integration
adapter/UI sources under
GPL-2.0-or-later. The small patches retain upstream source context: the CMake
file is BSD-2-Clause; MainWin.cpp and the XYCurve.cpp point-row hook are
GPL-2.0-or-later. The corresponding
unmodified license texts are included in `LICENSES/`. Upstream copyrights and
per-file SPDX headers remain intact in the patched donor checkout.

This directory does not redistribute a full donor checkout, artwork, compiled
binaries or development SDKs. The local `_workspace` checkout retains all other
original license files and third-party notices. The adapter has no fees or
additional service dependencies.
