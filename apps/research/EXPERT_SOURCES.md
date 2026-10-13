# Research sources in Expert

This change extends the existing discussion, KnowledgeStore, JobManager and native Qt Expert window. It adds no provider, index service or research owner.

## Source contract

New requests carry `context.selected_sources = [{document_id, revision}]`. The existing `selected_document_ids` remains readable and can mirror those identities. A nonempty legacy ID-only selection must be explicitly reviewed and pinned before a new round. Saved drafts/turns are not silently upgraded.

A frozen round preserves its exact pins. Before new dispatch, the existing source reader checks the revision and current workspace access. An old pending round that cannot be resolved becomes `BLOCKED_SOURCES`, retaining its draft, jobs and turns; a new explicit Ask can use the repaired current draft. Recovery first looks for the already-submitted matching job and does not submit another.

Expert source tools always use the selected set, including an empty set. An omitted tool revision resolves to its selected pin, never latest. Search builds a bounded temporary view of those archived revisions using the existing Haystack BM25 implementation; ordinary library search remains latest-version browsing. Requested filters narrow the pins. No second persistent index/store is created.

Prior runtime history uses the full read-source ledger. Discussion history uses the originating round's frozen source set, conservatively retaining only permitted turns in provider context. Legacy turns without known source provenance remain visible locally but are omitted from new inference context. A nested consultation cannot receive a source unavailable to its role; a narrower recipient is rejected because the generated consultation question could itself quote parent evidence.

Selecting/importing a source grants no model transmission. External transmission additionally requires the existing workspace/provider policy and a deliberate request grant for the exact `transmission_scope.source_refs` plus collections. Revocation is checked at source reads and again before inference. Content already sent to a running provider cannot be retracted by a later local revocation. OpenScience uses the same scoped tool closures and checks; no API-key fallback is added.

## Checkpoint status

The backend source/pinned retrieval and binary upload client are authored first. Native Add file/library selection/preview and focused Qt tests are being connected in the same branch; this checkpoint alone is not completion of the Expert user flow.

Pro remote execution: **NOT_RUN** (executor disconnected). Tests use actual existing archive/BM25/JobManager code with explicitly labelled scripted generators or a fake OpenScience host. No provider, solver, device or paid service was invoked.

Focused backend check:

```powershell
python -m pytest tests/test_expert_sources.py -q
```

Full Expert/Co-STORM behavior, real authorized inference and native OS/DPI acceptance remain outside these focused checks.
