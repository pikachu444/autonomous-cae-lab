"""Read-only reports and portable bundles of Core-verified local evidence.

The local ledger detects changed bytes; it is not a cryptographic signature or
an engineering approval. No backend-specific file names or solver rules belong
in this module.
"""

from copy import deepcopy
import hashlib
from html import escape
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import zipfile

from caelab.storage import canonical_hash, check_id


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}
_LIMITATIONS = {
    "scope": "LOCAL_PORTABLE_EXPORT",
    "ledger": "Same-store byte hashes; not a cryptographic signature",
    "study": "Current study metadata snapshot; not a historical signed record",
    "remote_durability": False,
    "cryptographically_signed": False,
    "physical_validation": False,
    "engineering_release": False,
    "description": "로컬 파일 검증 및 휴대용 내보내기입니다. 원격 보존, 전자서명, 물리 검증 또는 출하 승인을 뜻하지 않습니다.",
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _relative(path):
    """Accept one portable, unambiguous POSIX relative file name."""
    if (not isinstance(path, str) or not path or "\x00" in path or "\\" in path
            or ":" in path or PurePosixPath(path).is_absolute()
            or PureWindowsPath(path).drive
            or any(part in ("", ".", "..") for part in path.split("/"))):
        raise ValueError(f"Unsafe artifact path: {path!r}")
    # A Linux store can contain names that Windows normalizes while extracting
    # a ZIP. Refuse aliases/devices rather than silently changing verified names.
    for part in path.split("/"):
        if (part.endswith((".", " ")) or any(char in '<>"|?*' or ord(char) < 32 for char in part)
                or part.split(".", 1)[0].rstrip(" ").upper() in _WINDOWS_RESERVED):
            raise ValueError(f"Unsafe artifact path: {path!r}")
    return path


def _casefold_paths(paths, *, reserved=()):
    """Refuse portable aliases across the complete set, never rename bytes."""
    reserved_names = {path.casefold() for path in reserved}
    seen = {path.casefold(): path for path in reserved}
    for path in paths:
        _relative(path)
        folded = path.casefold()
        if folded in seen and (seen[folded] != path or folded in reserved_names):
            raise ValueError(f"Case-insensitive export path collision: {seen[folded]} / {path}")
        seen[folded] = path


def _inside(root, path, *, directory=False):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f"Path escapes verified root: {path.name}")
    if not (resolved.is_dir() if directory else resolved.is_file()):
        raise ValueError(f"Expected {'directory' if directory else 'file'}: {path.name}")
    return resolved


def _read(root, path, *, expected=None, size=None):
    """Check containment and byte identity again when collecting an export."""
    resolved = _inside(root, path)
    with resolved.open("rb") as stream:
        before = os.fstat(stream.fileno())
        data = stream.read()
        after = os.fstat(stream.fileno())
    current = _inside(root, path)
    stat = current.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if resolved != current or identity(before) != identity(after) or identity(after) != identity(stat):
        raise ValueError(f"File changed during verification: {path.name}")
    if expected is not None and _sha(data) != expected:
        raise ValueError(f"File hash mismatch: {path.name}")
    if size is not None and len(data) != size:
        raise ValueError(f"File size mismatch: {path.name}")
    return data


def _json(data):
    def bad_constant(value):
        raise ValueError(f"Nonfinite JSON value: {value}")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(data.decode("utf-8"), parse_constant=bad_constant, object_pairs_hook=unique_keys)
    if not isinstance(value, dict):
        raise ValueError("Stored document must be a JSON object")
    return value


def _expected_hash(value):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError("Invalid recorded SHA-256")
    return value


def _document(store, path, role, *, boundary=None):
    data = _read(boundary or store, path)
    return _json(data), {"path": path.relative_to(store).as_posix(),
                         "sha256": _sha(data), "size_bytes": len(data), "role": role}


