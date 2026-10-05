"""Research handoff shares the existing writer, store and HTTP gates."""

from http.client import HTTPConnection
import json
import threading

import pytest

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService, ServiceError


class Bridge:
    def __init__(self, terminal="COMPLETED", wait=False):
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.terminal = terminal
        self.wait = wait

    def status(self):
        return {"configured": True, "available": True, "state": "READY",
                "model": "openai-codex/gpt-5.6-sol", "profile": "test-scope"}

    def run(self, question, session_id=None, *, cancellation_requested=lambda: False):
        self.calls.append((question, session_id))
        self.started.set()
        while self.wait and not self.release.wait(.01):
            if cancellation_requested():
                # Test double returns only after its controlled cleanup point.
                return {"kind": "openscience_research", "status": "CANCELLED",
                        "answer": "취소 전 받은 실제 부분 응답", "decision": "NOT_RELEASED"}
        return {"kind": "openscience_research", "status": self.terminal,
                "answer": "UNKNOWN이며 강도 승인은 할 수 없습니다.", "decision": "NOT_RELEASED",
                "tools": [{"tool": "analysis", "status": "error"}]}


def service(tmp_path, bridge=None, library=False):
    libraries = None
    if library:
        (tmp_path / "old").mkdir()
        libraries = {"old": tmp_path / "old"}
    return LabService(tmp_path / "new", libraries=libraries, research=bridge)


def finish(lab, job):
    lab._job_threads[job["id"]].join(2)
    assert not lab._job_threads[job["id"]].is_alive()
    return lab.job(job["id"])


def test_disabled_bridge_has_no_false_available_operation(tmp_path):
    lab = service(tmp_path)
    assert lab.research_status()["available"] is False
    with pytest.raises(ServiceError) as exc:
        lab.submit("research_run", {"question": "연구해 주세요"})
    assert exc.value.status == 503


def test_recovery_status_never_calls_official_bridge(tmp_path):
    from apps.lab.job_journal import HTTPJobJournal
    store = tmp_path / "recovery"
    journal = HTTPJobJournal(store)
    (journal.root / "claim.json").write_text('{"kind":"FOREIGN"}')
    bridge = Bridge()
    bridge.status = lambda: (_ for _ in ()).throw(AssertionError("No status facade during recovery"))
    lab = LabService(store, research=bridge, http_journal=HTTPJobJournal(store))
    assert lab.research_status()["state"] == "RECOVERY_REQUIRED"
    with pytest.raises(ServiceError):
        lab.submit("research_run", {"question": "must not execute"})
    assert bridge.calls == []


def test_http_journal_keeps_existing_mock_bridge_arguments_and_result(tmp_path):
    from apps.lab.job_journal import HTTPJobJournal
    store = tmp_path / "mock"
    bridge = Bridge()
    lab = LabService(store, research=bridge, http_journal=HTTPJobJournal(store))
    question = "승인된 모델로 기존 질문 그대로"
    job = lab.submit("research_run", {"question": question})
    terminal = finish(lab, job)
    assert terminal["status"] == "COMPLETED" and bridge.calls == [(question, None)]
    assert terminal["result"]["decision"] == "NOT_RELEASED"
    restored = LabService(store, http_journal=HTTPJobJournal(store))
    assert restored.job(job["id"])["result"] == terminal["result"]


@pytest.mark.parametrize("arguments", [
    {"question": " "}, {"question": True}, {"question": "가" * 5462},
    {"question": "hello\0"}, {"question": "hello", "owner": "foreign"},
    {"question": "hello", "session_id": "ses_foreign/path"},
    {"question": "hello", "cancellation_requested": True},
    {"question": "hello", "evidence_prepared": "client callback"},
])
def test_invalid_request_never_enters_official_bridge(tmp_path, arguments):
    bridge = Bridge()
    lab = service(tmp_path, bridge)
    with pytest.raises(ServiceError) as exc:
        lab.submit("research_run", arguments)
    assert exc.value.status == 400 and not bridge.calls


def test_question_is_exact_and_failed_numerics_do_not_erase_answer(tmp_path):
    bridge = Bridge("FAILED")
    lab = service(tmp_path, bridge)
    question = '  조건을 바꿔 비교해 줘.\n"한글" $() --model other  '
    job = lab.submit("research_run", {"question": question, "session_id": "ses_known123"})
    result = finish(lab, job)
    assert bridge.calls == [(question, "ses_known123")]
    assert result["status"] == "FAILED"
    assert result["result"]["answer"].startswith("UNKNOWN")
    assert result["result"]["tools"][0]["status"] == "error"
    assert result["result"]["decision"] == "NOT_RELEASED"


def test_library_and_busy_share_the_existing_gate(tmp_path):
    bridge = Bridge(wait=True)
    lab = service(tmp_path, bridge, library=True)
    lab.select_store("old")
    assert lab.research_status()["available"] is False
    with pytest.raises(ServiceError) as exc:
        lab.submit("research_run", {"question": "read only"})
    assert exc.value.status == 403 and not bridge.calls
    lab.select_store("local")
    job = lab.submit("research_run", {"question": "original"})
    assert bridge.started.wait(1)
    for action in (lambda: lab.select_store("old"),
                   lambda: lab.submit("research_run", {"question": "second"})):
        with pytest.raises(ServiceError) as exc:
            action()
        assert exc.value.status == 409
    assert lab.research_status()["available"] is False
    bridge.release.set()
    assert finish(lab, job)["status"] == "COMPLETED"
    assert lab.research_status()["available"] is True


def test_confirmed_cancel_retains_partial_answer_and_opens_gate(tmp_path):
    bridge = Bridge(wait=True)
    lab = service(tmp_path, bridge)
    job = lab.submit("research_run", {"question": "long"})
    assert bridge.started.wait(1)
    lab.cancel(job["id"])
    terminal = finish(lab, job)
    assert terminal["status"] == "CANCELLED" and terminal["cancel_observed"]
    assert terminal["result"]["answer"] == "취소 전 받은 실제 부분 응답"
    assert lab.research_status()["available"] is True


def test_live_job_progress_is_a_copy_of_retained_events(tmp_path):
    bridge = Bridge(wait=True)
    original = {"answer": "실제 부분 답변", "tools": [{"tool": "inspect", "status": "running"}]}
    bridge.progress = lambda: original
    lab = service(tmp_path, bridge)
    job = lab.submit("research_run", {"question": "long"})
    assert bridge.started.wait(1)
    snapshot = lab.job(job["id"])
    assert snapshot["progress"]["answer"] == "실제 부분 답변"
    snapshot["progress"]["tools"][0]["status"] = "changed"
    assert original["tools"][0]["status"] == "running"
    assert len(bridge.calls) == 1
    assert "progress" not in lab._jobs[job["id"]]
    bridge.release.set()
    assert finish(lab, job)["status"] == "COMPLETED"


def test_new_read_route_uses_existing_host_and_origin_guard(tmp_path):
    server = LabHTTPServer(service(tmp_path, Bridge()), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for headers, expected in (({}, 200), ({"Origin": "https://foreign.example"}, 403)):
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            try:
                conn.request("GET", "/api/research", headers=headers)
                response = conn.getresponse()
                body = json.loads(response.read())
                assert response.status == expected
                if expected == 200:
                    assert body["model"] == "openai-codex/gpt-5.6-sol"
            finally:
                conn.close()
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()
