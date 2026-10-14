# Acceptance scenarios

| ID / Scenario | Expected user outcome | Requirements |
|---|---|---|
| AC-PC-001 Unit conversion | Same known field in Pa/MPa or m/mm produces zero difference after declared conversion; originals remain readable | REQ-PC-001, REQ-PC-002, REQ-PC-006 |
| AC-PC-002 Rotated/translated geometry | A translated frame aligns points without adding translation to vectors; a 90° vector/tensor rotation yields analytically known components | REQ-PC-003, REQ-PC-008 |
| AC-PC-003 Tensor convention | Explicit six/nine component layout and engineering/tensor shear are handled consistently; unknown layout blocks the dependent comparison | REQ-PC-003, REQ-PC-007 |
| AC-PC-004 Time selection | Exact equivalent clocks or a linear field at a bracketed intermediate time compare correctly; unsupported gaps/extrapolation are shown | REQ-PC-004 |
| AC-PC-005 Spatial/association transfer | Explicit supported point/cell transfer shows method and support mask; outside-domain and missing values remain invalid | REQ-PC-005, REQ-PC-008 |
| AC-PC-006 Usable controls | Source→quantity→conversion preview→apply→original/transformed/difference view works through GUI without raw JSON | REQ-PC-001, REQ-PC-002, REQ-PC-003, REQ-PC-004, REQ-PC-005, REQ-PC-006 |
| AC-PC-007 Save and recovery | Save/reopen retains values, choices and masks; changed input rejects stale preview and Cancel preserves prior result | REQ-PC-006, REQ-PC-008 |
| AC-PC-008 Legacy/invalid input | Old scalar recipes work; incompatible dimensions/measures, unknown bases and invalid rotations do not yield fabricated differences | REQ-PC-002, REQ-PC-003, REQ-PC-007, REQ-PC-008 |

Use deterministic manufactured fields for unit checks and one small native ParaView
workflow for wiring. This proves implementation behavior, not engineering qualification.
