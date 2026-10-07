# ADR0059 — Admit a separately pinned explicit-solver successor

Status: accepted for bounded local qualification; remote CI verification pending.

The original OpenRadioss `latest-20260728` release archive became unavailable
at its vendor GitHub URL. CI at source commit `acbe38c` failed during download,
before any explicit numerical test. The old archive and acceptance artifacts
remain locally preserved and are not reidentified as a new solver run. Keeping
the dead URL would make the explicit CI gate permanently unexecutable. Moving
to an unpinned current release or a different engine would erase the solver
identity needed for reproducible engineering evidence.

Admit the community successor OpenCourant `latest-20261006` as a second explicit
runtime under the existing bounded `explicit.openradioss` adapter. The adapter
checks its distinct source commit, archive SHA-256, critical binaries/libraries
and reader configuration; the original 20260728 pin remains supported for old
experiments. The current launcher and CI installer select the new archive
explicitly. No automatic fallback chooses another solver when a pin fails.
Each experiment records the runtime actually used.

The new native TH40 output adds one global energy-balance channel. The parser
accepts that 23-channel layout only for the exact new runtime identity and
checks its value against the source expression. The old 22-channel layout is
unchanged. This extends a verified native schema; it does not weaken any
freeflight, impulse, contact, energy, input-admission or engineering threshold.
The old ideal rigid-wall failure and invalid metrics remain visible in their
original and newly executed campaigns.

Alternatives considered: republish the surviving official ZIP under this
repository (deferred because corresponding-source/dependency distribution
review is incomplete); consume a third-party container based on an older build
(different and incompletely qualified bytes); keep the dead vendor URL
(blocks CI); change to an unrelated solver (requires a new adapter and separate
engineering qualification). The selected upstream-successor asset has a live
release, source commit and digest and passed fresh local native comparisons.

Requirement impact: the fixed explicit examples, native history/provenance,
invalid-input gate and `UNKNOWN` physical-validation gates stay in force. The
Core/OpenScience contract does not change: Core retains solver-independent
schemas, evidence and verdicts; OpenScience may interpret only the exact
recorded runtime and results. No physical release or general contact claim
follows from a numerical PASS. The clean local qualification and exact remaining
CI gate are recorded in
[`docs/OPENCOURANT_RUNTIME_QUALIFICATION_20261008.md`](../docs/OPENCOURANT_RUNTIME_QUALIFICATION_20261008.md).
