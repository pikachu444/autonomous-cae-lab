# Expert connection

This is setup for the independent native Expert window. It uses the existing
local service, discussion documents, source archive, bounded rounds and
Numerical/Study return actions. It creates no model answer during setup.

## First connection

1. Open Expert directly: Start-CAE-Lab.cmd -Tool expert. You can already write
   a question, import/read local sources and save a discussion without a model.
2. Choose **Connection…**. Select the existing owned OpenScience profile and
   its installed pinned runtime. **Browse…** selects existing directories;
   nothing is downloaded, installed or signed in by this dialog.
3. Choose the configured model hint or enter its exact openai-codex/model name.
   The model remains **UNVERIFIED** until an actual authorized request succeeds.
   The dialog does not treat a catalog entry, login file or developer Pro
   subscription as product inference entitlement.
4. If there are no roles, choose **Use example roles** or **Choose roles…**.
   These load the existing editable role-definition format. The role table
   permits an explicit model override on the same subscription route.
5. In **Transmission**, explicitly allow question transmission if desired.
   Sources require individually allowed collections and the discussion's exact
   selected revision grants; results require both operator permission and the
   discussion's exact attachment grant. None is enabled automatically.
6. **Apply connection** saves the local operator settings and applies them to
   this same service when its current jobs/requests finish. Leave the dialog
   open for a deferred apply, or reopen and retry later. It never stops jobs.
   Cancel before Apply changes neither configuration nor discussion.
7. Back in the discussion, select the roles and explicitly enable the desired
   per-question scope. **Request round** is still the action that invokes a
   bounded model round. Setup does not request a test answer.

**Check local setup** verifies profile ownership, provider policy, executable
pin and the existing PowerShell 7 host path. Python package import readiness,
local file verification, authentication, model entitlement and inference are
separate rows. Missing authentication/entitlement remains UNVERIFIED; an
unavailable runtime is not replaced by a paid API or another provider.

The existing supported route uses OpenScience 2.0.146 and openai-codex.
No API key field, API fallback, account change or subscription purchase is added.
The profile's credential store is not read by setup. Its auth-only configuration
and binary pin retain the existing host's checks.

## What Apply changes

The local native dialog edits the existing operator JSON file using a hash
check and atomic replacement. The usual Windows path is
%LOCALAPPDATA%/AutonomousCAELab/workbench-config.json. For a service started
with another explicit config, select that same file via **Status → Choose
service config…**. A path returned by HTTP is not used blindly as a write target.

Only the Expert runtime and inline role definitions are changed. Other operator
settings are preserved. The replacement ExpertRuntime reuses the existing
KnowledgeStore, literature store, callbacks and saved sessions. All document
owners, the Workbench session, unsaved Qt question buffers and existing jobs
remain. Role availability is refreshed without reopening the discussion. If a legacy
roles file is missing, Connection still lets you explicitly choose replacement
roles. Initial activation builds the replacement without trying to open that
missing old file. A rejected configuration-file choice disables Apply until
the actual service file has been read successfully again.

A service-side reload request accepts only the hash of the already saved,
CLI-bound local file. It accepts no runtime, model, policy, executable or path.
Model/HTTP callers cannot write or redirect that file through this endpoint.
Changing other operator keys requires an explicit ordinary restart; this dialog
does not force-stop a service. Unknown prior process cleanup also blocks reload.

Reload and final job admission share a short lock. Direct assistance calls
increment/decrement an active count but run outside that lock so scoped tools
can submit work on another thread. A cleanup-unknown exception blocks subsequent
reload. Active queued/running jobs are deferred, not cancelled.

The launcher still checks process/listener/store/source/dependency ownership.
After a hot apply it can reconcile only the config hash, requiring the same
service session and the exact in-memory applied file hash on every reuse.
This also rejects restoring an older file on disk without applying it, even
when that older file matches the launch receipt. A file merely saved on disk
does not satisfy that check. First launch binds the operator file path
even when it is initially absent.

## Native Windows host

The existing bounded OpenScience host now invokes an installed PowerShell 7
directly on Windows. It does not run wslpath there. The existing WSL route keeps
its path conversion. Neither path installs a shell or invokes a provider during
setup. The existing pinned executable, ephemeral MCP tool allowlist, bounded
steps, source permissions and cancellation checks remain in the host.

Role-specific OpenScience model choices are now used by both the original call
and bounded correction call. Nested consultations select the target role's
model while retaining the common operator transmission policy and budgets.

## Focused verification and limits

Commands for the existing runtime:

~~~powershell
python -m pytest tests/test_expert_connection.py tests/test_expert_connection_ui.py -q
python -m pytest tests/test_server_config_encoding.py -q
python -m pytest tests/test_windows_desktop_launcher.py -k "applied_expert_config or reuse_checks_loaded_config or conflicting_owned_service" -q
python -m pytest tests/test_workbench_assist.py -k "openscience_step_reservation or openscience_host_cancellation or openscience_host_uses_utf8" -q
~~~

Tests use public pinned-file doubles, actual shared owners/HTTP/Qt where stated,
and stdlib launcher doubles. They do not execute a provider or read credentials.
They cover Cancel/Apply/reopen, local-write conflicts, unrelated-setting
preservation, pending work, question-buffer preservation, explicit permissions
and role/model selection. Existing Plan/Study workflows are reused.

Pro remote compilation, pytest, Qt, Windows PowerShell and live inference:
**NOT_RUN** (executor disconnected). Root's later Windows checks must be
recorded separately. This feature does not claim full Co-STORM acceptance,
model entitlement, an actual AI answer, or engineering approval.
