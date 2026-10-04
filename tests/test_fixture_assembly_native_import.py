"""Synthetic source/API/process controls, NEVER actual native acceptance.

Seven deliberately coincident bodies and shuffled internal indices test identity
loss. These artificial arrays are not geometry, quality or runtime qualification.
"""
from copy import deepcopy
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


BASE = Path(__file__).resolve().parents[1]
PACKAGE = "_assembly_native_import_source_tests"
package = ModuleType(PACKAGE)
package.__path__ = [str(BASE / "caelab/adapters")]
sys.modules[PACKAGE] = package


def load(name):
    path = BASE / "caelab/adapters" / (name + ".py")
    module = ModuleType(PACKAGE + "." + name)
    module.__package__, module.__file__ = PACKAGE, str(path)
    sys.modules[module.__name__] = module
    exec(compile(path.read_bytes(), str(path), "exec", dont_inherit=True), module.__dict__)
    return module


r = load("fixture_assembly_mesh_reuse")
foundation = load("codeaster_worker")
w = load("fixture_assembly_native_import_worker")
a = load("fixture_assembly_native_import")


def pin(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def save(path, value):
    data = r._canonical(value) + b"\n"
    path.write_bytes(data)
    return pin(data)


def example():
    # Explicit test expectations: original sparse nodes and cell IDs are never
    # interpreted as native indices. All seven body coordinate sets coincide.
    points = [[-0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.],
              [.5, 0., 0.], [.5, .5, 0.], [0., .5, 0.], [0., 0., .5],
              [0., .5, .5], [.5, 0., .5]]
    components = ["printed_base", "printed_support_left", "printed_support_right",
                  "metal_roller_left", "metal_roller_right", "metal_loading_nose", "specimen"]
    edges = {(0, 1): 4, (1, 2): 5, (0, 2): 6, (0, 3): 7, (2, 3): 8, (1, 3): 9}
    triples = list(itertools.permutations(range(4), 3))[:11]
    mapping = {"units": "mm", "frame": "global_assembly_cartesian_mm", "mesh_size_mm": 3.,
               "nodes": [], "elements": [], "physical_groups": []}
    for body, component in enumerate(components, start=1):
        ids = [body * 1000 + i * 17 for i in range(1, 11)]
        mapping["nodes"].extend({"id": nid, "xyz_mm": deepcopy(xyz)} for nid, xyz in zip(ids, points))
        volume = {"dim": 3, "tag": body, "name": f"V{body:04d}", "entity_tags": [body],
                  "component_id": component, "catalog_face_id": None, "node_ids": ids}
        mapping["physical_groups"].append(volume)
        mapping["elements"].append({"id": body * 10000, "type": 11, "dim": 3,
            "physical_tag": body, "entity_tag": body, "component_id": component,
            "catalog_face_id": None, "node_ids": ids})
        for face, triple in enumerate(triples, start=1):
            ordinal = (body-1)*11+face
            conn = [ids[i] for i in triple] + [ids[edges[tuple(sorted((triple[i], triple[j])))]]
                                              for i, j in ((0, 1), (1, 2), (2, 0))]
            group = {"dim": 2, "tag": ordinal+7, "name": f"F{ordinal:04d}", "entity_tags": [ordinal],
                     "component_id": component, "catalog_face_id": f"{component}:face-{face:03d}",
                     "node_ids": conn}
            mapping["physical_groups"].append(group)
            mapping["elements"].append({"id": body*10000+face*13, "type": 9, "dim": 2,
                "physical_tag": ordinal+7, "entity_tag": ordinal, "component_id": component,
                "catalog_face_id": group["catalog_face_id"], "node_ids": conn})
    # Source textual order differs from both mapping order and native indices.
    source_nodes = list(reversed(mapping["nodes"]))
    source_cells = list(reversed(mapping["elements"]))
    physical = [f'  {g["dim"]}\t{g["tag"]}  "{g["name"]}"  \r\n' for g in mapping["physical_groups"]]
    nodes = [f' {n["id"]}\t' + "  ".join(format(x, ".17e") for x in n["xyz_mm"]) + "  \r\n"
             for n in source_nodes]
    elements = [f' {e["id"]}  {e["type"]}\t2 {e["physical_tag"]}  {e["entity_tag"]}\t' +
                "  ".join(map(str, e["node_ids"])) + "  \r\n" for e in source_cells]
    data = ("\r\n$MeshFormat\r\n  2.2\t0 8  \r\n$EndMeshFormat\r\n\r\n$PhysicalNames\r\n84\r\n" +
            "".join(physical) + "$EndPhysicalNames\r\n$Nodes\r\n70\r\n" + "".join(nodes) +
            "$EndNodes\r\n$Elements\r\n84\r\n" + "".join(elements) + "$EndElements\r\n\r\n").encode("ascii")
    actual_node_ids = [n["id"] for n in source_nodes[9:] + source_nodes[:9]]
    native_index = {nid: i for i, nid in enumerate(actual_node_ids)}
    actual_cells = source_cells[20:] + source_cells[:20]
    native_cells, cell_groups, node_groups = [], {}, {}
    for index, e in enumerate(actual_cells):
        # Reference literal permutations are independent from production constants.
        permutation = (0, 1, 2, 3, 4, 5) if e["type"] == 9 else (0, 1, 2, 3, 4, 5, 6, 7, 9, 8)
        native_cells.append({"index": index, "type": "TRIA6" if e["type"] == 9 else "TETRA10",
                             "node_indices": [native_index[e["node_ids"][i]] for i in permutation]})
    by_source_id = {n["id"]: n["xyz_mm"] for n in mapping["nodes"]}
    for g in mapping["physical_groups"]:
        members = [i for i, e in enumerate(actual_cells) if e["dim"] == g["dim"] and e["physical_tag"] == g["tag"]]
        cell_groups[g["name"]] = members
        node_groups[g["name"]] = sorted({n for i in members for n in native_cells[i]["node_indices"]}, reverse=True)
    catalog = {"schema_version": 1, "units": "mm", "index_convention": "zero_based_native_numeric",
        "node_count": 70, "cell_count": 84, "node_indices": list(reversed(range(70))),
        "coordinates_mm": [by_source_id[nid] for nid in actual_node_ids], "cells": native_cells,
        "group_names": list(reversed(cell_groups)), "group_cell_indices": cell_groups,
        "group_node_indices": node_groups, "standalone_node_groups": {},
        "labels": {"nodes": {"status": "OBSERVED", "values": [f"opaque-N-{i+901}" for i in range(70)]},
                   "cells": {"status": "UNAVAILABLE", "values": None}}}
    return SimpleNamespace(mapping=mapping, original=data, catalog=catalog,
                           node_ids=actual_node_ids, cell_ids=[e["id"] for e in actual_cells])


def test_transport_preserves_every_other_byte_and_resolves_known_entity_collision():
    e = example()
    original, before = e.original, deepcopy(e.mapping)
    converted, receipt = a.transport_msh(original, e.mapping)
    # Build expected bytes from independently retained original element row spans.
    head, tail = original.split(b"$Elements\r\n84\r\n", 1)
    rows, ending = tail.split(b"$EndElements", 1)
    expected_rows = []
    for row in rows.splitlines(keepends=True):
        tokens = list(__import__("re").finditer(rb"\S+", row))
        token = tokens[4]
        expected_rows.append(row[:token.start()] + b"0" + row[token.end():])
    assert converted == head + b"$Elements\r\n84\r\n" + b"".join(expected_rows) + b"$EndElements" + ending
    assert receipt["source_entry"] == pin(original) and receipt["transport_entry"] == pin(converted)
    assert original == e.original and e.mapping == before
    assert b"-0.00000000000000000e+00" in converted
    collision = next(g for g in e.mapping["physical_groups"] if g["name"] == "F0008")
    assert collision["tag"] == 15 and collision["entity_tags"] == [8]
    assert next(g for g in e.mapping["physical_groups"] if g["name"] == "F0001")["tag"] == 8
    assert len(receipt["entity_changes"]) == 84 and {r["transport_entity_tag"] for r in receipt["entity_changes"]} == {0}


@pytest.mark.parametrize("fault", ["binary", "unknown_section", "duplicate_section", "row_count", "zero_tag",
    "extra_tag", "duplicate_node", "coordinate", "nonfinite", "connectivity", "physical_name", "foreign_element"])
def test_transport_rejects_malformed_or_foreign_source(fault):
    e = example(); data = e.original
    if fault == "binary": data = data.replace(b"2.2\t0 8", b"2.2\t1 8")
    elif fault == "unknown_section": data += b"$Alien\n$EndAlien\n"
    elif fault == "duplicate_section": data += b"$Nodes\n1\n1 0 0 0\n$EndNodes\n"
    elif fault == "row_count": data = data.replace(b"$Nodes\r\n70", b"$Nodes\r\n71")
    elif fault == "zero_tag": data = data.replace(b'2\t8  "F0001"', b'2\t0  "F0001"')
    elif fault == "extra_tag": data = data.replace(b"\t2 ", b"\t3 ", 1)
    elif fault == "duplicate_node":
        rows = data.split(b"$Nodes\r\n70\r\n")[1].split(b"$EndNodes")[0].splitlines(keepends=True)
        data = data.replace(rows[1], rows[0], 1)
    elif fault == "coordinate": data = data.replace(b"1.00000000000000000e+00", b"1.00000000000000001e+01", 1)
    elif fault == "nonfinite": data = data.replace(b"1.00000000000000000e+00", b"NaN", 1)
    elif fault == "connectivity": data = data.replace(b"7132  7132", b"7132  0") if b"7132  7132" in data else data.replace(b"7017  7034", b"7017  7017", 1)
    elif fault == "physical_name": data = data.replace(b'"F0077"', b'"F0076"')
    elif fault == "foreign_element": data = data.replace(b" 70000  ", b" 999999  ", 1)
    assert data != e.original
    with pytest.raises((ValueError, UnicodeError)):
        a.transport_msh(data, e.mapping)


def test_complete_body_local_bijection_preserves_coincident_bodies_and_sparse_ids():
    e = example()
    assert foundation.coordinate_bijection(e.catalog["coordinates_mm"], [n["xyz_mm"] for n in e.mapping["nodes"]]) is None
    check = w.validate_native_catalog(e.mapping, e.catalog)
    assert check["source_node_ids_by_native_index"] == e.node_ids
    assert check["source_element_ids_by_native_index"] == e.cell_ids
    assert check["group_count"] == 84 and check["node_count"] == 70 and check["cell_count"] == 84
    assert check["solver_status"] == "NOT_RUN" and check["decision"] == "NOT_RELEASED"
    assert len(check["bodies"]) == 7 and check["maximum_coordinate_error_mm"] == 0


@pytest.mark.parametrize("fault", ["missing_group", "duplicate_group", "same_count_wrong_face", "body_merge",
    "wrong_order", "wrong_type", "orphan", "sparse_as_native", "nonfinite", "boolean_index", "bad_labels",
    "fake_unavailable_labels", "unknown_standalone_group", "bad_node_membership"])
def test_actual_catalog_rejects_incomplete_or_misassociated_identity(fault):
    e = example(); c = deepcopy(e.catalog)
    if fault == "missing_group": c["group_names"].pop()
    elif fault == "duplicate_group": c["group_names"][0] = c["group_names"][1]
    elif fault == "same_count_wrong_face":
        c["group_cell_indices"]["F0001"], c["group_cell_indices"]["F0012"] = c["group_cell_indices"]["F0012"], c["group_cell_indices"]["F0001"]
        c["group_node_indices"]["F0001"], c["group_node_indices"]["F0012"] = c["group_node_indices"]["F0012"], c["group_node_indices"]["F0001"]
    elif fault == "body_merge":
        c["group_cell_indices"]["V0002"] = c["group_cell_indices"]["V0001"]
        c["group_node_indices"]["V0002"] = c["group_node_indices"]["V0001"]
    elif fault == "wrong_order": c["cells"][0]["node_indices"][0:2] = reversed(c["cells"][0]["node_indices"][0:2])
    elif fault == "wrong_type": c["cells"][0]["type"] = "TRIA3"
    elif fault == "orphan": c["cells"].pop(); c["cell_count"] -= 1
    elif fault == "sparse_as_native": c["cells"][0]["index"] = e.cell_ids[0]
    elif fault == "nonfinite": c["coordinates_mm"][0][0] = float("nan")
    elif fault == "boolean_index": c["node_indices"][0] = True
    elif fault == "bad_labels": c["labels"]["nodes"]["values"][-1] = c["labels"]["nodes"]["values"][0]
    elif fault == "fake_unavailable_labels": c["labels"]["cells"]["values"] = ["invented"]
    elif fault == "unknown_standalone_group": c["standalone_node_groups"] = {"GUESSED": [0]}
    elif fault == "bad_node_membership": c["group_node_indices"]["F0001"].pop()
    with pytest.raises(ValueError): w.validate_native_catalog(e.mapping, c)


def test_coordinate_absolute_limit_and_optional_absence_are_explicit():
    e = example(); c = deepcopy(e.catalog)
    c["labels"]["nodes"] = {"status": "UNAVAILABLE", "values": None}
    c["coordinates_mm"][0][0] += 5e-13
    assert 0 < w.validate_native_catalog(e.mapping, c)["maximum_coordinate_error_mm"] <= 1e-12
    c["coordinates_mm"][0][0] += 2e-12
    with pytest.raises(ValueError): w.validate_native_catalog(e.mapping, c)


def test_actual_api_observer_retains_complete_arrays_without_label_creation():
    e = example(); c = e.catalog
    class FakeMesh:
        sdj = SimpleNamespace(NOMNOE=SimpleNamespace(get=lambda: None), NOMMAI=SimpleNamespace(get=lambda: []))
        def getNumberOfNodes(self): return c["node_count"]
        def getNumberOfCells(self): return c["cell_count"]
        def getNodes(self, group=None): return c["node_indices"] if group is None else c["standalone_node_groups"][group]
        def getCoordinates(self): return SimpleNamespace(toNumpy=lambda: SimpleNamespace(tolist=lambda: deepcopy(c["coordinates_mm"])))
        def getConnectivity(self): return [cell["node_indices"] for cell in c["cells"]]
        def getCellTypeName(self, i): return c["cells"][i]["type"]
        def getGroupsOfCells(self): return c["group_names"]
        def getCells(self, g): return c["group_cell_indices"][g]
        def getNodesFromCells(self, g): return c["group_node_indices"][g]
        def getGroupsOfNodes(self): return []
    observed = w.capture_native_catalog(FakeMesh())
    for key in ("coordinates_mm", "cells", "group_names", "group_cell_indices", "group_node_indices", "node_indices"):
        assert observed[key] == c[key]
    assert observed["labels"]["nodes"]["status"] == observed["labels"]["cells"]["status"] == "UNAVAILABLE"
    assert w.validate_native_catalog(e.mapping, observed)["group_count"] == 84


@pytest.fixture
def controlled_job(tmp_path, monkeypatch):
    e, events = example(), []
    image, executable = tmp_path / "synthetic.sif", tmp_path / "synthetic-runtime"
    image.write_bytes(b"SYNTHETIC image identity; never executed")
    executable.write_bytes(b"SYNTHETIC owned child boundary; never executed")
    executable.chmod(0o755)
    monkeypatch.setenv("CAELAB_CODEASTER_IMAGE", str(image))
    monkeypatch.setenv("CAELAB_CODEASTER_IMAGE_SHA256", a._entry(image)["sha256"])
    monkeypatch.setattr(a.shutil, "which", lambda command: str(executable))
    # Actual class type is retained. Only its already-tested external capture/
    # recheck boundary is injected; production contains no bypass or fake mode.
    bundle = object.__new__(r.QualifiedAssemblyMeshBundle)
    state = {"fault": None}
    def capture(self, parent, parent_root, output):
        assert self is bundle and parent == {"synthetic": True}
        events.append("capture")
        output.mkdir()
        mesh_pin = pin(e.original); (output / "mesh.msh").write_bytes(e.original)
        mapping_pin = save(output / "mapping.json", e.mapping)
        receipt = {"mesh_revision": "c"*64, "parent": {"experiment_id": "SYNTHETIC", "cad_revision": "d"*64, "native_revision": "e"*64},
                   "profile": {"name": "coarse3", "mesh_size_mm": 3.},
                   "output_files": {"mesh.msh": mesh_pin, "mapping.json": mapping_pin}}
        receipt_pin = save(output / "mesh-reuse-receipt.json", receipt)
        return {"receipt": {"path": "mesh-reuse-receipt.json", **receipt_pin},
                "capture_root": str(output), "scope": "SYNTHETIC boundary only"}
    def recheck(self, output):
        assert self is bundle and output.name == "mesh-reuse"
        events.append("recheck")
        if state["fault"] == "recheck" and "import" in events:
            raise ValueError("SYNTHETIC same-object post-execution drift")
    monkeypatch.setattr(r.QualifiedAssemblyMeshBundle, "capture", capture)
    monkeypatch.setattr(r.QualifiedAssemblyMeshBundle, "recheck", recheck)
    def process(command, folder, label, *, timeout):
        assert timeout is None
        if label == "container-version":
            events.append("runtime-version")
            return "SYNTHETIC version boundary; no runtime executed"
        events.append("import")
        assert "OMP_NUM_THREADS=1" in command and "/work/native/import.export" == command[-1]
        if state["fault"] == "exit": raise RuntimeError("SYNTHETIC native-import nonzero exit17")
        config = json.loads((folder / "input.json").read_text())
        runtime = {"versions": {"code_aster": "17.4.0", "qualification": "SYNTHETIC"}, "code_aster_runtime": {"version": "17.4.0"}}
        catalog_pin = save(folder / "native-catalog.json", e.catalog)
        save(folder / "runtime-before.json", runtime); save(folder / "runtime-after.json", runtime)
        raw = {"schema_version": 1, "status": "IMPORTED_OBSERVED_NOT_COMPARED",
            "input_entry": a._entry(folder / "input.json"), "transport_entry": config["transport_entry"],
            "native_sources": config["native_sources"], "mesh_revision": config["mesh_revision"],
            "parent": config["parent"], "profile": config["profile"],
            "solver_status": "NOT_RUN", "converged": None, "decision": "NOT_RELEASED",
            "runtime_before": runtime, "runtime_after": runtime, "catalog_entry": catalog_pin}
        if state["fault"] == "input": raw["input_entry"]["sha256"] = "0"*64
        elif state["fault"] == "worker": raw["native_sources"][_WORKER]["sha256"] = "0"*64
        elif state["fault"] == "catalog_hash": raw["catalog_entry"]["sha256"] = "0"*64
        elif state["fault"] == "runtime": raw["runtime_after"] = {"versions": {"code_aster": "17.3.0"}}
        elif state["fault"] == "profile": raw["profile"] = {"name": "FOREIGN"}
        elif state["fault"] == "image": image.write_bytes(b"SYNTHETIC image changed during process")
        elif state["fault"] == "transport": (folder / "mesh-transport.msh").write_bytes(b"changed")
        save(folder / "worker-result.json", raw)
        return "SYNTHETIC exit0; actual native import NOT_RUN"
    _WORKER = "fixture_assembly_native_import_worker.py"
    monkeypatch.setattr(a, "_owned_process", process)
    return SimpleNamespace(e=e, bundle=bundle, parent=tmp_path / "synthetic-parent", output=tmp_path / "new-import",
                           events=events, state=state, image=image)


def test_owned_import_call_order_same_object_guards_and_no_mechanical_claim(controlled_job, monkeypatch):
    c = controlled_job
    original_compare, original_save = a.validate_native_catalog, a._save
    def comparison(mapping, catalog):
        result = original_compare(mapping, catalog)
        c.events.append("comparison")
        return result
    def save_result(root, name, value):
        if name == "result.json":
            c.events.append("admit")
        return original_save(root, name, value)
    monkeypatch.setattr(a, "validate_native_catalog", comparison)
    monkeypatch.setattr(a, "_save", save_result)
    result = a.import_bundle(c.bundle, {"synthetic": True}, c.parent, c.output)
    assert c.events == ["capture", "runtime-version", "recheck", "import", "comparison", "recheck", "admit"]
    assert result["status"] == "IMPORTED_VERIFIED" and result["scope"] == "NATIVE_IMPORT_ONLY"
    assert result["solver_status"] == "NOT_RUN" and result["converged"] is None and result["decision"] == "NOT_RELEASED"
    assert (c.output / "mesh-reuse/mesh.msh").read_bytes() == c.e.original
    assert json.loads((c.output / "native-comparison.json").read_text())["source_element_ids_by_native_index"] == c.e.cell_ids
    export = (c.output / "native/import.export").read_text()
    assert "P time_limit 86400\n" in export and "P mpi_nbcpu 1\nP ncpus 1\n" in export
    assert "F rmed" not in export
    assert not (c.output / "failure.json").exists()


@pytest.mark.parametrize("fault", ["exit", "input", "worker", "catalog_hash", "runtime", "profile", "image", "transport", "recheck"])
def test_bad_owned_result_or_drift_never_admits_and_retains_partial_evidence(controlled_job, fault):
    c = controlled_job; c.state["fault"] = fault
    with pytest.raises((ValueError, RuntimeError)):
        a.import_bundle(c.bundle, {"synthetic": True}, c.parent, c.output)
    assert not (c.output / "result.json").exists()
    assert (c.output / "failure.json").is_file()
    assert (c.output / "mesh-reuse/mesh.msh").read_bytes() == c.e.original
    assert "import" in c.events and c.events[-1] == "recheck"
    assert c.events.count("recheck") == (3 if fault == "recheck" else 2)


def test_operator_image_mismatch_refuses_before_runtime_or_import(controlled_job, monkeypatch):
    c = controlled_job
    monkeypatch.setenv("CAELAB_CODEASTER_IMAGE_SHA256", "f"*64)
    with pytest.raises(ValueError, match="SIF hash"):
        a.import_bundle(c.bundle, {"synthetic": True}, c.parent, c.output)
    assert c.events == ["capture", "recheck"]
    assert not (c.output / "native").exists() and (c.output / "failure.json").exists()


def test_actual_runtime_file_drift_after_comparison_blocks_admission(controlled_job, monkeypatch):
    c = controlled_job
    original = a.validate_native_catalog
    def comparison(mapping, catalog):
        result = original(mapping, catalog)
        (c.output / "native/runtime-after.json").write_bytes(b"{\"altered_actual_runtime\":true}\n")
        return result
    monkeypatch.setattr(a, "validate_native_catalog", comparison)
    with pytest.raises(ValueError, match="Reuse byte pin drift: runtime-after.json"):
        a.import_bundle(c.bundle, {"synthetic": True}, c.parent, c.output)
    assert not (c.output / "result.json").exists() and (c.output / "failure.json").exists()
    assert c.events[-1] == "recheck"
    assert c.events.count("recheck") == 2


def test_fresh_path_and_real_object_required_before_any_capture(controlled_job):
    c = controlled_job
    with pytest.raises(TypeError): a.import_bundle(SimpleNamespace(), {}, c.parent, c.output)
    c.output.mkdir(); (c.output / "old.txt").write_text("preserve")
    with pytest.raises(ValueError, match="Fresh empty"): a.import_bundle(c.bundle, {}, c.parent, c.output)
    assert not c.events and (c.output / "old.txt").read_text() == "preserve"


def test_symlink_output_refuses_before_capture(controlled_job, tmp_path):
    c = controlled_job; real = tmp_path / "real"; real.mkdir()
    try: c.output.symlink_to(real, target_is_directory=True)
    except OSError: pytest.skip("Actual symlink creation unavailable on this platform")
    with pytest.raises(ValueError, match="Symlink/junction/reparse"):
        a.import_bundle(c.bundle, {}, c.parent, c.output)
    assert not c.events and not list(real.iterdir())
