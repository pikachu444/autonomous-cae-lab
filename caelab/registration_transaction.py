"""Core-owned recovery for a bounded group of filesystem revisions.

Adapters prepare private native bytes. This module does not interpret them.
Cooperating Lab writers use the store lock; foreign edits cause a conflict.
Process interruption and injected write failures are covered, not power loss
or exclusion of noncooperating GUI writers between the final check and replace.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from .storage import check_id, load_json, utc_now


TERMINAL = {"COMMITTED", "ROLLED_BACK", "ABORTED"}
HASH = re.compile(r"^[0-9a-f]{64}$")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                       allow_nan=False) + "\n").encode("utf-8")


def file_hash(path: Path) -> str | None:
    return digest(path.read_bytes()) if path.is_file() else None


def _sync_directory(path: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _atomic_bytes(path: Path, data: bytes) -> None:
    """Write one file atomically, retaining transaction before/after images."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".caelab-registration-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _inside(root: Path, path: Path) -> Path:
    path = path.absolute()
    resolved = path.resolve()
    if resolved != path or not resolved.is_relative_to(root.resolve()):
        raise ValueError("REGISTRATION_PATH_INVALID: replacement must stay inside its owned root without symlinks")
    if path.exists() and not path.is_file():
        raise ValueError("REGISTRATION_PATH_INVALID: expected a regular file")
    return resolved


def _target(store: Path, path: Path) -> Path:
    target = _inside(store, path)
    relative = target.relative_to(store)
    if relative.parts[0] in {"experiments", "registration_transactions", "registration_preparations", ".registration.lock"}:
        raise ValueError("REGISTRATION_PATH_INVALID: cannot replace experiments or transaction controls")
    return target


def journals(store: Path):
    root = store / "registration_transactions"
    if not root.exists():
        return
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError("REGISTRATION_JOURNAL_INVALID: unexpected transaction path")
        path = folder / "journal.json"
        if not path.is_file() or path.is_symlink():
            raise ValueError("REGISTRATION_JOURNAL_INVALID: missing journal; preserve the folder")
        value = load_json(path)
        if (not isinstance(value, dict) or value.get("schema") != 1 or
                value.get("state") not in TERMINAL | {"PREPARING", "PREPARED", "CONFLICT"} or
                not isinstance(value.get("files"), list)):
            raise ValueError("REGISTRATION_JOURNAL_INVALID: unsupported recovery record")
        check_id(value.get("study_id"))
        yield folder, value


def assert_no_pending(store: Path) -> None:
    pending = [folder.name for folder, value in journals(store) if _pending(folder, value)]
    if pending:
        raise ValueError("REGISTRATION_RECOVERY_REQUIRED: pending transaction " + ", ".join(pending))


def _pending(folder: Path, value: dict) -> bool:
    return value["state"] not in TERMINAL or (folder / "pending").exists()


