"""Retained human file transport; native document semantics remain in the adapter."""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import re
import uuid
import zipfile

from caelab.storage import check_id, source_identity, utc_now


MIN_NATIVE_BYTES = 100
MAX_NATIVE_BYTES = 25 * 1024 * 1024  # Same bound as the pinned native importer.
MAX_METADATA_BYTES = 2 * 1024 * 1024
IMPORT_ID = re.compile(r"^U[0-9a-f]{32}$")


def folder(store, identifier):
    from .service import contained
    if not isinstance(identifier, str) or not IMPORT_ID.fullmatch(identifier):
        raise ValueError("A retained native input ID is required")
    return contained(Path(store), "native_imports/" + identifier)


def _read(path, maximum):
    with path.open("rb") as stream:
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError("Retained native input or metadata exceeds its bound")
    return payload


def _entry(payload):
    return {"sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}


def _json(payload):
    def pairs(items):
        value = {}
        for name, item in items:
            if name in value:
                raise ValueError("Duplicate native input metadata key")
            value[name] = item
        return value
    def constant(_value):
        raise ValueError("Non-finite native input metadata")
    value = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError("Native input metadata must be an object")
    return value


def _transport_source():
    return {name: _entry((Path(__file__).parent / name).read_bytes())
            for name in ("native_input.py", "server.py", "service.py")}


def _write_new(path, payload):
    with path.open("xb") as stream:
        stream.write(payload)


def _save_new(path, value):
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                          allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > MAX_METADATA_BYTES:
        raise ValueError("Native import metadata exceeds its bound")
    _write_new(path, payload)
    return _entry(payload)


def validate_payload(payload):
    if not isinstance(payload, bytes) or not MIN_NATIVE_BYTES <= len(payload) <= MAX_NATIVE_BYTES:
        raise ValueError("FCStd input must be 100 bytes to 25 MiB")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if "Document.xml" not in archive.namelist():
                raise ValueError("Editable FreeCAD document history is required")
    except zipfile.BadZipFile as error:
        raise ValueError("An editable FreeCAD FCStd archive is required") from error
    # No archive is extracted or geometry inferred here. Existing native inspection
    # and final-solid/parameter checks still run inside Lab.import_native_model.


def retain_input(store, payload):
    validate_payload(payload)
    identifier = "U" + uuid.uuid4().hex
    root = folder(store, identifier)
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(exist_ok=False)
    _write_new(root / "original.FCStd", payload)
    receipt = {"schema_version": 1, "kind": "CAELAB_NATIVE_INPUT", "id": identifier,
               "created_utc": utc_now(), "filename": "original.FCStd",
               "input": _entry(payload), "step": "HUMAN_FILE_TRANSPORT",
               "transport_source": _transport_source()}
    receipt_pin = _save_new(root / "input.json", receipt)
    capture = {"id": identifier, "input": receipt["input"], "receipt": receipt_pin}
    verified_input(store, capture)
    return capture


def verified_input(store, capture):
    if not isinstance(capture, dict) or set(capture) != {"id", "input", "receipt"}:
        raise ValueError("Native input capture is required")
    root = folder(store, capture["id"])
    from .service import contained
    original = contained(Path(store), f"native_imports/{capture['id']}/original.FCStd")
    receipt_path = contained(Path(store), f"native_imports/{capture['id']}/input.json")
    receipt_bytes = _read(receipt_path, MAX_METADATA_BYTES)
    if _entry(receipt_bytes) != capture["receipt"]:
        raise ValueError("Native input receipt changed")
    receipt = _json(receipt_bytes)
    if (receipt.get("kind") != "CAELAB_NATIVE_INPUT" or receipt.get("schema_version") != 1
            or receipt.get("id") != capture["id"] or receipt.get("filename") != "original.FCStd"
            or receipt.get("input") != capture["input"]):
        raise ValueError("Native input receipt does not match its capture")
    payload = _read(original, MAX_NATIVE_BYTES)
    if _entry(payload) != capture["input"]:
        raise ValueError("Retained original native bytes changed")
    return original, receipt


def producer_identity(store, capture):
    _original, receipt = verified_input(store, capture)
    if receipt.get("transport_source") != _transport_source():
        raise ValueError("Native import transport source changed")
    # The potentially slow Git probe runs inside the already admitted job.
    return source_identity(Path(__file__).resolve().parents[2])


def retain_result(store, capture, info, producer):
    _original, receipt = verified_input(store, capture)
    if receipt.get("transport_source") != _transport_source():
        raise ValueError("Native import transport source changed")
    if not isinstance(info, dict) or not isinstance(info.get("design"), str):
        raise ValueError("Native importer did not return a model ID")
    model = check_id(info["design"])
    if info.get("source_sha256") != capture["input"]["sha256"]:
        raise ValueError("Imported native revision differs from the retained original")
    root = folder(store, capture["id"])
    result = {"schema_version": 1, "kind": "CAELAB_NATIVE_IMPORT", "id": capture["id"],
              "capture": deepcopy(capture), "model": model, "prepared_utc": utc_now(),
              "native_result": deepcopy(info),
              "producer": deepcopy(producer)}
    pin = _save_new(root / "import.json", result)
    verified_input(store, capture)
    _save_new(root / "import-receipt.json", {"schema_version": 1, "id": capture["id"], "result": pin,
              "status": "COMPLETED", "completed_utc": utc_now()})
    return {**deepcopy(info), "native_import": {"id": capture["id"], "input": deepcopy(capture["input"]),
            "original_integrity": "VERIFIED", "kind": "FCStd", "model": model}}


def inspect_import(store, identifier, *, verify_original=True):
    from .service import contained
    root = folder(store, identifier)
    result_path = contained(Path(store), f"native_imports/{identifier}/import.json")
    result_bytes = _read(result_path, MAX_METADATA_BYTES)
    pin_bytes = _read(contained(Path(store), f"native_imports/{identifier}/import-receipt.json"), MAX_METADATA_BYTES)
    pin = _json(pin_bytes)
    if (pin.get("schema_version") != 1 or pin.get("id") != identifier
            or pin.get("status") != "COMPLETED" or not isinstance(pin.get("completed_utc"), str)
            or pin.get("result") != _entry(result_bytes)):
        raise ValueError("Native import record changed")
    result = _json(result_bytes)
    info, capture = result.get("native_result"), result.get("capture")
    if (result.get("kind") != "CAELAB_NATIVE_IMPORT" or result.get("schema_version") != 1
            or result.get("id") != identifier or not isinstance(info, dict)
            or result.get("model") != info.get("design") or not isinstance(capture, dict)
            or set(capture) != {"id", "input", "receipt"} or capture.get("id") != identifier
            or not isinstance(capture.get("input"), dict)
            or info.get("source_sha256") != capture["input"].get("sha256")):
        raise ValueError("Native import record identity is invalid")
    check_id(result["model"])
    if verify_original:
        verified_input(store, result["capture"])
    return {"id": identifier, "model": result["model"], "created_utc": pin["completed_utc"],
            "document": result["native_result"].get("document"), "input": result["capture"]["input"],
            "original_integrity": "VERIFIED" if verify_original else "NOT_CHECKED",
            "imported_revision": result["native_result"]["source_sha256"],
            "current_native_revision": "NOT_CHECKED"}


def list_imports(store, limit=50):
    from .service import contained
    root = contained(Path(store), "native_imports")
    folders = sorted((path for path in root.iterdir() if path.is_dir()),
                     key=lambda path: path.stat().st_mtime_ns, reverse=True) if root.exists() else []
    rows = []
    for path in folders[:limit]:
        try:
            rows.append(inspect_import(store, path.name, verify_original=False))
        except (ValueError, OSError, KeyError, TypeError) as error:
            rows.append({"id": path.name, "status": "UNCONFIRMED", "original_integrity": "NOT_CHECKED",
                         "error": f"{type(error).__name__}: {error}"})
    return {"imports": rows, "omitted": max(0, len(folders) - limit), "limit": limit}
