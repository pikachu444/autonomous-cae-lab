# Research sources in Expert

This change extends the existing discussion, KnowledgeStore, JobManager and native Qt Expert window. It adds no provider, index service or research owner.

## Use the independent Expert window

```powershell
.\Start-CAE-Lab.cmd -Tool expert
# Or reopen one saved discussion:
.\Start-CAE-Lab.cmd -Tool expert -DocumentId X...
```

1. Enter the question and select the existing registered roles. Open **Sources → Add file…** for PDF, Markdown (.md), UTF-8 text or CSV. The native chooser accepts a nonempty file up to 16 MiB. Select its library collection.
2. The existing upload endpoint registers its bytes; the existing **knowledge.ingest** job extracts text. Read the actual archived text by page/section. Failed pages and empty/scanned PDFs stay explicit; OCR is not performed and extracted formulas/tables/figures are not independently verified.
3. **Library…** also lists already accessible sources. Check the sources to attach. An existing older revision stays selected; **Current library version** is an explicit change, and **Saved selection** restores the earlier choice before confirmation.
4. **Attach selected sources** changes only the latest local question's source selection. The question, roles, result attachments and other edits remain. **Cancel** does not change that composer. A completed library import remains in the library. **Resume import** retries the same submission identity after an unconfirmed submission/result read; a terminal failed import stays failed.
5. **Read source** opens its pinned text. **Details…** shows exact revision and segment locator when needed. **Remove**, **Apply edits**, Undo/Redo, Save and reopen use the existing discussion owner.
6. A separate **Request scope → Transmit selected sources** control grants only the revisions selected at that click, within existing workspace/provider policy. Import/attachment never enables transmission. A newly added source needs its own explicit grant before external inference.
7. **Add intervention** remains a local authored turn. With the model unconfigured, all source/question/history/save work remains available. **Request round** is explicit and uses existing model/permission/budget rules; importing a source creates no AI answer or Plan.
8. Select an actual returned turn to inspect its citations or an actual PLANNED proposal. Source citations open their exact archived segment in the readable Sources view. Existing Numerical Plan and result-return actions remain unchanged.

Unknown old ID-only selections are labelled for review; open Library, inspect and explicitly choose a version before a new round. A missing/revoked source is not replaced with latest or another file. Deselect it or repair the accessible library selection explicitly.

## Source contract

New requests carry `context.selected_sources = [{document_id, revision}]`. The existing `selected_document_ids` remains readable and can mirror those identities. A nonempty legacy ID-only selection must be explicitly reviewed and pinned before a new round. Saved drafts/turns are not silently upgraded.

A frozen round preserves its exact pins. Before new dispatch, the existing source reader checks the revision and current workspace access. An old pending round that cannot be resolved becomes `BLOCKED_SOURCES`, retaining its draft, jobs and turns; a new explicit Ask can use the repaired current draft. Recovery first looks for the already-submitted matching job and does not submit another.

Expert source tools always use the selected set, including an empty set. An omitted tool revision resolves to its selected pin, never latest. Search builds a bounded temporary view of those archived revisions using the existing Haystack BM25 implementation; ordinary library search remains latest-version browsing. Requested filters narrow the pins. No second persistent index/store is created.

Prior runtime history uses the full read-source ledger. Discussion history uses the originating round's frozen source set, conservatively retaining only permitted turns in provider context. Legacy turns without known source provenance remain visible locally but are omitted from new inference context. A nested consultation cannot receive a source unavailable to its role; a narrower recipient is rejected because the generated consultation question could itself quote parent evidence.

Selecting/importing a source grants no model transmission. External transmission additionally requires the existing workspace/provider policy and a deliberate request grant for the exact `transmission_scope.source_refs` plus collections. Revocation is checked at source reads and again before inference. Content already sent to a running provider cannot be retracted by a later local revocation. OpenScience uses the same scoped tool closures and checks; no API-key fallback is added.

## Authorship, checks and limits

The backend checkpoint is **7090d1c**. The following Qt checkpoint adds file/library selection, actual text preview, removal, explicit permission and source-citation display. Independent source review identified a legacy-history edge: old running rounds had previously been able to search without selected IDs. Their harvested provenance must remain unknown. The correction stamps new rounds' validated scope outside their unchanged frozen draft and keeps old missing scope unknown; old displayed turns and input hashes are preserved.

Pro remote Python/Qt execution: **NOT_RUN** (executor disconnected). The tests are authored for Codex's focused Windows run:

```powershell
python -m pytest tests/test_expert_sources.py tests/test_expert_sources_ui.py -q
```

The Qt tests use the actual loopback HTTP service, binary upload client (including expired-token refresh and Unicode filenames), existing JobManager/KnowledgeStore and discussion owner. They exercise the native file chooser with a selected-path test double, preview/Cancel/Attach, unchanged question, removal/Undo/Redo, local intervention, ordinary Save/reopen, older revision selection and blank-PDF diagnostics. No provider is required.

Retrieval tests use actual archive/BM25 code and explicitly labelled scripted generators or a fake OpenScience host. They check updated/revoked sources, unselected documents in the same collection, both history paths, narrower consultation scope, explicit transmission and legacy-round repair. A mocked host is not evidence of actual provider readiness.

Whole Expert/Co-STORM completion, real authorized inference, PDF visual fidelity and native OS/DPI acceptance remain unverified. No provider, solver, physical device or paid service was invoked by the author. Existing proposals/result-return remain supported paths, not newly fabricated outcomes.
