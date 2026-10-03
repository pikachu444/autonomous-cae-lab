# Code_Aster contact benchmark input provenance

`ssnp121a-17.4.0.mmed` is the unmodified public SSNP121A test mesh from
Code_Aster tag17.4.0, commit50ebc13c70ee9df62faf93ddcb746a3757b3042a:
https://gitlab.com/codeaster/src/-/raw/17.4.0/astest/ssnp121a.mmed
Copyright EDF R&D; the original Code_Aster test source states GPL-3.0-or-later.
The GPLv3 text is included as `COPYING.GPL-3.0`; no solver executable/source
distribution or company CAD/data is stored here.

`ssnp121a-17.4.0.mesh.json` is the actual MED catalogue extracted read-only
with the existing MEDLoader9.14.0, retaining all coordinates/connectivity/
groups and original zero-based node indices. It does not invent a replacement
mesh. It retains N14's actual x=2.98023223876953e-08 m rather than snapping to0.
Mesh units are independently supplied by the official problem definition.

The original problem/reference/ModelA documents are available through
https://codeaster.gitlab.io/doc/docaster/manuals/man_v/v6/v6.03.121/index.html
and source conditions are frozen in
`benchmarks/specifications/contact-patch-ssnp121a-v1.json`.
Actual native asset has92SEG2 rather than the document's132; the native body
labels reverse the figure's plate numbering. The native17.4 input uses
SIMPSON/order4; its equivalence to the old SIMPSON2 description is UNKNOWN.
This case is SSNP121A, not a NAFEMS CGS1 reproduction.
