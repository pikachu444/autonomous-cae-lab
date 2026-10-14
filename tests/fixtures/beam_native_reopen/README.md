# Supplied native save/reopen regression records

These files are unmodified copies of the user's native Windows execution records
in `native-correction-source.zip/native`. They were not calculated by this patch's
author and are not synthetic solver outputs. This directory is test input, not a
claim that a native application or solver was run during Python testing.

`moment_1` and `section_90` retain the original sparse mesh, input, snapshot and
editable files. Their original `mesh.json` labels are 101, 108, …, 241 and 1001,
1012, …, 1100. The FCStd archive already contains the compacted UNV mesh. The
adjacent `reopen-binding.json` retains the observed native reload labels,
coordinates, ordered Seg3 and B32R connections and original CAD pins. Tests
compare exact coordinates and both local node orders, not a numbering formula.

`calculation-run1` and its summary are retained solely for byte-preservation
checks. The supplied product status is FAILED; it is not reclassified or used as
a passing physical reference. Its old STATIC card, automatic ERROR output and
all original values remain untouched. Result-reader and STATIC correction are
outside this patch's ownership.

The production example `examples/beam/cantilever-10x20.FCStd` has a separately
verified metadata-only update. It is NOT substituted for the original fixture.
Its original archive was byte-identical to this directory's
`moment_1/editable.FCStd`. The fixture remains unchanged; a regression checks
all archive members and all other XML property values in the updated example.
