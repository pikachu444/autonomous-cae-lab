# Actual CalculiX 2.21 DOUBLE-FRD format fixture

Root ran one direct native output-format probe on clean source
`ab188cd973c8612d27c052f7eaf40e03686c5f14` in the fresh path
`artifacts/p2-family-calculix-double-probe-20261002-01`. The input was copied
from rejected Native03 coarse beamFx `[6,1,1]`, changing only both FILE cards
to request DOUBLE. Mesh, loads, material, restraints and DAT requests stayed
identical. Installed `/usr/bin/ccx` bytes were unchanged:
`6adaabf5bf0382fc2bfd692b984320ed375dba777f7dc8297562f818043faa1b`.
Actual job exited0; it made no Core/model calls or Domain acceptance verdict.
The original Native03 remains REJECTED. All five fixture files are exact raw
probe bytes; text conversion is disabled. The DAT is also byte-identical to
Native03's coarse DAT, including its rounded RF observations.

The fixture has80 nodes,6 HEXA20 elements and162 integration points. Binary
FRD uses the observed Linux ELF64 little-endian x86-64/SysV Cint32/double64
layout and contains native coordinates/topology, U/RF/nodal S and ERROR.
Every DOUBLE U/RF component is corroborated by the seven-significant-digit DAT.
Measured native U/RF preserve their unrounded values; restrained reactions
subtract serialized CLOAD once on each restrained component. Neither reactions
nor response are reconstructed to make an equilibrium or reference gate pass.
All27 DAT S/COORD points remain primary integration-point observations; nodal
averaged S and ERROR remain separate diagnostics. This fixture proves format
parsing only. Fresh Core mesh/cross-solver/research/GUI acceptance, original
MIDAS replication and engineering qualification are separate gates.