def _preflight(store, identifier):
    folder = store / "experiments" / check_id(identifier)
    root = _inside(store, folder, directory=True)
    result, result_file = _document(store, folder / "result.json", "result", boundary=root)
    if result.get("experiment_id") != identifier:
        raise ValueError("Stored experiment ID mismatch")
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Artifact manifest must be a list")
    names = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("Artifact manifest entry must be a mapping")
        name = _relative(artifact.get("path"))
        if name.casefold() in names:
            raise ValueError(f"Duplicate artifact path: {name}")
        names.add(name.casefold())
        _expected_hash(artifact.get("sha256"))
        if type(artifact.get("size_bytes")) is not int or artifact["size_bytes"] < 0:
            raise ValueError(f"Invalid artifact byte size: {name}")
        _inside(root, folder / name)

    # These common documents are explicit export inputs, never a folder scan.
    thread, thread_file = _document(store, folder / "thread.json", "thread", boundary=root)
    proposal, proposal_file = _document(store, folder / "proposal.json", "proposal", boundary=root)
    ledger, ledger_file = _document(store, store / "ledger" / f"{identifier}.json", "ledger")
    study_id = check_id(result["study"]["id"])
    study, study_file = _document(store, store / "studies" / study_id / "study.json", "study")
    if (ledger.get("experiment_id") != identifier or proposal.get("id") != identifier
            or proposal.get("study_id") != study_id or thread.get("experiment") != identifier
            or thread.get("study") != study_id):
        raise ValueError("Stored document identity mismatch")
    for label, info in (("result", result_file), ("thread", thread_file)):
        if _expected_hash(ledger.get(f"{label}_sha256")) != info["sha256"]:
            raise ValueError(f"{label}.json hash mismatch")
    if canonical_hash(proposal) != result["provenance"]["proposal_sha256"]:
        raise ValueError("Proposal canonical hash mismatch")
    documents = [result_file, thread_file, proposal_file, ledger_file, study_file]
    registry = None
    registry_file = None
    registry_path = folder / "registry_snapshot.json"
    if registry_path.exists() or registry_path.is_symlink():
        registry, registry_file = _document(store, registry_path, "registry_snapshot", boundary=root)
        if canonical_hash(registry) != result["provenance"]["registry_sha256"]:
            raise ValueError("Registry snapshot canonical hash mismatch")
        documents.append(registry_file)
    return {
        "result": result, "proposal": proposal, "thread": thread, "study": study,
        "registry_snapshot": registry, "ledger": ledger, "integrity": "VERIFIED",
        "hashes": {"result_sha256": result_file["sha256"], "thread_sha256": thread_file["sha256"],
                   "proposal_sha256": proposal_file["sha256"], "ledger_sha256": ledger_file["sha256"],
                   "study_sha256": study_file["sha256"],
                   "registry_snapshot_sha256": registry_file["sha256"] if registry_file else None,
                   "artifacts": deepcopy(artifacts), "documents": documents},
        "parent_chain": [], "limitations": deepcopy(_LIMITATIONS),
    }


def _source_files(record):
    """One exact expected-byte set, deduplicating manifest common documents."""
    identifier = record["result"]["experiment_id"]
    revision = (record["result"].get("cad_revision") or record["result"].get("model_revision")
                or record["result"].get("proposal_revision"))
    _casefold_paths([*(document["path"] for document in record["hashes"]["documents"]),
                     *(f"experiments/{identifier}/{artifact['path']}" for artifact in record["result"]["artifacts"])])
    files = {}
    for document in record["hashes"]["documents"]:
        files[document["path"]] = {**document, "source_experiment_id": identifier, "revision": revision}
    for artifact in record["result"]["artifacts"]:
        path = f"experiments/{identifier}/{artifact['path']}"
        entry = {"path": path, "sha256": artifact["sha256"], "size_bytes": artifact["size_bytes"],
                 "role": "artifact", "source_experiment_id": identifier, "revision": artifact.get("revision"),
                 "mime_type": artifact.get("mime_type")}
        if path in files:
            if any(files[path][key] != entry[key] for key in ("sha256", "size_bytes")):
                raise ValueError(f"Manifest/document hash mismatch: {path}")
            files[path].update(revision=entry["revision"], mime_type=entry["mime_type"])
        else:
            files[path] = entry
    return files


def _all_source_files(records, *, reserved=()):
    sources = [(record, _source_files(record)) for record in records]
    _casefold_paths((path for _, files in sources for path in files), reserved=reserved)
    return sources