class RegistrationTransaction:
    def __init__(self, store: Path, study_id: str):
        self.store = store.resolve()
        name = "T-" + uuid.uuid4().hex
        self.folder = self.store / "registration_preparations" / name
        published = self.store / "registration_transactions" / name
        if (self.folder.resolve() != self.folder or published.resolve() != published or
                not self.folder.is_relative_to(self.store) or not published.is_relative_to(self.store)):
            raise ValueError("REGISTRATION_PATH_INVALID: initial journal roots escaped the store")
        self.folder.mkdir(parents=True, exist_ok=False)
        self.value = {"schema": 1, "study_id": check_id(study_id), "state": "PREPARING",
                      "created_utc": utc_now(), "files": []}
        self._write_journal()
        # A failed first write or an early process exit stays private. No live
        # replacement is possible before a complete journal becomes visible.
        published.parent.mkdir(parents=True, exist_ok=True)
        if published.exists():
            raise FileExistsError("Registration journal ID already exists")
        self.folder.rename(published)
        self.folder = published
        _sync_directory(published.parent)

    @classmethod
    def open(cls, store: Path, folder: Path, value: dict):
        instance = cls.__new__(cls)
        instance.store, instance.folder, instance.value = store.resolve(), folder, value
        return instance

    @property
    def work(self) -> Path:
        output = self.folder / "work"
        output.mkdir(exist_ok=True)
        return output

    def _write_journal(self) -> None:
        _atomic_bytes(self.folder / "journal.json", json_bytes(self.value))

    def add(self, target: Path, prepared: Path, before_sha256: str | None,
            after_sha256: str) -> None:
        if self.value["state"] != "PREPARING":
            raise ValueError("Registration images are already frozen")
        target = _target(self.store, target)
        prepared = _inside(self.folder, prepared)
        if not HASH.fullmatch(after_sha256) or (before_sha256 is not None and not HASH.fullmatch(before_sha256)):
            raise ValueError("REGISTRATION_IMAGE_INVALID: expected SHA256")
        relative = target.relative_to(self.store).as_posix()
        if any(row["target"] == relative for row in self.value["files"]):
            raise ValueError("REGISTRATION_IMAGE_INVALID: duplicate target")
        before = target.read_bytes() if target.is_file() else None
        after = prepared.read_bytes()
        if (None if before is None else digest(before)) != before_sha256 or digest(after) != after_sha256:
            raise ValueError("REGISTRATION_SOURCE_CHANGED: prepare images no longer match")
        number = len(self.value["files"])
        for kind, data in (("before", before), ("after", after)):
            if data is not None:
                _atomic_bytes(self.folder / kind / f"{number:04d}.bin", data)
        self.value["files"].append({"target": relative, "before": before_sha256,
                                   "after": after_sha256,
                                   "before_size": None if before is None else len(before),
                                   "after_size": len(after)})

    def prepare(self) -> None:
        if self.value["state"] != "PREPARING" or not self.value["files"]:
            raise ValueError("REGISTRATION_IMAGE_INVALID: no prepared revisions")
        self._validated_images()
        self.value["state"] = "PREPARED"
        self._write_journal()
        # A marker-write error after os.replace must not look acknowledged.
        _atomic_bytes(self.folder / "pending", b"UNACKNOWLEDGED_REGISTRATION\n")

    def abort_preparation(self, reason: str) -> None:
        if self.value["state"] == "PREPARING":
            self.value.update(state="ABORTED", completed_utc=utc_now(), reason=reason)
            self._write_journal()

    def _validated_images(self):
        records, targets = [], set()
        for number, row in enumerate(self.value["files"]):
            relative = row.get("target")
            if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("REGISTRATION_IMAGE_INVALID: invalid target")
            target = _target(self.store, self.store / relative)
            if target in targets:
                raise ValueError("REGISTRATION_IMAGE_INVALID: duplicate target")
            targets.add(target)
            images = {}
            for kind in ("before", "after"):
                expected = row.get(kind)
                if expected is None and kind == "before":
                    images[kind] = None
                    continue
                if not isinstance(expected, str) or not HASH.fullmatch(expected):
                    raise ValueError("REGISTRATION_IMAGE_INVALID: invalid image hash")
                image = _inside(self.folder, self.folder / kind / f"{number:04d}.bin")
                data = image.read_bytes()
                if digest(data) != expected or len(data) != row.get(kind + "_size"):
                    raise ValueError("REGISTRATION_IMAGE_INVALID: recovery image changed")
                images[kind] = data
            records.append((target, row, images))
        return records

    def commit(self) -> None:
        if self.value["state"] != "PREPARED":
            raise ValueError("REGISTRATION_RECOVERY_REQUIRED: transaction is not prepared")
        records = self._validated_images()
        if any(file_hash(target) != row["before"] for target, row, _ in records):
            raise ValueError("REGISTRATION_SOURCE_CHANGED: original revisions changed before publication")
        for target, row, images in records:
            if file_hash(target) != row["before"]:
                raise ValueError("REGISTRATION_SOURCE_CHANGED: target changed before publication")
            _atomic_bytes(target, images["after"])
        if any(file_hash(target) != row["after"] for target, row, _ in records):
            raise ValueError("REGISTRATION_RECOVERY_REQUIRED: publication did not persist")
        self.value.update(state="COMMITTED", completed_utc=utc_now())
        self._write_journal()
        self._acknowledge()

    def _acknowledge(self) -> None:
        # Keep the recovery gate until the final fallible filesystem action.
        # Images and the completed journal are already synced. Do not add a
        # post-unlink fsync that can fail after the gate has disappeared.
        # Power-loss durability of this acknowledgement remains unqualified.
        _sync_directory(self.folder)
        (self.folder / "pending").unlink(missing_ok=True)

    def rollback(self) -> dict:
        if not _pending(self.folder, self.value):
            return {"transaction_id": self.folder.name, "status": self.value["state"]}
        # Validate ALL images and targets before changing any public byte.
        records = self._validated_images()
        if any(file_hash(target) not in {row["before"], row["after"]} for target, row, _ in records):
            self.value.update(state="CONFLICT", reason="FOREIGN_TARGET_BYTES")
            self._write_journal()
            raise ValueError("REGISTRATION_RECOVERY_CONFLICT: preserve external target bytes")
        for target, row, images in reversed(records):
            current = file_hash(target)
            if current not in {row["before"], row["after"]}:
                raise ValueError("REGISTRATION_RECOVERY_CONFLICT: target changed during recovery")
            if current == row["before"]:
                continue
            if images["before"] is None:
                target.unlink()
                _sync_directory(target.parent)
            else:
                _atomic_bytes(target, images["before"])
        if any(file_hash(target) != row["before"] for target, row, _ in records):
            raise ValueError("REGISTRATION_RECOVERY_REQUIRED: rollback did not persist")
        self.value.update(state="ROLLED_BACK", completed_utc=utc_now())
        self._write_journal()
        self._acknowledge()
        return {"transaction_id": self.folder.name, "status": "ROLLED_BACK"}


def recover(store: Path, study_id: str) -> list[dict]:
    check_id(study_id)
    return [RegistrationTransaction.open(store, folder, value).rollback()
            for folder, value in journals(store) if value["study_id"] == study_id and _pending(folder, value)]
