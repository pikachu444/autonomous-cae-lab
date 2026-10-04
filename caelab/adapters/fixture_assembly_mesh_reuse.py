"""Internal byte reuse of a trusted assembly preprocessing bundle.

Constructor pins are operator configuration, never research settings. Initial
verification reuses the original captured numerical verifier; later rechecks
only verify bytes and the live CAD parent. This is not mechanics admission.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from types import ModuleType


_OUTPUTS = frozenset(("mesh.msh", "mapping.json", "jacobians.npz", "jacobian_metadata.json",
                     "mesher.log", "imported_geometry.json", "quality.json", "lifecycle.json"))
_SOURCES = frozenset(("fixture_assembly_mesh.py", "fixture_assembly_mesh_worker.py",
                     "assembly_mesh.py", "gmsh.py"))
_RECEIPT = "mesh-reuse-receipt.json"
_LOAD_POLICY = "Pinned bytes compile/exec; complete capsule membership; exact Domain-only standalone hook; no pyc/cache or global setting"


@dataclass(frozen=True)
class _Pin:
    sha256: str
    size_bytes: int

    def value(self):
        return {"sha256": self.sha256, "size_bytes": self.size_bytes}


def _pin(value) -> _Pin:
    if not isinstance(value, dict) or set(value) != {"sha256", "size_bytes"}:
        raise ValueError("Malformed trusted byte pin")
    digest, size = value["sha256"], value["size_bytes"]
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None or type(size) is not int or size < 0:
        raise ValueError("Malformed trusted hash/size")
    return _Pin(digest, size)


def _name(value) -> str:
    if not isinstance(value, str) or not value or any(c in value for c in "\\:") or any(ord(c) < 32 for c in value):
        raise ValueError("Unsafe reuse artifact path")
    parts = value.split("/")
    for part in parts:
        stem = part.split(".", 1)[0].upper()
        if not part or part in (".", "..") or part.endswith((".", " ")) or stem in {"CON", "PRN", "AUX", "NUL", "CLOCK$"} or re.fullmatch(r"(?:COM|LPT)[1-9]", stem):
            raise ValueError("Unsafe reuse artifact path")
    return value


def _map(value) -> tuple:
    if not isinstance(value, dict) or not value:
        raise ValueError("Complete nonempty trusted byte map required")
    result, folded = {}, set()
    for name, pin in value.items():
        name = _name(name)
        if name in result or name.casefold() in folded:
            raise ValueError("Duplicate/aliased trusted artifact path")
        result[name] = _pin(pin)
        folded.add(name.casefold())
    names = sorted(result)
    if any(b.startswith(a + "/") for i, a in enumerate(names) for b in names[i + 1:]):
        raise ValueError("Trusted file/directory path collision")
    return tuple((name, result[name]) for name in names)


def _values(entries):
    return {name: pin.value() for name, pin in entries}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate reuse JSON key: " + key)
            result[key] = value
        return result
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Nonfinite reuse JSON number")
        return result
    def invalid(value):
        raise ValueError("Nonfinite reuse JSON number: " + value)
    return json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                      parse_float=number, parse_constant=invalid)


def _no_links(path: Path):
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValueError("Symlink/junction/reparse reuse path forbidden: " + str(item))
        if hasattr(item, "is_junction") and item.is_junction():
            raise ValueError("Symlink/junction/reparse reuse path forbidden: " + str(item))


def _absolute(value) -> Path:
    path = Path(value)
    if not path.is_absolute() or any(p in (".", "..") for p in path.parts):
        raise ValueError("Absolute canonical reuse root required")
    _no_links(path)
    return path.resolve()


def _safe(root: Path, name: str) -> Path:
    path = root.joinpath(*_name(name).split("/"))
    _no_links(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Escaping reuse artifact path")
    return path


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read(root: Path, name: str, expected: _Pin, *, keep=False):
    path = _safe(root, name)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink > 1:
        raise ValueError("Regular unshared reuse file required: " + name)
    parts, total, digest = [], 0, hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise ValueError("Reuse file identity changed before read: " + name)
        while block := stream.read(1024 * 1024):
            digest.update(block); total += len(block)
            if keep:
                parts.append(block)
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise ValueError("Reuse file identity changed during read: " + name)
    _no_links(path)
    if _identity(path.lstat()) != _identity(before):
        raise ValueError("Reuse file identity changed after read: " + name)
    if _Pin(digest.hexdigest(), total) != expected:
        raise ValueError("Reuse byte pin drift: " + name)
    return b"".join(parts) if keep else None, _identity(before)


def _check(root, entries, identities=None):
    observed = {name: _read(root, name, pin)[1] for name, pin in entries}
    if identities is not None and observed != identities:
        raise ValueError("Frozen reuse file identity drift")
    return observed


def _membership(root: Path, entries):
    expected = {name for name, _ in entries}
    directories = {""}
    for name in expected:
        parts = name.split("/")
        directories.update("/".join(parts[:i]) for i in range(1, len(parts)))
    found = set()
    pending = [root]
    _no_links(root)
    if not root.is_dir():
        raise ValueError("Complete reuse tree missing")
    while pending:
        base = pending.pop()
        for child in base.iterdir():
            _no_links(child)
            name = child.relative_to(root).as_posix()
            _name(name)
            if child.is_dir():
                if name not in directories:
                    raise ValueError("Unexpected reuse tree member (cache forbidden): " + name)
                pending.append(child)
            elif child.is_file() and name in expected:
                found.add(name)
            else:
                raise ValueError("Unexpected reuse tree member (cache forbidden): " + name)
    if found != expected:
        raise ValueError("Incomplete reuse tree membership")


def _overlap(a, b):
    if a.is_relative_to(b) or b.is_relative_to(a):
        raise ValueError("Reuse source/destination/parent roots overlap")


def _main_helper():
    # Existing Main CAD verifier; this does not import Gmsh or generate CAD.
    from . import fixture_assembly_mesh
    return fixture_assembly_mesh


@dataclass(frozen=True)
class _Capture:
    parent_root: Path
    parent_result: bytes
    request: bytes
    result: bytes
    files: tuple
    original_identities: tuple
    copied_identities: tuple
    parent_identities: tuple
    receipt: _Pin
    descriptor: bytes


class QualifiedAssemblyMeshBundle:
    """Trusted original bundle, with only capture and post-execution byte recheck."""
    __slots__ = ("_root", "_request_pin", "_result_pin", "_revision", "_sources", "_captures")

    def __init__(self, bundle_root, *, request_entry, result_entry, mesh_revision, source_files):
        self._root = _absolute(bundle_root)
        if not self._root.is_dir():
            raise ValueError("Retained original reuse bundle directory required")
        self._request_pin, self._result_pin = _pin(request_entry), _pin(result_entry)
        if not isinstance(mesh_revision, str) or re.fullmatch(r"[0-9a-f]{64}", mesh_revision) is None:
            raise ValueError("Trusted original mesh revision required")
        self._revision, self._sources = mesh_revision, _map(source_files)
        if not _SOURCES.issubset(dict(self._sources)):
            raise ValueError("Complete trusted mesh source capsule required")
        self._captures = {}

    def _guard(self):
        request = _json(_read(self._root, "request.json", self._request_pin, keep=True)[0])
        result = _json(_read(self._root, "result.json", self._result_pin, keep=True)[0])
        if not isinstance(request, dict) or not isinstance(result, dict) or request.get("source_files") != _values(self._sources):
            raise ValueError("Original request differs from independently trusted source map")
        _membership(self._root / "capsule", self._sources)
        _check(self._root / "capsule", self._sources)
        if result.get("mesh_revision") != self._revision or result.get("profile") != request.get("profile") or not isinstance(request.get("profile"), dict):
            raise ValueError("Trusted mesh revision/profile differs")
        if result.get("source_files") != _values(self._sources) or result.get("parent") != request.get("parent"):
            raise ValueError("Original result source/parent identity differs")
        parent = _map(request["parent_files"])
        outputs = _map(result["output_files"])
        if set(dict(outputs)) != _OUTPUTS:
            raise ValueError("Exactly eight trusted mesh outputs required")
        files = (("request.json", self._request_pin), ("result.json", self._result_pin))
        files += tuple(("capsule/" + name, pin) for name, pin in self._sources)
        files += tuple(("parent/" + name, pin) for name, pin in parent) + outputs
        return request, result, parent, files

    def _current(self):
        current = _main_helper()
        if current.source_fingerprint() != _values(self._sources):
            raise ValueError("Main parent verifier source differs from the trusted original capsule")
        return current

    def _live_parent(self, current, result, root, request, parent_files):
        identities = _check(root, parent_files)
        actual = current.validate_parent(result, root)
        if actual["identity"] != request["parent"] or actual["files"] != _values(parent_files):
            raise ValueError("Actual CAD parent identity/files differ from frozen mesh parent")
        _check(root, parent_files, identities)
        return identities

    def _source_module(self, name, module_name):
        # Membership and all independent pins precede every captured code load.
        self._guard()
        pin = dict(self._sources)[name]
        path = _safe(self._root / "capsule", name)
        source, _ = _read(self._root / "capsule", name, pin, keep=True)
        module = ModuleType(module_name)
        module.__file__, module.__package__ = str(path), ""
        exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
        self._guard()
        return module

    def _original_helper(self):
        helper = self._source_module("fixture_assembly_mesh.py", "_qualified_original_mesh_helper")
        domain_path = _safe(self._root / "capsule", "assembly_mesh.py")
        def standalone(path, name):
            # The original verifier uses precisely these two Domain load names.
            # Loading policy changes; quality/revision/verifier logic does not.
            if Path(path) != domain_path or name not in ("_captured_mesh_domain", "_assembly_mesh_domain"):
                raise ValueError("Only the exact pinned assembly Domain source/module may load")
            return self._source_module("assembly_mesh.py", name)
        helper.standalone = standalone
        return helper

    def capture(self, parent_result, parent_root, output):
        root, live = _absolute(output), _absolute(parent_root)
        _overlap(self._root, live)
        _overlap(root, self._root); _overlap(root, live)
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise ValueError("Fresh empty reuse capture directory required")
        parent_result_bytes = _canonical(parent_result)
        request, result, parent_files, files = self._guard()
        current = self._current()
        # Reject a foreign/stale live CAD parent before captured code or large
        # original numerical-array reads; all export/copy gates remain later.
        parent_ids = self._live_parent(current, _json(parent_result_bytes), live, request, parent_files)
        self._current()
        originals = _check(self._root, files)
        helper = self._original_helper()
        # Full numerical verification happens once on original paths/provenance.
        helper.verify_output(self._root, result, request)
        self._guard(); _check(self._root, files, originals)
        _check(live, parent_files, parent_ids)
        self._current()
        root.mkdir(parents=True, exist_ok=True)
        copied = {}
        for name, pin in files:
            source, destination = _safe(self._root, name), _safe(root, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _no_links(destination)
            source_before = source.lstat()
            if _identity(source_before) != originals[name]:
                raise ValueError("Original file identity changed before capture: " + name)
            descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as reader, destination.open("xb") as writer:
                if _identity(os.fstat(reader.fileno())) != originals[name]:
                    raise ValueError("Original file identity changed during capture: " + name)
                while block := reader.read(1024 * 1024):
                    writer.write(block)
                if _identity(os.fstat(reader.fileno())) != originals[name]:
                    raise ValueError("Original file changed during capture: " + name)
            copied[name] = _read(root, name, pin)[1]
            if copied[name][:2] == originals[name][:2] or os.path.samefile(source, destination):
                raise ValueError("Reuse capture must be independent bytes, never a hardlink")
        _membership(root, files)
        self._guard(); _check(self._root, files, originals)
        self._current()
        _check(live, parent_files, parent_ids)
        self._live_parent(current, _json(parent_result_bytes), live, request, parent_files)
        _check(root, files, copied)
        receipt = {"schema_version": 1, "capture_only": True, "status": "CAPTURED_BYTE_REUSE",
            "original_bundle_root": str(self._root), "live_cad_parent_root": str(live), "capture_root": str(root),
            "mesh_revision": self._revision, "parent": request["parent"], "profile": request["profile"],
            "request_entry": self._request_pin.value(), "result_entry": self._result_pin.value(),
            "source_files": _values(self._sources), "parent_files": _values(parent_files),
            "output_files": result["output_files"], "captured_files": _values(files),
            "original_runtime_before": result["runtime_before"], "original_runtime_after": result["runtime_after"],
            "runtime_paths_role": "Original preprocessing execution; unchanged, not an execution in the copy",
            "source_load_policy": _LOAD_POLICY, "native_calls": 0, "solver_calls": 0, "provider_calls": 0,
            "solver_status": "NOT_RUN", "decision": "NOT_RELEASED"}
        receipt_bytes = _canonical(receipt) + b"\n"
        with _safe(root, _RECEIPT).open("xb") as stream:
            stream.write(receipt_bytes)
        receipt_pin = _Pin(hashlib.sha256(receipt_bytes).hexdigest(), len(receipt_bytes))
        descriptor = {"status": "CAPTURED_BYTE_REUSE", "capture_only": True, "capture_root": str(root),
            "mesh_revision": self._revision, "parent": {k: request["parent"][k] for k in ("experiment_id", "cad_revision", "native_revision")},
            "profile": request["profile"], "receipt": {"path": _RECEIPT, **receipt_pin.value()},
            "source_load_policy": _LOAD_POLICY, "runtime_paths_role": receipt["runtime_paths_role"],
            "solver_status": "NOT_RUN", "decision": "NOT_RELEASED", "native_calls": 0, "solver_calls": 0, "provider_calls": 0}
        capture = _Capture(live, parent_result_bytes, _canonical(request), _canonical(result), files,
                           tuple(originals.items()), tuple(copied.items()), tuple(parent_ids.items()), receipt_pin,
                           _canonical(descriptor))
        self._captures[root] = capture
        # Receipt and all pinned bytes are checked again before returning success.
        return self.recheck(root)

    def recheck(self, output):
        root = _absolute(output)
        if root not in self._captures:
            raise ValueError("Only this object's completed frozen capture may be rechecked")
        captured = self._captures[root]
        request, result, parent_files, files = self._guard()
        if _canonical(request) != captured.request or _canonical(result) != captured.result or files != captured.files:
            raise ValueError("Completed reuse capture binding drift")
        _check(self._root, files, dict(captured.original_identities))
        current = self._current()
        _check(captured.parent_root, parent_files, dict(captured.parent_identities))
        self._live_parent(current, _json(captured.parent_result), captured.parent_root, request, parent_files)
        _membership(root / "capsule", self._sources)
        _membership(root / "parent", parent_files)
        _check(root, files, dict(captured.copied_identities))
        _read(root, _RECEIPT, captured.receipt)
        self._guard(); _check(self._root, files, dict(captured.original_identities))
        self._current(); _check(captured.parent_root, parent_files, dict(captured.parent_identities))
        return _json(captured.descriptor)
