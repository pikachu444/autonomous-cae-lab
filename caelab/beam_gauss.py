"""Exact B32R RECT point numbering from CalculiX 2.22 gauss3d13.

Primary source: Dhondtguido/CalculiX cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54,
 src/gauss.f lines 234-285, src/printoutint.f (mint3d=50).
These are natural coordinates for identifying a reported point, never a
substitute for a missing native DAT COORD observation. Not ordinary HEX20R's
8-point rule and not a reordered Cartesian product of a 5-point Gauss rule.
"""
G = .577350269189626
B = .5773502692
A = .9258200998
# First eight points are stored first by the native solver. Remaining 21
# section points at each axial station follow et-fast, ze-slow order, omitting
# the four points that have already been emitted. Keep native printed precision.
FIRST = tuple((x,y,z) for z in (-B,B) for y in (-B,B) for x in (-G,G))
REMAINDER = tuple((y,z) for z in (-A,-B,0.,B,A) for y in (-A,-B,0.,B,A)
                  if not (abs(y)==B and abs(z)==B))
B32R_RECT_GAUSS50 = FIRST + tuple((x,y,z) for x in (-G,G) for y,z in REMAINDER)
assert len(B32R_RECT_GAUSS50) == len(set(B32R_RECT_GAUSS50)) == 50
