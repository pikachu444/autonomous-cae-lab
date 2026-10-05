"""Synthetic full-field/source controls. No CAD, solver or native acceptance.

Sparse/shuffled identifiers and seven coincident bodies deliberately defeat a
global coordinate join. Native tables below are artificial test observations.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


BASE = Path(__file__).resolve().parents[1]
PACKAGE = "_assembly_affine_source_tests"
package = ModuleType(PACKAGE)
package.__path__ = [str(BASE / "caelab/adapters")]
sys.modules[PACKAGE] = package


def load(name):
    path = BASE / "caelab/adapters" / (name + ".py")
    module = ModuleType(PACKAGE + "." + name)
    module.__file__, module.__package__ = str(path), PACKAGE
    sys.modules[module.__name__] = module
    exec(compile(path.read_bytes(), str(path), "exec", dont_inherit=True), module.__dict__)
    return module


w = load("fixture_assembly_affine_field_worker")
a = load("fixture_assembly_affine_field")
from plugins.fixture_design.assembly_field_reference import canonical_settings
from plugins.fixture_design.assembly_field_comparison import compare_fields

_common_package = ModuleType("_affine_common_source_tests")
_common_package.__path__ = [str(BASE / "caelab")]
sys.modules[_common_package.__name__] = _common_package
_outcomes_path = BASE / "caelab/outcomes.py"
_outcomes = ModuleType(_common_package.__name__ + ".outcomes")
_outcomes.__file__, _outcomes.__package__ = str(_outcomes_path), _common_package.__name__
exec(compile(_outcomes_path.read_bytes(), str(_outcomes_path), "exec"), _outcomes.__dict__)


def pin(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def save(path, value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    path.write_bytes(data)
    return pin(data)


def synthetic():
    components = canonical_settings()["components"]
    core_xyz = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.], [.25, .25, .25],
                [.5, 0., 0.], [.5, .5, 0.], [0., .5, 0.], [0., 0., .5], [.5, 0., .5], [0., .5, .5],
                [.125, .125, .125], [.625, .125, .125], [.125, .625, .125], [.125, .125, .625]]
    # Positive native ordering, manually listed. Genuine interior nodes4,11..14
    # are shared by the four sub-tetrahedra, never constrained by the patch.
    core_tets = [[0, 1, 2, 4, 5, 6, 7, 11, 12, 13],
                 [1, 0, 3, 4, 5, 8, 9, 12, 11, 14],
                 [0, 2, 3, 4, 7, 10, 8, 11, 13, 14],
                 [2, 1, 3, 4, 6, 9, 10, 13, 12, 14]]
    core_faces = [[0, 1, 2, 5, 6, 7], [0, 1, 3, 5, 9, 8],
                  [0, 2, 3, 7, 10, 8], [1, 2, 3, 6, 10, 9]]
    tet_xyz = [[0., 1., 0.], [0., 0., 1.], [0., 0., 0.], [1., 0., 0.],
               [0., .5, .5], [0., 0., .5], [0., .5, 0.], [.5, .5, 0.], [.5, 0., .5], [.5, 0., 0.]]
    tet_faces = [[0, 1, 2, 4, 5, 6], [0, 1, 3, 4, 8, 7],
                 [0, 2, 3, 6, 9, 7], [1, 2, 3, 5, 9, 8]]
    xyz = core_xyz + [[p[0], p[1], p[2]+z] for z in (20., 40.) for p in tet_xyz]
    tets = core_tets + [[15+i for i in range(10)], [25+i for i in range(10)]]
    faces = core_faces + [[offset+i for i in f] for offset in (15, 25) for f in tet_faces]
    mapping = {"units": "mm", "frame": "global_assembly_cartesian_mm", "mesh_size_mm": 3.,
               "nodes": [], "elements": [], "physical_groups": []}
    native_source_cells, reactions = [], {}
    stress_matrix = ((.32, .016, .032), (.016, -.16, -.016), (.032, -.016, .64))
    for number, component in enumerate(components, 1):
        ids = [number*100000 + 17*(i+1) for i in range(len(xyz))]
        mapping["nodes"] += [{"id": nid, "xyz_mm": deepcopy(p)} for nid, p in zip(ids, xyz)]
        mapping["physical_groups"].append({"name": f"V{number:04d}", "dim": 3, "tag": number,
            "entity_tags": [number], "component_id": component, "catalog_face_id": None, "node_ids": ids})
        for ordinal, conn in enumerate(tets, 1):
            eid = number*10000 + ordinal*31
            nodes = [ids[i] for i in conn]
            gmsh = nodes[:8] + [nodes[9], nodes[8]]
            mapping["elements"].append({"id": eid, "type": 11, "dim": 3,
                "physical_tag": number, "entity_tag": number, "component_id": component,
                "catalog_face_id": None, "node_ids": gmsh})
            native_source_cells.append((eid, "TETRA10", nodes))
        for face_group in range(11):
            ordinal = (number-1)*11 + face_group + 1
            selected = [face_group] if face_group < 10 else [10, 11]
            group_nodes = sorted({ids[i] for face in selected for i in faces[face]})
            name, face_id = f"F{ordinal:04d}", component + ":synthetic-face-" + str(face_group)
            mapping["physical_groups"].append({"name": name, "dim": 2, "tag": ordinal+7,
                "entity_tags": [ordinal], "component_id": component, "catalog_face_id": face_id,
                "node_ids": group_nodes})
            for face in selected:
                eid = number*10000 + 1000 + face*47
                nodes = [ids[i] for i in faces[face]]
                mapping["elements"].append({"id": eid, "type": 9, "dim": 2, "physical_tag": ordinal+7,
                    "entity_tag": ordinal, "component_id": component, "catalog_face_id": face_id, "node_ids": nodes})
                native_source_cells.append((eid, "TRIA6", nodes))
        # Independent consistent surface-force integral: quadratic triangle
        # corners integrate to0, each midside shape integrates to area/3.
        rf = [[0., 0., 0.] for _ in xyz]
        for face, conn in enumerate(faces):
            p, q, r = [xyz[i] for i in conn[:3]]
            u, v = ([q[i]-p[i] for i in range(3)], [r[i]-p[i] for i in range(3)])
            cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
            center = [.25, .25, .25 + (0. if face < 4 else 20. if face < 8 else 40.)]
            if sum(cross[i] * (p[i]-center[i]) for i in range(3)) < 0:
                cross = [-x for x in cross]
            traction_integral = [sum(s*c for s, c in zip(row, cross))/6. for row in stress_matrix]
            for index in conn[3:]:
                rf[index] = [old+force for old, force in zip(rf[index], traction_integral)]
        reactions.update(zip(ids, rf))
    source_nodes = list(reversed(mapping["nodes"]))
    source_to_native = {n["id"]: i for i, n in enumerate(source_nodes)}
    source_cells = list(reversed(native_source_cells))
    catalog = {"schema_version": 1, "index_convention": "zero_based_native_numeric", "units": "mm",
        "node_count": len(source_nodes), "cell_count": len(source_cells),
        "node_indices": list(reversed(range(len(source_nodes)))),
        "coordinates_mm": [n["xyz_mm"] for n in source_nodes],
        "cells": [{"index": i, "type": kind, "node_indices": [source_to_native[n] for n in conn]}
                  for i, (_, kind, conn) in enumerate(source_cells)],
        "group_names": [g["name"] for g in mapping["physical_groups"]],
        "group_cell_indices": {}, "group_node_indices": {}, "standalone_node_groups": {},
        "labels": {name: {"status": "UNAVAILABLE", "values": None} for name in ("nodes", "cells")}}
    elements = {e["id"]: e for e in mapping["elements"]}
    for group in mapping["physical_groups"]:
        catalog["group_cell_indices"][group["name"]] = [i for i, (eid, _, _) in enumerate(source_cells)
            if elements[eid]["dim"] == group["dim"] and elements[eid]["physical_tag"] == group["tag"]]
        catalog["group_node_indices"][group["name"]] = [source_to_native[n] for n in group["node_ids"]]
    tables = {}
    for name in ("DEPL", "REAC_NODA"):
        table = {k: [] for k in ("NOEUD", "NUME_ORDRE", "COOR_X", "COOR_Y", "COOR_Z", "DX", "DY", "DZ")}
        for index in reversed(range(len(source_nodes))):
            node = source_nodes[index]; x, y, z = node["xyz_mm"]
            values = ([.012+1e-4*x+4e-5*y-5e-5*z, -.007-2e-5*x-2e-4*y+6e-5*z,
                       .003+9e-5*x-8e-5*y+3e-4*z] if name == "DEPL" else reactions[node["id"]])
            row = [str(index+1).rjust(8), 1, x, y, z, *values]
            for key, value in zip(table, row): table[key].append(value)
        tables[name] = table
    stress_cols = ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", "COOR_X", "COOR_Y", "COOR_Z",
                   "SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ")
    geom_cols = ("MAILLE", "POINT", "SOUS_POINT", "X", "Y", "Z", "W")
    tables["SIEF_ELGA"], tables["COOR_ELGA"] = ({k: [] for k in cols} for cols in (stress_cols, geom_cols))
    reference_points = ((.25, .25, .25), (1/6, 1/6, 1/6), (1/6, 1/6, .5),
                        (1/6, .5, 1/6), (.5, 1/6, 1/6))
    for cell in reversed(catalog["cells"]):
        if cell["type"] != "TETRA10": continue
        vertices = [catalog["coordinates_mm"][i] for i in cell["node_indices"][:4]]
        eid = source_cells[cell["index"]][0]
        determinant = .25 if (eid % 10000)//31 <= 4 else 1.
        for point in reversed(range(1, 6)):
            x, y, z = reference_points[point-1]
            coords = [sum(l*p[axis] for l, p in zip((y, z, 1-x-y-z, x), vertices)) for axis in range(3)]
            name = str(cell["index"]+1).rjust(8)
            sr = [name, point, 1, 1, *coords, .32, -.16, .64, .016, .032, -.016]
            gr = [name, point, 1, *coords, (-2/15 if point == 1 else 3/40)*determinant]
            for key, value in zip(stress_cols, sr): tables["SIEF_ELGA"][key].append(value)
            for key, value in zip(geom_cols, gr): tables["COOR_ELGA"][key].append(value)
    _, _, boundary = w.body_layout(mapping, catalog, components)
    raw = {"solver_status": "COMPLETED", "converged": True, "order": 1, "available_orders": [1],
        "access_parameters": {"NUME_ORDRE": [1], "INST": [0.]}, "tables": tables,
        "identity_verified_before_model": True, "boundary": boundary,
        "geometry_context": {"basis": "CHAM_GD from CALC_CHAM_ELEM on the same imported model",
            "result_order_binding": "DERIVED_COMMAND_CONTEXT_NOT_NATIVE_GEOMETRY_ORDER",
            "selected_result_order": 1, "volume_groups": [f"V{i:04d}" for i in range(1, 8)]},
        "native_energy": {c: {"status": "OBSERVED", "selection": {"GROUP_MA": f"V{i:04d}", "NUME_ORDRE": 1,
            "option": "ENER_POT"}, "table": {"TOTALE": [.00006448], "NUME_ORDRE": [1], "LIEU": [f"V{i:04d}"]}}
            for i, c in enumerate(components, 1)}}
    quality = {"status": "PASS", "bodies": [{"component_id": c, "status": "PASS", "integrated_mesh_volume_mm3": .5}
                                              for c in components]}
    msh = ("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$PhysicalNames\n84\n" +
        "".join(f'{g["dim"]} {g["tag"]} "{g["name"]}"\n' for g in mapping["physical_groups"]) +
        "$EndPhysicalNames\n$Nodes\n" + str(len(mapping["nodes"])) + "\n" +
        "".join(str(n["id"]) + " " + " ".join(format(v, ".17g") for v in n["xyz_mm"]) + "\n" for n in mapping["nodes"]) +
        "$EndNodes\n$Elements\n" + str(len(mapping["elements"])) + "\n" +
        "".join(f'{e["id"]} {e["type"]} 2 {e["physical_tag"]} {e["entity_tag"]} ' +
                " ".join(map(str, e["node_ids"])) + "\n" for e in mapping["elements"]) + "$EndElements\n").encode()
    return SimpleNamespace(mapping=mapping, catalog=catalog, quality=quality, raw=raw, original=msh)


@pytest.fixture
def e():
    return synthetic()


def admitted(e):
    return w.parse_native_fields(e.raw, e.mapping, e.catalog, e.quality, canonical_settings())


def test_complete_shuffled_coincident_bodies_signed_weights_and_interior_nodes(e):
    fields = admitted(e)
    assert w.foundation.coordinate_bijection(e.catalog["coordinates_mm"], e.catalog["coordinates_mm"]) is None
    assert fields["geometry_order_binding"] == "DERIVED_COMMAND_CONTEXT_NOT_NATIVE_GEOMETRY_ORDER"
    for body in fields["bodies"].values():
        assert len(body["nodes"]) == 35 and len(body["gauss"]) == 30
        assert sum(not n["exterior"] for n in body["nodes"]) == 5
        assert sum(p["weight_mm3"] < 0 for p in body["gauss"]) == 6
    result = compare_fields(canonical_settings(), fields)
    assert result["status"] == "PASS" and result["decision"] == "NOT_RELEASED"
    assert result["material_qualification"] == "HYPOTHETICAL_NOT_MEASURED"
    assert set(result["metrics"]) == set(canonical_settings()["limits"])
    assert all(c["status"] == "PASS" for c in result["checks"])
    assert all(b["derived_boundary_work_n_mm"] == pytest.approx(.00006448) for b in result["bodies"])


@pytest.mark.parametrize("fault", ["last_node", "duplicate_node", "label_guess", "missing_rf", "nodal_order",
    "coordinate", "last_gauss", "duplicate_gauss", "foreign_cell", "point", "subpoint", "stress_order",
    "missing_w", "nonfinite", "weight_sign", "point_permutation", "boundary", "access_order", "connectivity"])
def test_incomplete_or_misbound_native_fields_fail_closed(e, fault):
    tables = e.raw["tables"]
    if fault == "last_node":
        for values in tables["DEPL"].values(): values.pop()
    elif fault == "duplicate_node": tables["DEPL"]["NOEUD"][-1] = tables["DEPL"]["NOEUD"][0]
    elif fault == "label_guess": tables["DEPL"]["NOEUD"][0] = "N1"
    elif fault == "missing_rf": tables["REAC_NODA"]["DZ"][0] = None
    elif fault == "nodal_order": tables["DEPL"]["NUME_ORDRE"][0] = 2
    elif fault == "coordinate": tables["DEPL"]["COOR_X"][0] += 1e-5
    elif fault == "last_gauss":
        for values in tables["SIEF_ELGA"].values(): values.pop()
    elif fault == "duplicate_gauss":
        for key in ("MAILLE", "POINT", "SOUS_POINT"): tables["SIEF_ELGA"][key][-1] = tables["SIEF_ELGA"][key][0]
    elif fault == "foreign_cell": tables["SIEF_ELGA"]["MAILLE"][0] = "99999999"
    elif fault == "point": tables["SIEF_ELGA"]["POINT"][0] = 6
    elif fault == "subpoint": tables["SIEF_ELGA"]["SOUS_POINT"][0] = 2
    elif fault == "stress_order": tables["SIEF_ELGA"]["NUME_ORDRE"][0] = 2
    elif fault == "missing_w": del tables["COOR_ELGA"]["W"]
    elif fault == "nonfinite": tables["SIEF_ELGA"]["SIXX"][0] = math.inf
    elif fault == "weight_sign": tables["COOR_ELGA"]["W"][-1] = abs(tables["COOR_ELGA"]["W"][-1])
    elif fault == "point_permutation":
        for key in ("X", "Y", "Z", "W"):
            values = tables["COOR_ELGA"][key]; values[0], values[1] = values[1], values[0]
    elif fault == "boundary": e.raw["boundary"][0]["exterior_node_indices"].append(e.raw["boundary"][0]["interior_node_indices"][0])
    elif fault == "access_order": e.raw["access_parameters"]["NUME_ORDRE"] = [2]
    elif fault == "connectivity": e.catalog["cells"][-1]["node_indices"][8:] = list(reversed(e.catalog["cells"][-1]["node_indices"][8:]))
    with pytest.raises((ValueError, KeyError)):
        admitted(e)


def test_curved_midside_cannot_be_replaced_by_corner_only_gauss_coordinates(e):
    cell = next(c for c in e.catalog["cells"] if c["type"] == "TETRA10")
    index = cell["node_indices"][9]
    e.catalog["coordinates_mm"][index][0] += .01
    # The mapping's JSON lists are shared with the artificial actual catalogue;
    # deliberately bind both before changing nodal table coordinates.
    assert e.mapping["nodes"]
    for field in ("DEPL", "REAC_NODA"):
        table = e.raw["tables"][field]
        row = next(i for i, n in enumerate(table["NOEUD"]) if int(n) == index+1)
        table["COOR_X"][row] = e.catalog["coordinates_mm"][index][0]
    with pytest.raises(ValueError, match="curved geometry"):
        admitted(e)


@pytest.mark.parametrize("fault", ["stress", "interior_u", "force", "native_energy", "qualified_volume"])
def test_exact_body_limits_reject_observed_failures_without_averaging_or_tuning(e, fault):
    fields = admitted(e)
    component = canonical_settings()["components"][0]
    body = fields["bodies"][component]
    if fault == "stress": body["gauss"][0]["stress6_mpa"][0] += .001
    elif fault == "interior_u": next(n for n in body["nodes"] if not n["exterior"])["displacement_mm"][0] += .001
    elif fault == "force":
        body["nodes"][0]["reaction_n"][0] += 1.
        fields["bodies"][canonical_settings()["components"][1]]["nodes"][0]["reaction_n"][0] -= 1.
    elif fault == "native_energy": body["native_energy"]["value_n_mm"] *= 1.01
    else: body["qualified_mesh_volume_mm3"] *= 1.001
    result = compare_fields(canonical_settings(), fields)
    assert result["status"] == "FAIL" and result["decision"] == "NOT_RELEASED"
    assert result["limits"] == canonical_settings()["limits"]
    assert any(c["status"] == "FAIL" and c["code"].endswith(":"+component) for c in result["checks"])


@pytest.mark.parametrize("fault", ["unavailable", "missing_totale", "wrong_lieu", "wrong_order", "nan"])
def test_missing_native_energy_stays_unknown_despite_correct_derived_work(e, fault):
    component = canonical_settings()["components"][0]
    observation = e.raw["native_energy"][component]
    if fault == "unavailable": observation["status"] = "UNKNOWN"
    elif fault == "missing_totale": del observation["table"]["TOTALE"]
    elif fault == "wrong_lieu": observation["table"]["LIEU"] = ["FOREIGN"]
    elif fault == "wrong_order": observation["table"]["NUME_ORDRE"] = [2]
    else: observation["table"]["TOTALE"] = [math.nan]
    result = compare_fields(canonical_settings(), admitted(e))
    assert result["status"] == "UNKNOWN" and not result["metrics"]["energy_relative"]["valid"]
    assert result["metrics"]["energy_relative"]["value"] is None
    assert any(c["code"].startswith("derived_boundary_work") and c["status"] == "PASS" for c in result["checks"])


@pytest.fixture
def controlled_job(e, tmp_path, monkeypatch):
    bundle = object.__new__(a.transport.QualifiedAssemblyMeshBundle)
    events, state = [], {"fault": None}
    def capture(self, parent, parent_root, root):
        assert self is bundle
        events.append("capture"); root.mkdir()
        (root / "mesh.msh").write_bytes(e.original)
        outputs = {"mesh.msh": pin(e.original), "mapping.json": save(root / "mapping.json", e.mapping),
                   "quality.json": save(root / "quality.json", e.quality)}
        receipt = {"mesh_revision": "a"*64, "parent": {"cad_revision": "b"*64},
                   "profile": {"name": "coarse3", "mesh_size_mm": 3.}, "output_files": outputs}
        receipt_pin = save(root / "receipt.json", receipt)
        return {"receipt": {"path": "receipt.json", **receipt_pin}}
    def recheck(self, root):
        assert self is bundle; events.append("recheck"); assert (root / "mesh.msh").read_bytes() == e.original
        if state["fault"] == "final_table" and "native-mock" in events:
            path = root.parent / "native/depl.table.json"
            table = json.loads(path.read_bytes()); table["DX"][0] += .1
            save(path, table)
    monkeypatch.setattr(a.transport.QualifiedAssemblyMeshBundle, "capture", capture)
    monkeypatch.setattr(a.transport.QualifiedAssemblyMeshBundle, "recheck", recheck)
    image, runtime = tmp_path / "synthetic.sif", tmp_path / "synthetic-runtime"
    image.write_bytes(b"SYNTHETIC not an executable image"); runtime.write_bytes(b"SYNTHETIC not a runtime")
    monkeypatch.setattr(a.transport, "_image_identity", lambda: (image, a.transport._entry(image), runtime, a.transport._entry(runtime)))
    monkeypatch.setattr(a.transport, "_budgets", lambda: {"solver_time_seconds": 86400,
        "solver_memory_mb": 1024, "subprocess_timeout_seconds": None})
    def process(command, native, label, *, timeout):
        assert timeout is None
        if label == "container-version": events.append("version"); return "SYNTHETIC"
        events.append("native-mock")
        assert command[-1] == "/work/native/affine.export"
        if state["fault"] == "exit":
            (native / "partial.raw.txt").write_text("SYNTHETIC partial native output")
            raise RuntimeError("SYNTHETIC nonzero exit")
        config = json.loads((native / "input.json").read_bytes())
        raw = deepcopy(e.raw)
        runtime_record = {"versions": {"code_aster": "17.4.0", "qualification": "SYNTHETIC"}, "code_aster_runtime": {}}
        raw.update({"schema_version": 1, "status": "AFFINE_NATIVE_OBSERVED_NOT_COMPARED",
            "input_entry": a.transport._entry(native / "input.json"),
            "native_sources": config["native_sources"], "transport_entry": config["transport_entry"],
            "mesh_revision": config["mesh_revision"], "parent": config["parent"], "profile": config["profile"],
            "decision": "NOT_RELEASED", "runtime_before": runtime_record, "runtime_after": runtime_record,
            "catalog_entry": save(native / "native-catalog.json", e.catalog), "table_entries": {}})
        save(native / "runtime-before.json", runtime_record); save(native / "runtime-after.json", runtime_record)
        for name, table in raw["tables"].items(): raw["table_entries"][name] = save(native / (name.lower()+".table.json"), table)
        for component, value in raw["native_energy"].items(): save(native / ("energy-"+component+".table.json"), value)
        if state["fault"] == "input": raw["input_entry"] = {"sha256": "0"*64, "size_bytes": 0}
        elif state["fault"] == "image": image.write_bytes(b"SYNTHETIC changed image")
        elif state["fault"] == "table": raw["tables"]["DEPL"]["DX"][0] += .1
        save(native / "worker-result.json", raw)
        return "SYNTHETIC exit0; native acceptance NOT_RUN"
    monkeypatch.setattr(a.transport, "_owned_process", process)
    return SimpleNamespace(e=e, bundle=bundle, adapter=a.FixtureAssemblyAffineFieldAdapter(bundle),
        output=tmp_path / "fresh-affine", parent=tmp_path / "synthetic-cad", state=state, events=events)


def test_adapter_reuses_one_bundle_and_standard_outcome_with_frozen_process_budgets(controlled_job):
    c = controlled_job
    outcome = c.adapter.solve({}, c.parent, c.output, canonical_settings())
    _outcomes.validate_outcome(outcome)
    assert outcome["status"] == "COMPLETED" and outcome["solver_status"] == "COMPLETED"
    assert c.events == ["capture", "version", "recheck", "native-mock", "recheck"]
    assert outcome["raw_result"] == "simulation/comparison.json" and outcome["pending_validations"]
    assert (c.output / "mesh-reuse/mesh.msh").exists() and (c.output / "admitted-fields.json").exists()
    assert outcome["provenance"]["budgets"]["subprocess_timeout_seconds"] is None
    assert outcome["provenance"]["budgets"]["solver_time_seconds"] == 86400
    export = (c.output / "native/affine.export").read_text()
    assert "P time_limit 86400" in export and "F rmed /work/native/fields.med R 80" in export
    assert set(outcome["metrics"]) == set(c.adapter.default_metrics)


@pytest.mark.parametrize("fault", ["exit", "input", "image", "table", "final_table"])
def test_adapter_rejects_and_preserves_partial_or_misbound_results(controlled_job, fault):
    c = controlled_job; c.state["fault"] = fault
    outcome = c.adapter.solve({}, c.parent, c.output, canonical_settings())
    _outcomes.validate_outcome(outcome)
    assert outcome["status"] == "REJECTED" and outcome["converged"] is None
    assert (c.output / "failure.json").exists() and not (c.output / "adapter-outcome.json").exists()
    assert c.events[-1] == "recheck" and not outcome["metrics"]["native_field_admission"]["valid"]
    if fault == "exit": assert (c.output / "native/partial.raw.txt").exists()
    else: assert (c.output / "native/worker-result.json").exists()


def test_adapter_native_energy_unknown_blocks_admission_and_passes_common_outcome(controlled_job):
    c = controlled_job
    # Complete synthetic U/RF still cannot stand in for native energy.
    c.e.raw["native_energy"][canonical_settings()["components"][0]] = {
        "status": "UNKNOWN", "table": None, "reason": "SYNTHETIC missing native energy"}
    outcome = c.adapter.solve({}, c.parent, c.output, canonical_settings())
    _outcomes.validate_outcome(outcome)
    assert outcome["status"] == "REJECTED" and outcome["solver_status"] == "COMPLETED"
    assert not outcome["metrics"]["energy_relative"]["valid"]
    assert any(c["status"] == "UNKNOWN" for c in outcome["checks"])
    assert any(c["status"] == "FAIL" for c in outcome["checks"])


def test_frozen_settings_and_fresh_path_block_before_capture(controlled_job):
    c = controlled_job; settings = canonical_settings(); settings["limits"]["stress_absolute_mpa"] = 1.
    with pytest.raises(ValueError, match="frozen"): c.adapter.solve({}, c.parent, c.output, settings)
    assert not c.events and not c.output.exists()
    c.output.mkdir(); (c.output / "old.raw").write_text("preserve")
    with pytest.raises(ValueError, match="Fresh empty"): c.adapter.solve({}, c.parent, c.output, canonical_settings())
    assert (c.output / "old.raw").read_text() == "preserve" and not c.events
    with pytest.raises(TypeError): a.FixtureAssemblyAffineFieldAdapter(SimpleNamespace())


def test_standalone_comm_bootstrap_loads_pinned_pure_capsule_without_native_sdk(tmp_path):
    sources = a.source_files()
    pins = {}
    for name in a._CAPSULE:
        data = sources[name].read_bytes(); (tmp_path / name).write_bytes(data); pins[name] = pin(data)
    ns = {"__name__": "_synthetic_affine_bootstrap", "__package__": "", "__file__": str(tmp_path / a._WORKER)}
    exec(compile((tmp_path / a._WORKER).read_bytes(), str(tmp_path / a._WORKER), "exec"), ns)
    prefixes = ("_affine_capsule", "plugins")
    saved = {name: value for name, value in sys.modules.items() if any(name == p or name.startswith(p+".") for p in prefixes)}
    native_before = {name for name in sys.modules if name == "code_aster" or name.startswith("code_aster.")}
    try:
        for name in saved: del sys.modules[name]
        modules = ns["_capsule_modules"](tmp_path, pins)
        assert callable(modules[a._WORKER].parse_native_fields)
        assert modules["assembly_field_reference.py"].canonical_settings() == canonical_settings()
        assert {name for name in sys.modules if name == "code_aster" or name.startswith("code_aster.")} == native_before
    finally:
        for name in list(sys.modules):
            if any(name == p or name.startswith(p+".") for p in prefixes): del sys.modules[name]
        sys.modules.update(saved)


@pytest.mark.parametrize("fault", [None, "ordered_connectivity", "foreign_group", "all_nodes_boundary"])
def test_worker_checks_same_mesh_identity_before_model_and_keeps_interior_free(e, tmp_path, monkeypatch, fault):
    """Fake native API stops deliberately at MECA; no real SDK is imported."""
    native, capsule, capture = (tmp_path / name for name in ("native", "capsule", "mesh-reuse"))
    for folder in (native, capsule, capture): folder.mkdir()
    pins = {}
    for name in a._CAPSULE:
        data = a.source_files()[name].read_bytes(); (capsule / name).write_bytes(data); pins[name] = pin(data)
    transport_bytes, _ = a.transport.transport_msh(e.original, e.mapping)
    (native / "fort.20").write_bytes(transport_bytes)
    config = {"settings": canonical_settings(), "native_sources": pins,
        "mapping_entry": save(capture / "mapping.json", e.mapping),
        "quality_entry": save(capture / "quality.json", e.quality), "transport_entry": pin(transport_bytes)}
    save(native / "input.json", config)
    calls, node_groups = [], {}
    catalog = deepcopy(e.catalog)
    if fault == "ordered_connectivity":
        cell = next(c for c in catalog["cells"] if c["type"] == "TETRA10")
        cell["node_indices"][8], cell["node_indices"][9] = cell["node_indices"][9], cell["node_indices"][8]
    elif fault == "foreign_group": catalog["group_cell_indices"]["V0001"].append(catalog["group_cell_indices"]["V0002"][0])
    class Mesh:
        sdj = SimpleNamespace(NOMNOE=SimpleNamespace(get=lambda: None), NOMMAI=SimpleNamespace(get=lambda: None))
        def getNumberOfNodes(self): return catalog["node_count"]
        def getNumberOfCells(self): return catalog["cell_count"]
        def getGroupsOfCells(self): return catalog["group_names"]
        def getGroupsOfNodes(self): return list(node_groups)
        def getConnectivity(self): return [c["node_indices"] for c in catalog["cells"]]
        def getCellTypeName(self, index): return catalog["cells"][index]["type"]
        def getCoordinates(self): return SimpleNamespace(toNumpy=lambda: SimpleNamespace(tolist=lambda: catalog["coordinates_mm"]))
        def getCells(self, group): return catalog["group_cell_indices"][group]
        def getNodesFromCells(self, group): return catalog["group_node_indices"][group]
        def getNodes(self, group=None): return list(range(catalog["node_count"])) if group is None else node_groups[group]
    mesh = Mesh()
    vendor = ModuleType("code_aster.Commands")
    def groups(**kwargs):
        assert kwargs["reuse"] is mesh and kwargs["MAILLAGE"] is mesh
        declarations = kwargs["CREA_GROUP_NO"]
        if isinstance(declarations, dict): declarations = [declarations]
        for declaration in declarations:
            if "GROUP_MA" in declaration:
                node_groups[declaration["NOM"]] = list(mesh.getNodesFromCells(declaration["GROUP_MA"]))
            else:
                node_groups[declaration["NOM"]] = sorted({n for g in declaration["UNION"] for n in node_groups[g]})
                if fault == "all_nodes_boundary": node_groups[declaration["NOM"]] = mesh.getNodes()
        calls.append("node-groups")
        return mesh
    def model(**kwargs):
        assert kwargs["MAILLAGE"] is mesh
        assert kwargs["AFFE"]["GROUP_MA"] == [f"V{i:04d}" for i in range(1, 8)]
        calls.append("model")
        return object()
    def cine(**kwargs):
        assert kwargs["MECA_IMPO"]["GROUP_NO"] == "AFF_EXT"
        exterior = set(mesh.getNodes("AFF_EXT"))
        assert len(exterior) == 210 and len(set(mesh.getNodes())-exterior) == 35
        calls.append("exterior-cine")
        return object()
    def meca(**kwargs):
        calls.append("MECA")
        assert kwargs["INST"] == 0.0 and kwargs["OPTION"] == "SIEF_ELGA"
        assert kwargs["SOLVEUR"] == {"METHODE": "MUMPS", "STOP_SINGULIER": "OUI"}
        assert set(kwargs) == {"MODELE", "CHAM_MATER", "INST", "EXCIT", "OPTION", "SOLVEUR"}
        raise RuntimeError("SYNTHETIC_STOP_AT_MECA")
    for name in ("CALC_CHAM_ELEM", "CALC_CHAMP", "CREA_TABLE", "FIN", "IMPR_RESU", "POST_ELEM"):
        setattr(vendor, name, lambda **kwargs: pytest.fail("Unexpected mock operation after intentional MECA stop"))
    vendor.DEBUT = lambda: calls.append("DEBUT")
    vendor.LIRE_MAILLAGE = lambda **kwargs: mesh
    vendor.DEFI_GROUP, vendor.AFFE_MODELE, vendor.AFFE_CHAR_CINE_F, vendor.MECA_STATIQUE = groups, model, cine, meca
    vendor.DEFI_MATERIAU = lambda **kwargs: object()
    vendor.AFFE_MATERIAU = lambda **kwargs: object()
    vendor.FORMULE = lambda **kwargs: kwargs
    syntax = ModuleType("code_aster.Cata.Syntax"); syntax._F = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "code_aster", ModuleType("code_aster"))
    monkeypatch.setitem(sys.modules, "code_aster.Commands", vendor)
    monkeypatch.setitem(sys.modules, "code_aster.Cata", ModuleType("code_aster.Cata"))
    monkeypatch.setitem(sys.modules, "code_aster.Cata.Syntax", syntax)
    monkeypatch.setattr(w.foundation, "_runtime_versions", lambda: ({"code_aster": "17.4.0", "qualification": "SYNTHETIC"}, {}))
    monkeypatch.chdir(native)
    reference_module = sys.modules["plugins.fixture_design.assembly_field_reference"]
    with pytest.raises((RuntimeError, ValueError)):
        w.run_affine(native / "input.json", {"assembly_field_reference.py": reference_module})
    failure = json.loads((native / "native-failure.json").read_bytes())
    assert failure["numerical_verdict"] == "UNKNOWN" and failure["decision"] == "NOT_RELEASED"
    assert (native / "native-catalog.json").exists() and not (native / "worker-result.json").exists()
    if fault is None:
        assert calls.index("model") < calls.index("exterior-cine") < calls.index("MECA")
        assert failure["phase"] == "MECA" and (native / "pre-meca-import-comparison.json").exists()
    else:
        assert "model" not in calls and "MECA" not in calls and failure["phase"] == "PRE_MECA_IDENTITY"
