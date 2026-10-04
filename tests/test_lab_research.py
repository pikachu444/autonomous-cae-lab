"""Controlled bridge checks: synthetic owned runtime, no actual subprocess/provider."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from apps.lab import research


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(research, "windows_path", lambda path: "C:\\SYNTHETIC\\" + str(Path(path).resolve()).replace(":", "").replace("/", "\\").lstrip("\\"))
    repo, store = tmp_path / "repo", tmp_path / "store"
    owner_path = tmp_path / "runtime-owner.json"
    powershell = tmp_path / "pwsh.exe"
    powershell.write_bytes(b"SYNTHETIC_NOT_EXECUTABLE")
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts/lab-openscience.ps1").write_bytes(b"SYNTHETIC_NOT_NATIVE")
    store.mkdir()
    win = research.windows_path
    definition = {"kind": "autonomous-cae-lab.openscience-research-definition", "schema": 1,
                  "agent": "research", "budgets": {"command_timeout_seconds": 3600},
                  "capabilities": [{"backend": "fixture.calculix", "operations": ["analysis_run"]}]}
    owner = {"kind": "autonomous-cae-lab.openscience-runtime", "schema": 1, "state": "ready",
             "run_name": "synthetic-owned", "repo_root": win(repo), "profile_root": "C:\\SYNTHETIC\\profile",
             "runtime_url": "http://127.0.0.1:4098", "workspace_url": "http://127.0.0.1:4098/prj_synthetic/session",
             "boot_source_sha256": "b" * 64,
             "boot_source": {"kind": "autonomous-cae-lab.repository-source-pin", "repo_root": win(repo),
                             "source_commit": "a" * 40},
             "context": {"OwnerPath": win(owner_path), "RepoRoot": win(repo), "StoreRoot": win(store),
                         "Purpose": "Research", "Transport": "ChatGPT", "Model": research.MODEL,
                         "RunName": "synthetic-owned", "ProfileRoot": "C:\\SYNTHETIC\\profile",
                         "ArtifactRoot": win(tmp_path / "evidence"), "ResearchDefinition": definition,
                         "ResearchDefinitionSha256": "c" * 64,
                         "ProjectBinding": {"project_id": "prj_synthetic", "access": "write",
                                            "source_directory": win(repo), "working_root": win(repo),
                                            "project_directory": "C:\\SYNTHETIC\\managed-project"}}}
    save(owner_path, owner)
    owner_reads = []
    def read_host_owner(command, **options):
        # SYNTHETIC_NOT_NATIVE: the Windows-owned file is represented by this
        # fixture; only the new metadata seam is intercepted, not admission.
        assert command == [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                           win(repo / "scripts/lab-openscience.ps1"), "-ReadOwnerBytes", "-OwnerPath", win(owner_path)]
        assert options == {"cwd": repo, "stdin": research.subprocess.DEVNULL,
                           "stdout": research.subprocess.PIPE, "stderr": research.subprocess.PIPE,
                           "shell": False, "timeout": 10, "check": False}
        owner_reads.append(command)
        return research.subprocess.CompletedProcess(command, 0, owner_path.read_bytes(), b"")
    monkeypatch.setattr(research.subprocess, "run", read_host_owner)
    bridge = research.OpenScienceResearch(owner_path, store, repo=repo, powershell=powershell,
                                         evidence_root=tmp_path / "evidence")
    assert bridge._configuration_error is None
    bridge._synthetic_owner_reads = owner_reads
    return bridge, owner, owner_path


class FakeProcess:
    """Owned synthetic Popen observation; forbidden termination is detectable."""
    def __init__(self, exited=True):
        self.exited = exited

    def poll(self):
        return 0 if self.exited else None

    def kill(self):
        raise AssertionError("Bridge must not kill unconfirmed native ownership")

    terminate = kill


def response(bridge, directory, **fields):
    request = directory / "request.json"
    value = {"request_sha256": hashlib.sha256(request.read_bytes()).hexdigest(), "owner_sha256": bridge._owner_sha,
             "cleanup_confirmed": True, "cleanup_pending": False, "profile": "FixtureScalar",
             "workspace_url": bridge._initial["workspace_url"], "status": "COMPLETED", "session_id": "ses_owned123",
             "user_cancelled": False, "timed_out": False, "cancellation_idle_confirmed": False,
             "resident_idle_confirmed": True, "command_started": True,
             "launcher_still_running": False, "log_relay_still_running": False}
    value.update(fields)
    save(directory / "response.json", value)


def events(directory, values):
    path = directory / "command/stdout.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(value, ensure_ascii=False) for value in values) + "\n", encoding="utf-8")


def test_exact_unicode_request_and_file_argument_vector(configured, monkeypatch):
    bridge, _, _ = configured
    question = '  볼트 간격을 바꾸면?\r\nUnicode Ω 😀 " --model evil ; $()\n'
    seen = []
    def start(directory, command):
        seen.append(directory)
        assert (directory / "question.txt").read_bytes() == question.encode("utf-8")
        request = json.loads((directory / "request.json").read_bytes())
        assert request["session_id"] == "ses_exact7"
        assert request["question_bytes"] == len(question.encode("utf-8"))
        assert command == [str(bridge.powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                           research.windows_path(bridge.facade), "-RequestPath", research.windows_path(directory / "request.json")]
        assert not any(question in argument for argument in command)
        response(bridge, directory)
        events(directory, [{"type": "text", "part": {"text": "실제 모의 답변 Ω"}}])
        return FakeProcess()
    monkeypatch.setattr(bridge, "_start", start)
    result = bridge.run(question, "ses_exact7")
    assert result["question"] == question and result["answer"] == "실제 모의 답변 Ω"
    assert result["source_commit"] == "a" * 40
    assert result["decision"] == "NOT_RELEASED" and result["completion_is_engineering_approval"] is False
    assert len(seen) == 1 and not bridge.active


@pytest.mark.parametrize("question", [None, 7, "", " \r\n\t", "\ud800", "a\0b", "가" * 5462, "x" * 16385])
def test_question_refused_before_launch(configured, monkeypatch, question):
    bridge, _, _ = configured
    monkeypatch.setattr(bridge, "_start", lambda *_: pytest.fail("Invalid request launched"))
    with pytest.raises(ValueError):
        bridge.run(question)
    assert not bridge.active


@pytest.mark.parametrize("session", ["", "ses_bad-id", "ses_", "--continue", 1, "ses_ok\n"])
def test_invalid_session_refused_before_launch(configured, session):
    with pytest.raises(ValueError):
        configured[0].run("질문", session)


def test_exact_question_byte_boundary():
    assert len(research.validate_question("x" * 16384)) == 16384
    assert research.validate_question("  Ω\r\n") == "  Ω\r\n".encode()


@pytest.mark.parametrize("field,value", [("Model", "openai-codex/other"), ("Purpose", "Acceptance"),
    ("Transport", "Ollama"), ("StoreRoot", "C:\\foreign"), ("RepoRoot", "C:\\foreign"),
    ("ProfileRoot", "C:\\foreign"), ("RunName", "other")])
def test_owner_drift_never_infers(configured, monkeypatch, field, value):
    bridge, owner, path = configured
    owner["context"][field] = value
    save(path, owner)
    monkeypatch.setattr(bridge, "_start", lambda *_: pytest.fail("Drift launched"))
    assert bridge.status()["available"] is False
    with pytest.raises(ValueError, match="소유권"):
        bridge.run("질문")


@pytest.mark.parametrize("change", ["project", "source", "descriptor", "deleted"])
def test_project_source_descriptor_or_dead_owner_refused(configured, monkeypatch, change):
    bridge, owner, path = configured
    if change == "deleted":
        path.unlink()
    else:
        if change == "project": owner["context"]["ProjectBinding"]["project_id"] = "prj_foreign"
        if change == "source": owner["boot_source"]["source_commit"] = "d" * 40
        if change == "descriptor": owner["context"]["ResearchDefinition"]["budgets"]["command_timeout_seconds"] = 3599
        save(path, owner)
    monkeypatch.setattr(bridge, "_start", lambda *_: pytest.fail("Drift launched"))
    assert bridge.status()["state"] == "UNAVAILABLE"
    with pytest.raises(ValueError, match="소유권") as caught:
        bridge.run("안전한 연결 오류")
    assert str(path) not in str(caught.value) and "C:\\" not in str(caught.value)
    assert not bridge.active


@pytest.mark.parametrize("phase", ["owner_read", "start"])
def test_review_prestart_private_errors_are_safely_retained(configured, monkeypatch, phase):
    bridge, _, path = configured
    original_error = OSError(f"Cannot open {path}; executable={bridge.powershell} authorization=PRIVATE_SECRET")
    def fail(*_):
        raise original_error
    monkeypatch.setattr(bridge, "_current_owner" if phase == "owner_read" else "_start", fail)
    with pytest.raises(ValueError, match="소유권") as caught:
        bridge.run("시작할 수 없는 질문")
    assert str(path) not in str(caught.value) and str(bridge.powershell) not in str(caught.value)
    assert "PRIVATE_SECRET" not in str(caught.value) and "Cannot open" not in str(caught.value)
    assert not bridge.active and not bridge.cleanup_pending and bridge._process is None
    retained = [json.loads(item.read_bytes()) for item in bridge.evidence_root.rglob("observer-error-*.json")]
    assert len(retained) == 1 and retained[0]["phase"] == "before_popen"
    assert str(path) in retained[0]["error"] and "PRIVATE_SECRET" not in retained[0]["error"]


@pytest.mark.parametrize("invalid", ["missing", "malformed", "request", "owner"])
def test_review_exited_facade_missing_or_invalid_response_retains_same_handle(configured, monkeypatch, invalid):
    bridge, _, _ = configured
    process, seen, waits = FakeProcess(), [], []
    def start(directory, command):
        seen.append(directory)
        save(directory / "command/command-request.json", {"provenance": "SYNTHETIC_NOT_NATIVE"})
        save(directory / "command/relay-final.json", {"provenance": "SYNTHETIC_NOT_NATIVE", "exit_code": 0})
        save(directory / "command/command.json", {"launcher_still_running": False, "log_relay_still_running": False})
        events(directory, [{"type": "text", "part": {"text": "종료 후 남은 부분 응답"}}])
        if invalid == "malformed":
            (directory / "response.json").write_text('{"status":', encoding="utf-8")
        elif invalid in {"request", "owner"}:
            response(bridge, directory, **{invalid + "_sha256": "0" * 64})
        return process
    def sleep(_):
        waits.append(True)
        assert bridge.active and bridge.cleanup_pending and bridge._process is process
        assert process.exited and bridge.progress()["answer"] == "종료 후 남은 부분 응답"
        with pytest.raises(ValueError, match="already owns"):
            bridge.run("새 추론 금지")
        if len(waits) == 1:
            # Even deletion of the raw start receipt and a false response flag
            # cannot undo actual start evidence already observed on this handle.
            for name in ("command-request.json", "relay-final.json"):
                (seen[0] / "command" / name).unlink()
            response(bridge, seen[0], command_started=False, resident_idle_confirmed=False)
        else:
            assert len(waits) == 2
            response(bridge, seen[0], command_started=False, resident_idle_confirmed=True)
    monkeypatch.setattr(bridge, "_start", start)
    monkeypatch.setattr(research.time, "sleep", sleep)
    result = bridge.run("같은 실행 정리 확인")
    assert result["status"] == "COMPLETED" and result["answer"] == "종료 후 남은 부분 응답"
    assert len(seen) == 1 and len(waits) == 2 and not bridge.active and bridge._process is None


def test_review_precommand_facade_exit_is_safe_failure(configured, monkeypatch):
    bridge, _, _ = configured
    seen = []
    def start(directory, command):
        seen.append(directory)
        return FakeProcess()
    monkeypatch.setattr(bridge, "_start", start)
    monkeypatch.setattr(research.time, "sleep", lambda _: pytest.fail("Pre-command exit waited"))
    result = bridge.run("추론 전에 종료")
    assert result["status"] == "FAILED" and not bridge.active and not bridge.cleanup_pending
    assert len(seen) == 1 and not (seen[0] / "command").exists()


def test_review_guard_failure_remains_failed_and_public_error_safe(configured, monkeypatch):
    bridge, _, _ = configured
    def start(directory, command):
        original = "C:\\private\\profile\\guard.json authorization=PRIVATE_SECRET restoration failed"
        response(bridge, directory, status="FAILED", user_cancelled=True, cancellation_idle_confirmed=True,
                 failure="Workspace guard restoration failed: " + original,
                 guard_restore_failure=original, error="Workspace guard restoration failed: " + original)
        return FakeProcess()
    monkeypatch.setattr(bridge, "_start", start)
    result = bridge.run("취소 후 제한 복원 실패")
    assert result["status"] == "FAILED" and "restoration failed" in result["error"]
    public = json.dumps(result, ensure_ascii=False)
    assert "private" not in public and "PRIVATE_SECRET" not in public and "C:\\" not in public
    assert not bridge.active


def test_review_marker_write_error_keeps_live_facade_and_retries_same_handle(configured, monkeypatch):
    bridge, _, _ = configured
    process, seen, waits, marker_attempts = FakeProcess(exited=False), [], [], []
    def start(directory, command):
        seen.append(directory)
        save(directory / "command/command-request.json", {"provenance": "SYNTHETIC_NOT_NATIVE"})
        events(directory, [{"type": "text", "part": {"text": "기록 오류 전 부분 답변"}}])
        return process
    original_write = research._write_new
    def fail_once(path, data):
        if path.name == "cancel.txt":
            marker_attempts.append(path)
            if len(marker_attempts) == 1:
                raise OSError("Controlled cancel marker is temporarily unwritable")
        original_write(path, data)
    def sleep(_):
        waits.append(True)
        assert bridge.active and bridge.cleanup_pending and bridge._process is process
        assert bridge.progress()["answer"] == "기록 오류 전 부분 답변"
        with pytest.raises(ValueError, match="already owns"):
            bridge.run("교체 추론 금지")
        if len(waits) == 1:
            assert not process.exited and not (seen[0] / "cancel.txt").exists()
        elif len(waits) == 2:
            assert (seen[0] / "cancel.txt").read_bytes() == b"CANCEL_REQUESTED\n"
            process.exited = True
            response(bridge, seen[0], status="CANCELLED", user_cancelled=True,
                     cancellation_idle_confirmed=True, resident_idle_confirmed=False)
        else:
            assert len(waits) == 3
            response(bridge, seen[0], status="CANCELLED", user_cancelled=True,
                     cancellation_idle_confirmed=True, resident_idle_confirmed=True)
    monkeypatch.setattr(bridge, "_start", start)
    monkeypatch.setattr(research, "_write_new", fail_once)
    monkeypatch.setattr(research.time, "sleep", sleep)
    result = bridge.run("표시 기록 재시도", cancellation_requested=lambda: True)
    assert result["status"] == "CANCELLED" and result["answer"] == "기록 오류 전 부분 답변"
    assert len(seen) == 1 and len(marker_attempts) == 2 and len(waits) == 3 and not bridge.active
    diagnostics = [json.loads(item.read_bytes()) for item in seen[0].glob("observer-error-*.json")]
    assert len(diagnostics) == 1 and diagnostics[0]["phase"] == "after_popen_observation"
    assert "temporarily unwritable" in diagnostics[0]["error"]


def test_review_persistent_marker_error_still_observes_verified_actual_completion(configured, monkeypatch):
    bridge, _, _ = configured
    process, seen, waits = FakeProcess(exited=False), [], []
    def start(directory, command):
        seen.append(directory)
        save(directory / "command/command-request.json", {"provenance": "SYNTHETIC_NOT_NATIVE"})
        return process
    write = research._write_new
    def marker_unwritable(path, data):
        if path.name == "cancel.txt":
            raise OSError("Controlled persistent marker failure")
        write(path, data)
    def sleep(_):
        waits.append(True)
        assert len(waits) == 1 and bridge.active and bridge.cleanup_pending and bridge._process is process
        process.exited = True
        response(bridge, seen[0], status="COMPLETED", user_cancelled=False, resident_idle_confirmed=True)
    monkeypatch.setattr(bridge, "_start", start)
    monkeypatch.setattr(research, "_write_new", marker_unwritable)
    monkeypatch.setattr(research.time, "sleep", sleep)
    result = bridge.run("실제 완료 관찰", cancellation_requested=lambda: True)
    assert result["status"] == "COMPLETED" and len(seen) == len(waits) == 1 and not bridge.active
    assert not (seen[0] / "cancel.txt").exists()
    assert len(list(seen[0].glob("observer-error-*.json"))) == 1


def test_status_uses_verified_facade_and_exposes_public_fields(configured, monkeypatch):
    bridge, _, _ = configured
    def start(directory, command):
        assert json.loads((directory / "request.json").read_text())["mode"] == "status"
        assert not (directory / "question.txt").exists()
        response(bridge, directory, available=True, capabilities=[{"backend": "fixture.calculix", "operations": ["analysis_run"]}])
        return FakeProcess()
    monkeypatch.setattr(bridge, "_start", start)
    status = bridge.status()
    assert status["state"] == "READY" and status["model"] == research.MODEL
    assert set(status) == {"configured", "available", "state", "model", "profile", "workspace_url", "capabilities"}
    assert "C:\\" not in json.dumps(status)


def test_partial_answer_and_failed_numerical_receipt_are_retained(configured, monkeypatch):
    bridge, _, _ = configured
    def start(directory, command):
        events(directory, [{"type": "text", "part": {"text": "첫 부분 답변"}},
             {"type": "tool_use", "part": {"tool": "caelab_analysis_run", "state": {"status": "completed",
                  "output": json.dumps({"experiment_id": "E-actual", "status": "FAILED_EXECUTION"})}}},
             {"type": "tool_use", "part": {"tool": "caelab_experiment_inspect", "state": {"status": "error", "error": "C:\\private\\auth.json authorization=SECRET"}}}])
        with (directory / "command/stdout.jsonl").open("a") as stream:
            stream.write('{"type":"text","part":')
        response(bridge, directory, status="FAILED", error="C:\\private\\auth.json authorization=SECRET")
        return FakeProcess()
    monkeypatch.setattr(bridge, "_start", start)
    result = bridge.run("조건을 살펴보세요")
    assert result["status"] == "FAILED" and result["answer"] == "첫 부분 답변"
    assert result["tools"][0] == {"tool": "caelab_analysis_run", "status": "FAILED_EXECUTION", "tool_status": "completed", "experiment_id": "E-actual"}
    assert result["tools"][1]["status"] == "error"
    assert "private" not in result["error"] and "SECRET" not in result["error"]
    assert bridge.last_result == result


def test_cancellation_marker_once_and_unconfirmed_cleanup_keeps_same_owner(configured, monkeypatch):
    bridge, _, _ = configured
    process = FakeProcess(exited=False)
    seen, stages = [], []
    def start(directory, command):
        seen.append(directory)
        events(directory, [{"type": "text", "part": {"text": "취소 전 부분 답변"}}])
        response(bridge, directory, status="CANCELLED", cleanup_pending=True, cleanup_confirmed=False,
                 user_cancelled=True, cancellation_idle_confirmed=False, launcher_still_running=True, log_relay_still_running=True)
        save(directory / "progress.json", {"cleanup_pending": True})
        return process
    def sleep(_):
        stages.append(True)
        assert bridge.active and bridge.cleanup_pending and bridge._process is process
        assert bridge.progress()["answer"] == "취소 전 부분 답변"
        assert bridge.progress()["cleanup_pending"] is True
        assert (seen[0] / "cancel.txt").read_bytes() == b"CANCEL_REQUESTED\n"
        with pytest.raises(ValueError, match="already owns"):
            bridge.run("두 번째 질문")
        if len(stages) == 1:
            response(bridge, seen[0], status="CANCELLED", user_cancelled=True, cancellation_idle_confirmed=True,
                     resident_idle_confirmed=True)
        else:
            process.exited = True
    monkeypatch.setattr(bridge, "_start", start)
    monkeypatch.setattr(research.time, "sleep", sleep)
    writes = []
    write = research._write_new
    def tracked(path, data):
        if path.name == "cancel.txt": writes.append(path)
        write(path, data)
    monkeypatch.setattr(research, "_write_new", tracked)
    result = bridge.run("취소 테스트", cancellation_requested=lambda: True)
    assert result["status"] == "CANCELLED" and result["answer"] == "취소 전 부분 답변"
    assert len(seen) == len(writes) == 1 and len(stages) == 2
    assert not bridge.active and not bridge.cleanup_pending
    assert bridge.progress() == {}


def test_missing_resident_idle_evidence_never_publishes_cancelled(configured, monkeypatch):
    bridge, _, _ = configured
    process, seen, waits = FakeProcess(), [], []
    def start(directory, command):
        seen.append(directory)
        response(bridge, directory, status="CANCELLED", user_cancelled=True, cancellation_idle_confirmed=True,
                 resident_idle_confirmed=False)
        return process
    def sleep(_):
        waits.append(True)
        assert bridge.active and bridge.cleanup_pending and bridge._process is process
        response(bridge, seen[0], status="CANCELLED", user_cancelled=True, cancellation_idle_confirmed=True,
                 resident_idle_confirmed=True)
    monkeypatch.setattr(bridge, "_start", start)
    monkeypatch.setattr(research.time, "sleep", sleep)
    assert bridge.run("정리 확인", cancellation_requested=lambda: True)["status"] == "CANCELLED"
    assert len(waits) == len(seen) == 1


@pytest.mark.parametrize("status,timed_out", [("COMPLETED", False), ("FAILED", True)])
def test_every_started_terminal_waits_for_resident_idle(configured, monkeypatch, status, timed_out):
    bridge, _, _ = configured
    process, seen, waits = FakeProcess(), [], []
    def start(directory, command):
        seen.append(directory)
        events(directory, [{"type": "text", "part": {"text": "원본 부분 답변"}}])
        response(bridge, directory, status=status, timed_out=timed_out, resident_idle_confirmed=False)
        return process
    def sleep(_):
        waits.append(True)
        assert bridge.active and bridge.cleanup_pending and bridge._process is process
        assert bridge.progress()["answer"] == "원본 부분 답변"
        with pytest.raises(ValueError, match="already owns"):
            bridge.run("별도 쓰기")
        response(bridge, seen[0], status=status, timed_out=timed_out, resident_idle_confirmed=True)
    monkeypatch.setattr(bridge, "_start", start)
    monkeypatch.setattr(research.time, "sleep", sleep)
    result = bridge.run("정리 확인")
    assert result["status"] == status and result["answer"] == "원본 부분 답변"
    assert len(waits) == len(seen) == 1 and not bridge.active


def test_late_cancel_request_does_not_relabel_completed_run(configured, monkeypatch):
    bridge, _, _ = configured
    def start(directory, command):
        response(bridge, directory)
        return FakeProcess()
    monkeypatch.setattr(bridge, "_start", start)
    assert bridge.run("완료 직전", cancellation_requested=lambda: True)["status"] == "COMPLETED"


def test_timeout_remains_failure_instead_of_user_cancellation(configured, monkeypatch):
    bridge, _, _ = configured
    def start(directory, command):
        response(bridge, directory, status="FAILED", timed_out=True, user_cancelled=False,
                 cancellation_idle_confirmed=True, error="command budget exhausted")
        return FakeProcess()
    monkeypatch.setattr(bridge, "_start", start)
    assert bridge.run("오래 걸리는 질문")["status"] == "FAILED"


def test_subprocess_start_uses_no_shell_and_owned_output_files(configured, monkeypatch):
    bridge, _, _ = configured
    directory, command, _ = bridge._request("status")
    seen = []
    def popen(arguments, **kwargs):
        seen.append((arguments, kwargs))
        assert kwargs["shell"] is False and kwargs["cwd"] == bridge.repo
        assert Path(kwargs["stdout"].name).parent == directory
        assert Path(kwargs["stderr"].name).parent == directory
        return FakeProcess()
    monkeypatch.setattr(research.subprocess, "Popen", popen)
    bridge._start(directory, command)
    assert seen[0][0] == command


def test_native_wsl_path_mapping_refuses_unmounted_and_network_paths(monkeypatch):
    monkeypatch.setattr(research.os, "name", "posix")
    assert research.windows_path(Path("/mnt/c/SourceCodes/lab")) == "C:\\SourceCodes\\lab"
    for path in (Path("/home/person/request"), Path("/tmp/request"), Path("/mnt/server/request")):
        with pytest.raises(ValueError, match="mounted local-drive"):
            research.windows_path(path)


def test_owner_io_authoritative_host_bytes_initialize_and_refresh_with_blind_linux_view(configured, monkeypatch):
    bridge, owner, owner_path = configured
    raw = b"\xef\xbb\xbf" + json.dumps(owner, ensure_ascii=False, indent=3).replace("\n", "\r\n").encode("utf-8") + b"\r\n"
    calls = []
    original_read = Path.read_bytes
    def linux_read(path):
        if path == owner_path:
            raise FileNotFoundError("SYNTHETIC Linux view cannot see the Windows owner")
        return original_read(path)
    def host_read(command, **options):
        calls.append((command, options))
        assert command == [str(bridge.powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                           research.windows_path(bridge.facade), "-ReadOwnerBytes", "-OwnerPath", research.windows_path(owner_path)]
        assert options == {"cwd": bridge.repo, "stdin": research.subprocess.DEVNULL,
                           "stdout": research.subprocess.PIPE, "stderr": research.subprocess.PIPE,
                           "shell": False, "timeout": 10, "check": False}
        return research.subprocess.CompletedProcess(command, 0, raw, b"")
    monkeypatch.setattr(Path, "read_bytes", linux_read)
    monkeypatch.setattr(research.subprocess, "run", host_read)
    monkeypatch.setattr(research.subprocess, "Popen", lambda *_args, **_options: pytest.fail("Metadata read launched inference"))
    authoritative = research.OpenScienceResearch(owner_path, bridge.store, repo=bridge.repo,
                                                 powershell=bridge.powershell, evidence_root=bridge.evidence_root)
    assert authoritative._configuration_error is None and authoritative._initial == owner
    assert authoritative._owner_sha == hashlib.sha256(raw).hexdigest()
    assert authoritative._current_owner() == owner and authoritative._read_owner_bytes() == raw
    assert len(calls) == 3 and not authoritative.active and not authoritative.cleanup_pending
    assert not bridge.evidence_root.exists()  # Metadata reads do not copy the owner or mutate profiles.


def test_owner_io_native_windows_keeps_direct_file_read(configured, monkeypatch):
    bridge, _, owner_path = configured
    raw = owner_path.read_bytes()
    monkeypatch.setattr(research, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(research.subprocess, "run", lambda *_args, **_options: pytest.fail("Native Windows read spawned a child"))
    assert bridge._read_owner_bytes() == raw and bridge._current_owner() == bridge._initial


@pytest.mark.parametrize("failure", ["nonzero", "stderr", "timeout", "oserror"])
def test_owner_io_read_failures_are_private_and_never_infer(configured, monkeypatch, failure):
    bridge, _, owner_path = configured
    private = f"{owner_path} authorization=OWNER_SECRET; PRIVATE_OWNER_BODY".encode()
    def fail_read(command, **options):
        if failure == "timeout":
            raise research.subprocess.TimeoutExpired(command, 10, output=private, stderr=private)
        if failure == "oserror":
            raise OSError(private.decode())
        return research.subprocess.CompletedProcess(command, 1 if failure == "nonzero" else 0, private, private)
    monkeypatch.setattr(research.subprocess, "run", fail_read)
    monkeypatch.setattr(bridge, "_start", lambda *_: pytest.fail("Owner read failure launched inference"))
    status = bridge.status()
    assert status["state"] == "UNAVAILABLE" and "소유권" in status["reason"]
    with pytest.raises(ValueError, match="소유권") as caught:
        bridge.run("읽기 실패")
    public = json.dumps(status, ensure_ascii=False) + str(caught.value)
    assert str(owner_path) not in public and "OWNER_SECRET" not in public and "PRIVATE_OWNER_BODY" not in public
    assert not bridge.active and not bridge.cleanup_pending and bridge._process is None
    initial = research.OpenScienceResearch(owner_path, bridge.store, repo=bridge.repo,
                                          powershell=bridge.powershell, evidence_root=bridge.evidence_root)
    assert initial._initial is None and "소유권" in initial._configuration_error


@pytest.mark.parametrize("change", ["changed", "deleted"])
def test_owner_io_refresh_never_reuses_an_initial_snapshot(configured, monkeypatch, change):
    bridge, _, owner_path = configured
    before = len(bridge._synthetic_owner_reads)
    if change == "deleted":
        owner_path.unlink()
    else:
        owner_path.write_bytes(owner_path.read_bytes() + b"\r\n")
    monkeypatch.setattr(bridge, "_start", lambda *_: pytest.fail("Changed/deleted owner launched inference"))
    with pytest.raises(ValueError, match="소유권"):
        bridge.run("현재 원본 확인")
    assert len(bridge._synthetic_owner_reads) == before + 1 and not bridge.active


@pytest.mark.parametrize("missing", ["powershell", "facade"])
def test_owner_io_missing_trusted_reader_fails_before_child(configured, monkeypatch, missing):
    bridge, _, _ = configured
    getattr(bridge, missing).unlink()
    monkeypatch.setattr(research.subprocess, "run", lambda *_args, **_options: pytest.fail("Missing trusted reader spawned"))
    with pytest.raises(ValueError, match="소유권"):
        bridge._current_owner()


def test_owner_io_unsupported_platform_fails_before_child(configured, monkeypatch):
    bridge, _, _ = configured
    monkeypatch.setattr(research, "os", SimpleNamespace(name="unsupported"))
    monkeypatch.setattr(research.subprocess, "run", lambda *_args, **_options: pytest.fail("Unsupported reader spawned"))
    with pytest.raises(ValueError, match="소유권"):
        bridge._read_owner_bytes()
