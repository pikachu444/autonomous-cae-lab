# ADR0057 — Qualified native runtime and retained numerical interpretation

Status: accepted for the bounded MCP lifetime fix and per-run execution binding.

The installed official OpenScience2.0.146 Windows MCP launcher can remove the
release marker before the proxy finishes activation. The retained failed startup
does not prove that race was its only cause. A single-source local patch keeps
the marker until initialize succeeds or exact owned closure succeeds. It is a
local build of official source4082a2ecb73e166d4503963798228ba700f3840f,
not a newly published vendor release. The patch is retained under
`openscience/patches/2.0.146-windows-mcp-release.patch`.

The actual auth-free candidate execution r03 confirmed MCP activation, exact
registered Windows Job closure, official disconnect/disposal, isolated ledger0
and pipeEOF. Its serve root required termination through Root's retained own
Process handle; normal native root shutdown is NOT_CONFIRMED. Failed r01 Git
ancestor selection and r02 MSIX path alias refusal remain retained separately.
No provider/tool/solver request was made by these diagnostics. Old run02 cleanup
remains UNKNOWN_UNCONFIRMED.

Changing the original authentication marker would invalidate old contexts'
lifecycle checks. Copying credentials, changing the model or bypassing binary
pins was rejected. Instead, an explicit external execution capsule preserves the
original authentication marker, installed Node/launcher/runtime and data root.
It independently pins a copied unchanged official launcher, the reviewed build
and actual activation proofs, native package/EXE/map and the tracked patch.
The new research intent/context/owner pins that binding. Default contexts still
require their original complete runtime pin. No automatic runtime substitution
or authentication migration is provided. Partial setup is retained on failure.

Official credential baseline/disposal can revoke entries across the shared data
ledger. Qualified new context/start admission therefore requires an existing
strict empty array before startup; nonempty/malformed/missing rows refuse new
activation without mutation. This observation does not close old roots or prove
global absence. Lifecycle validation remains possible with the new runtime's own
registered rows. This is not general concurrent shared-auth scheduling or an
atomic filesystem snapshot; uncontrolled concurrent ledger writers remain an
open lifecycle limitation. Original owned session/source/command/process gates
and application permissions remain required.

Schema2 local settings explicitly add `qualified_runtime_binding_path` to the
unchanged original runtime/auth/project paths. Schema1/default behavior remains.
The separate NumericalReports profile admits exactly seven original-ID reads
for DOE/optimization/report/multiobjective and study/experiment inspection.
It does not admit campaign creation, solver/CAD execution or numerical candidate
generation. The approved model remains openai-codex/gpt-5.6-sol. Core verifies
records; OpenScience interprets the same records and proposes future research.
Assumed distributions, SYNTHETIC observations, invalid metrics, physical UNKNOWN
and NOT_RELEASED are retained. This is not completion of52 requirements/Phases.

Verification: binding drift/foreign shared-ledger admission controls, unchanged
auth/default runtime and native-hook read/write admission controls, common local
launcher regressions; actual approved-provider execution is recorded separately
from source controls and the auth-free r03 transport result. The exact611f1ec CI
failed two stale synthetic PDE fixtures; those fixtures now explicitly declare
`pde_model_declaration=True`, preserving PDE namespace expectations and the
original cancellation/engineering thresholds.
