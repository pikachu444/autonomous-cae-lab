# Actual pinned Code_Aster 17.4 import observation

These five raw files are byte-identical copies from Root's fresh
`p2-family-codeaster-import-probe-20261002-01` on clean source
`af9bd45ef2e5c6f66a6c9b46caa44d4ebb213d96`. The exact original Native04
coarse beam mesh was imported in the same pinned SIF, SHA256
`f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64`.
One import process executed; MECA, Core and model calls were zero. Original
Native04, source and image bytes remained unchanged. Native04 is still partial:
CCX three levels passed, while Aster failed before MECA at the name gate.

The follow-up import observes 80 nodes and 102 cells (6 HEXA20 + 96 POI1).
MSH2 canonical `ALL_NODES` is returned as `ALL_NODE`, consistent with pinned
`pregms.F90` character length8. Exact canonical-to-native name mapping is checked
as a bijection before any native command; prefix collisions, missing/extra
groups or map drift are refused. All source cell types, ordered connectivity,
physical memberships and group node sets remain exact. Original mesh/catalogue
names and dimensions/tags are unchanged. Raw5 paths disable text conversion.

The observation contains no displacement, reaction or stress solution. It
proves import identity only; fresh numerical/cross-solver/OpenScience/GUI gates
are separate. Arbitrary-case reader compatibility and roof singleton automatic
node groups were not exercised by this uppercase beam probe. Material, physical
and engineering qualification remain UNKNOWN and NOT_RELEASED.
