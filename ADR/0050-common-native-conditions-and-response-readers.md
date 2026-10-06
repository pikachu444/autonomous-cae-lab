# ADR 0050 — Common native conditions and retained response readers

Status: accepted for software integration; numerical contact acceptance remains open.

## Decision

Reuse the existing revision-bound conditions, job lifecycle, Core artifact checks,
and result readers. Domain owns per-body isotropic materials, selected partial
DOFs, prescribed displacement or force excitation, and explicit tie/frictionless
contact declarations. The Code_Aster adapter owns native commands, mesh transport,
native field indexing and solver output. A separately trusted operator capsule
admits the preserved qualified mesh; browser paths and default MCP/Core execution
do not acquire that authority. Empty force lists are valid only with nonzero
declared displacement. No dummy force, spring, stabilization or loosened numerical
criterion is introduced.

The common field reader dispatches by result family. The history reader also
dispatches by family and admits retained OpenRadioss v1/v1.1 native records through
their exact producer contracts. Preserve original signs, SI units, entity/variable
identity, native TIME and velocity half-step TIME-DT/2. A derived world-up force
is labeled separately from the signed native spring force. Wall FNZ is cumulative
impulse, not instantaneous force. Comparison 1.3 requires explicitly declared
quantity, component, frame and actual axis; mismatch retains values with a null
verdict. There is no interpolation, new inverse engine or new solver execution.

Research summaries compact large selection catalogs to referenced declarations
and a verified full-record link. This is a read projection, not an execution
catalog. Smaller existing catalogs retain their previous representation.

## Evidence and limitations

See `benchmarks/records/20261006-common-native-controls-r01.json`. Source controls,
actual retained-history reads/comparisons and actual owned cancellation are
distinct from successful mechanics. The force-driven contact attempts failed;
the displacement attempt was intentionally cancelled through the live owned UI
handle after the user asked to stop the repeated example. HTTP, Core and native
terminal receipts agree. Partial output and original models remain preserved.
No usable new contact field or numerical success is claimed. Error DOF-to-body
association and the unique physical failure cause remain UNKNOWN.

## Work-order correction

The user explicitly rejected continued fixation on the assembly example. Do not
make another mesh/import/contact attempt a prerequisite for the remaining system
development. Preserve open numerical gates and proceed with Phase 3's common
numerical research integration, then the existing Phase 4–7 implementations in
order. Reuse existing engines; do not add example-specific execution/receipt
scripts to provide product behavior. Develop a large bundle, Root runs/fixes and
integrates it, then perform one final independent bundle review.

## Requirement and contract impact

Advances conditions, artifact reuse, general result/history research and native
cancellation within supported families. No R01–R52 requirement is removed or
promoted to complete. The approved research model/OAuth, tools and profiles remain
unchanged. Core/Domain/adapter boundaries and numerical-engine candidate ownership
are preserved. Solver execution and comparison are not physical qualification;
UNKNOWN, invalid metrics and NOT_RELEASED remain.
