# Actual CalculiX 2.21 parser fixture

These public benchmark input/output bytes were generated locally in
`p2-family-native-20261002-02`, source
`fa0b1a8e6cee992300bb4264f34baec28e0b46fc`, first coarse regular beam Fx mesh
`[6,1,1]`. Actual `/usr/bin/ccx` SHA256:
`6adaabf5bf0382fc2bfd692b984320ed375dba777f7dc8297562f818043faa1b`.
The solver exited0/Job finished. Core retained FAILED_EXECUTION because the
then-current parser omitted native DAT step/increment and FRD ERROR metadata.
The original failed store remains preserved. No new result replaces that failure.

The fixture contains80 nodes,6 HEXA20 elements and162 integration points, all
nodal U/internal RF and all27 Cartesian S/COORD points per element. Native
FRD's additional scalar `ERROR/STR(%)` is an extrapolation estimator, not a
measured reference error or residual. It must be complete/finite if present;
it never replaces the analytical/cross-solver gates. This regression fixture
establishes parsing of actual output, not three-mesh numerical acceptance,
original MIDAS replication or engineering qualification. Build source UNKNOWN.
