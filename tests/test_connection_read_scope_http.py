"""Existing immutable read scope must live in the actual HTTP handler thread."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import threading
import time

import pytest

from caelab import material_document
from caelab.storage import revision_read_cache
from caelab.workbench_client import WorkbenchHTTPError
from examples.portable_connection_public import create_public_store
from test_portable_connection_c1_http import serving


def test_actual_http_scope_rechecks_next_request_and_preserves_late_owner_gate(tmp_path, monkeypatch):
    wb, docs = create_public_store(tmp_path / 'HTTP scope source')
    wb.shutdown()
    calls = []
    original_load = material_document.load_json
    main_thread = threading.get_ident()

    def tracked_load(path):
        path = Path(path)
        if path.name == 'revision.json' and 'documents' in path.parts:
            calls.append((str(path), threading.get_ident(), revision_read_cache() is not None))
        return original_load(path)

    monkeypatch.setattr(material_document, 'load_json', tracked_load)
    with serving(wb.workspace) as (server, client):
        planid, materialid = docs['plan']['id'], docs['material']['id']
        before_jobs = server.workbench.manager.list()
        assert revision_read_cache() is None
        started = time.monotonic()
        listing = client.connection_catalog(planid)
        print(f'Actual HTTP scoped catalog {time.monotonic()-started:.3f}s', flush=True)
        assert listing['sources'] and not listing['issues']
        assert calls and all(tid != main_thread and scoped for _, tid, scoped in calls)
        assert max(Counter(path for path, _, _ in calls).values()) == 1
        assert revision_read_cache() is None

        # A new HTTP request must not trust the previous verified revision.
        saved = server.workbench.material_documents._folder(materialid) / 'revisions' / docs['material']['saved_revision'] / 'document.json'
        raw = saved.read_bytes()
        try:
            saved.write_bytes(raw + b'\n')
            calls.clear()
            changed = client.connection_catalog(planid)
            assert any(row['document_id'] == materialid for row in changed['issues'])
            assert not any(row['selection']['document_id'] == materialid for row in changed['sources'])
            assert calls and all(tid != main_thread and scoped for _, tid, scoped in calls)
        finally:
            saved.write_bytes(raw)

        # Restoring the exact bytes admits a fresh read, not an old cached issue.
        listing = client.connection_catalog(planid)
        assert not listing['issues']
        proposal = client.connection_preview(listing['target'], 'material', 'unlink', None)
        current = client.document_read(planid)
        draft = deepcopy(current['draft']); draft['seed'] += 1
        client.document_command(planid, 'numerical.update', {'draft': draft},
            session_id=current['session_id'], expected_generation=current['generation'], command_id='ClateScopeEdit')
        calls.clear()
        with pytest.raises(WorkbenchHTTPError):
            client.connection_apply(proposal, confirmed=True, command_id='ClateScopeMustReject')
        assert all(not scoped for _, _, scoped in calls)
        assert client.document_read(planid)['draft'] == draft
        assert draft['material']['document_id'] == materialid
        assert server.workbench.manager.list() == before_jobs
        assert server.workbench._assistance is None and revision_read_cache() is None
