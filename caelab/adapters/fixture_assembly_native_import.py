"""Internal seven-body import gate over a qualified, unchanged mesh bundle.

Operator configuration owns the bundle and runtime pins. This is neither an
AnalysisAdapter nor a public backend, and returns no mechanical Outcome.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import struct

from . import fixture_assembly_mesh_reuse as reuse
from .fixture_assembly_native_import_worker import source_catalog, validate_native_catalog


QualifiedAssemblyMeshBundle = reuse.QualifiedAssemblyMeshBundle
_TRANSFORM = "MSH2.2 exact two tags: replace only each second/entity tag token with ASCII0; all other bytes unchanged"
_WORKER = "fixture_assembly_native_import_worker.py"


def _entry(path):
    reuse._no_links(path)
    info = path.lstat()
    if not path.is_file() or info.st_nlink != 1:
        raise ValueError("Regular independent import file required")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    if reuse._identity(path.lstat()) != reuse._identity(info):
        raise ValueError("Import file identity drift during hashing")
    return {"sha256": digest.hexdigest(), "size_bytes": info.st_size}


def _bytes(root, name, pin):
    return reuse._read(root, name, reuse._pin(pin), keep=True)[0]


def _save(root, name, value):
    path = reuse._safe(root, name)
    with path.open("xb") as stream:
        stream.write(reuse._canonical(value) + b"\n")
    return _entry(path)


def transport_msh(original, mapping):
    """Validate sparse source identity and preserve every non-entity byte."""
    source = source_catalog(mapping)
    if not isinstance(original, bytes):
        raise ValueError("Immutable original MSH bytes required")
    original.decode("ascii", errors="strict")
    lines = original.splitlines(keepends=True)
    sections, spans, pending, start = {}, {}, None, None
    allowed = ("MeshFormat", "PhysicalNames", "Nodes", "Elements")
    order = []
    for index, line in enumerate(lines):
        token = line.strip()
        if token.startswith(b"$"):
            if token.startswith(b"$End"):
                name = token[4:].decode("ascii")
                if pending != name:
                    raise ValueError("Malformed MSH section ending")
                sections[name] = lines[start:index]
                spans[name] = (start, index)
                pending = None
            else:
                name = token[1:].decode("ascii")
                if pending is not None or name not in allowed or name in sections:
                    raise ValueError("Duplicate/unexpected MSH section")
                pending, start = name, index + 1
                order.append(name)
        elif pending is None and token:
            raise ValueError("Unexpected MSH content outside sections")
    if pending is not None or tuple(order) != allowed or set(sections) != set(allowed):
        raise ValueError("Complete ordered MSH2.2 sections required")
    if len(sections["MeshFormat"]) != 1 or sections["MeshFormat"][0].split() != [b"2.2", b"0", b"8"]:
        raise ValueError("Only MSH2.2 ASCII binary64 supported")
    def records(name):
        rows = sections[name]
        if not rows or not re.fullmatch(rb"[1-9][0-9]*", rows[0].strip()) or int(rows[0]) != len(rows)-1:
            raise ValueError("MSH declared row count differs: " + name)
        return rows[1:]
    physical = {}
    for row in records("PhysicalNames"):
        match = re.fullmatch(rb'([23])[ \t]+([1-9][0-9]*)[ \t]+"([VF][0-9]{4})"', row.strip())
        if match is None:
            raise ValueError("Malformed physical name/tag")
        key, name = (int(match[1]), int(match[2])), match[3].decode("ascii")
        if key in physical or name in physical.values():
            raise ValueError("Duplicate physical identity")
        physical[key] = name
    if physical != {(g["dim"], g["tag"]): name for name, g in source["groups"].items()}:
        raise ValueError("Original MSH physical names/tags differ from mapping")
    nodes = {}
    for row in records("Nodes"):
        tokens = row.split()
        if len(tokens) != 4 or re.fullmatch(rb"[1-9][0-9]*", tokens[0]) is None:
            raise ValueError("Malformed source node row")
        nid = int(tokens[0])
        if nid in nodes:
            raise ValueError("Duplicate MSH node identifier")
        try:
            xyz = [float(v) for v in tokens[1:]]
            bits = b"".join(struct.pack("!d", v) for v in xyz)
            expected = b"".join(struct.pack("!d", v) for v in source["nodes"][nid])
        except (ValueError, KeyError, OverflowError) as exc:
            raise ValueError("Malformed/foreign MSH node XYZ") from exc
        if bits != expected:
            raise ValueError("MSH source binary64 coordinates differ from mapping")
        nodes[nid] = xyz
    if set(nodes) != set(source["nodes"]):
        raise ValueError("Incomplete MSH node scope")
    elements, replacements = {}, []
    start, _ = spans["Elements"]
    for offset, row in enumerate(records("Elements"), start=1):
        token_spans = list(re.finditer(rb"\S+", row))
        tokens = [m.group() for m in token_spans]
        if len(tokens) < 5 or any(re.fullmatch(rb"[0-9]+", v) is None for v in tokens):
            raise ValueError("Malformed MSH element tokens")
        values = [int(v) for v in tokens]
        eid, kind, ntags, physical_tag, entity_tag = values[:5]
        expected = source["elements"].get(eid)
        if (expected is None or eid in elements or ntags != 2 or physical_tag <= 0 or entity_tag <= 0 or
                kind != expected["type"] or physical_tag != expected["physical_tag"] or
                entity_tag != expected["entity_tag"] or values[5:] != expected["node_ids"]):
            raise ValueError("MSH element type/order/two-tag/membership differs")
        elements[eid] = values
        span = token_spans[4]
        replacements.append({"element_id": eid, "original_entity_tag": entity_tag,
                             "transport_entity_tag": 0})
        lines[start + offset] = row[:span.start()] + b"0" + row[span.end():]
    if set(elements) != set(source["elements"]):
        raise ValueError("Incomplete MSH element scope")
    transport = b"".join(lines)
    return transport, {"transform": _TRANSFORM, "node_count": len(nodes), "cell_count": len(elements),
        "physical_group_count": len(physical), "entity_changes": replacements,
        "source_entry": {"sha256": hashlib.sha256(original).hexdigest(), "size_bytes": len(original)},
        "transport_entry": {"sha256": hashlib.sha256(transport).hexdigest(), "size_bytes": len(transport)},
        "units": "mm", "frame": "global_assembly_cartesian_mm"}


def source_files():
    base = Path(__file__).resolve().parent
    return {"fixture_assembly_native_import.py": Path(__file__).resolve(),
            _WORKER: base / _WORKER, "codeaster_worker.py": base / "codeaster_worker.py",
            "fixture_assembly_mesh_reuse.py": base / "fixture_assembly_mesh_reuse.py",
            "codeaster_elasticity.py": base / "codeaster_elasticity.py",
            "codeaster_execution.py": base / "codeaster_execution.py",
            "execution_control.py": base.parent / "execution_control.py",
            "storage.py": base.parent / "storage.py"}


def _source_pins():
    return {name: _entry(path) for name, path in source_files().items()}


def _owned_process(command, folder, label, *, timeout):
    from .codeaster_elasticity import _process
    return _process(command, folder, label, timeout=timeout)


def _budgets():
    from .codeaster_execution import process_budgets
    return process_budgets()


def _image_identity():
    value, expected = os.environ.get("CAELAB_CODEASTER_IMAGE", ""), os.environ.get("CAELAB_CODEASTER_IMAGE_SHA256", "")
    if not value or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ValueError("Operator-pinned existing Code_Aster SIF required")
    image = reuse._absolute(value)
    image_pin = _entry(image)
    if image_pin["sha256"] != expected:
        raise ValueError("Code_Aster SIF hash differs")
    executable = shutil.which(os.environ.get("CAELAB_SINGULARITY_COMMAND", "singularity"))
    if not executable:
        raise ValueError("Existing Apptainer/Singularity runtime required")
    executable = Path(executable).resolve()
    if not os.access(executable, os.X_OK):
        raise ValueError("Executable container runtime required")
    return image, image_pin, executable, _entry(executable)


def import_bundle(bundle, parent_result, parent_root, output):
    """Capture once, import once, recheck this same object; return import only."""
    if type(bundle) is not QualifiedAssemblyMeshBundle:
        raise TypeError("Existing trusted QualifiedAssemblyMeshBundle object required")
    root = reuse._absolute(output)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("Fresh empty native import output required")
    sources, budgets = _source_pins(), _budgets()
    root.mkdir(parents=True, exist_ok=True)
    captured, final_bundle_checked, known_files = False, False, {}
    try:
        descriptor = bundle.capture(parent_result, parent_root, root / "mesh-reuse")
        captured = True
        capture_root = root / "mesh-reuse"
        receipt = reuse._json(_bytes(capture_root, descriptor["receipt"]["path"],
                                    {k: descriptor["receipt"][k] for k in ("sha256", "size_bytes")}))
        original_pin = receipt["output_files"]["mesh.msh"]
        mapping_pin = receipt["output_files"]["mapping.json"]
        mapping = reuse._json(_bytes(capture_root, "mapping.json", mapping_pin))
        original = _bytes(capture_root, "mesh.msh", original_pin)
        transport, transform = transport_msh(original, mapping)
        if transform["source_entry"] != original_pin:
            raise ValueError("Captured original MSH pin differs")
        image, image_pin, executable, executable_pin = _image_identity()
        for name in ("native", "capsule", "preferences", "scratch"):
            (root / name).mkdir(exist_ok=False)
        native = root / "native"
        with (native / "mesh-transport.msh").open("xb") as stream:
            stream.write(transport)
        native_sources = {}
        for name in (_WORKER, "codeaster_worker.py"):
            data = reuse._read(source_files()[name].parent, source_files()[name].name,
                              reuse._pin(sources[name]), keep=True)[0]
            with (root / "capsule" / name).open("xb") as stream:
                stream.write(data)
            native_sources[name] = _entry(root / "capsule" / name)
        config = {"schema_version": 1, "mesh_revision": receipt["mesh_revision"],
                  "parent": receipt["parent"], "profile": receipt["profile"],
                  "original_mesh_entry": original_pin, "mapping_entry": mapping_pin,
                  "transport_entry": transform["transport_entry"], "native_sources": native_sources}
        input_pin = _save(native, "input.json", config)
        _save(root, "transport.json", transform)
        _save(root, "intent.json", {"scope": "NATIVE_IMPORT_ONLY", "solver_status": "NOT_RUN",
            "decision": "NOT_RELEASED", "reuse": descriptor, "source_files": sources,
            "native_sources": native_sources, "input_entry": input_pin,
            "image": {"path": str(image), **image_pin},
            "container_runtime": {"path": str(executable), **executable_pin}, "budgets": budgets,
            "OMP_NUM_THREADS": 1, "compiled_image_source_equivalence": "UNKNOWN"})
        comm = ("from pathlib import Path\nimport hashlib\n"
                "p=Path('/work/capsule/fixture_assembly_native_import_worker.py')\nb=p.read_bytes()\n"
                f"assert hashlib.sha256(b).hexdigest()=={native_sources[_WORKER]['sha256']!r} and len(b)=={native_sources[_WORKER]['size_bytes']}\n"
                "ns={'__file__':str(p),'__name__':'_assembly_native_import_worker'}\n"
                "exec(compile(b,str(p),'exec',dont_inherit=True),ns)\n"
                "ns['run_import']('/work/native/input.json')\n")
        (native / "import.comm").write_text(comm, encoding="utf-8", newline="\n")
        export = (f"P actions make_etude\nP memory_limit {budgets['solver_memory_mb']}\n"
                  f"P time_limit {budgets['solver_time_seconds']}\nP mpi_nbcpu 1\nP ncpus 1\n"
                  "F comm /work/native/import.comm D 1\nF mmed /work/native/mesh-transport.msh D 20\n"
                  "F mess /work/native/aster.mess R 6\nF resu /work/native/aster.resu R 8\n")
        (native / "import.export").write_text(export, encoding="utf-8", newline="\n")
        for name in ("native/input.json", "native/mesh-transport.msh", "native/import.comm", "native/import.export",
                     "capsule/" + _WORKER, "capsule/codeaster_worker.py", "transport.json", "intent.json"):
            known_files[name] = _entry(root / name)
        def recheck_inputs():
            if _source_pins() != sources or _entry(image) != image_pin or _entry(executable) != executable_pin:
                raise ValueError("Image/runtime/controller source drift")
            for name, pin in known_files.items():
                _bytes(root, name, pin)
        recheck_inputs()
        runtime_version = _owned_process([str(executable), "--version"], native, "container-version",
                                        timeout=budgets["subprocess_timeout_seconds"])
        _save(root, "container-version.json", {"observed": runtime_version})
        recheck_inputs()
        command = [str(executable), "exec", "--cleanenv", "--containall", "--no-home", "--env", "OMP_NUM_THREADS=1",
                   "--bind", str(root) + ":/work:rw", "--bind", str(root / "preferences") + ":" + str(Path.home()) + ":rw",
                   "--bind", str(root / "scratch") + ":/tmp:rw", "--pwd", "/work", str(image),
                   "/bin/bash", "--noprofile", "--norc", "-c", 'source /opt/activate.sh; exec run_aster "$1"',
                   "caelab-assembly-import", "/work/native/import.export"]
        # Capture already performs its full check. Keep the next full same-object
        # check at the actual native boundary, after the runtime version probe.
        bundle.recheck(capture_root)
        recheck_inputs()
        _owned_process(command, native, "native-import", timeout=budgets["subprocess_timeout_seconds"])
        recheck_inputs()
        result_pin = _entry(native / "worker-result.json")
        raw = reuse._json(_bytes(native, "worker-result.json", result_pin))
        if (type(raw.get("schema_version")) is not int or raw["schema_version"] != 1 or
                raw.get("status") != "IMPORTED_OBSERVED_NOT_COMPARED" or
                raw.get("input_entry") != input_pin or raw.get("transport_entry") != config["transport_entry"] or
                raw.get("native_sources") != native_sources or raw.get("mesh_revision") != config["mesh_revision"] or
                raw.get("parent") != config["parent"] or raw.get("profile") != config["profile"] or
                raw.get("solver_status") != "NOT_RUN" or raw.get("converged") is not None or
                raw.get("decision") != "NOT_RELEASED"):
            raise ValueError("Native import result/input/source/parent/profile identity differs")
        before_pin, after_pin = _entry(native / "runtime-before.json"), _entry(native / "runtime-after.json")
        before = reuse._json(_bytes(native, "runtime-before.json", before_pin))
        after = reuse._json(_bytes(native, "runtime-after.json", after_pin))
        if (before != raw.get("runtime_before") or after != raw.get("runtime_after") or before != after or
                before.get("versions", {}).get("code_aster") != "17.4.0"):
            raise ValueError("Actual native runtime records differ")
        catalog_pin = reuse._pin(raw["catalog_entry"]).value()
        catalog = reuse._json(_bytes(native, "native-catalog.json", catalog_pin))
        checks = validate_native_catalog(mapping, catalog)
        _save(root, "native-comparison.json", checks)
        recheck_inputs()
        _bytes(native, "worker-result.json", result_pin)
        _bytes(native, "native-catalog.json", catalog_pin)
        _bytes(native, "runtime-before.json", before_pin)
        _bytes(native, "runtime-after.json", after_pin)
        outcome = {"status": "IMPORTED_VERIFIED", "scope": "NATIVE_IMPORT_ONLY", "solver_status": "NOT_RUN",
                   "converged": None, "decision": "NOT_RELEASED", "mesh_revision": config["mesh_revision"],
                   "parent": config["parent"], "profile": config["profile"], "source_files": sources,
                   "transport": transform, "reuse": descriptor, "native_runtime": before,
                   "container_version": runtime_version, "native_comparison": "native-comparison.json",
                   "worker_result_entry": result_pin, "native_catalog_entry": catalog_pin,
                   "artifacts": {name: _entry(root / name) for name in sorted(known_files)} | {
                       "native/worker-result.json": result_pin, "native/native-catalog.json": catalog_pin,
                       "native/runtime-before.json": before_pin, "native/runtime-after.json": after_pin,
                       "native-comparison.json": _entry(root / "native-comparison.json")},
                   "limitations": ["Import identity only; no mechanics/contact/Gauss/reference qualification",
                       "Original preprocessing runtime paths retain their original execution role",
                       "Engineering material/mounting/fastener/physical/strength/durability UNKNOWN"]}
        # Final full original/live-parent verification follows all host comparisons
        # and output pins. Cheap byte checks also cover the duration of that check.
        bundle.recheck(capture_root)
        final_bundle_checked = True
        recheck_inputs()
        _bytes(native, "worker-result.json", result_pin)
        _bytes(native, "native-catalog.json", catalog_pin)
        _bytes(native, "runtime-before.json", before_pin)
        _bytes(native, "runtime-after.json", after_pin)
        _bytes(root, "native-comparison.json", outcome["artifacts"]["native-comparison.json"])
        _save(root, "result.json", outcome)
        return outcome
    except BaseException as exc:
        _save(root, "failure.json", {"scope": "NATIVE_IMPORT_ONLY", "solver_status": "NOT_RUN",
            "decision": "NOT_RELEASED", "error": type(exc).__name__ + ": " + str(exc),
            "partial_files": "PRESERVED", "captured": captured})
        raise
    finally:
        if captured and not final_bundle_checked:
            bundle.recheck(root / "mesh-reuse")
