# ADR 0014: Identify new native sketch selections without positional collisions

Date: 2026-10-01. Status: implementation decision; source and actual acceptance
are recorded separately. Applies to R06, R07, R13, R25 and R50 / P1.2a.

## Problem and retained evidence

The pinned fixture worker registers a Sketcher dimension with its original
positional `key` and its renamed `constraint`. Generation resolves the name,
so ordinary index shifts preserve the registered dimension. Discovery removes
all current targets whose positional key appears in the registry. A different
new dimension inserted at that old index therefore disappears.

Clean Main `671b81817ca5c0babf0c3f0aa2c2f2e6b18519c2` with pinned fixture
`3e48bf6138f495299f45b1af254bfb4aaff307b8` reproduced this in an actual imported
FCStd: registered `locator_radius` moved from index0 to1; new driving
`center_x` at index0 was absent from Core discovery. Existing stale-source
execution correctly refused before an experiment/export. The original source,
result, edited FCStd and failed discovery are preserved in the new red store.
The independent code investigation found that adding the missing positional
candidate alone would create duplicate native paths and borrow old bounds.

## Decision and ownership

Keep the fixture pin, its geometry/effect/registration/domain/export algorithms
and common Core/registry/operation schemas. Add one adapter-owned FreeCAD worker
that imports the exact pinned worker. It reads the unfiltered targets and
registered definitions in the same native document and validates unique live
identities before creating dictionaries.

Resolve registered properties by object/property and registered Sketcher
dimensions by a unique supported driving constraint name. Preserve their
literal legacy or opaque `entry.key`; do not add a current positional alias.
Reject duplicate keys/resolved identities and missing, renamed, deleted or
non-driving registered dimensions. An unregistered legacy positional constraint
path cannot fall back to a different current dimension.

Only unregistered Sketcher candidates use an opaque adapter selector containing
the current FCStd SHA256 and index in a separate namespace. Verify its source
bytes before translating to the pinned registration target. Preserve that
selector as the newly registered native `entry.key` after the pinned worker
renames and checks its actual geometry effect. Subsequent resolution checks the
current registry key first; a registered selector's historical SHA is not an
expiry condition after a later native revision. Core research IDs, mappings,
existing bounds and native names are unchanged.

The pinned runner hardcodes its worker path. A small adapter launcher retains
the existing JSON request/result protocol, fixed trusted worker path and
150s worker / 180s bridge bounds. It adds transport plumbing without copying
the geometry or domain implementation. Do not patch the upstream module's ROOT
or process-global subprocess functions to redirect its executable secretly.

## Alternatives and compatibility

An upstream refactor is possible, but would change the pinned dependency and
require a separately verified migration. Copying its worker or moving native
syntax into Core would duplicate ownership. Merging raw positional candidates
without new selectors leaves the alias/bounds collision. Replacing all legacy
registered keys would unnecessarily invalidate existing stores.

Existing registered positional paths remain valid named mappings. Old clients
selecting an unregistered positional Sketcher index must rediscover and use the
advertised selector; selecting arbitrary indices after edits is ambiguous.
Part property paths and all common operation signatures stay unchanged. The
existing native acceptance selects its unregistered sketch dimension from
actual discovered metadata and retains the same radius/geometry/rejection gates.

## Verification and limitations

Source checks cover omitted candidates, collision/bounds refusal, stale new
selectors, historical registered selectors, legacy fallback refusal and invalid
registered identities. Actual `verify_native_edits` freezes synthetic Box and
circle/extrusion inputs and analytical references before execution: lengths,
volume, signed centroid and unchanged original artifact hashes. It imports
editable FCStd, inserts/removes/reorders dimensions, proves source-refresh
gates and exercises malformed registered definitions without export.

Circle radius6 / extrusion8 requires bounds `[12,12,8]` and volume `288*pi mm^3`.
The six-argument DistanceX/Y fixture is explicitly center-to-origin: positive
datum5/7 requires signed centroid `[-5,-7,4]`. It is not an absolute-coordinate
metric. FreeCAD's [Sketcher scripting reference](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_scripting.md)
defines the circle-center point index; the
[horizontal-distance API reference](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_ConstrainDistanceX.md)
supplies the two-point dimensional form. Native and exported STEP fields are
compared with these predeclared analytical values; thresholds are fixed.
The versioned [FreeCAD1.1.4 constraint insertion](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Sketcher/App/Sketch.cpp#L2678)
passes the points in order; its [difference residual](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Sketcher/App/planegcs/Constraints.cpp#L603)
is point2 minus point1 minus the datum. This agrees with the retained actual
red case's center_x datum2 and signed centroid-2; no absolute-value substitute.

Representative editor revisions use the same actual FreeCAD object API and
editable files; they do not prove a human GUI click. Deleting a constraint and
reusing its name for a semantically different dimension cannot be certified as
identical from existing name-only definitions. Concurrent native-file edits and
cross-file registry write recovery require separate P1.2b work. Engineering
UNKNOWN, NOT_RELEASED and solver NOT_RUN remain; numerical optimization is
unaffected. The OpenScience contract continues to treat native selectors as
opaque values only at discovery/registration boundaries.
