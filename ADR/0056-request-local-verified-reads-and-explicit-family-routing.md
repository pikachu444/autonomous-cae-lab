# ADR 0056 — Request-local verified reads and explicit family routing

Status: accepted for the bounded common read/control correction, 2026-10-07.

## Problem

The same immutable campaign repeatedly resolves each source artifact and its
shared parent directories. On this Windows store through WSL, the original UQ
Core read took 39.6228s; its actual HTTP reopening took 94.8455s. The byte and
source checks are required, but redundant directory traversal delays research.

Exact a89947c CI also exposed a family-routing defect: a custom backend present
in both registries was sent to the PDE output/namespace without declaring that
contract. An owned model-process test looked for its original simulation output
and failed. This was a routing defect, not solver convergence or slow startup.
Two additional tests retained the previous registry/metric catalogue inventory.

## Decision

Use a context-local, single-request path guard for campaign/report reads. Cache
only directory identity during traversal, inspect files on every access, and
recheck all inspected identities and the selected store before returning. Reject
symlinks, Windows reparse points, ambiguous/traversing paths, replacement and
boundary escapes. Distinct threads/stores and later requests have separate guards.
Appending another experiment may change a shared directory mtime but cannot
change its identity. No artifact bytes or successful verdict are cached.

Existing artifact hash/schema/source checks and the HTTP reader's file-handle
before/after/current identity and byte/size checks remain. This guard does not
claim filesystem snapshot isolation against arbitrary simultaneous hostile writes.
It reduces repeated traversal and refuses observed mutation before a return.

Route a declared model through the PDE namespace only when its backend is in
the PDE registry and its selected adapter explicitly has
`pde_model_declaration is True`. Shared key membership alone is insufficient.
Keep the original cancellation readiness/cleanup bounds unchanged. Preserve
the canonical nine coupled benchmark metrics; its additive public catalogue
also advertises the four selected-mesh signed extrema, without substituting
them for the canonical reference responses.

## Alternatives, verification and scope

Removing integrity checks or keeping a persistent path/verdict cache was
rejected. Building another result/solver pipeline was unnecessary. The original
scientific records, numerical thresholds, native producers and approved
OpenScience model/profile admission remain unchanged.

Real filesystem controls reject replacement, redirects and boundary escapes,
retain independent request/thread/store contexts and allow separate experiment
append. Existing UQ/report tamper controls pass. Actual HTTP UQ/MOO reads return
the exact original envelopes/vectors, not newly computed numerical results.
The final routing regression retains actual owned-child cancellation for all
four families. See `20261007-common-read-control-r01.json` for exact sources,
timings, retained failed diagnosis and CI distinctions.

This advances common usability/control under R11/R31/R35. Read latency remains
OPEN at roughly 27s for these aggregate HTTP reads. No new solver/provider
acceptance, physical qualification, full52/Phase completion or release follows.
