# C3A exact API / late-reply contract

All APIs reuse the existing Workbench and Client. The existing `/api/workbench/portable-project/` POST namespace has strict fields. General request cap remains 128 KiB; create retains its existing 8 MiB special cap. The Data raw object is bounded by its existing 512 KiB contract. No extra upload endpoint, owner or dispatcher is introduced.

| Workbench / Client method | Request fields | Outcome |
|---|---|---|
| portable_recovery_catalog | document_ids: list of current IDs | Actual kept Qs plus already carried originals; unkept_buffers_included=false. Invalid entries are unselectable, not silently repaired. |
| portable_inspect | selections; draft_policy='acknowledged'; optional recovery_archives | Existing inspection plus explicit archive inventory and source pins. No save/Keep/apply/compute. |
| portable_create | inspection, destination, approved, command_id, session_id | Existing staged copy, last manifest publication and exact retry behavior. |
| portable_recovery_read | archive_id; facet='layers'; selection=None | Original validated archive facets; no owner mutation or original approval. HTTP requires all three keys. |
| portable_recovery_preview | archive_id, target_identity, buffer | Exact current-owner replacement review and deterministic command_id. |
| portable_recovery_resume | preview, approved, overwrite_approved, live_buffer, command_id | BUFFER_READY after existing current owner UPDATE only. |

Archive selections have exactly one of two shapes: `{document_id, capsule_id}` for a kept Q in the selected actual current owner, or `{archive_id}` for a carried original whose current owner is selected. IDs in these contracts are machine identities, not the user menu labels. Path/session/permission overrides and mixed shapes are rejected.

Read facets:

- `layers`, empty selection: original complete Q plus current navigation ID, original identity/state/verification and immutable permissions. Raw/local_draft/focus/selection and full acknowledged document/Undo/Redo/receipt records are available.
- `saved`, empty selection for original base, or exactly `{document_id, saved_revision}` for an explicitly retained original saved source.
- `job`, `{job_id}` and optional boolean `include_result`: original job/state/error and, only when PUBLISHED, existing verified result with axes/components/units/values. NOT_PUBLISHED is not turned into a success.
- Data only: `source-preview` with `{data_id}`; `table-source` with optional `{draft_path}`. They delegate to existing Data C3 APIs and do not register or apply a source. No arbitrary filesystem path input is accepted.

Current target identity is obtained through the existing `recovery.identity` operation, never reconstructed from original Q. `buffer_token` takes the actual noncommitting raw snapshot and returns `{editor_revision, raw_sha256}`. Preview and resume verify current full document/CAS and original projection independently. GUI transport must verify its live token before request and before applying response; stale views must not render returned raw. A failed request keeps the exact preview/command for retry only while current target/buffer are still equal. No automatic command regeneration.

Python example (using an existing actual Workbench `wb` and a real owner raw snapshot):

```python
from caelab.portable_recovery_resume import buffer_token
from caelab.related_save_recovery import RawRecoveryDrafts

records = wb.portable_recovery_catalog([current_document_id])
row = next(r for r in records['archives'] if r['source'] == 'CARRIED_ORIGINAL')
archive_id = row['selection']['archive_id']
original = wb.portable_recovery_read(archive_id)
current = wb.document_read(current_document_id)
identity = RawRecoveryDrafts(wb.root, wb._document_owner).identity(current)
token = buffer_token(actual_noncommitting_raw_snapshot)
review = wb.portable_recovery_preview(archive_id, target_identity=identity, buffer=token)
# Only after the user reviews this target and explicitly approves replacement:
packet = wb.portable_recovery_resume(review, approved=True, overwrite_approved=True,
    live_buffer=token, command_id=review['command_id'])
# Actual existing editor restore consumes packet['raw']; do not parse/apply it here.
```

CLI module `python -m caelab.portable_recovery_commands` calls the same existing Client. Actions catalog/read/inspect/create/preview/resume take `--service`, `--request` JSON file, optional exclusive `--output`. Create/resume require `--approved`; resume also `--overwrite-approved`. Request files require the exact fields listed by module help/implementation (including explicit default fields for inspect/read). It starts no service and no owner.

No new optional MCP action was added. Existing MCP/tool surfaces remain unchanged. Python/Client/HTTP/CLI parity is tested for the C3A endpoints; Qt parity is supplied as tests but NOT_RUN in this environment. Full C3 acceptance 12 for all owners and optional surfaces is not claimed.
