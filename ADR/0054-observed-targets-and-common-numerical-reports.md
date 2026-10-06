# ADR 0054 — frozen observed targets and common numerical reports

Status: accepted; bounded software research scope, NOT_RELEASED.

Core reuses existing model/fixed-condition bindings, SciPy LHS and DE. DOE plans
keep a null objective and every original native response/ID. A scalar observation
can be frozen into a match objective only after exact same-study/model/response,
unit, origin/reference and input-condition checks. Its scale is not tolerance.
Advertised finite scalar integral-float/int leaves can compare by numeric value;
raw settings remain retained, booleans/nonfinite values and distinct large integers
are refused. Other settings, units, axes and frames remain exact.

Core owns saved numerical reports: empirical statistics, signed normalized OLS,
seeded training/test surrogate errors and original-ID non-dominance. Adaptive DE
samples cannot claim uniform-input UQ. No population probability, causal inference,
Sobol index, global optimum or physical qualification follows. Invalid responses
stay excluded with explicit reasons. This reuses numerical engines rather than
adding an LLM optimizer or per-example execution scripts.

HTTP/UI reopen the same guarded plan/result/report. Existing MCP inspect reads
add checked report_context; optional compact view omits only duplicate per-row
model settings/declarations and preserves original signed response, feedback,
constraints, hashes, validity and UNKNOWN. Full reads remain compatible. Approved
fourteen-tool AI scope/model/auth are not expanded. Source-byte execution guards
read all current bytes without repeated unused Git metadata; producer provenance
still records actual Git state and the identical byte digest.

New report creation requires currently advertised response admission. Sealed
report reopening recomputes against retained original records/units/receipts
without requiring a currently installed adapter. Fixed-CAD Domain rejections
retain a missing-child/null response rather than borrowing the common CAD
parent's response. UI report requests and their question actions hold an exact
selection generation; late success/error cannot replace another selected report.
DOE questions carry the Core-verified inline report and existing experiment reads;
they never request an optimizer inspection of a DOE or expand AI tool admission.

Acceptance: record20261007-common-numerical-research-r01. Actual DOE8/DE13 native
histories and independent integration/statistical comparisons pass the declared
software checks. Two-generation search ended without matching target tolerance;
retain the original residual and MAX_GENERATIONS. Three source-test fixture/seam
failures are preserved and corrected with targeted PASS. Whole52 and broad
Phase7 probability/MOO/multiphysics/HPC are incomplete. OpenScience interpretation
is a separate actual gate. No obligatory mesh convergence or old failed solve
repetition is introduced.
