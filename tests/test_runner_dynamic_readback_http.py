"""Real HTTP preparation over a retained controlled process failure; no native solve."""
from copy import deepcopy

import pytest

from apps.lab.service import LabService
from caelab.workbench_client import Client, WorkbenchHTTPError
from test_dynamic_r2_recovery import managed
from test_lab_server import running


def test_http_prepares_exact_source_without_submitting_and_rejects_extra_fields(monkeypatch, tmp_path):
    wb, source, calls = managed(monkeypatch, tmp_path, failed=True)
    workspace = wb.workspace
    original = deepcopy(wb.manager.status(source["id"]))
    wb.shutdown()
    with running(LabService(workspace)) as transport:
        client = Client(f"http://127.0.0.1:{transport.server.server_port}")
        manager = transport.server.workbench.manager
        before = manager.list()
        arguments = client.dynamic_reprocess_request(source["id"])
        assert set(arguments) == {"source_job_id", "source_record"}
        assert arguments["source_job_id"] == source["id"]
        assert arguments["source_record"]["relative"] == "contact_execution.json"
        assert client.dynamic_reprocess_request(source["id"]) == arguments
        assert manager.list() == before
        assert manager.status(source["id"]) == original
        with pytest.raises(WorkbenchHTTPError) as error:
            client.request("/api/workbench/dynamic-reprocess-request", {
                "source_job_id": source["id"], "output": "UNTRUSTED_OUTPUT"})
        assert error.value.code == 400
        assert manager.list() == before
        assert len(calls) == 1  # Only the controlled initial process, never a readback solve.
