# ADR 0010 — Explicit runtime admission for the material inverse prerequisite

Status: accepted for bounded research execution, 2026-09-30.

## Problem and decision

The independently pulled CI image has different SIF bytes from the measured
local image, although its OCI definition and six measured installed binding/tool
hashes match. The reason for that SIF difference remains UNKNOWN. A matching OCI
address alone cannot substitute for actual native runtime verification.

Keep `LOCAL_EXACT_SIF` as the default for `material.mfront.inverse`. Add the
explicit deployment-only `SEALED_OCI` profile in this adapter. Research inputs,
model settings and an LLM cannot select it. No automatic fallback is permitted.

Before discovery/plan/native candidates, the adapter verifies the configured
actual SIF SHA, exact OCI definition and six installed native identities through
a fixed read-only probe. It rejects all Singularity/Apptainer environment override
namespaces without retaining their values. Source, configuration, image, runtime,
probe and resource policies are frozen and rechecked around execution. Native
stress feedback still requires all original material-point numerical gates.

The common Core schema/engine and model-analysis route stay unchanged. The
adapter supplies the existing runtime-identity contract in ADR0009; native image
syntax, binding paths and admission commands remain inside the adapter. CI
selects the explicit profile for its inverse step only and retains the entire
fresh store, including failed admissions. Local launchers retain their default.

## Alternatives and consequences

Replacing the local image or hard-coding CI's SIF bytes would discard the measured
environment or assume another build. Trusting only the OCI digest/native version
would miss altered bindings or mounts. Automatic fallback would let a failed exact
policy silently change execution. These alternatives are rejected.

This admission adds bounded read-only native commands; it does not import solver
sources/binaries into the repository, qualify a different native inventory or
establish container immutability beyond the retained checks. Repeated native
admissions retain their command/output provenance. Existing v1 evidence stays
at its original source and exact runtime; no earlier result is rewritten.

## Verification and requirement impact

Reviewed source f0b5fa39 passed nine fresh actual local candidates with747
artifacts/818 files,19 admissions/38 bounded commands and immutable completion.
Final evidence73639f6 passed independent source/projection review. Default exact
SIF behavior, altered metadata/environment/output/resource/drift rejection and
pure construction are covered by120 corrective contract tests. Main integration
and actual alternate-runtime CI are separately attributed gates; this ADR is
not their success claim. SIF-difference cause, measured-material identification,
coupling, physical/strength/durability and corporate deployment remain UNKNOWN.

Preserves R03,R06,R11,R18–R21,R27,R31,R43,R51 and all52 requirements. No full
phase, convergence/global optimum or RELEASED decision is established.
