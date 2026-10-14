# Independent CalculiX projection utility

This standalone numerical command is licensed GPL-2.0-only. It is a Python
translation of the six-node paths in CalculiX 2.22 `attach_2d.f` and
`distattach_2d.f`, Copyright (C) 1998-2015 Guido Dhondt.
Pinned upstream commit: `cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54`.

Sources:
- https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/attach_2d.f
- https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/distattach_2d.f

Changes (2026-10-14): Python implementation, six-node faces only, finite/bounded
generic JSON file input and exclusive output, command-line errors. The search
starts at (0,0), divides step by ten eight times, preserves loop order, strict
minimum comparisons, grid-center updates, square bounds and triangle fold.
No original Fortran source or other element branches are bundled.

The complete corresponding source is `projection.py` alongside this notice and
the GPLv2 text in `COPYING`. It imports only the Python standard library and runs
independently; it never imports CAE Lab, Qt, document owners or shared schemas.

Usage: `python projection.py --input points.json --output projected.json`.
Input: `{"cases":[{"face":[[x,y,z], ... six nodes],"point":[x,y,z]}]}`.
Output: `{"projections":[{"point":[x,y,z],"weights":[... six weights]}]}`.
Input and output coordinates use the caller's consistent length unit.
This does not select a master face, establish a tied MPC or run a solver.

CAE Lab invokes the program by file/subprocess, not by importing its code. This
engineering boundary is not a claim that all distribution license questions
are automatically settled by using a separate process. The project-wide
distribution license remains a separate release decision.
