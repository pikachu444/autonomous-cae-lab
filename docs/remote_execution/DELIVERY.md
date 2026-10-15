# B8.4 remote execution delivery

2026-10-16, Sol implementation. The preserved 2026-10-15 three-module checkpoint
was continued; it was not discarded or relabelled as a recovered Pro implementation.
Root integrated only the Workbench, HTTP route and Runner menu hunks. No new
scheduler service, document owner, SSH credential manager or solver was created.

Implemented: registered SSH/Slurm/OpenPBS preparation/submission/query/cancel,
durable original input and scheduler token, exact retry/cold reconnect,
explicit post-termination collection, existing typed exchange admission,
ExternalFilesAdapter worker, native input/Post registration, Korean Runner dialog,
and GUI pending-request recovery across process/service port restart.

`_workspace/delivery-remote-b84/` holds the initial checkpoint bytes, root-only
integration.patch, test XML, native process receipts, actual normal/narrow QWindows
captures, cold GUI receipt and final source manifest. Failures during development
are retained: the first workflow fixture used a declaration field rejected by the
existing variable contract; an initial worker assertion compared NumPy arrays
with scalar equality; the first new Runner-open check called `job()` instead of
the existing Client.status API. None was relabelled as a successful run.

Independent review raised two implementation gaps, corrected together: GUI
pending requests previously lived only in memory, and local cancellation of a
query/collection could send remote cancel. Pending requests now use existing
desktop QSettings before transmission and restore the original arguments/ID;
reconnect/collect cancellation preserves remote facts and never issues cancel.
First definite pre-admission rejection returns to editable inputs. Uncertain
requests only reuse their original identity or find the exact existing job.

Verification uses real JobManager/storage/local HTTP/QWindows and controlled remote
command receipts. Two tiny public local file-writing processes exercise the
existing external adapter; they are not an engineering solver or remote host.
Checks cover lost replies, cold service/GUI resume, request identity, typed values,
missing/failed/duplicate/stale rows, units, forbidden array/path references,
atomic submit/cancel claims, scheduler accounting, local-only observation cancel,
raw-file/first-Post preservation, Runner candidate/response display and normal/
narrow windows. Test-created processes and windows use native_check/finally and
do not close user sessions. Exact final counts and receipts are in FINAL_MANIFEST.

**NOT_RUN:** no live SSH login, Slurm/OpenPBS controller, POSIX supervisor/native
cleanup acceptance, real user runtime/output or physical numerical validation.
No approved remote host/account was supplied. No credentials or SSH configuration
were read, copied or modified; no host was contacted, key created, installation,
paid API/provider call or solver campaign performed. A deployed runtime must
remain foreground and cooperate with owned cancellation. Memory enforcement for
SSH is not claimed. Native Post registration/navigation is tested with public
controlled VTU bytes; a real remote result in ParaView is not claimed.

The local product workflow and controlled boundary checks are distinct from
actual remote and engineering acceptance. Root owns CURRENT_STATE, review record,
staging, commits and publication. See [usage](USAGE_KO.md) and [contract](CONTRACT.md).
