"""Small append-only filesystem store for versioned experiments and evidence."""

from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any


SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".caelab-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                                allow_nan=False) + "\n")
    temporary.replace(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_manifest(folder: Path, *, revision: str) -> list[dict[str, Any]]:
    records = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if rel in ("result.json", "thread.json"):
            continue
        records.append({"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "size_bytes": path.stat().st_size,
                        "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                        "revision": revision})
    return records


def check_artifacts(folder: Path, artifacts: list[dict[str, Any]]) -> list[str]:
    corrupt = []
    for record in artifacts:
        path = folder / record["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            corrupt.append(record["path"])
    return corrupt


def check_id(identifier: str) -> str:
    if not isinstance(identifier, str) or not SAFE_ID.fullmatch(identifier):
        raise ValueError("Invalid study or experiment ID")
    return identifier


def source_identity(root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                         text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"],
                                             cwd=root, text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unavailable", None
    files = [*sorted((root / "caelab").rglob("*.py")), *sorted((root / "schemas").glob("*.json"))]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {"core_commit": commit, "core_dirty": dirty, "core_source_sha256": digest.hexdigest()}
