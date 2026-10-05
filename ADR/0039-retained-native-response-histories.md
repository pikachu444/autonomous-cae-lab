# ADR0039 — Exact retained history samples in the common research flow

Status: accepted, bounded Maxwell implementation. Date: 2026-10-06.

## Reason and decision

Defect hypotheses and virtual-test feasibility need a named response at an
explicit condition/time, not anonymous nested arrays or another solver example.
Reuse retained native results and ADR0038 append-only comparisons.

Core exposes `response_histories` and permits `history_channel + sample_index`
as a mutually exclusive alternative to scalar/flat-array selection. The adapter
owns component order, stress measure, driver, recorded axis, units and origin.
The first adapter reads the qualified Maxwell MGIS stress6/branch6 and separate
MGIS/MTest stored/dissipated energy2+2. It checks native arrays against valid
metrics, exact model timestamps, conventions and the manifest-bound raw JSON.
The initial zero state remains UNPREPARED_INITIAL_CONDITION. Component basis is
the declared Tridimensional model; sensor/world alignment remains UNKNOWN.
Analytical work is not native energy. MPa energy is per reference volume, not J.

Observation time must be explicitly declared. Exact quantity/unit and recorded
sample are required; an off-grid time preserves both values but nulls the delta
and tolerance verdict. No interpolation, nearest sample, unit conversion,
time shift or physical scope qualification is inferred. Scalar records remain
version1.0; exact-history comparisons use1.1 and preserve the complete channel.
Core checks source/receipt/calculation on reopen. HTTP preflight/rechecks and
existing write fences remain, with no global lock or native replay.

The human GUI plots signed recorded samples, permits channel/time selection,
stores comparisons and reopens their own channel/axis even when another source
is selected. Expanded original metadata remains available. Source-only tests,
actual retained-result/ref comparison, GUI save/reload and independent read
review are recorded in `benchmarks/records/20261006-response-history-r01.json`.

## Alternatives, impact and limits

Flattening arbitrary arrays would lose tensor/driver/axis meaning. A generic
curve fit or another native solve is unnecessary for this read/save slice.
R01–R03/R09–R13/R19–R21/R24 gain bounded response/history access; all52 and
Phase1–7 remain. Measured data qualification, general curves/inverse, spatial
material coupling, contact/load-parameter and explicit staggered axes are OPEN.
No canonical numerical threshold changed. No new MCP/profile/provider admission
or research model choice: approved5.6Sol/OAuth is unchanged. OpenScience reading
and interpreting these same structured records is the next connected slice.
UNKNOWN/USER_DECLARED_UNVERIFIED/NOT_EVALUATED/NOT_RELEASED are retained.
