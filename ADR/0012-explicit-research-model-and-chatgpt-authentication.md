# ADR 0012 — Explicit research model and official ChatGPT authentication

Status: accepted for model selection and auth-only setup, 2026-10-01.
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

The current legacy controller's Ollama proxy cannot transport official Codex
OAuth. A future native OAuth branch must preserve owned boot/process/config/MCP/
attach/abort/idle gates. Public `chat.params` and `tool.execute.before` hooks can
check logical streams and actual tool calls. They do not inspect final offered
tool schemas or every SDK/Codex HTTP retry. Do not claim proxy-equivalent wire
receipts/source checks for OAuth; those remain UNKNOWN until separately proved.
Do not loosen ADR0011 research acceptance to turn auth-only work into PASS.

Next: complete actual login, verify available model/access, implement and review
the native provider transport, read the resource through OpenScience's actual
MCP connection, then run the unchanged valid/rejected CAD and interpretation
cases in a new clean-source store. P1.1 and Phases2–7 remain open.

## Verification and requirement impact

Auth adapter19 checks, legacy controller52/launcher47 mocks and resource8 tests
passed separately, with no inference/CAD/Core mutations. Actual stdio resource
execution created no store. The first resource test assumption about commit/
dirty availability failed and was corrected to retain independent UNKNOWN;
the timeout was not extended. See the ChatGPT connection preparation record.
Advances R03/R10–R13/R21/R25/R43/R51/R52; all52 requirements, OpenScience control
plane, numerical-engine optimization and UNKNOWN/NOT_RELEASED are preserved.
