# Original retained M4 native failure fixture

Request: PRO-M4-NATIVE-CORRECTION-20261015-02.
The four files below are byte-identical copies of `native/` entries in the user-supplied `m4-native-correction-source-02.zip`. They are original INPUTS, not outputs manufactured by the correction tests.

`source.caepre` retains the accepted nested-slider motion source. `draft.caepre` is the failed first-body candidate, not a completed editable/FEM model. `geometry.json` records a read-only observation of only the first Base occurrence. `receipt.json` identifies the preserved selection. None of these proves four-occurrence preparation, Gmsh or cold reopen success.

The test reads FreeCAD's original `.Shape.bin` in these archives using a test-only BinTools_ShapeSet adapter and compares full geometry using the unchanged product algorithm. It does not regenerate a box from dimensions or alter/recompute the source. The archive hashes before/after are checked.

SHA-256:

```
d8cadd4d86529d99346782fad88e4187c916a0522945fa01c52ed145a11499a8  draft.caepre
dae59320f4f572b7b41720844f05690441a1082407dbff8510336989527247a1  geometry.json
0d6e19905c82f10b4ba5035297a7ec887a19524a78520c1c37d15df4e45e7b20  receipt.json
d0cb4600deb027633da3d038f3ff54246895b0b5d22a6ac479c47f46906f2ea8  source.caepre
```

No personal application windows or native test processes were opened to run this Linux fixture test.
