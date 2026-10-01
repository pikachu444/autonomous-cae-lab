# ADR 0012 — Explicit research model and official ChatGPT authentication

Status: accepted for model selection, authentication and native provider source,
2026-10-01.
Authenticated inference and connected research transport acceptance remain OPEN.

## Decision

The owner objected to Root silently fixing Qwen3-4B as the research model while
the installed official OpenScience supports ChatGPT sign-in. Existing local
availability was not user selection or an upstream model recommendation.
Remove automatic Qwen selection from all new local configuration/launch paths.
Keep the historical explicitly selected Ollama transport and failed stores;
never fall back to another provider/model after authentication or execution fails.

Use pinned official OpenScience2.0.146 `keys signin` and its built-in
`openai-codex` authentication. The auth-only profile has no selected model, MCP
tools or inference. Keep credentials in a marked external LOCALAPPDATA profile,
outside the public repository. Reuse that exact `OPENSCIENCE_DATA_DIR` for
subsequent provider access; do not copy tokens from the user's Codex profile.
Human account login/consent is the only required user action. Root performs
configuration, version checks, execution and verification.

Login exit zero does not prove completion. This installed CLI returned zero
with `Sign-in wasn't completed` and no authentication file. The model command
also returned zero with `Provider not found` before authentication. Require an
updated owned authentication file and valid provider model metadata separately;
only actual completed inference can establish model access. Metadata is not
subscription entitlement or a research acceptance. Model choice remains explicit.

Expose a read-only MCP `caelab://runtime/source-identity` resource so Root can
inspect the actual connected MCP import paths and bounded Git/disk observations
without creating a store, running CAD or calling a model. Its disk hashes reuse
the existing Core/fixture semantics; they do not measure cached Python bytecode
or repair historical provenance. Git failures/timeouts stay UNKNOWN.

## Alternatives, limits and next gate

Silently retaining/replacing the tiny local model, copying global credentials,
using a paid API-key fallback or treating login/catalog/CI as research success
are rejected. No native OpenScience binary, model body, Core schema, numerical
threshold, fixture implementation or engineering verdict is changed.

The legacy controller's Ollama proxy cannot transport official Codex OAuth.
The native branch reuses owned boot/process/config/MCP/attach/abort/idle gates
with an external research config and the exact separately owned auth data dir.
Only native executable/runtime fields matching the independent auth pin may
launch; the immutable context hash binds store/model/environment/settings.
Inference config/plugin drift blocks research while exact owned cancellation,
idle and no-proxy cleanup remain available. Public `chat.params` and
`tool.execute.before` hooks can
check logical streams and actual tool calls. They do not inspect final offered
tool schemas or every SDK/Codex HTTP retry. Do not claim proxy-equivalent wire
receipts/source checks for OAuth; those remain UNKNOWN until separately proved.
Do not loosen ADR0011 research acceptance to turn auth-only work into PASS.

The third official login actually completed; the owner selected5.6 Sol. The CLI
model list is a public catalog/fixed OAuth support list, not account entitlements.
Official latest2.0.147 also lacks6.1 Sol in the filter; its account access remains
UNKNOWN. Native28/Node20/shared-auth19/launcher47 source checks and independent
review closed the bounded source unit. See the native provider source record.

Next: verify selected-model access and native loading, read the resource through OpenScience's actual
MCP connection, then run the unchanged valid/rejected CAD and interpretation
cases in a new clean-source store. P1.1 and Phases2–7 remain open.

## Verification and requirement impact

Actual clean5365ae8 research completed fourteen selected5.6 Sol stages and
thirteen real MCP calls, including valid/rejected CAD, results and interpretation.
The resident source resource,32 store files and20 artifacts were independently
verified. See20261001-openscience-native-research.json. Full P1.1 remains OPEN.

The same run retained sixteen source-check refusals followed by accepted checks.
Their initial cause is UNKNOWN. Pinned upstream retry.ts treats ordinary Error
text containing "unavailable" as provider overload, causing unintended retries
of a policy denial. Keep the fail-closed source check and detailed Error.code/
receipt code; use fixed non-transient thrown text. Add sanitized capture/compare
status, bounded monotonic elapsed_ms and fixed error classes to receipts, without
raw child output, exception messages, paths or environment. A failed initial
capture retains a rejected plugin.loaded receipt and returns no hooks; only an
accepted exact-process/boot receipt admits loading. Increasing timeout/retry
budgets or accepting a cached boot pin are rejected. Node25 and native28 source
checks pass; actual corrected-source research remains NOT_RUN. This adds no
research operation, numerical threshold, optimizer or engineering approval.

The initial08df MCP.environment seam failed in actual startup: upstream encrypts
those values in place, so strict config byte identity correctly blocked plugin
loading. Preserve that failure and retain the strict hash gate. Export the fixed
inert-config path from the tracked Git bridge through WSLENV/p to its host Git
child instead; avoid the mutable environment map. NOSYSTEM1/PROMPT0 and a missing
config125 exit are fixed in the pinned LF source. Microsoft documents the path
translation flag. This does not alter system/user Git settings or Core/adapter
behavior. See the wslenv-git-config record; fresh actual research remains required.

Actual native7f loading/MCP connection passed, but its zero-model resident
resource exposed Git128/UNKNOWN. Official subprocessSnapshot replaces global
Git config with os.devNull on Windows; that path fails in Windows Git launched
through WSL. Use the official MCP.environment last-merge seam to replace only
that child's config path with tracked/hash-bound inert source, preserving
NOSYSTEM1/PROMPT0. Changing user/global config, upgrading Git/OpenScience,
editing the pinned native binary or widening safe.directory is unnecessary.
The bridge bytes, Core/fixture implementations and numerical gates are preserved.
Four child probes/controller56/native28 and independent review pass; a fresh
actual resident resource and research run are still required. Preserve prior
UNKNOWN results. See the20261001-openscience-mcp-git-config record.

Auth adapter19 checks, legacy controller52/launcher47 mocks and resource8 tests
passed separately, with no inference/CAD/Core mutations. Actual stdio resource
execution created no store. The first resource test assumption about commit/
dirty availability failed and was corrected to retain independent UNKNOWN;
the timeout was not extended. See the ChatGPT connection preparation record.
Advances R03/R10–R13/R21/R25/R43/R51/R52; all52 requirements, OpenScience control
plane, numerical-engine optimization and UNKNOWN/NOT_RELEASED are preserved.
