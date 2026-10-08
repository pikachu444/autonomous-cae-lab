"""Temporary local API smoke check for the design-review file store."""
import importlib.util
import json
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

module_path = Path(__file__).resolve().parent.parent / "server.py"
spec = importlib.util.spec_from_file_location("design_lab_server", module_path)
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


def request(base, path, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
    service = server_module.LabServer(("127.0.0.1", 0), Path(directory))
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    status, created = request(base, "/api/docs", "POST", {"kind": "pre", "title": "시험", "data": {"points": [[0, 1]], "views": {}}})
    assert status == 201 and created["revision"] == 1
    doc_id = created["id"]
    status, saved = request(base, f"/api/docs/{doc_id}", "PUT", {"expectedRevision": 1, "title": "시험", "data": {"points": [[0, 2]], "views": {}}})
    assert status == 200 and saved["revision"] == 2
    status, conflict = request(base, f"/api/docs/{doc_id}", "PUT", {"expectedRevision": 1, "title": "충돌", "data": {"points": []}})
    assert status == 409 and conflict["current"]["revision"] == 2
    status, prior = request(base, f"/api/docs/{doc_id}?revision=1")
    assert status == 200 and prior["data"]["points"] == [[0, 1]]
    status, current = request(base, f"/api/docs/{doc_id}")
    assert status == 200 and current["data"]["points"] == [[0, 2]]
    assert prior["semanticHash"] != current["semanticHash"]
    status, changed_view = request(base, f"/api/docs/{doc_id}", "PUT", {"expectedRevision": 2, "title": "시험", "data": {"points": [[0, 2]], "views": {"selection": "point:0"}}})
    assert status == 200 and changed_view["semanticHash"] == current["semanticHash"]
    status, _ = request(base, "/api/docs/not-a-document-id")
    assert status == 404
    status, _ = request(base, "/api/docs/%2e%2e%2foutside")
    assert status == 404
    status, _ = request(base, "/api/docs", "POST", {"kind": "../../escape", "title": "잘못된 종류", "data": {}})
    assert status == 400
    status, _ = request(base, f"/api/docs/{doc_id}?revision=0")
    assert status == 400
    service.shutdown()
    thread.join(timeout=5)
    service.server_close()
print("Design Lab API: save, 409, historical revision, presentation-only hash and invalid ID/path passed")