def _recheck(store, records):
    # Evaluate the entire chain before reading its first file: two individually
    # safe experiments can otherwise collide on a case-insensitive filesystem.
    for record, files in _all_source_files(records):
        identifier = record["result"]["experiment_id"]
        folder = store / "experiments" / identifier
        root = _inside(store, folder, directory=True)
        for entry in files.values():
            path = store / entry["path"]
            boundary = root if entry["path"].startswith(f"experiments/{identifier}/") else store
            _read(boundary, path, expected=entry["sha256"], size=entry["size_bytes"])


def preflight_records(lab, experiment_ids):
    """Verify one deduplicated set for an aggregate Core inspection.

    Aggregate views need paths, ledgers and payload identity, without rendering
    an unused research summary for every experiment and its parents. This set
    belongs to one call; callers recheck it after Core finishes the inspection.
    """
    store = Path(lab.store).resolve(strict=True)
    records = {}
    for requested in experiment_ids:
        identifier = check_id(requested)
        seen = set()
        while identifier:
            if identifier in seen or len(seen) >= 64:
                raise ValueError("Cyclic or excessively deep experiment parent chain")
            seen.add(identifier)
            if identifier not in records:
                records[identifier] = _preflight(store, identifier)
            parent = records[identifier]["result"].get("parent_experiment_id")
            identifier = check_id(parent) if parent is not None else None
    result = list(records.values())
    _recheck(store, result)
    return result


def recheck_records(lab, records):
    """Keep exact expected hashes, containment and race checks after inspection."""
    _recheck(Path(lab.store).resolve(strict=True), records)


def verified_record(lab, experiment_id):
    """Preflight the entire parent chain before Core reads any manifest path."""
    store = Path(lab.store).resolve(strict=True)
    identifier = check_id(experiment_id)
    records = []
    seen = set()
    while identifier:
        if identifier in seen or len(seen) >= 64:
            raise ValueError("Cyclic or excessively deep experiment parent chain")
        seen.add(identifier)
        record = _preflight(store, identifier)
        records.append(record)
        parent = record["result"].get("parent_experiment_id")
        identifier = check_id(parent) if parent is not None else None
    _recheck(store, records)
    for index, record in enumerate(records):
        if index:
            _recheck(store, records)
        identifier = record["result"]["experiment_id"]
        inspected = lab.inspect_experiment(identifier)
        if inspected != record["result"]:
            raise ValueError("Result changed during Core inspection")
        # research_summary performs a second Core inspection. Check the same
        # complete safe set again rather than passing it a newly changed path.
        _recheck(store, records)
        record["summary"] = lab.research_summary(identifier)
        if lab.inspect_study(record["result"]["study"]["id"]) != record["study"]:
            raise ValueError("Study changed during Core inspection")
    _recheck(store, records)
    records[0]["parent_chain"] = records[1:]
    return records[0]


def _text(value):
    if isinstance(value, str):
        return escape(value, quote=True)
    return escape(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False), quote=True)


def _detail(label, value):
    return f"<section><h2>{_text(label)}</h2><pre>{_text(value)}</pre></section>"


