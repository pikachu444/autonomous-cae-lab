"""Pure native-contract tests. Synthetic fields are never solver evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import types

import pytest

from caelab.adapters import structural_family_codeaster as adapter_module
from caelab.adapters.structural_family_codeaster import StructuralFamilyCodeAsterAdapter
from caelab.adapters import structural_family_codeaster_worker as worker
from caelab.adapters.structural_family_mesh import hexa20_point_coordinates, write_gmsh


def save(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def catalogue():
    # Canonical bottom/top/vertical order. NativeMesh deliberately reverses
    # node/cell indices, so catalogue IDs cannot be guessed as native indices.
    points = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
              (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
              (0, -1, -1), (1, 0, -1), (0, 1, -1), (-1, 0, -1),
              (0, -1, 1), (1, 0, 1), (0, 1, 1), (-1, 0, 1),
              (-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)]
    ids = list(range(1, 21))
    nodes = [{"id": node, "coordinates_mm": [float(value) for value in point]} for node, point in zip(ids, points)]
    return {"schema_version": "1", "case": "SYNTHETIC_EXTRACTION_FIXTURE", "cells": [1, 1, 1], "element_type": "HEXA20",
            "nodes": nodes, "elements": [{"id": 1, "node_ids": ids}],
            "groups": {"ROOT": [node for node, point in zip(ids, points) if point[0] == -1],
                       "TIP": [node for node, point in zip(ids, points) if point[0] == 1], "ALL_NODES": ids},
            "supports": [{"node_id": ids[0], "components": [1]}],
            "nodal_loads_n": [{"node_id": node, "value": [1.0 if node == ids[1] else 0.0, 0.0, 0.0]} for node in ids],
            "response_node_ids": {"tip": [ids[1], ids[2]]}, "checks": {}}


def expected_mesh(tmp_path, source=None):
    mesh = deepcopy(source if source is not None else catalogue())
    msh = tmp_path / "mesh.msh"
    write_gmsh(mesh, msh)
    mesh["native_import"] = worker.gmsh_import_contract(mesh, msh)
    return mesh


class Array:
    def __init__(self, rows): self.rows = rows
    def toNumpy(self): return self
    def tolist(self): return deepcopy(self.rows)


class NativeMesh:
    def __init__(self, expected):
        self.ids = list(reversed([row["id"] for row in expected["nodes"]]))
        source_nodes = {row["id"]: row["coordinates_mm"] for row in expected["nodes"]}
        self.coordinates = [deepcopy(source_nodes[node]) for node in self.ids]
        self.index_by_id = {node: index for index, node in enumerate(self.ids)}
        self.cells = list(reversed(deepcopy(expected["native_import"]["cells"])))
        self.connectivity = [[self.index_by_id[node] for node in cell["node_ids"]] for cell in self.cells]
        # Pinned pregms.F90 stores physical names in character(len=8).
        # Derive the mock import independently of the recorded adapter map.
        self.cell_groups = {name[:8]: [index for index, cell in enumerate(self.cells) if cell["group"] == name]
                            for name in expected["native_import"]["physical_groups"]}
        self.node_groups = {}
    def getCoordinates(self): return Array(self.coordinates)
    def getNodes(self, group=None): return list(range(len(self.ids))) if group is None else list(self.node_groups[group])
    def getNumberOfNodes(self): return len(self.ids)
    def getNumberOfCells(self): return len(self.cells)
    def getConnectivity(self): return deepcopy(self.connectivity)
    def getGroupsOfCells(self): return list(self.cell_groups)
    def getCells(self, group): return list(self.cell_groups[group])
    def getCellTypeName(self, index): return self.cells[index]["type"]
    def getNodesFromCells(self, group): return sorted({node for index in self.cell_groups[group] for node in self.connectivity[index]})


def native_raw(expected, *, mesh=None):
    mesh = mesh or NativeMesh(expected)
    guard = worker.validate_native_mesh(mesh, expected)
    guard["support_and_load_groups_verified"] = True
    order = 7
    tables = {}
    for field in ("DEPL", "REAC_NODA"):
        table = {column: [] for column in ("NOEUD", "NUME_ORDRE", *worker.COORDINATE_COMPONENTS, *worker.VECTOR_COMPONENTS)}
        for index in reversed(range(len(mesh.ids))):
            values = [0.0, 0.0, 0.0]
            if field == "REAC_NODA" and mesh.ids[index] == expected["supports"][0]["node_id"]:
                values = [-1.0, 999.0, -999.0]  # Free components must not enter the restrained resultant.
            table["NOEUD"].append(str(index + 1)); table["NUME_ORDRE"].append(order)
            for column, value in zip(worker.COORDINATE_COMPONENTS, mesh.coordinates[index]): table[column].append(value)
            for column, value in zip(worker.VECTOR_COMPONENTS, values): table[column].append(value)
        tables[field] = table
    table = {column: [] for column in ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", *worker.COORDINATE_COMPONENTS, *worker.STRESS_COMPONENTS)}
    nodes = {row["id"]: row["coordinates_mm"] for row in expected["nodes"]}
    elements = {row["id"]: row["node_ids"] for row in expected["elements"]}
    for mapping in guard["source_element_mapping"]:
        physical = [nodes[node] for node in elements[mapping["source_element_id"]]]
        for point in range(27, 0, -1):
            coordinates = hexa20_point_coordinates(physical, worker.ASTER_GAUSS27[point - 1])
            table["MAILLE"].append(str(mapping["native_cell_index"] + 1)); table["POINT"].append(point)
            table["SOUS_POINT"].append(1); table["NUME_ORDRE"].append(order)
            for column, value in zip(worker.COORDINATE_COMPONENTS, coordinates): table[column].append(value)
            for axis, column in enumerate(worker.STRESS_COMPONENTS): table[column].append(float(point + axis))
    tables["SIEF_ELGA"] = table
    return {"schema_version": "1", "solver_status": "COMPLETED", "converged": True, "order": order,
            "available_orders": [order], "native_mesh_checks": guard, "native_coordinates_mm": mesh.getCoordinates().tolist(),
            "tables": tables, "versions": {"code_aster": "17.4.0", "python": "3.11.14", "numpy": "1.26.4"},
            "code_aster_runtime": {"version": "17.4.0", "parentid": "SYNTHETIC", "branch": "SYNTHETIC"}}


def test_gmsh_and_native_all_cell_bijection_keeps_external_ids_and_grouped_points(tmp_path):
    expected = expected_mesh(tmp_path)
    mesh = NativeMesh(expected)
    guard = worker.validate_native_mesh(mesh, expected)
    assert guard["node_count"] == 20 and guard["volume_element_count"] == 1
    assert guard["total_cell_count"] == 1 + sum(len(nodes) for nodes in expected["groups"].values())
    assert guard["source_node_ids_by_native_index"] == mesh.ids
    assert guard["source_element_mapping"][0]["native_cell_index"] != 0
    assert len(guard["source_cell_mapping"]) == mesh.getNumberOfCells()
    assert "ALL_NODES" not in mesh.getGroupsOfCells() and "ALL_NODE" in mesh.getGroupsOfCells()
    assert guard["canonical_to_native_group_names"]["ALL_NODES"] == "ALL_NODE"
    assert "ALL_NODES" in guard["native_group_node_indices"]


def test_gmsh_duplicate_named_physical_group_cannot_hide_an_extra_tag(tmp_path):
    expected = expected_mesh(tmp_path)
    path = tmp_path / "mesh.msh"
    lines = path.read_text().splitlines()
    start = lines.index("$PhysicalNames") + 1
    end = lines.index("$EndPhysicalNames")
    lines[start] = str(int(lines[start]) + 1)
    lines.insert(end, '0 99 "ROOT"')
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="groups differ"):
        worker.gmsh_import_contract(expected, path)


def test_eight_character_alias_collision_blocks_source_contract_before_native_work(tmp_path):
    mesh = catalogue()
    mesh["groups"]["ALL_NODEX"] = list(mesh["groups"]["ALL_NODES"])
    with pytest.raises(ValueError, match="collide"):
        worker.gmsh_import_contract(mesh, tmp_path / "NOT_CREATED.msh")


@pytest.mark.parametrize("name,alias", [("ALL_NODES", "ALL_NODE"), ("X_SYMMETRY", "X_SYMMET"),
    ("Y_SYMMETRY", "Y_SYMMET"), ("DIAPHRAGM", "DIAPHRAG"),
    ("LONGITUDINAL_SYMMETRY", "LONGITUD"), ("POINT_B", "POINT_B"), ("MixedCase", "MixedCas")])
def test_pinned_name_map_is_exact_prefix_and_preserves_case(name, alias):
    # Source-level policy only; actual probe covers uppercase beam groups.
    assert worker._native_group_name_map({name: {"dimension": 0, "tag": 2}}) == {name: alias}


@pytest.mark.parametrize("failure", ["missing_map", "missing_key", "extra_key", "wrong_alias", "malformed_map", "policy", "dimension", "tag", "boolean_tag", "extra_physical_group"])
def test_native_name_metadata_drift_is_rejected_before_any_native_getter(tmp_path, failure):
    expected = expected_mesh(tmp_path)
    contract = expected["native_import"]
    if failure == "missing_map": del contract["canonical_to_native_group_names"]
    elif failure == "missing_key": del contract["canonical_to_native_group_names"]["ALL_NODES"]
    elif failure == "extra_key": contract["canonical_to_native_group_names"]["EXTRA"] = "EXTRA"
    elif failure == "wrong_alias": contract["canonical_to_native_group_names"]["ALL_NODES"] = "ALL_NODES"
    elif failure == "malformed_map": contract["canonical_to_native_group_names"] = []
    elif failure == "policy": contract["physical_name_policy"] = "CASEFOLD"
    elif failure == "dimension": contract["physical_groups"]["ROOT"]["dimension"] = 3
    elif failure == "tag": contract["physical_groups"]["ROOT"]["tag"] = 99
    elif failure == "boolean_tag": contract["physical_groups"]["SOLID"]["tag"] = True
    elif failure == "extra_physical_group": contract["physical_groups"]["EXTRA"] = {"dimension": 0, "tag": 99}
    unavailable = types.SimpleNamespace(getCoordinates=lambda: pytest.fail("Map rejection precedes native getters"))
    with pytest.raises(ValueError): worker.validate_native_mesh(unavailable, expected)


@pytest.mark.parametrize("failure", ["missing", "extra", "untruncated", "case_drift", "duplicate"])
def test_native_physical_names_require_exact_bijective_aliases(tmp_path, failure):
    expected = expected_mesh(tmp_path); mesh = NativeMesh(expected)
    if failure == "missing": del mesh.cell_groups["ALL_NODE"]
    elif failure == "extra": mesh.cell_groups["EXTRA"] = [0]
    elif failure == "untruncated": mesh.cell_groups["ALL_NODES"] = mesh.cell_groups.pop("ALL_NODE")
    elif failure == "case_drift": mesh.cell_groups["all_node"] = mesh.cell_groups.pop("ALL_NODE")
    elif failure == "duplicate": mesh.getGroupsOfCells = lambda: [*mesh.cell_groups, "ALL_NODE"]
    with pytest.raises(ValueError, match="physical group names"):
        worker.validate_native_mesh(mesh, expected)


def test_source_physical_tag_drift_is_rejected_even_without_native_work(tmp_path):
    expected = expected_mesh(tmp_path)
    path = tmp_path / "mesh.msh"
    lines = path.read_text().splitlines()
    row = lines.index('3 1 "SOLID"')
    lines[row] = '3 99 "SOLID"'
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="dimensions/tags"):
        worker.gmsh_import_contract(expected, path)


@pytest.mark.parametrize("failure", ["coordinates", "topology", "point_cell", "extra_group", "group", "cell_count", "cell_type"])
def test_native_import_refuses_any_geometry_topology_or_physical_group_drift(tmp_path, failure):
    expected = expected_mesh(tmp_path)
    mesh = NativeMesh(expected)
    if failure == "coordinates": mesh.coordinates[0][0] += 1e-5
    elif failure == "topology":
        index = mesh.getCells("SOLID")[0]
        mesh.connectivity[index][12], mesh.connectivity[index][16] = mesh.connectivity[index][16], mesh.connectivity[index][12]
    elif failure == "point_cell": mesh.connectivity[0] = mesh.connectivity[1]
    elif failure == "extra_group": mesh.cell_groups["EXTRA"] = [0]
    elif failure == "group": mesh.cell_groups["ROOT"] = mesh.cell_groups["TIP"]
    elif failure == "cell_count": mesh.cells.pop()
    elif failure == "cell_type": mesh.cells[mesh.getCells("SOLID")[0]]["type"] = "HEXA8"
    with pytest.raises(ValueError): worker.validate_native_mesh(mesh, expected)


def test_complete_fields_use_actual_internal_indices_all27points_and_mask_restrained_dofs(tmp_path):
    expected = expected_mesh(tmp_path)
    raw = native_raw(expected)
    record = worker.parse_field_tables(raw, expected)
    assert record["node_ids"] == sorted(row["id"] for row in expected["nodes"])
    assert len(record["displacements_mm"]) == 20 and len(record["stress_points"]) == 27
    assert {row["point_id"] for row in record["stress_points"]} == set(range(1, 28))
    assert record["reaction_n"] == [-1.0, 0.0, 0.0]
    assert record["reaction_moment_n_mm"] == [0.0, 1.0, -1.0]
    assert record["applied_force_n"] == [1.0, 0.0, 0.0]
    assert record["field_completeness"] == {"displacement": True, "stress": True, "reaction": True, "native_mesh": True}
    assert all(set(point) == {"element_id", "point_id", "coordinates_mm", "components_mpa"} for point in record["stress_points"])
    assert raw["tables"]["REAC_NODA"]["DY"].count(999.0) == 1
    # Native point 2 varies z; canonical xi-fast point 2 varies x.
    assert record["stress_points"][1]["components_mpa"][0] == 10.0


@pytest.mark.parametrize("field", ["DEPL", "REAC_NODA", "SIEF_ELGA"])
@pytest.mark.parametrize("failure", ["missing", "extra", "duplicate", "wrong_order", "coordinate", "nonfinite", "missing_component"])
def test_every_native_table_requires_complete_finite_correctly_identified_rows(tmp_path, field, failure):
    expected = expected_mesh(tmp_path); raw = native_raw(expected); table = raw["tables"][field]
    identity = "MAILLE" if field == "SIEF_ELGA" else "NOEUD"
    component = "SIYZ" if field == "SIEF_ELGA" else "DZ"
    if failure == "missing":
        for values in table.values(): values.pop()
    elif failure == "extra":
        for values in table.values(): values.append(values[0])
    elif failure == "duplicate":
        table[identity][0] = table[identity][1]
        if field == "SIEF_ELGA": table["POINT"][0] = table["POINT"][1]
    elif failure == "wrong_order": table["NUME_ORDRE"][0] = 8
    elif failure == "coordinate": table["COOR_X"][0] += 1e-5
    elif failure == "nonfinite": table[component][0] = float("nan")
    elif failure == "missing_component": del table[component]
    with pytest.raises(ValueError): worker.parse_field_tables(raw, expected)


@pytest.mark.parametrize("failure", ["point_label_only", "wrong_native_element", "subpoint", "available_order", "available_order_float", "source_mapping", "native_guard"])
def test_point_number_or_exit_success_cannot_replace_checked_source_coordinate_identity(tmp_path, failure):
    expected = expected_mesh(tmp_path); raw = native_raw(expected)
    if failure == "point_label_only": raw["tables"]["SIEF_ELGA"]["POINT"][0], raw["tables"]["SIEF_ELGA"]["POINT"][1] = raw["tables"]["SIEF_ELGA"]["POINT"][1], raw["tables"]["SIEF_ELGA"]["POINT"][0]
    elif failure == "wrong_native_element": raw["tables"]["SIEF_ELGA"]["MAILLE"][0] = "1"  # Actual native cell1 is POI1.
    elif failure == "subpoint": raw["tables"]["SIEF_ELGA"]["SOUS_POINT"][0] = 2
    elif failure == "available_order": raw["available_orders"] = [7, 8]
    elif failure == "available_order_float": raw["available_orders"] = [7.0]
    elif failure == "source_mapping": raw["native_mesh_checks"]["source_node_ids_by_native_index"][0] = 1
    elif failure == "native_guard": raw["native_mesh_checks"]["support_and_load_groups_verified"] = False
    with pytest.raises(ValueError): worker.parse_field_tables(raw, expected)


@pytest.mark.parametrize("failure", ["map", "missing_map", "canonical_names", "actual_names", "policy"])
def test_raw_field_guard_cannot_drift_physical_name_metadata(tmp_path, failure):
    expected = expected_mesh(tmp_path); raw = native_raw(expected)
    guard = raw["native_mesh_checks"]
    if failure == "map": guard["canonical_to_native_group_names"]["ALL_NODES"] = "ALL_NODX"
    elif failure == "missing_map": del guard["canonical_to_native_group_names"]
    elif failure == "canonical_names": guard["canonical_physical_group_names"].remove("ALL_NODES")
    elif failure == "actual_names": guard["actual_native_physical_group_names"].append("EXTRA")
    elif failure == "policy": guard["physical_name_policy"] = "UNKNOWN"
    with pytest.raises(ValueError, match="physical name map"):
        worker.parse_field_tables(raw, expected)


def prepare_worker_input(tmp_path, expected):
    level = tmp_path / "level_0"; level.mkdir()
    # Isolated native imports are mocked, but source bytes are actual assigned
    # worker/helper files and are checked by the production worker.
    hashes = {}
    for source in (adapter_module.WORKER, adapter_module._HELPER, adapter_module._MESH):
        target = tmp_path / source.name; shutil.copyfile(source, target); hashes[source.name] = digest(target)
    shutil.copyfile(tmp_path / "mesh.msh", level / "mesh.msh")
    save(level / "expected_mesh.json", expected)
    config = {"settings": {"case": "SYNTHETIC"}, "material": {"youngs_modulus_mpa": 220000.0, "poisson_ratio": 0.0},
              "mesh_sha256": digest(level / "mesh.msh"), "expected_mesh_sha256": digest(level / "expected_mesh.json"), "source_hashes": hashes}
    save(level / "input.json", config)
    return level


def mock_native_commands(monkeypatch, level, expected, mesh, *, wrong_singleton=False):
    calls = []
    raw = native_raw(expected)
    class Result:
        def getIndexes(self): return [7]
        def getAccessParameters(self): return {"INST": [0.0]}
    result = Result()
    def debut(**kwargs):
        calls.append(("DEBUT", kwargs)); shutil.copyfile(level / "mesh.msh", Path("fort.20"))
    def read(**kwargs): calls.append(("LIRE_MAILLAGE", kwargs)); return mesh
    def groups(**kwargs):
        calls.append(("DEFI_GROUP", kwargs))
        definitions = kwargs["CREA_GROUP_NO"]
        for definition in ([definitions] if isinstance(definitions, dict) else definitions):
            if "GROUP_MA" in definition: values = mesh.getNodesFromCells(definition["GROUP_MA"])
            else:
                values = mesh.node_groups[definition["GROUP_NO"]][definition["NUME_INIT"] - 1:definition["NUME_FIN"]]
                if wrong_singleton: values = [0]
            mesh.node_groups[definition["NOM"]] = values
        return mesh
    def command(name, answer=None):
        def call(**kwargs): calls.append((name, kwargs)); return answer
        return call
    class Table:
        def __init__(self, field): self.field = field
        def EXTR_TABLE(self): return self
        def values(self): return deepcopy(raw["tables"][self.field])
    def table(**kwargs): calls.append(("CREA_TABLE", kwargs)); return Table(kwargs["RESU"]["NOM_CHAM"])
    def med(**kwargs): calls.append(("IMPR_RESU", kwargs)); (level / "results.med").write_bytes(b"SYNTHETIC MED PLACEHOLDER; NO SOLVER EXECUTED")
    commands = types.ModuleType("code_aster.Commands")
    for name, callback in {"DEBUT": debut, "LIRE_MAILLAGE": read, "DEFI_GROUP": groups,
        "AFFE_MODELE": command("AFFE_MODELE", "MODEL"), "DEFI_MATERIAU": command("DEFI_MATERIAU", "MAT"),
        "AFFE_MATERIAU": command("AFFE_MATERIAU", "FIELD"), "AFFE_CHAR_MECA": command("AFFE_CHAR_MECA", "LOAD"),
        "MECA_STATIQUE": command("MECA_STATIQUE", result), "CALC_CHAMP": command("CALC_CHAMP", result),
        "CREA_TABLE": table, "IMPR_RESU": med, "FIN": command("FIN")}.items(): setattr(commands, name, callback)
    syntax = types.ModuleType("code_aster.Cata.Syntax"); syntax._F = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "code_aster.Commands", commands)
    monkeypatch.setitem(sys.modules, "code_aster.Cata.Syntax", syntax)
    monkeypatch.setattr(worker, "_runtime_versions", lambda: (raw["versions"], raw["code_aster_runtime"]))
    return calls


def test_native_command_contract_compiles_exact_nodal_forces_and_supported_dofs(tmp_path, monkeypatch):
    expected = expected_mesh(tmp_path); level = prepare_worker_input(tmp_path, expected); mesh = NativeMesh(expected)
    calls = mock_native_commands(monkeypatch, level, expected, mesh); monkeypatch.chdir(level)
    worker.solve_level(str(level / "input.json"))
    load = next(kwargs for name, kwargs in calls if name == "AFFE_CHAR_MECA")
    for source, actual in zip(expected["nodal_loads_n"], load["FORCE_NODALE"]):
        index = mesh.index_by_id[source["node_id"]]
        assert actual["GROUP_NO"] == f"CAE_N{index}"
        assert [actual[axis] for axis in ("FX", "FY", "FZ")] == source["value"]
    assert load["DDL_IMPO"] == ({"GROUP_NO": f"CAE_N{mesh.index_by_id[expected['supports'][0]['node_id']]}", "DX": 0.0},)
    assert "FORCE_FACE" not in load and "FORCE_INTERNE" not in load
    assert next(kwargs for name, kwargs in calls if name == "AFFE_MODELE")["AFFE"]["GROUP_MA"] == "SOLID"
    assert [name for name, _ in calls].index("DEFI_GROUP") < [name for name, _ in calls].index("MECA_STATIQUE")
    assert (level / "worker_result.json").is_file() and (level / "sief_elga.table.json").is_file()


@pytest.mark.parametrize("failure", ["collision", "missing_map", "alias", "tag"])
def test_name_refusal_precedes_first_native_command_and_preserves_not_run(tmp_path, monkeypatch, failure):
    expected = expected_mesh(tmp_path); level = prepare_worker_input(tmp_path, expected); mesh = NativeMesh(expected)
    calls = mock_native_commands(monkeypatch, level, expected, mesh)
    if failure == "collision": expected["groups"]["ALL_NODEX"] = list(expected["groups"]["ALL_NODES"])
    elif failure == "missing_map": del expected["native_import"]["canonical_to_native_group_names"]
    elif failure == "alias": expected["native_import"]["canonical_to_native_group_names"]["ALL_NODES"] = "ALL_NODX"
    elif failure == "tag": expected["native_import"]["physical_groups"]["TIP"]["tag"] = 99
    save(level / "expected_mesh.json", expected)
    config = json.loads((level / "input.json").read_text())
    config["expected_mesh_sha256"] = digest(level / "expected_mesh.json")
    save(level / "input.json", config)
    monkeypatch.chdir(level)
    with pytest.raises(RuntimeError, match="pre-command name guard"):
        worker.solve_level(str(level / "input.json"))
    assert calls == []
    assert json.loads((level / "native_mesh_checks.json").read_text())["solver_status"] == "NOT_RUN"


@pytest.mark.parametrize("failure", ["coordinate", "source_hash", "catalogue_hash", "singleton"])
def test_native_pre_meca_failures_block_solver_and_preserve_rejection_artifact(tmp_path, monkeypatch, failure):
    expected = expected_mesh(tmp_path); level = prepare_worker_input(tmp_path, expected); mesh = NativeMesh(expected)
    calls = mock_native_commands(monkeypatch, level, expected, mesh, wrong_singleton=failure == "singleton")
    if failure == "coordinate": mesh.coordinates[0][0] += 0.01
    elif failure == "source_hash": (tmp_path / adapter_module._HELPER.name).write_text("CHANGED SYNTHETIC COPY")
    elif failure == "catalogue_hash": (level / "expected_mesh.json").write_text("CHANGED SYNTHETIC COPY")
    monkeypatch.chdir(level)
    phase = "pre-command name guard rejected" if failure == "catalogue_hash" else "pre-MECA guard rejected"
    with pytest.raises(RuntimeError, match=phase): worker.solve_level(str(level / "input.json"))
    if failure == "catalogue_hash": assert calls == []
    assert not any(name == "MECA_STATIQUE" for name, _ in calls)
    assert json.loads((level / "native_mesh_checks.json").read_text())["solver_status"] == "NOT_RUN"
    assert not (level / "worker_result.json").exists()


def settings():
    return {"case": "ansys_vmd1_regular", "load_case": "Fx", "load_factor": 1.0, "mesh_cells": [[1, 1, 1], [2, 1, 1]]}


@pytest.mark.parametrize("patch", [{"case": "UNKNOWN"}, {"load_factor": True}, {"load_factor": 0.0},
                                   {"load_factor": 2.1}, {"native_command": "UNAUTHORIZED"}, {"mesh_cells": [[48, 48, 48], [49, 49, 49]]}])
def test_invalid_settings_block_all_runtime_commands_and_keep_original_request(tmp_path, monkeypatch, patch):
    monkeypatch.setattr(adapter_module, "_process", lambda *args, **kwargs: pytest.fail("Invalid settings cannot start any process"))
    request = {**settings(), **patch}; original = deepcopy(request)
    result = StructuralFamilyCodeAsterAdapter().solve(tmp_path / "simulation", request)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN" and result["metrics"] == {}
    assert request == original and (tmp_path / "simulation/analysis_raw.json").is_file()


def test_existing_or_linked_output_is_preserved_before_any_native_work(tmp_path):
    original = tmp_path / "original"; original.mkdir(); retained = original / "retained.med"; retained.write_bytes(b"ORIGINAL")
    with pytest.raises(ValueError, match="cannot be overwritten"): StructuralFamilyCodeAsterAdapter().solve(original, settings())
    linked = tmp_path / "linked"; linked.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match="Linked"): StructuralFamilyCodeAsterAdapter().solve(linked, settings())
    assert retained.read_bytes() == b"ORIGINAL" and list(original.iterdir()) == [retained]


def mock_adapter_execution(tmp_path, monkeypatch, mutate=None, process_limits=None):
    image = tmp_path / "SYNTHETIC.sif"; image.write_bytes(b"NOT AN IMAGE; NO NATIVE EXECUTION")
    identity = {"image_sha256": digest(image), "binaries": {"singularity": "SYNTHETIC"}}
    monkeypatch.setattr(adapter_module, "_admitted_runtime", lambda _: ((image, digest(image), "SYNTHETIC_RUNTIME", "SYNTHETIC_GMSH", "SYNTHETIC_PRLIMIT"), identity))
    monkeypatch.setattr(adapter_module, "_assert_runtime", lambda expected: None)
    calls = []
    def process(command, level, label, **kwargs):
        calls.append((label, command))
        if process_limits is not None:
            process_limits.append({"label": label, "timeout": kwargs.get("timeout")})
        if label != "solver": return "SYNTHETIC VERSION; NO EXECUTABLE CALL"
        expected = json.loads((level / "expected_mesh.json").read_text()); raw = native_raw(expected)
        config = json.loads((level / "input.json").read_text())
        raw["input_sha256"] = digest(level / "input.json"); raw["mesh_input_sha256"] = digest(level / "mesh.msh")
        raw["native_mesh_checks"].update({"expected_mesh_sha256": digest(level / "expected_mesh.json"),
            "checked_msh_sha256": digest(level / "mesh.msh"), "input_sha256": raw["input_sha256"]})
        scratch = level.parent / "scratch" / level.name; (scratch / "synthetic-retained.db").write_bytes(b"SYNTHETIC")
        (level / "results.med").write_bytes(b"SYNTHETIC MED PLACEHOLDER")
        if mutate: mutate(raw, level)
        save(level / "worker_result.json", raw); save(level / "native_mesh_checks.json", raw["native_mesh_checks"])
        return "SYNTHETIC PROCESS SUCCESS DOES NOT PROVE NUMERICAL ACCEPTANCE"
    monkeypatch.setattr(adapter_module, "_process", process)
    return calls


def test_mocked_adapter_reuses_fixed_domain_verdict_and_keeps_all_native_fields(tmp_path, monkeypatch):
    process_limits = []
    calls = mock_adapter_execution(tmp_path, monkeypatch, process_limits=process_limits)
    result = StructuralFamilyCodeAsterAdapter().solve(tmp_path / "simulation", settings())
    # Synthetic zero displacement does not satisfy the fixed reference. The
    # process contract is retained without fabricating numerical success.
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED"
    assert result["metrics"]["primary_response"]["valid"] is False
    assert "original_midas_replication" in result["pending_validations"]
    assert result["provenance"]["solver"]["measured_linear_residual"] is None
    budgets = {"solver_memory_mb": 1024, "solver_time_seconds": 86400,
               "subprocess_timeout_seconds": None,
               "solver_time_source": "PINNED_RUN_ASTER_DEFAULT",
               "wall_time_source": "NO_WALL_TIME_LIMIT", "qualification": "UNKNOWN"}
    assert result["provenance"]["process_budgets"] == budgets
    assert json.loads((tmp_path / "simulation/process_budgets.json").read_text()) == budgets
    assert [row["timeout"] for row in process_limits if row["label"] == "solver"] == [None, None]
    records = json.loads((tmp_path / "simulation/mesh_records.json").read_text())
    assert len(records) == 2 and all(len(record["stress_points"]) == record["element_count"] * 27 for record in records)
    for index in range(2):
        level = tmp_path / "simulation" / f"level_{index}"
        assert (level / "results.med").is_file() and (level / "parsed_fields.json").is_file()
        assert "P time_limit 86400\n" in (level / "model.export").read_text()
        assert "P memory_limit 1024\n" in (level / "model.export").read_text()
        assert not (tmp_path / "simulation/scratch" / level.name).exists()
    command = next(command for label, command in calls if label == "solver")
    assert all(value in command for value in ("--cleanenv", "--containall", "--no-home", "--noprofile", "--norc", "OMP_NUM_THREADS=2"))
    assert command[-1] == "/work/level_0/model.export"


def test_failed_solver_keeps_predeclared_budget_and_no_completed_verdict(tmp_path, monkeypatch):
    process_limits = []
    def stop_before_complete_fields(raw, level):
        raise RuntimeError("SYNTHETIC native timeout; no actual process executed")
    mock_adapter_execution(tmp_path, monkeypatch, stop_before_complete_fields, process_limits)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError, match="SYNTHETIC native timeout"):
        StructuralFamilyCodeAsterAdapter().solve(output, settings())
    assert json.loads((output / "process_budgets.json").read_text()) == {
        "solver_memory_mb": 1024, "solver_time_seconds": 86400,
        "subprocess_timeout_seconds": None,
        "solver_time_source": "PINNED_RUN_ASTER_DEFAULT",
        "wall_time_source": "NO_WALL_TIME_LIMIT", "qualification": "UNKNOWN"}
    assert [row["timeout"] for row in process_limits if row["label"] == "solver"] == [None]
    assert "P time_limit 86400\n" in (output / "level_0/model.export").read_text()
    assert not (output / "analysis_raw.json").exists()
    assert not (output / "mesh_records.json").exists()


@pytest.mark.parametrize("failure", ["missing_component", "wrong_version", "input_hash", "source_copy", "point_coordinate", "expected_mesh_file"])
def test_partial_native_fields_or_source_drift_preserve_failed_scratch_and_do_not_publish_verdict(tmp_path, monkeypatch, failure):
    def mutate(raw, level):
        if failure == "missing_component": del raw["tables"]["SIEF_ELGA"]["SIYZ"]
        elif failure == "wrong_version": raw["versions"]["code_aster"] = "17.6.0"
        elif failure == "input_hash": raw["input_sha256"] = "UNKNOWN"
        elif failure == "source_copy": (level.parent / "domain_reference.py").write_text("CHANGED SYNTHETIC SOURCE COPY")
        elif failure == "point_coordinate": raw["tables"]["SIEF_ELGA"]["COOR_X"][0] += 1.0
        elif failure == "expected_mesh_file":
            expected = json.loads((level / "expected_mesh.json").read_text())
            expected["checks"]["tampered_source"] = True
            save(level / "expected_mesh.json", expected)
            # A self-consistent altered receipt cannot replace the immutable
            # expected mesh digest declared before native execution.
            raw["native_mesh_checks"]["expected_mesh_sha256"] = digest(level / "expected_mesh.json")
    calls = mock_adapter_execution(tmp_path, monkeypatch, mutate)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError): StructuralFamilyCodeAsterAdapter().solve(output, settings())
    assert sum(label == "solver" for label, _ in calls) == 1
    assert (output / "level_0/worker_result.json").is_file() and (output / "scratch/level_0/synthetic-retained.db").is_file()
    assert not (output / "analysis_raw.json").exists()


def test_runtime_override_names_block_admission_without_exposing_values(tmp_path, monkeypatch):
    monkeypatch.setenv("SINGULARITY_BIND", "PRIVATE SYNTHETIC VALUE")
    monkeypatch.setattr(adapter_module, "_image_identity", lambda _: pytest.fail("Overrides must block image/runtime access"))
    with pytest.raises(RuntimeError, match="Inherited container overrides") as caught: adapter_module._admitted_runtime(tmp_path)
    assert "PRIVATE SYNTHETIC" not in str(caught.value)


_IMPORT_FIXTURE = Path(__file__).with_name("fixtures") / "codeaster_174_structural_import"
_IMPORT_FIXTURE_HASHES = {
    "expected_mesh.json": "dbf19de6e4af36d36f58f0cf430892afdcb098e7e4169dbfc2b6936573b788f5",
    "import-observations.json": "2f0db39c065f4c582a3f979293e68d04ccd40218b72bf15059e6a8a84da14caa",
    "mesh.msh": "23a5d261f6f53aff05c7c8bd34e94a338a5f9795479e778805757f3221756892",
    "probe-intent.json": "06d6f4c80afe99ded2f6a4cad882415562d39aa6d602a993066334513259308e",
    "probe-receipt.json": "aef5833424e814b9e166deae8216c556daf7d33cfe3ac3733b785f776a1140f9",
}


class ObservedImportMesh:
    """Read-only exact native import snapshot; it contains no solved fields."""
    def __init__(self, observation): self.observation = deepcopy(observation)
    def getCoordinates(self): return Array(self.observation["coordinates"])
    def getNodes(self, group=None):
        return list(range(self.getNumberOfNodes())) if group is None else list(self.observation["node_groups"][group])
    def getNumberOfNodes(self): return self.observation["node_count"]
    def getNumberOfCells(self): return self.observation["cell_count"]
    def getConnectivity(self): return deepcopy(self.observation["connectivity"])
    def getGroupsOfCells(self): return list(self.observation["group_cell_names"])
    def getCells(self, group): return list(self.observation["cell_groups"][group])
    def getCellTypeName(self, index): return self.observation["cell_type_names"][index]
    def getNodesFromCells(self, group): return list(self.observation["group_nodes_from_cells"][group])


def observed_import_fixture():
    for name, expected_hash in _IMPORT_FIXTURE_HASHES.items():
        assert digest(_IMPORT_FIXTURE / name) == expected_hash
    expected = json.loads((_IMPORT_FIXTURE / "expected_mesh.json").read_text())
    original_contract = expected["native_import"]
    corrected_contract = worker.gmsh_import_contract(expected, _IMPORT_FIXTURE / "mesh.msh")
    # Original bytes and every old source cell/name/dimension/tag remain exact;
    # only fresh in-memory adapter import metadata acquires the explicit map.
    assert all(corrected_contract[key] == value for key, value in original_contract.items())
    expected["native_import"] = corrected_contract
    observation = json.loads((_IMPORT_FIXTURE / "import-observations.json").read_text())
    return expected, observation


def test_actual_pinned_import_snapshot_replays_all80nodes102cells_without_solving():
    expected, observation = observed_import_fixture()
    intent = json.loads((_IMPORT_FIXTURE / "probe-intent.json").read_text())
    receipt = json.loads((_IMPORT_FIXTURE / "probe-receipt.json").read_text())
    assert intent["source_commit"] == receipt["source_commit"] == "af9bd45ef2e5c6f66a6c9b46caa44d4ebb213d96"
    assert intent["image_sha256"] == receipt["image_sha256"] == "f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64"
    assert all(intent[key] == receipt[key] == 0 for key in ("mechanical_solves", "Core_operations", "model_calls"))
    assert intent["native_processes"] == 1 and receipt["status"] == "PASS_IMPORT_OBSERVATION_ONLY"
    assert observation["mechanical_solves"] == 0 and observation["status"] == "OBSERVED_NATIVE_IMPORT_ONLY"
    assert observation["version"]["version"] == "17.4.0"
    assert observation["source_unit20_sha256"] == _IMPORT_FIXTURE_HASHES["mesh.msh"]
    assert receipt["observation_sha256"] == _IMPORT_FIXTURE_HASHES["import-observations.json"]
    assert receipt["original_native04"] == "UNCHANGED"
    guard = worker.validate_native_mesh(ObservedImportMesh(observation), expected)
    assert guard["node_count"] == 80 and guard["total_cell_count"] == 102 and guard["volume_element_count"] == 6
    assert len(guard["source_cell_mapping"]) == 102 and len(guard["source_element_mapping"]) == 6
    assert guard["canonical_to_native_group_names"] == {"SOLID": "SOLID", "ALL_NODES": "ALL_NODE", "ROOT": "ROOT", "TIP": "TIP"}
    assert guard["canonical_physical_group_names"] == ["ALL_NODES", "ROOT", "SOLID", "TIP"]
    assert guard["actual_native_physical_group_names"] == ["ALL_NODE", "ROOT", "SOLID", "TIP"]
    assert guard["native_group_node_indices"]["ALL_NODES"] == observation["group_nodes_from_cells"]["ALL_NODE"]
    # This native snapshot proves import identity only, never U/RF/GP stress.
    assert "tables" not in observation and "support_and_load_groups_verified" not in guard
    assert all(digest(_IMPORT_FIXTURE / name) == value for name, value in _IMPORT_FIXTURE_HASHES.items())


@pytest.mark.parametrize("failure", ["coordinate", "topology", "missing_group", "extra_group", "native_name_drift", "group_nodes"])
def test_actual_import_snapshot_drift_is_rejected_without_altering_raw_bytes(failure):
    expected, observation = observed_import_fixture()
    if failure == "coordinate": observation["coordinates"][0][0] += 1.0
    elif failure == "topology": observation["connectivity"][96][0], observation["connectivity"][96][1] = observation["connectivity"][96][1], observation["connectivity"][96][0]
    elif failure == "missing_group": observation["group_cell_names"].remove("ALL_NODE")
    elif failure == "extra_group": observation["group_cell_names"].append("EXTRA")
    elif failure == "native_name_drift": observation["group_cell_names"][1] = "ALL_NODX"
    elif failure == "group_nodes": observation["group_nodes_from_cells"]["ROOT"] = observation["group_nodes_from_cells"]["TIP"]
    with pytest.raises(ValueError): worker.validate_native_mesh(ObservedImportMesh(observation), expected)
    assert all(digest(_IMPORT_FIXTURE / name) == value for name, value in _IMPORT_FIXTURE_HASHES.items())
