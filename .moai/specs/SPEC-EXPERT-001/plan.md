# Implementation packet

The full product scope and current source are in CURRENT_STATE. Actual Pro writes
this feature after completing the current Post→Numerical slice. Codex integrates
shared contracts, checks Windows behavior and records status; Astra independently
reviews the meaningful source-to-discussion contract. No concurrent shared-file
writers and no new provider/model subscription.

1. Extend existing Expert controls with a compact Sources area: add file, choose
   library, preview, remove. Native dialogs and readable content replace raw JSON.
   Reuse the existing upload/knowledge.ingest JobManager path, showing progress
   and unsupported/extraction errors. Do not require a separately prepared index.
2. Connect selected sources to the existing discussion draft and exact source
   reader. Preserve composer edits, result attachments and access scope. Resolve
   exact revision behavior at round freeze and retrieval, not only in a UI label.
3. Keep Request round, interventions, citations and Plan/result return on existing
   commands. Provider availability is not entitlement: inspect current supported
   configuration without credentials, and keep unavailable behavior honest.
4. Supply relevant focused tests, usage docs and branch commits. Root checks
   compile/basic Qt operation and changed owner units. Broader provider/native
   campaigns wait until the connected features exist.

Design choice: include first file import in this slice. A library-only picker
would leave a new independent Expert user unable to attach their own research.
Keep library import separate from selecting it into a composer so Cancel has a
clear result. Short visible titles; revision/locator details on demand.

## Concrete integration seams

Source inspection at `a7977f9` confirms the following reuse points. These are
implementation constraints for this feature, not a new source service:

- `POST /api/workbench/upload` already accepts a bounded octet-stream and a
  percent-UTF-8 filename. Feed its registered input ID into the existing
  `knowledge.ingest` job; Workbench resolves the approved local path and title.
  Poll the job through the current client rather than ingesting on the GUI thread.
- `KnowledgeStore.source(document_id, revision, locator)` already reads archived
  revisions. `list` returns the latest revision and `search` currently indexes
  only the latest content. Pinning the chooser label alone does not pin retrieval.
- In `ExpertRuntime._ask`, initial selected snippets, `knowledge.search`,
  `knowledge.source`, delegated `experts.consult`, and reused history must honor
  the same selected source/revision scope. Current transmission checks restrict
  collections, but do not themselves restrict document IDs within a collection.
  A round with selected source A must not introduce unselected B from that same
  collection. Apply this rule to the existing OpenScience path as well.
- Keep legacy discussion drafts readable. Resolve old unpinned selections
  explicitly before a new round; do not silently rewrite previously saved turns.

Pro owns the source chooser, Expert view wiring, bounded discussion/runtime
extension and focused tests. Codex coordinates any shared contract change and
owns integration/status documentation. Post/Numerical files remain under the
current Post assignment until that feature is submitted.
