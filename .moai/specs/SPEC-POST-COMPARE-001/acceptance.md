# Acceptance scenarios

| Scenario | Expected user outcome | Requirements |
|---|---|---|
| Unit conversion | Same known field in Pa/MPa or m/mm produces zero difference after declared conversion; originals remain readable | PC-001, PC-002, PC-006 |
| Rotated/translated geometry | A translated frame aligns points without adding translation to vectors; a 90° vector/tensor rotation yields analytically known components | PC-003, PC-008 |
| Tensor convention | Explicit six/nine component layout and engineering/tensor shear are handled consistently; unknown layout blocks the dependent comparison | PC-003, PC-007 |
| Time selection | Exact equivalent clocks or a linear field at a bracketed intermediate time compare correctly; unsupported gaps/extrapolation are shown | PC-004 |
| Spatial/association transfer | Explicit supported point/cell transfer shows method and support mask; outside-domain and missing values remain invalid | PC-005, PC-008 |
| Usable controls | Source→quantity→conversion preview→apply→original/transformed/difference view works through GUI without raw JSON | PC-001–PC-006 |
| Save and recovery | Save/reopen retains values, choices and masks; changed input rejects stale preview and Cancel preserves prior result | PC-006, PC-008 |
| Legacy/invalid input | Old scalar recipes work; incompatible dimensions/measures, unknown bases and invalid rotations do not yield fabricated differences | PC-002, PC-003, PC-007, PC-008 |

Use deterministic manufactured fields for unit checks and one small native ParaView
workflow for wiring. This proves implementation behavior, not engineering qualification.