def render_html(record):
    """Render exact observations; validity and release remain separate verdicts."""
    result = record["result"]
    metrics = "".join(
        "<tr>" + "".join(f"<td>{_text(value)}</td>" for value in (
            name, metric.get("value"), metric.get("unit"), metric.get("valid"), metric.get("reason"))) + "</tr>"
        for name, metric in result["metrics"].items())
    artifacts = "".join(
        "<tr>" + "".join(f"<td>{_text(artifact.get(key))}</td>" for key in (
            "path", "sha256", "size_bytes", "revision")) + "</tr>"
        for artifact in result["artifacts"])
    title = f"Autonomous CAE Lab · {result['experiment_id']}"
    sections = [
        _detail("연구와 가설 (현재 연구 메타데이터)", record["study"]),
        _detail("실행 입력과 공통 모델 선언", record["proposal"]),
        _detail("실제 입력 매개변수", result["input_parameters"]),
        _detail("실행 및 판정", {key: result.get(key) for key in (
            "status", "solver_status", "converged", "decision")}),
        '<section><h2>수치 관측값</h2><table><thead><tr><th>지표</th><th>값</th><th>단위</th>'
        '<th>유효 여부</th><th>무효 사유</th></tr></thead><tbody>' + metrics + '</tbody></table></section>',
        _detail("독립 검증 판정과 UNKNOWN 항목", result["validations"]),
        _detail("검증 근거 (전체 evidence)", result["evidence"]),
        _detail("리비전과 실행 출처", {key: result.get(key) for key in (
            "cad_revision", "model_revision", "proposal_revision", "registry_revision", "provenance")}),
        _detail("연구 요약", record["summary"]),
        _detail("연결 기록 (thread)", record["thread"]),
        _detail("레지스트리 스냅샷", record["registry_snapshot"]),
        _detail("원본 ledger와 실제 파일 SHA-256", {"ledger": record["ledger"], "hashes": record["hashes"]}),
        '<section><h2>등록된 원본·가공 파일</h2><table><thead><tr><th>상대 경로</th><th>SHA-256</th>'
        '<th>바이트</th><th>리비전</th></tr></thead><tbody>' + artifacts + '</tbody></table></section>',
        _detail("부모 CAD 연결 기록", record.get("parent_chain", [])),
        _detail("내보내기 범위와 한계", record["limitations"]),
    ]
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{_text(title)}</title><style>'
            'body{font-family:system-ui,sans-serif;max-width:1100px;margin:32px auto;padding:0 20px;line-height:1.6;color:#17212b}'
            'h1{font-size:1.6rem}h2{font-size:1.15rem}section{margin:28px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;'
            'background:#f2f5f7;padding:14px;border-radius:8px}table{border-collapse:collapse;width:100%;font-size:.9rem}'
            'td,th{border:1px solid #ced7df;padding:8px;text-align:left;overflow-wrap:anywhere}p{padding:12px;background:#fff4d8}'
            '</style></head><body>' + f'<h1>{_text(title)}</h1><div>파일 무결성: {_text(record["integrity"])}</div>'
            '<p>솔버 실행 상태와 수치 검증 판정은 별도로 기록합니다. UNKNOWN은 미검증이며, '
            '실행 완료나 수치 PASS가 강도 검증 또는 RELEASED를 뜻하지 않습니다.</p>'
            + "".join(sections) + '</body></html>')


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def bundle_bytes(lab, experiment_id):
    """Export only verified named bytes, preserving the local parent chain."""
    record = verified_record(lab, experiment_id)
    store = Path(lab.store).resolve(strict=True)
    records = [record, *record["parent_chain"]]
    payloads = {}
    manifest_files = {}
    sources = _all_source_files(records, reserved=("report.html", "report.json", "bundle_manifest.json"))
    for source, files in sources:
        identifier = source["result"]["experiment_id"]
        root = _inside(store, store / "experiments" / identifier, directory=True)
        for path, entry in files.items():
            _relative(path)
            boundary = root if path.startswith(f"experiments/{identifier}/") else store
            data = _read(boundary, store / path, expected=entry["sha256"], size=entry["size_bytes"])
            if path in payloads:
                if payloads[path] != data:
                    raise ValueError(f"Shared export document changed: {path}")
                continue
            payloads[path] = data
            manifest_files[path] = entry
    root_result = record["result"]
    revision = root_result.get("cad_revision") or root_result.get("model_revision") or root_result.get("proposal_revision")
    for path, data in (("report.json", _json_bytes(record)), ("report.html", render_html(record).encode("utf-8"))):
        payloads[path] = data
        manifest_files[path] = {"path": path, "sha256": _sha(data), "size_bytes": len(data), "role": "report",
                                "source_experiment_id": root_result["experiment_id"], "revision": revision}
    _recheck(store, records)
    manifest = {"schema_version": "1.0", "integrity": "VERIFIED", "export_type": "LOCAL_PORTABLE_EXPORT",
                "experiment_id": root_result["experiment_id"], "limitations": deepcopy(_LIMITATIONS),
                "files": [manifest_files[path] for path in sorted(manifest_files)]}
    payloads["bundle_manifest.json"] = _json_bytes(manifest)
    _casefold_paths(payloads)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(payloads):
            archive.writestr(path, payloads[path])
    return output.getvalue()
