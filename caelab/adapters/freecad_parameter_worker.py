"""Trusted FreeCAD worker adding only current identities and opaque selectors.

The pinned upstream worker owns discovery metadata, datums, registration's
geometry perturbation and all generation/domain/export checks.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback


def _load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("The trusted FreeCAD worker dependency is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _worker_path():
    if "__file__" in globals():
        return Path(__file__).resolve()
    # The existing AppImage console exec does not set __file__. The bridge
    # overwrites this child-only value with its fixed worker, and the wrapper
    # supplies the matching actual script argument. Neither selects a root.
    expected = os.environ.get("CAELAB_FREECAD_PARAMETER_WORKER")
    actual = os.environ.get("FIXTURE_FREECAD_SCRIPT")
    if not expected or not actual or not Path(expected).is_absolute() or not Path(actual).is_absolute():
        raise RuntimeError("NATIVE_WORKER_ENTRY_INVALID: The fixed native worker path is missing")
    expected, actual = Path(expected).resolve(), Path(actual).resolve()
    if (expected != actual or expected.name != "freecad_parameter_worker.py" or
            expected.parent.name != "adapters" or expected.parent.parent.name != "caelab" or not expected.is_file()):
        raise RuntimeError("NATIVE_WORKER_ENTRY_INVALID: The fixed native worker paths disagree")
    return expected


_WORKER_PATH = _worker_path()
selectors = _load_file("caelab_freecad_parameters", _WORKER_PATH.with_name("freecad_parameters.py"))


def _upstream_worker():
    path = _WORKER_PATH.parents[2] / "plugins/fixture_design/upstream/fixturelab/freecad_worker.py"
    return _load_file("caelab_pinned_freecad_worker", path)


def _sha(document):
    return hashlib.sha256(Path(document).read_bytes()).hexdigest()


def _inspect_doc(worker, doc, source_sha256):
    registry = worker._registry(doc)
    targets = worker._targets(doc)
    resolved = selectors.registered_targets(doc, registry, targets, worker._datum)
    info = worker.inspect(doc)
    candidates = selectors.discovery_candidates(targets, resolved, source_sha256)
    selectors.unique_paths([*candidates, *info["parameters"]])
    return {**info, "candidates": candidates, "source_sha256": source_sha256}, registry, targets, resolved


def inspect_document(worker, document):
    source_sha256 = _sha(document)
    doc = worker.App.openDocument(str(document))
    try:
        info, _, _, _ = _inspect_doc(worker, doc, source_sha256)
        if _sha(document) != source_sha256:
            raise ValueError("Native CAD source changed during inspection; rediscover the document")
        return info
    finally:
        worker.App.closeDocument(doc.Name)


def register_document(worker, request):
    document = request["document"]
    source_sha256 = _sha(document)
    doc = worker.App.openDocument(str(document))
    try:
        _, registry, targets, resolved = _inspect_doc(worker, doc, source_sha256)
        selected, registered = selectors.resolve_selection(request["target"], source_sha256,
            request.get("source_sha256"), targets, resolved)
        if registered is not None:
            raise ValueError("The native CAD dimension is already registered")
        if selected["kind"] == "constraint":
            index = selectors.raw_constraint_index(selected)
            constraints = doc.getObject(selected["object"]).Constraints
            if any(value.Name == request["name"] and i != index for i, value in enumerate(constraints)):
                raise ValueError("NATIVE_DUPLICATE_IDENTITY: The new name already identifies a different Sketcher constraint")
        before = json.loads(json.dumps(registry))
        if _sha(document) != source_sha256:
            raise ValueError("Native CAD source changed before registration; rediscover the document")
    finally:
        worker.App.closeDocument(doc.Name)
    # Delegate the real rename, range/geometry-effect proof and native save.
    worker.dispatch({**request, "action": "register", "target": selected["key"]})
    doc = worker.App.openDocument(str(document))
    try:
        registry = worker._registry(doc)
        entries = registry["parameters"]
        if (registry.get("final") != before.get("final") or len(entries) != len(before["parameters"]) + 1 or
                entries[:-1] != before["parameters"]):
            raise ValueError("Native CAD definitions changed during registration")
        entry = entries[-1]
        if (entry.get("name") != request["name"] or entry.get("key") != selected["key"] or
                entry.get("object") != selected["object"] or entry.get("kind") != selected["kind"]):
            raise ValueError("The pinned registration returned a different native CAD dimension")
        # A legacy positional key may equal the newly selected raw index. Keep
        # the pinned renamed identity and replace only this new public key.
        entry["key"] = request["target"]
        selectors.registered_targets(doc, registry, worker._targets(doc), worker._datum)
        worker._save_registry(doc, registry)
        doc.recompute()
        doc.save()
        info, _, _, _ = _inspect_doc(worker, doc, _sha(document))
        return info
    finally:
        worker.App.closeDocument(doc.Name)


def dispatch(request, worker=None):
    worker = worker if worker is not None else _upstream_worker()
    if request["action"] == "inspect":
        return inspect_document(worker, request["document"])
    if request["action"] == "register":
        return register_document(worker, request)
    # Other native algorithms are retained verbatim in the pinned worker.
    if request["action"] not in ("bootstrap", "bootstrap_sketch"):
        inspect_document(worker, request["document"])
    return worker.dispatch(request)


if __name__ == "__main__":
    result_path = Path(os.environ["FIXTURE_FREECAD_RESULT"])
    try:
        request = json.loads(Path(os.environ["FIXTURE_FREECAD_REQUEST"]).read_text(encoding="utf-8"))
        answer = dispatch(request)
        result_path.write_text(json.dumps({"ok": True, "result": answer}, ensure_ascii=False), encoding="utf-8")
    except Exception as error:
        result_path.write_text(json.dumps({"ok": False, "error": str(error), "traceback": traceback.format_exc()}), encoding="utf-8")
        sys.exit(1)
