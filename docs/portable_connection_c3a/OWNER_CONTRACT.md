# C3A owner / raw / receipt contract

## Identity and authority

Original identity is the exact Q identity: document_id, kind, store_id, session_id, generation, input_revision, input_sha256 and saved_revision. Capsule canonical SHA and Q file raw SHA are separate pins. Q, declared Q.assets and any existing discard marker are immutable under `portable/recovery/A…/`. Old Q is never installed under a new owner's `raw-recovery/`. Original owner/related-save receipt bytes remain AS_RECORDED; originals are never executed, acknowledged, discarded or reconciled by reading.

Current editable document/revision identities are created by the existing Portable owner adapters. A separate `portable/recovery-maps/H….json` contains the existing TypedProjection mapping, bounded by the existing MAX_HOPS=32. The chain must end at the manifest's actual current owner/project. Only typed draft/reference paths are projected. Raw strings, arbitrary text, source files and original execution input/result are not string-replaced.

Original recover/discard permission is always NOT_GRANTED. New current UPDATE/Keep/save/recovery commands belong to the current session and owner. Historical `_save_command`/`_mutation_command` markers are removed from the editable copy and preserved only as HISTORY_ONLY; immutable originals remain unchanged. Data current save retains original-import proof through a small existing-owner hook. No old JobManager submission or CAPTURE/publication capability is installed.

## Verification ownership

`portable_recovery_archive.inspect_capsule` uses the actual DataDocuments / MaterialDocuments / NumericalDocuments class fingerprint plus existing `related_save_recovery_assets.verify_snapshot/verify_assets`. It constructs no owner/store. For Data it delegates to the actual `data_recovery_inputs.inspect_capsule`, and preview/table reads use the actual Data C3 source APIs. Material/Plan get the missing immutable archive reader, not a fake folder-backed owner.

Q canonical/raw hashes, safe names, original saved manifests, original owner fingerprints, declared files and sizes, source/registration/calibration closure, job/result pins and receipt identity are checked before publication and on archive reads. Unknown document/raw fields remain unchanged and do not grant authority. Nonretained legacy acknowledged state is never synthesized from current working data. Running/unpublished jobs are returned AS_RECORDED and their unavailable result read is refused.

A copied Data import requires original input/job and result proof for current Keep: original Data result diagnostics identify the original submitted source, not the new navigation owner. `portable_data_execution` proves exact typed relocation and gives existing `verify_import_sources` the original run. It does not relax that validator, rewrite a result hash or run import again. Proof assets are retained with the current Data saved revision; repeated copies replay the original proof. Legacy C2 imports lacking the original proof fail this new capability explicitly.

## Current buffer resume

`buffer_token(raw)` uses the existing bounded raw JSON copier and hashes the entire noncommitting raw snapshot with its editor_revision. The API sends this small token, not a raw upload; it does not infer the current widget or collect a path found in raw text.

Preview re-reads the original archive/projection and actual current owner under the owner lock. It binds exact recovery identity, the full acknowledged current document hash, archive raw/canonical pins, projected draft/raw hashes and current buffer token. `command_id` is derived from that exact review. Preview does not mutate the owner.

Resume requires approved=True and overwrite_approved=True, same live buffer token, exact current session/store/CAS and the original unchanged preview. It calls the actual owner UPDATE for the projected acknowledged draft only. Raw/local_draft remain unapplied. Existing owner command persistence handles response-loss retry with the same command; a changed review cannot reuse it. A newer owner after the recorded command is not replaced by a late raw reply.

`BUFFER_READY` carries current document/identity, raw, original provenance, current command and original permissions NOT_GRANTED; raw_applied/saved_revision_created/job_submitted are false. GUI rechecks current view/base/token, renders the returned acknowledged document and invokes the existing Data/Material/Plan raw restore. The GUI wrapper refuses a dirty target instead of auto-Keeping or discarding it. Other actual Plan widgets are not substituted or rewritten.

A server response can be lost after its legitimate current UPDATE. Retry must use the same pending command, not create a new one. On unrecoverable transport/CAS error the original archive and current input remain available, and the GUI reports the error instead of claiming restoration. Existing current-owner Keep/save/close gates own subsequent persistence. A new Keep must match the final current saved base.

## GUI and root ownership

New dedicated: connection_window_recovery, portable_recovery_dialog, portable_recovery_host. Existing generic recovery host `_Review`, RawEditorFocusGuard and actual owner restore methods are consumed, not replaced. User labels use task terms/titles/time/status, not IDs/hash/schema menus. Error diagnostics retain the precise underlying refusal; engineering field/unit/path details are visible when inspecting original content.

Root-only patch: Workbench/Client/routes, two original-execution checks in related_save_recovery_assets, Data `_retain_inputs`, two menu install hooks. Existing connection window has only dedicated selection/review changes. Sol owns GUI integration refinement; Astra independent review and root Windows verification are NOT_RUN here. Product is local Qt; using the existing loopback Client for transport does not replace the product screen with a web UI.
