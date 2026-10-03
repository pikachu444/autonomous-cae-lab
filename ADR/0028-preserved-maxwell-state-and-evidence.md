# ADR0028 — preserved Maxwell state, exact-ramp reference and execution evidence

Status: source decision accepted after independent adapter and publication
review; fresh native qualification is a separate gate. The original six drafts remain immutable.

P5.2b reuses the existing synthetic infinitesimal 3D single-branch Maxwell law
and draft adapter. It extends the existing declared-model operation, rather
than adding a solver-specific Core operation, schema, registry or optimizer.
The material-point Domain owns history/material meaning and numerical verdicts.
The adapter owns MFront syntax, protected local runtime, MGIS/MTest state,
build evidence and conversion of actual outputs to the common result envelope.
OpenScience remains the research control plane; deterministic engines own
numerical search. MaterialPoints currently admits only the qualified SVK law;
Maxwell Research admission follows fresh native qualification.

The old fake update omitted MGIS's real K reset and hid a committed-state
evidence gap. Preserve the actual post-update snapshot and hash, bind it to
the prior nominal endpoint, and require the next baseline to match the full
committed state except the new declared increment dt. Clones for every signed
FD probe must have independent native buffers and serialized containers.
Record the post-update K as returned; a zero cache is not a fabricated tangent.
The actual nominal pre-update tangent remains the algorithmic response tested.
Partial failure retains the last actual state and invalid observations.

For x=dt/tau, q is the relaxing branch stress and z=C1*delta_strain. The original
expanded dissipation subtracts large terms at small x. Use the algebraically
equivalent positive-quadratic expression:

    dD = -expm1(-2*x)/2 * Q(q0 + tanh(x/2)/x*z)
         + (x - 2*tanh(x/2))/x**2 * Q(z)

Here Q(q)=q:C1_inverse:q. Modal bulk/deviatoric contractions avoid cancellation
in high-contrast hydrostatic states. Independent integrated stress work remains
separate from native stored/dissipated energy. The fixed 1/8 small-x switch only
selects reviewed series evaluation; it is not an admission threshold. Fixed
scientific limits, supported material/history ranges and signed FD steps remain.
The independent high-precision oracle and original failed range observations
are retained. Shared-time refinement tests exact-ramp composition, not a
measured temporal convergence order; per-increment tangents depend on dt.

The analytically bounded causal-history x-rounds-to-zero limit does not qualify
a native driver or flush-to-zero runtime. Native describe/solve refuse x==0 or
nonfinite before export/capture/execution. Positive subnormal native behavior,
arbitrary histories, spatial FE and physical materials remain unqualified.
No cutoff or clipping is added merely to obtain acceptance.

MTest records the exact imposed Kelvin history separately from actual returned
gradients. Its existing strict strain residual <1e-14, stress epsilon1e-10,
one substep and ten iterations are frozen. The previous 1e-15 interpretation
of returned strain as exact input identity was incorrect. References continue
to use the prescribed history; actual buffers are never projected or substituted
into it. Scientific stress/branch/tangent/energy criteria remain unchanged.

Reuse the existing shared compiler classifier with a fixed trusted behavior
identifier. Both producer and consumer reconstruct all five compile/dependency/
non-LTO link records and bind original logs, flags, sources, objects, libraries
and complete dependency hashes. Preserve the original SVK default and all other
classifier semantics. Admit only the two reviewed exact LF/CRLF transport byte
forms; freeze equality to the actual selected capture. A narrow law LF attribute
preserves its fixed digest without changing global Git newline policy.

Reuse common owned process management, cancellation and declared budgets.
Default CPU86400/wallNone replaces the old hidden CPU180/wall240/build120
assumptions; explicit existing budget settings remain. Budget/process/parse/
identity failure keeps convergence UNKNOWN. Reliable constitutive execution is
separate from analytical acceptance: a reference disagreement remains REJECTED
with invalid metrics even when reliable execution is proven. A typed unreliable
native return reports False and its actual phase/code; it does not diagnose a
Newton mechanism. No common schema change is needed.

Alternatives rejected: manufacturing a post-update tangent, keeping the masking
fake, replacing native energy with Python energy, loosening scientific limits,
repeating unchanged failed native runs, copying the compiler/process helpers,
or permitting arbitrary native laws/runtime images. Each would erase evidence
or bypass an accepted boundary.

Requirement impact: R01/R02/R03/R05 retain platform ownership; R17/R29 gain
bounded viscoelastic material-point capability; R19/R20/R21/R33/R34/R43/R48/
R51/R52 require exact state/source/evidence/inspection and independent review.
All 52 requirements retain their wider scope. Contact/fixture coupling, Phase6,
Phase7, measured material/strength/durability, binary-source provenance and
corporate deployment approval remain OPEN or UNKNOWN and prevent release.

Acceptance order: preserve originals; reviewed state/range/build/runtime source
and one combined cold gate; coherent Main commit; fresh canonical9/refined17/
changed-tau9 plus preflight refusal; independent original state/FD/native energy
audit; explicit Research admission; one complete question and same-record human
inspection. Source tests and solver exit success do not close these later gates.

Publication correction: Root observed that the frozen draft law contained174
CRLF endings, although the accepted Git law policy is LF. Normalize the law to
exact Git7417B/SHA8501f6d338d0d58fd9391031274dd0d15ecaf333f6158f0c80a73ffdb99e3d7a
and change only the worker fixed digest. The constitutive text and all other
worker AST remain identical. Retain the original CRLF draft/seals; one new real
Main regression/import smoke and independent P2closure qualify this transport
correction without repeating or relabeling the original413/native evidence.

## Actual MTest phase/counter clarification

Native02 exposes an adapter consumer defect: printOutput uses globalu0[:6] and
committeds0/iv0, while e1 retains the last constitutive evaluation. Capture both
actual buffers independently and require exact table correspondence with u0,
s0 andiv0. Retain actual e0 as prepared prior-global strain, not an endpoint
copy. Full12-vector size follows six gradients and six imposed multipliers.
Official GenericSolver increments cumulativeiterations separately from local
iter. Preserve actual before/after and enforce local delta1..10, initial0 and
failedsubsteps0; cumulative16 is valid for eight two-iteration increments.
These decisions follow pinnedTFEL85554 primary and independent source review.
The installed tfel.math import registers the global-vector converter; capture
and seal its actual loaded/resolved file,size927872/SHA9685745 independently
within this adapter. Shared six-binary helpers and Core interfaces are unchanged.
Alternatives of replacing e1, comparing e0=e1, relaxing printed-gradient
identity/scientific limits, or changing the driveriteration limit are rejected.
Native energies remain actual mandatory table outputs. Old failedstores and
verdicts stay unchanged; clean corrected-source native03 is the next gate.
The CI transport negativecontrol chooses a real opposite exact LF/CRLF form
from the actual checkout; production selected-source admission is unchanged.

## Actual loaded/resolved binding clarification

Native03 exposes Root path-identity consumer failure after successful integration.
Retain actual module __file__ separately from strict Path.resolve; require both
exact protected aliases/resolved prefixes and unchanged actual SHA/spec/version.
Shared helpers and scientific law/state/limits remain unchanged. Arbitrary path
normalization or weaker package/hash verification is rejected. Bounded216 source
PASS and narrow independent review precede fresh04; old failed stores unchanged.
