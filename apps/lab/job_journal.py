"""Opt-in HTTP bookkeeping, never a Core/MCP/native execution lock.

Exclusive, fsynced events are authoritative. A lost controller leaves a claim;
only an intact terminal chain permits its release, never PID/result-file probes.
"""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from caelab.storage import canonical_hash, utc_now


JOB_ID = re.compile(r"J[0-9a-f]{32}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
UUID = re.compile(r"[0-9a-f]{32}\Z")
MAX_RECORD_BYTES = 8 * 1024 * 1024
MAX_JOBS = 4096
MAX_EVENTS = 4096
EVENTS = {"ADMITTED", "WORKER_STARTED", "PREPARED", "CANCEL_REQUESTED",
          "CLEANUP_PENDING", "TERMINAL", "RELEASED"}
TERMINALS = {"COMPLETED", "FAILED", "CANCELLED"}


class JournalError(ValueError):
    """Unconfirmed HTTP bookkeeping; execution must remain closed."""


def http_source_binding() -> dict:
    root = Path(__file__).resolve().parents[2]
    names = ["apps/lab/job_journal.py", "apps/lab/service.py", "apps/lab/server.py",
             "caelab/workbench.py", "caelab/jobs.py"]
    return {"repo_root": str(root), "http_source_sha256": canonical_hash([
        [name, hashlib.sha256((root / name).read_bytes()).hexdigest()] for name in names])}


class HTTPJobJournal:
    def __init__(self, store: Path, *, source: dict | None = None):
        self.store = Path(store).resolve()
        self.root = self.store / "_http_job_control"
        self.source = deepcopy(source if source is not None else http_source_binding())
        if (not isinstance(self.source, dict) or set(self.source) != {"repo_root", "http_source_sha256"}
                or not isinstance(self.source["repo_root"], str)
                or not HEX.fullmatch(str(self.source["http_source_sha256"]))):
            raise ValueError("HTTP source binding requires repo root and actual source SHA256")
        self.controller_id = uuid.uuid4().hex
        self.jobs: dict[str, dict] = {}
        self.errors: list[str] = []
        self._heads: dict[str, tuple[int, str, dict]] = {}
        self._cancel_intents: set[str] = set()
        self.recover()

    @property
    def blocked(self) -> bool:
        return bool(self.errors)

    def _path(self, *parts: str) -> Path:
        path = self.root
        for part in ("", *parts):
            if part:
                path = path / part
            if path.is_symlink() or not path.resolve().is_relative_to(self.store):
                raise JournalError("HTTP journal path association is unsafe")
        return path

    @staticmethod
    def _bytes(value: dict) -> bytes:
        payload = (json.dumps(value, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > MAX_RECORD_BYTES:
            raise JournalError("HTTP journal record exceeds its byte bound")
        return payload

    @staticmethod
    def _sync_directory(path: Path):
        if os.name != "nt":
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _write_new(self, path: Path, value: dict) -> str:
        payload = self._bytes(value)
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        self._sync_directory(path.parent)
        return hashlib.sha256(payload).hexdigest()

    def _read(self, path: Path) -> tuple[dict, str]:
        self._path(*path.relative_to(self.root).parts)
        if not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES:
            raise JournalError("HTTP journal file type/size is invalid")
        payload = path.read_bytes()
        if len(payload) > MAX_RECORD_BYTES:
            raise JournalError("HTTP journal record exceeds its byte bound")

        def pairs(rows):
            result = {}
            for key, value in rows:
                if key in result:
                    raise JournalError("Duplicate HTTP journal key")
                result[key] = value
            return result

        def constant(_):
            raise JournalError("Nonfinite HTTP journal JSON")

        value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant)
        if not isinstance(value, dict):
            raise JournalError("HTTP journal record must be an object")
        # Also refuses numeric overflow such as 1e999 and malformed nested JSON.
        self._bytes(value)
        return value, hashlib.sha256(payload).hexdigest()

    @contextmanager
    def _locked(self):
        # Persist each new directory entry in its parent, including the root's
        # entry in the store. File/immediate-parent fsync alone is insufficient.
        missing = []
        parent = self.store
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for path in reversed(missing):
            path.mkdir(exist_ok=True)
            self._sync_directory(path.parent)
        for path in (self._path(), self._path("jobs"), self._path("observations")):
            path.mkdir(exist_ok=True)
            self._sync_directory(path.parent)
        with self._path("journal.lock").open("a+b") as stream:
            if os.name == "nt":
                import msvcrt
                if not stream.tell():
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
            else:
                import fcntl
            deadline = time.monotonic() + 2
            while True:
                try:
                    if os.name == "nt":
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as error:
                    if error.errno not in {11, 13} or time.monotonic() >= deadline:
                        raise
                    time.sleep(.01)
            try:
                yield
            finally:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _validate_binding(self, record: dict):
        source = record.get("source")
        if (record.get("schema_version") != 1 or type(record.get("schema_version")) is not int
                or record.get("store_root") != str(self.store)
                or not isinstance(source, dict) or set(source) != {"repo_root", "http_source_sha256"}
                or not isinstance(source["repo_root"], str) or not source["repo_root"]
                or not isinstance(source["http_source_sha256"], str)
                or not HEX.fullmatch(source["http_source_sha256"])
                or not JOB_ID.fullmatch(str(record.get("job_id", "")))
                or not isinstance(record.get("controller_id"), str)
                or not UUID.fullmatch(record["controller_id"])
                or not isinstance(record.get("argument_sha256"), str)
                or not HEX.fullmatch(record["argument_sha256"])):
            raise JournalError("HTTP journal schema/store/source/controller binding differs")

    def _claim(self) -> tuple[dict, str] | None:
        path = self._path("claim.json")
        if not path.exists():
            return None
        value, digest = self._read(path)
        self._validate_binding(value)
        if (set(value) != {"schema_version", "kind", "job_id", "store_root", "source",
                           "controller_id", "argument_sha256", "nonce", "created_utc"}
                or value["kind"] != "HTTP_JOB_CLAIM"
                or not isinstance(value["nonce"], str)
                or not UUID.fullmatch(str(value["nonce"]))):
            raise JournalError("HTTP claim is malformed or foreign")
        return value, digest

    def _load_job(self, identifier: str) -> tuple[dict, tuple[int, str, dict]]:
        folder = self._path("jobs", identifier)
        leaves = sorted(folder.iterdir())
        if not leaves:
            raise JournalError("HTTP job has missing events")
        previous, admission, terminal = None, None, False
        for sequence, path in enumerate(leaves):
            if sequence >= MAX_EVENTS:
                # Retain the last bounded, sound snapshot for GET even when an
                # older producer left an over-limit chain. Never adopt it.
                raise JournalError("HTTP job event capacity exceeded; outcome is UNKNOWN")
            if path.name != f"{sequence:06d}.json":
                raise JournalError("HTTP event sequence is missing or foreign")
            record, digest = self._read(path)
            self._validate_binding(record)
            if (set(record) != {"schema_version", "kind", "job_id", "store_root", "source",
                               "controller_id", "argument_sha256", "claim_sha256", "sequence",
                               "previous_sha256", "event", "observed_utc", "job", "details"}
                    or record["kind"] != "HTTP_JOB_EVENT" or record["job_id"] != identifier
                    or type(record["sequence"]) is not int or record["sequence"] != sequence
                    or record["previous_sha256"] != previous or record["event"] not in EVENTS
                    or not HEX.fullmatch(str(record["claim_sha256"]))
                    or not isinstance(record["details"], dict)
                    or not isinstance(record["job"], dict)):
                raise JournalError("HTTP event identity/sequence/hash is invalid")
            job = record["job"]
            if (job.get("id") != identifier or not isinstance(job.get("operation"), str)
                    or job.get("status") not in {"RUNNING", "CANCEL_REQUESTED", "CLEANUP_PENDING", *TERMINALS}
                    or type(job.get("cleanup_pending")) is not bool):
                raise JournalError("HTTP job snapshot is invalid")
            if sequence == 0:
                if record["event"] != "ADMITTED" or job["status"] != "RUNNING":
                    raise JournalError("HTTP job lacks admission intent")
                admission = record
            else:
                for key in ("controller_id", "argument_sha256", "claim_sha256", "source"):
                    if record[key] != admission[key]:
                        raise JournalError("HTTP event owner/argument/claim changed")
                if (job["operation"] != admission["job"]["operation"]
                        or job.get("store_id") != admission["job"].get("store_id")
                        or record["event"] == "ADMITTED" or (terminal and record["event"] != "RELEASED")):
                    raise JournalError("HTTP event stage/operation/store changed")
            if record["event"] == "TERMINAL":
                if job["status"] not in TERMINALS or job["cleanup_pending"]:
                    raise JournalError("HTTP terminal does not confirm resource closure")
                terminal = True
            elif record["event"] == "RELEASED":
                if not terminal or job != last["job"]:
                    raise JournalError("HTTP release lacks its exact terminal")
                if sequence != len(leaves) - 1:
                    raise JournalError("HTTP records follow release")
            elif job["status"] in TERMINALS:
                raise JournalError("HTTP terminal snapshot has no terminal event")
            previous, last = digest, record
            # Retain the last sound snapshot even if a later record is torn.
            self.jobs[identifier] = deepcopy(job)
        return deepcopy(last["job"]), (sequence, digest, last)

    def _scan(self):
        self.jobs, self._heads, self.errors = {}, {}, []
        self._cancel_intents = set()
        folders = sorted(self._path("jobs").iterdir())
        if len(folders) > MAX_JOBS:
            # Admission owns the bound. Existing history must remain readable
            # even if an older controller exceeded it.
            self.errors.append("HTTP journal job capacity exceeded; new admission is refused")
        for folder in folders:
            try:
                if not JOB_ID.fullmatch(folder.name) or not folder.is_dir():
                    raise JournalError("Foreign HTTP job directory")
                job, head = self._load_job(folder.name)
                self.jobs[folder.name], self._heads[folder.name] = job, head
            except (OSError, ValueError) as error:
                self.errors.append(str(error))
                if JOB_ID.fullmatch(folder.name):
                    self.jobs.setdefault(folder.name, {"id": folder.name, "operation": "UNKNOWN", "store_id": "local"})
                    self._unknown(folder.name, str(error))
        if any(path.name not in {"jobs", "observations", "journal.lock", "claim.json"}
               for path in self._path().iterdir()):
            raise JournalError("Unknown HTTP journal entry")
        observations = sorted(self._path("observations").iterdir())
        if len(observations) > MAX_EVENTS:
            self.errors.append("HTTP recovery observation capacity exceeded; outcome is UNKNOWN")
        for path in observations[:MAX_EVENTS]:
            try:
                value, _ = self._read(path)
                if (not UUID.fullmatch(path.stem) or path.suffix != ".json"
                        or type(value.get("schema_version")) is not int or value["schema_version"] != 1
                        or value.get("kind") not in {"HTTP_RECOVERY_OBSERVATION", "HTTP_RECOVERED_CANCEL_REQUEST"}
                        or value.get("store_root") != str(self.store)
                        or not JOB_ID.fullmatch(str(value.get("job_id", "")))
                        or not UUID.fullmatch(str(value.get("observer_id", "")))
                        or value.get("outcome") != "UNKNOWN"):
                    raise JournalError("HTTP recovery observation is malformed or foreign")
                if value["kind"] == "HTTP_RECOVERED_CANCEL_REQUEST":
                    if (value.get("cancel_observed") is not False
                            or value.get("cancel_requested", True) is not True):
                        raise JournalError("HTTP recovered cancellation cannot confirm observation")
                    self._cancel_intents.add(value["job_id"])
            except (OSError, ValueError) as error:
                self.errors.append(str(error))
        claim = self._claim()
        for identifier, head in self._heads.items():
            if head[2]["event"] != "RELEASED":
                if claim is None or not self._matches_claim(head[2], claim):
                    self.errors.append("Unresolved HTTP admission/claim association")
                    self._unknown(identifier, self.errors[-1])
        if claim is not None:
            identifier = claim[0]["job_id"]
            self.jobs.setdefault(identifier, {"id": identifier, "operation": "UNKNOWN", "store_id": "local"})
            if identifier not in self._heads:
                self.errors.append("HTTP claim has no complete admission")
                self._unknown(identifier, self.errors[-1])
            if (claim[0]["source"] != self.source and
                    (identifier not in self._heads or self._heads[identifier][2]["event"] not in {"TERMINAL", "RELEASED"})):
                self.errors.append("Unresolved HTTP claim belongs to a different source")
                self._unknown(identifier, self.errors[-1])
        return claim

    def _restore_cancel_intents(self):
        for identifier in self._cancel_intents:
            job = self.jobs.get(identifier)
            if job is not None and job.get("status") not in TERMINALS:
                # Apply after claim/chain uncertainty is known, including a
                # sound terminal whose release/claim association is damaged.
                # This preserves intent, never a token or observed native stop.
                job.update(cancel_requested=True, cancel_observed=False,
                           cancel_limitation="기록만 보존했습니다. 재연결 소유권이 없어 종료를 확인할 수 없습니다.")

    @staticmethod
    def _matches_claim(record: dict, claim: tuple[dict, str]) -> bool:
        return record["claim_sha256"] == claim[1] and all(
            record[key] == claim[0][key] for key in ("job_id", "controller_id", "argument_sha256", "store_root", "source"))

    def _unknown(self, identifier: str, reason: str):
        job = self.jobs[identifier]
        if job.get("status") != "RECOVERY_REQUIRED":
            job["retained_status"] = job.get("status", "UNKNOWN")
        job.update(status="RECOVERY_REQUIRED", outcome="UNKNOWN", recovery_reason=reason,
                   recovery_required=True)

    def _append(self, identifier: str, event: str, job: dict, details: dict | None = None):
        _, head = self._load_job(identifier)
        sequence, previous, last = head
        closing_slots = 0 if event == "RELEASED" else 1 if event == "TERMINAL" else 2
        if sequence + 2 + closing_slots > MAX_EVENTS:
            raise JournalError("HTTP job event capacity exhausted; terminal/release space is reserved; outcome is UNKNOWN")
        record = {**{key: last[key] for key in ("schema_version", "kind", "job_id", "store_root",
                  "source", "controller_id", "argument_sha256", "claim_sha256")},
                  "sequence": sequence + 1, "previous_sha256": previous, "event": event,
                  "observed_utc": utc_now(), "job": deepcopy(job), "details": details or {}}
        self._write_new(self._path("jobs", identifier, f"{sequence + 1:06d}.json"), record)

    def _observation(self, value: dict):
        if len(list(self._path("observations").iterdir())) >= MAX_EVENTS:
            raise JournalError("HTTP recovery observation capacity exhausted; outcome is UNKNOWN")
        self._write_new(self._path("observations", uuid.uuid4().hex + ".json"), value)

    def _release(self, identifier: str):
        claim = self._claim()
        _, head = self._load_job(identifier)
        if claim is None:
            if head[2]["event"] == "RELEASED":
                return
            raise JournalError("HTTP terminal claim is missing")
        if (not self._matches_claim(head[2], claim)
                or head[2]["event"] not in {"TERMINAL", "RELEASED"}):
            raise JournalError("HTTP terminal cannot release another claim")
        if head[2]["event"] == "TERMINAL":
            self._append(identifier, "RELEASED", head[2]["job"], {
                "observer_id": self.controller_id, "basis": "matching retained terminal and claim only"})
        self._path("claim.json").unlink()
        self._sync_directory(self.root)

    def recover(self):
        try:
            with self._locked():
                claim = self._scan()
                if self.errors:
                    for identifier, head in self._heads.items():
                        if head[2]["event"] != "RELEASED":
                            self._unknown(identifier, "HTTP recovery evidence is uncertain; outcome is UNKNOWN")
                if claim and not self.errors:
                    identifier = claim[0]["job_id"]
                    head = self._heads[identifier]
                    if head[2]["event"] in {"TERMINAL", "RELEASED"}:
                        self._release(identifier)
                    else:
                        reason = "HTTP controller ownership is unresolved; native outcome is UNKNOWN"
                        self.errors.append(reason)
                        self._unknown(identifier, reason)
                        try:
                            self._observation({
                                "schema_version": 1, "kind": "HTTP_RECOVERY_OBSERVATION",
                                "job_id": identifier, "head_sha256": head[1], "store_root": str(self.store),
                                "observer_id": self.controller_id, "observed_utc": utc_now(), "outcome": "UNKNOWN"})
                        except JournalError as error:
                            self.errors.append(str(error))
                if len(self.jobs) >= MAX_JOBS:
                    self.errors.append("HTTP journal job capacity reached; new admission is refused")
        except (OSError, ValueError) as error:
            self.errors.append(str(error))
            for identifier in self.jobs:
                head = self._heads.get(identifier)
                if head is None or head[2]["event"] != "RELEASED":
                    self._unknown(identifier, str(error))
        finally:
            # A malformed claim must not bypass valid independent intent.
            self._restore_cancel_intents()

    def reserve(self, job: dict, arguments: dict):
        with self._locked():
            claim = self._scan()
            if self.errors or claim is not None:
                raise JournalError("HTTP recovery is required before new execution")
            if len(self.jobs) >= MAX_JOBS:
                raise JournalError("HTTP journal job capacity reached; new admission is refused")
            minimum_events = 5 if job.get("operation") == "research_run" else 4
            if MAX_EVENTS < minimum_events:
                raise JournalError("HTTP job event capacity cannot retain start/terminal/release; new admission is refused")
            identifier = job["id"]
            if not JOB_ID.fullmatch(identifier) or identifier in self.jobs:
                raise JournalError("HTTP job ID is invalid or already retained")
            argument_hash = canonical_hash(arguments)
            claim = {"schema_version": 1, "kind": "HTTP_JOB_CLAIM", "job_id": identifier,
                     "store_root": str(self.store), "source": self.source,
                     "controller_id": self.controller_id, "argument_sha256": argument_hash,
                     "nonce": uuid.uuid4().hex, "created_utc": utc_now()}
            digest = self._write_new(self._path("claim.json"), claim)
            self._path("jobs", identifier).mkdir()
            self._sync_directory(self._path("jobs"))
            self._write_new(self._path("jobs", identifier, "000000.json"), {
                **{key: claim[key] for key in ("schema_version", "job_id", "store_root", "source",
                                              "controller_id", "argument_sha256")},
                "kind": "HTTP_JOB_EVENT", "claim_sha256": digest, "sequence": 0,
                "previous_sha256": None, "event": "ADMITTED", "observed_utc": utc_now(),
                "job": deepcopy(job), "details": {"launch_intent": True}})

    def append(self, identifier: str, event: str, job: dict, *, details: dict | None = None):
        if event not in EVENTS - {"ADMITTED", "RELEASED"}:
            raise JournalError("Unsupported HTTP event")
        if event == "TERMINAL" and (job.get("status") not in TERMINALS or job.get("cleanup_pending") is not False):
            raise JournalError("Unconfirmed HTTP terminal cannot release admission")
        with self._locked():
            claim = self._claim()
            if (claim is None or claim[0]["job_id"] != identifier
                    or claim[0]["controller_id"] != self.controller_id):
                raise JournalError("HTTP event requires its live controller claim")
            _, head = self._load_job(identifier)
            if not self._matches_claim(head[2], claim):
                raise JournalError("HTTP event claim differs from admission")
            self._append(identifier, event, job, details)
            if event == "TERMINAL":
                self._release(identifier)

    def cancellation_intent(self, identifier: str):
        """Retain a recovered request; it conveys no reconnect/stop authority."""
        with self._locked():
            self._observation({
                "schema_version": 1, "kind": "HTTP_RECOVERED_CANCEL_REQUEST",
                "job_id": identifier, "store_root": str(self.store),
                "observer_id": self.controller_id, "observed_utc": utc_now(),
                "cancel_requested": True, "cancel_observed": False, "outcome": "UNKNOWN"})
