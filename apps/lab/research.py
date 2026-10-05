"""Trusted Lab handoff to the existing owned official OpenScience launcher."""

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import threading
import time
from typing import Callable
from urllib.parse import urlsplit
import uuid


MODEL = "openai-codex/gpt-5.6-sol"
SOURCE_ROOT = Path(__file__).resolve().parents[2]
SESSION = re.compile(r"ses_[A-Za-z0-9]+\Z")
PROGRESS_PHASES = frozenset({"RUNTIME_VERIFY", "RESIDENT_VERIFY", "CLI_PREFLIGHT", "END_VERIFY"})


def windows_path(path: Path) -> str:
    """Only native Windows or mounted local-drive WSL paths are transported."""
    resolved = path.resolve()
    if os.name == "nt":
        value = str(resolved)
        if not re.match(r"^[A-Za-z]:\\", value):
            raise ValueError("A mounted local-drive path is required")
        return value
    match = re.fullmatch(r"/mnt/([A-Za-z])/(.+)", resolved.as_posix())
    if not match:
        raise ValueError("A mounted local-drive path is required")
    return str(PureWindowsPath(match[1].upper() + ":/", match[2]))


def validate_question(question: str, session_id: str | None = None) -> bytes:
    if not isinstance(question, str) or not question.strip() or "\0" in question:
        raise ValueError("A nonblank question is required")
    try:
        encoded = question.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ValueError("The question must be valid UTF-8") from error
    if len(encoded) > 16384:
        raise ValueError("The question exceeds 16384 UTF-8 bytes")
    if session_id is not None and (not isinstance(session_id, str) or not SESSION.fullmatch(session_id)):
        raise ValueError("An exact owned session ID is required")
    return encoded


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class OpenScienceResearch:
    def __init__(self, owner: Path, store: Path, *, repo: Path = SOURCE_ROOT,
                 powershell: Path | None = None, evidence_root: Path | None = None):
        self.owner, self.store, self.repo = Path(owner).resolve(), Path(store).resolve(), Path(repo).resolve()
        self.powershell = Path(powershell).resolve() if powershell else (
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PowerShell/7/pwsh.exe"
            if os.name == "nt" else Path("/mnt/c/Program Files/PowerShell/7/pwsh.exe"))
        self.facade = self.repo / "scripts/lab-openscience.ps1"
        self._lock = threading.Lock()
        self._active = False
        self._cleanup_pending = False
        self._process = None
        self._directory = None
        self._last_result = None
        self._initial = None
        self._owner_sha = None
        self._configuration_error = None
        self.evidence_root = Path(evidence_root).resolve() if evidence_root else None
        try:
            data = self._read_owner_bytes()
            self._owner_sha = hashlib.sha256(data).hexdigest()
            self._initial = self._validate_owner(json.loads(data))
            if self.evidence_root is None:
                artifact = self._initial["context"]["ArtifactRoot"]
                if os.name == "nt":
                    self.evidence_root = Path(artifact) / "lab-questions"
                else:
                    drive = PureWindowsPath(artifact)
                    self.evidence_root = Path("/mnt", drive.drive[0].lower(), *drive.parts[1:]) / "lab-questions"
            windows_path(self.evidence_root)
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            self._configuration_error = "AI 연구 런타임의 소유권 설정을 확인할 수 없습니다."

    @property
    def active(self) -> bool:
        return self._active

    @property
    def cleanup_pending(self) -> bool:
        return self._cleanup_pending

    @property
    def last_result(self) -> dict | None:
        return deepcopy(self._last_result)

    def progress(self) -> dict:
        """Read only already retained output; no runtime health or model call."""
        directory = self._directory
        if directory is None or not self._active:
            return {}
        answer, tools, errors = self._output(directory)
        metadata = (self._read(directory / "progress.json")
                    or self._read(directory / "command/command.json")
                    or self._read(directory / "command/command-request.json") or {})
        snapshot = {"session_id": metadata.get("session_id"), "answer": answer, "tools": tools,
                    "cleanup_pending": self._cleanup_pending, "model": MODEL,
                    "completion_is_engineering_approval": False, "decision": "NOT_RELEASED"}
        phase = metadata.get("phase")
        if isinstance(phase, str) and phase in PROGRESS_PHASES:
            snapshot["phase"] = phase
            stamp = metadata.get("phase_started_utc")
            if isinstance(stamp, str) and re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|\+00:00)", stamp):
                try:
                    datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    snapshot["phase_started_utc"] = stamp
                except ValueError:
                    pass
        if errors:
            snapshot["error"] = "\n".join(errors)
        return snapshot

    def _validate_owner(self, owner: dict) -> dict:
        context = owner["context"]
        binding = context["ProjectBinding"]
        definition = context["ResearchDefinition"]
        boot = owner["boot_source"]
        if (owner["kind"] != "autonomous-cae-lab.openscience-runtime" or owner["schema"] != 1
                or owner["state"] != "ready" or context["Purpose"] != "Research"
                or context["Transport"] != "ChatGPT" or context["Model"] != MODEL
                or context["RepoRoot"] != windows_path(self.repo)
                or context["StoreRoot"] != windows_path(self.store)
                or context["OwnerPath"] != windows_path(self.owner)
                or owner["run_name"] != context["RunName"]
                or owner["repo_root"] != context["RepoRoot"]
                or owner["profile_root"] != context["ProfileRoot"]
                or binding["source_directory"] != context["RepoRoot"]
                or binding["working_root"] != context["RepoRoot"]
                or binding["access"] != "write" or not re.fullmatch(r"prj_[A-Za-z0-9]+", binding["project_id"])
                or definition["kind"] != "autonomous-cae-lab.openscience-research-definition"
                or definition["agent"] != "research" or definition["budgets"]["command_timeout_seconds"] != 3600
                or boot["kind"] != "autonomous-cae-lab.repository-source-pin"
                or boot["repo_root"] != context["RepoRoot"]
                or not re.fullmatch(r"[0-9a-f]{40}", boot["source_commit"])
                or not re.fullmatch(r"[0-9a-f]{64}", owner["boot_source_sha256"])):
            raise ValueError("Research ownership differs from configured roots")
        runtime, workspace = urlsplit(owner["runtime_url"]), urlsplit(owner["workspace_url"])
        if (runtime.scheme != "http" or runtime.hostname != "127.0.0.1" or not runtime.port
                or runtime.username or runtime.password or runtime.query or runtime.fragment
                or runtime.path not in ("", "/")
                or workspace.scheme != runtime.scheme or workspace.netloc != runtime.netloc
                or workspace.path != "/" + binding["project_id"] + "/session"
                or workspace.query or workspace.fragment):
            raise ValueError("An owned loopback project URL is required")
        return owner

    def _read_owner_bytes(self) -> bytes:
        """Read the authoritative host file; this mode performs no runtime action."""
        message = "AI 연구 런타임의 소유권 파일을 읽을 수 없습니다."
        try:
            if os.name == "nt":
                return self.owner.read_bytes()
            if os.name != "posix" or not self.powershell.is_file() or not self.facade.is_file():
                raise ValueError(message)
            command = [str(self.powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                       windows_path(self.facade), "-ReadOwnerBytes", "-OwnerPath", windows_path(self.owner)]
            completed = subprocess.run(command, cwd=self.repo, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                                       timeout=10, check=False)
            if completed.returncode != 0 or completed.stderr:
                raise ValueError(message)
            return completed.stdout  # Hash the original bytes, including BOM/CRLF.
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError(message) from None

    def _current_owner(self) -> dict:
        if self._configuration_error or self._initial is None:
            raise ValueError("AI 연구 연결의 소유권을 확인할 수 없습니다.")
        data = self._read_owner_bytes()
        if hashlib.sha256(data).hexdigest() != self._owner_sha:
            raise ValueError("AI 연구 런타임의 소유권이 변경되었습니다.")
        return self._validate_owner(json.loads(data))

    def _safe_error(self, value: str) -> str:
        text = str(value)
        paths = [self.owner, self.store, self.repo, self.evidence_root, self.powershell]
        if self._initial:
            paths.extend(self._initial["context"].get(key) for key in ("ProfileRoot", "ConfigPath", "ArtifactRoot"))
        for path in paths:
            if path:
                text = text.replace(str(path), "[local path]")
        text = re.sub(r"[A-Za-z]:[\\/][^\s\"<>]+|/mnt/[A-Za-z]/[^\s\"<>]+", "[local path]", text)
        return self._redact_credentials(text)

    @staticmethod
    def _redact_credentials(value: str) -> str:
        text = re.sub(r"(?i)\b(?:api[_-]?key|access_token|refresh_token|authorization)\s*[:=]\s*\S+", "[credential omitted]", value)
        return re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._-]+", "[credential omitted]", text)

    def _retain_error(self, directory: Path | None, error: BaseException, phase: str) -> None:
        """Retain local diagnostics when possible without reading credentials."""
        try:
            if directory is None:
                self.evidence_root.mkdir(parents=True, exist_ok=True)
                directory = self.evidence_root / ("preflight-failure-" + uuid.uuid4().hex)
                directory.mkdir()
            diagnostic = {"phase": phase, "type": type(error).__name__,
                          "error": self._redact_credentials(str(error))}
            _write_new(directory / ("observer-error-" + uuid.uuid4().hex + ".json"),
                       json.dumps(diagnostic, ensure_ascii=False).encode("utf-8"))
        except Exception:
            pass  # Evidence I/O cannot abandon an already started command.

    def _request(self, mode: str, question: bytes | None = None, session_id: str | None = None):
        owner = self._current_owner()
        if not self.powershell.is_file() or not self.facade.is_file():
            raise ValueError("AI 연구 연결에 필요한 실행 파일을 확인할 수 없습니다.")
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        directory = self.evidence_root / (mode + "-" + uuid.uuid4().hex)
        directory.mkdir()
        context = owner["context"]
        request = {"schema": 1, "kind": "autonomous-cae-lab.lab-research-request", "mode": mode,
                   "owner_path": windows_path(self.owner), "owner_sha256": self._owner_sha,
                   "repo_root": windows_path(self.repo), "store_root": windows_path(self.store),
                   "run_name": context["RunName"], "profile_root": context["ProfileRoot"],
                   "project_id": context["ProjectBinding"]["project_id"],
                   "project_directory": context["ProjectBinding"]["project_directory"],
                   "source_commit": owner["boot_source"]["source_commit"],
                   "boot_source_sha256": owner["boot_source_sha256"],
                   "research_definition_sha256": context["ResearchDefinitionSha256"]}
        if question is not None:
            _write_new(directory / "question.txt", question)
            request.update(question_sha256=hashlib.sha256(question).hexdigest(),
                           question_bytes=len(question), session_id=session_id)
        payload = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
        _write_new(directory / "request.json", payload)
        command = [str(self.powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                   windows_path(self.facade), "-RequestPath", windows_path(directory / "request.json")]
        _write_new(directory / "invocation.json", json.dumps(command).encode("utf-8"))
        return directory, command, hashlib.sha256(payload).hexdigest()

    def _start(self, directory: Path, command: list[str]):
        with (directory / "facade.stdout.txt").open("xb") as stdout, (directory / "facade.stderr.txt").open("xb") as stderr:
            return subprocess.Popen(command, cwd=self.repo, stdout=stdout, stderr=stderr, shell=False,
                                    **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            return value if isinstance(value, dict) else None
        except (OSError, ValueError):
            return None

    def _observe(self, directory, process, request_sha, cancellation_requested):
        marker = directory / "cancel.txt"
        command_started = False
        retained_errors = set()
        while True:
            try:
                command = self._read(directory / "command/command.json") or {}
                command_started = command_started or any(
                    (directory / "command" / name).exists()
                    for name in ("command-request.json", "relay-ready.json", "relay-final.json")) or bool(
                        command.get("launcher_identity") or command.get("log_relay_identity")
                        or command.get("launcher_still_running") or command.get("log_relay_still_running"))
                try:
                    if cancellation_requested() and not marker.exists():
                        _write_new(marker, b"CANCEL_REQUESTED\n")
                except BaseException as error:
                    # A failed marker must not prevent observing a later valid
                    # completion from this same handle, or imply cancellation.
                    self._cleanup_pending = True
                    key = (type(error).__name__, str(error))
                    if key not in retained_errors:
                        retained_errors.add(key)
                        self._retain_error(directory, error, "after_popen_observation")
                response = self._read(directory / "response.json")
                if response is not None and (response.get("request_sha256") != request_sha
                                             or response.get("owner_sha256") != self._owner_sha):
                    response = None
                if response is not None:
                    command_started = command_started or response.get("command_started") is True
                progress = self._read(directory / "progress.json") or {}
                pending = bool(progress.get("cleanup_pending"))
                if response is not None:
                    pending = bool(response.get("cleanup_pending")) or response.get("cleanup_confirmed") is not True
                    if command_started and (response.get("resident_idle_confirmed") is not True
                            or response.get("launcher_still_running") is not False
                            or response.get("log_relay_still_running") is not False
                            or response.get("status") not in {"COMPLETED", "FAILED", "CANCELLED"}):
                        pending = True
                    if response.get("status") == "CANCELLED" and not (response.get("user_cancelled") is True
                            and response.get("timed_out") is False and response.get("cancellation_idle_confirmed") is True
                            and response.get("resident_idle_confirmed") is True
                            and response.get("launcher_still_running") is False and response.get("log_relay_still_running") is False):
                        pending = True
                else:
                    pending = pending or command_started
                pending = pending or bool(command.get("launcher_still_running") or command.get("log_relay_still_running"))
                exited = process.poll() is not None
                self._cleanup_pending = pending or not exited
                if response is not None and not pending and exited:
                    self._cleanup_pending = False
                    return response
                if exited and not pending and response is None and not command_started:
                    self._cleanup_pending = False
                    return {"status": "FAILED", "cleanup_confirmed": True, "command_started": False,
                            "error": "AI 연구 명령이 시작되기 전에 연결이 종료되었습니다."}
                time.sleep(0.1)
            except BaseException as error:
                # A facade/relay exit cannot prove that a synchronous native writer
                # stopped. Keep this exact Popen and let the same observer retry.
                self._cleanup_pending = True
                key = (type(error).__name__, str(error))
                if key not in retained_errors:
                    retained_errors.add(key)
                    self._retain_error(directory, error, "after_popen_observation")
                try:
                    time.sleep(0.1)
                except BaseException:
                    pass

    def status(self) -> dict:
        base = {"configured": True, "available": False, "state": "UNAVAILABLE", "model": MODEL,
                "profile": "", "workspace_url": "", "capabilities": []}
        if self._active:
            base["reason"] = "AI 연구 작업이 진행 중입니다."
            return base
        try:
            directory, command, sha = self._request("status")
            response = self._observe(directory, self._start(directory, command), sha, lambda: False)
            if response.get("available") is not True:
                raise ValueError(response.get("reason", "AI 연구 연결을 확인할 수 없습니다."))
            base.update(available=True, state="READY", profile=response["profile"],
                        workspace_url=response["workspace_url"], capabilities=response["capabilities"])
        except (OSError, ValueError, TypeError, KeyError) as error:
            base["reason"] = self._safe_error(self._configuration_error or str(error))
        return base

    def _output(self, directory: Path):
        answer, tools, errors = [], [], []
        path = directory / "command/stdout.jsonl"
        if not path.exists():
            return "", [], []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return "", [], ["AI 연구의 보존된 응답을 읽을 수 없습니다."]
        for line in lines:
            try:
                event = json.loads(line)
                part = event.get("part", {})
                if event.get("type") == "text" and isinstance(part.get("text"), str):
                    answer.append(part["text"])
                if event.get("type") == "tool_use":
                    state = part.get("state", {})
                    tool = {"tool": part["tool"], "status": state["status"]}
                    try:
                        output = json.loads(state.get("output", ""))
                    except (TypeError, ValueError):
                        output = None
                    if isinstance(output, dict):
                        if isinstance(output.get("status"), str):
                            tool["tool_status"], tool["status"] = tool["status"], output["status"]
                        if isinstance(output.get("experiment_id"), str):
                            tool["experiment_id"] = output["experiment_id"]
                    if state.get("error"):
                        errors.append(self._safe_error(state["error"]))
                    elif (state.get("status") == "completed" and isinstance(state.get("output"), str)
                          and isinstance(state.get("metadata"), dict)
                          and state["metadata"].get("truncated") is False):
                        # The observed MCP error is returned as completed plain
                        # text. Keep it on this row; a later tool can recover.
                        failure = re.fullmatch(r"Error executing tool ([A-Za-z0-9_]+): (\S[\s\S]*)", state["output"])
                        if failure and part["tool"] in {failure[1], "caelab_" + failure[1]}:
                            tool.update(status="FAILED", tool_status=state["status"],
                                        error=self._safe_error(failure[2]))
                    tools.append(tool)
                if event.get("type") == "error":
                    errors.append(self._safe_error(event.get("error", "OpenScience tool error")))
            except (ValueError, TypeError, KeyError, AttributeError):
                continue  # Original malformed/partial bytes remain in the raw log.
        return "\n".join(answer), tools, errors

    def run(self, question: str, session_id: str | None = None, *,
            cancellation_requested: Callable[[], bool] = lambda: False,
            evidence_prepared: Callable[[dict], None] | None = None) -> dict:
        encoded = validate_question(question, session_id)
        with self._lock:
            if self._active:
                raise ValueError("An AI research operation already owns this bridge")
            self._active = True
        directory = None
        cleanup_verified = False
        try:
            directory, command, sha = self._request("run", encoded, session_id)
            self._directory = directory
            if evidence_prepared is not None:
                request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
                evidence_prepared({"request_path": str(directory / "request.json"),
                                   "request_sha256": sha, "owner_path": request["owner_path"],
                                   "owner_sha256": request["owner_sha256"],
                                   "question_path": str(directory / "question.txt"),
                                   "question_sha256": request["question_sha256"],
                                   "source_commit": request["source_commit"],
                                   "boot_source_sha256": request["boot_source_sha256"],
                                   "store_root": request["store_root"]})
            self._process = self._start(directory, command)
            self._cleanup_pending = True
            response = self._observe(directory, self._process, sha, cancellation_requested)
            cleanup_verified = True
            answer, tools, errors = self._output(directory)
            status = response.get("status", "FAILED")
            if status not in {"COMPLETED", "FAILED", "CANCELLED"}:
                status = "FAILED"
            if status == "CANCELLED" and not (response.get("user_cancelled") is True
                    and response.get("timed_out") is False and response.get("cancellation_idle_confirmed") is True
                    and response.get("resident_idle_confirmed") is True
                    and response.get("launcher_still_running") is False and response.get("log_relay_still_running") is False):
                status = "FAILED"
            result = {"kind": "openscience_research", "status": status,
                      "session_id": response.get("session_id"), "model": MODEL,
                      "profile": response.get("profile", self._initial["context"]["ResearchDefinition"].get("profile", "FixtureScalar")),
                      "workspace_url": response.get("workspace_url", self._initial["workspace_url"]),
                      "question": question, "answer": answer, "tools": tools,
                      "source_commit": self._initial["boot_source"]["source_commit"],
                      "completion_is_engineering_approval": False, "decision": "NOT_RELEASED"}
            if response.get("error") or errors:
                result["error"] = self._safe_error(response.get("error") or "\n".join(errors))
            self._last_result = result
            return deepcopy(result)
        except (OSError, ValueError, TypeError, KeyError) as error:
            if self._process is not None:
                raise
            self._retain_error(directory, error, "before_popen")
            raise ValueError("AI 연구 연결을 시작할 수 없습니다. 소유권 설정과 실행 상태를 확인해 주세요.") from None
        finally:
            if self._process is None or cleanup_verified:
                self._process = None
                self._directory = None
                self._active = False
                self._cleanup_pending = False
