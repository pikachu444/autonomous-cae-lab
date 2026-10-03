"""Pure contact identity/table regressions; complete response fixtures are MOCK.

The retained official mesh is real input, but these tests run no native solver
and provide no contact/reference/strength acceptance evidence. Four captured
native no-solve ELGA format rows contain explicitly prescribed synthetic stress.
"""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import types

import pytest

from caelab.adapters import codeaster_contact_worker as worker


ASSET_ROOT = Path(__file__).resolve().parents[1] / "benchmarks/input-data/codeaster"
# Literal selected columns from native-api-readiness-01/native-api-observations.json,
# SHA256 4c6c2a60f31df6cddf0c02aa57c4917fca94bf243cf4b6fa95cde745db0bbef6.
# Runtime17.4.0, source50ebc13c70ee9df62faf93ddcb746a3757b3042a; original MED.
# CREA_CHAMP prescribed 101/102/103/104; zero material/contact/mechanical solves.
# Direct CHAM_GD extraction has no NUME_ORDRE/INST; those are MOCK in raw below.
CAPTURED_NATIVE_ELGA_FORMAT = {
    "MAILLE": ["93"] * 4, "POINT": [1, 2, 3, 4], "SOUS_POINT": [1] * 4,
    "COOR_X": [-0.9647791882712933, -0.8685541411446488, -0.8685541434063555, -0.9647791888773158],
    "COOR_Y": [0.01761039978820132, 0.017610400091212657, 0.06572290788202123, 0.06572290675116751],
    "COOR_Z": [0.0034722211874193307, 0.00347222124716371, 0.003472221187419367, 0.003472221127674988],
    "SIXX": [101.0] * 4, "SIYY": [102.0] * 4, "SIZZ": [103.0] * 4, "SIXY": [104.0] * 4,
}


def settings():
    return {"case": worker.CASE, "material": {"youngs_modulus_pa": 2e6, "poisson_ratio": 0.0},
            "top_displacement_m": -0.1, "limits": {"reference_relative": 0.01, "force_balance_relative": 1e-6}}


@pytest.fixture(scope="module")
def frozen():
    path = ASSET_ROOT / "ssnp121a-17.4.0.mesh.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == worker.MESH_INSPECTION_SHA256
    return json.loads(path.read_text(encoding="utf-8"))


def catalog(frozen, *, generated=True):
    """Deliberately put SEG2 before QUAD4 to exercise actual cell-index mapping."""
    cells, groups = [], {}
    for level, cell_type in (("-1", "SEG2"), ("0", "QUAD4")):
        data = frozen["levels"][level]
        offset = len(cells)
        cells.extend({"cell_id": offset + index, "cell_type": cell_type, "node_ids": deepcopy(nodes)}
                     for index, nodes in enumerate(data["cell_connectivity_in_native_order"]))
        groups.update({name: [offset + index for index in group["cell_ids"]] for name, group in data["groups"].items()})
    node_groups = {name: deepcopy(group["node_ids"]) for name, group in frozen["node_groups"].items()}
    if generated:
        node_groups.update({name: deepcopy(frozen["levels"]["-1"]["groups"][name]["node_ids"])
                            for name in worker.BOUNDARY_GROUPS})
    return {"schema_version": "1", "node_indexing": "ZERO_BASED_CODE_ASTER_UNRENUMBERED", "node_ids": list(range(313)),
            "coordinates_m": [[*point, 0.0] for point in frozen["coordinates_in_native_order"]],
            "native_node_names": deepcopy(frozen["node_name_field"]), "cells": cells,
            "group_cell_ids": groups, "group_node_ids": node_groups}


@pytest.fixture
def raw(frozen):
    mesh = catalog(frozen)
    coordinates = mesh["coordinates_m"]
    boundaries = frozen["levels"]["-1"]["groups"]
    top, bottom, slave = (boundaries[name]["node_ids"] for name in ("CD", "GH", "AB"))

    def nodal(nodes, components, values):
        rows = {"NOEUD": [f"{node + 1:8d}" for node in nodes], "NUME_ORDRE": [1] * len(nodes), "INST": [1.0] * len(nodes)}
        rows.update({column: [coordinates[node][axis] for node in nodes]
                     for axis, column in enumerate(worker.COORDINATE_COMPONENTS)})
        rows.update({component: [values(node)[axis] for node in nodes] for axis, component in enumerate(components)})
        return rows

    def reaction(node):
        return [0.0, -2e5 / len(top) if node in top else 2e5 / len(bottom) if node in bottom else 0.0]

    tables = {"DEPL": nodal(mesh["node_ids"], worker.VECTOR_COMPONENTS, lambda node: [0.0, -0.05 * (coordinates[node][1] + 1)]),
              "REAC_NODA": nodal(mesh["node_ids"], worker.VECTOR_COMPONENTS, reaction),
              "LAGS_C": nodal(slave, ("LAGS_C",), lambda node: [-1e5])}
    stress = {key: [] for key in ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", "INST",
                                *worker.COORDINATE_COMPONENTS, *worker.STRESS_COMPONENTS)}
    for cell in mesh["cells"]:
        if cell["cell_type"] != "QUAD4":
            continue
        geometry = worker._quad_gauss_geometry([coordinates[node] for node in cell["node_ids"]])
        for point, (position, weight) in enumerate(geometry, 1):
            values = {"MAILLE": f"{cell['cell_id'] + 1:8d}", "POINT": point, "SOUS_POINT": 1,
                      "NUME_ORDRE": 1, "INST": 1.0}
            values.update(dict(zip(worker.STRESS_COORDINATE_COMPONENTS, position)))
            values["COOR_Z"] = weight  # Exact native 2D column policy: W, not geometric Z.
            values.update(dict(zip(worker.STRESS_COMPONENTS, [0.0, -1e5, 0.0, 0.0])))
            for name in stress:
                stress[name].append(values[name])
    tables["SIEF_ELGA"] = stress
    # Native extraction need not sort rows. Keep all identities and raw names.
    for table in tables.values():
        for column in table:
            table[column].reverse()
    return {"schema_version": "1", "solver_status": "COMPLETED", "converged": True, "order": 1,
            "input_sha256": "0" * 64, "mesh_input_sha256": worker.MESH_SHA256,
            "mesh_inspection_sha256": worker.MESH_INSPECTION_SHA256, "mesh": mesh, "frozen_mesh": deepcopy(frozen),
            "available_orders": [0, 1], "access_parameters": {"NUME_ORDRE": [0, 1], "INST": [0.0, 1.0]},
            "native_tables": tables, "test_only": "MOCK response; native_solver_executed=False"}


def test_good_original_catalog_preserves_double_nodes_and_native_cell_ids(frozen):
    mesh = catalog(frozen)
    proof = worker.validate_mesh_catalog(mesh, frozen)
    assert proof["node_count"] == 313 and proof["body_element_count"] == 265 and proof["boundary_element_count"] == 92
    assert mesh["coordinates_m"][13][0] == 2.98023223876953e-08
    assert mesh["coordinates_m"][0] == mesh["coordinates_m"][4]
    assert set(proof["boundary_node_ids"]["AB"]).isdisjoint(proof["boundary_node_ids"]["EF"])
    assert proof["source_cell_mapping"][0] == {"native_cell_id": 0, "source_level": "-1", "source_cell_id": 0}
    assert proof["source_cell_mapping"][92] == {"native_cell_id": 92, "source_level": "0", "source_cell_id": 0}


@pytest.mark.parametrize("damage", ["snap", "origin", "index", "cell_index", "direction", "connectivity", "type",
                                    "group", "missing_group", "named_node", "missing_named", "generated", "labels", "bool"])
def test_mesh_drift_is_rejected_before_model_or_contact(frozen, damage):
    mesh = catalog(frozen)
    if damage == "snap": mesh["coordinates_m"][13][0] = 0.0
    elif damage == "origin": mesh["coordinates_m"][0][0] += 0.1
    elif damage == "index": mesh["node_ids"][0], mesh["node_ids"][4] = 4, 0
    elif damage == "cell_index": mesh["cells"][1]["cell_id"] = 0
    elif damage == "direction": mesh["cells"][0]["node_ids"].reverse()
    elif damage == "connectivity": mesh["cells"][92]["node_ids"][0] = 4
    elif damage == "type": mesh["cells"][92]["cell_type"] = "TETRA10"
    elif damage == "group": mesh["group_cell_ids"]["AB"][0] = mesh["group_cell_ids"]["EF"][0]
    elif damage == "missing_group": del mesh["group_cell_ids"]["PLAQUE2"]
    elif damage == "named_node": mesh["group_node_ids"]["A"] = [4]
    elif damage == "missing_named": del mesh["group_node_ids"]["N14"]
    elif damage == "generated": mesh["group_node_ids"]["AB"][0] = 4
    elif damage == "labels": mesh["native_node_names"][0] = "E"
    elif damage == "bool": mesh["cells"][0]["node_ids"][0] = False
    with pytest.raises(ValueError):
        worker.validate_mesh_catalog(mesh, frozen)


def test_frozen_source_tamper_is_rejected(frozen):
    altered = deepcopy(frozen)
    altered["coordinates_in_native_order"][13][0] = 0.0
    with pytest.raises(ValueError, match="sealed official"):
        worker.validate_mesh_catalog(catalog(frozen), altered)


def test_complete_mock_fields_bind_samples_signed_pressure_and_actual_numeric_ids(raw):
    before = deepcopy(raw)
    observed = worker.parse_contact_tables(raw)
    assert observed["samples"]["A"]["node_id"] == 0 and observed["samples"]["B"]["node_id"] == 1
    assert observed["samples"]["N14"]["node_id"] == 13
    assert observed["samples"]["N14"]["normal_traction_pa"] == -1e5
    assert observed["samples"]["N14"]["vertical_displacement_m"] == -0.05
    assert len(observed["slave_contact"]["node_ids"]) == 13
    fields = observed["fields"]
    assert len(fields["displacements_m"]) == len(fields["nodal_reactions_n_per_m"]) == 313
    assert len(fields["stresses_pa"]) == len(fields["stress_identifiers"]) == 1060
    assert fields["stress_component_order"] == ["xx", "yy", "zz", "xy"]
    assert fields["stress_coordinate_component_order"] == ["x", "y"]
    assert all(len(xy) == 2 for xy in fields["stress_point_coordinates_m"])
    assert all(len(xyz) == 3 and xyz[2] == 0.0 for xyz in fields["coordinates_m"])
    assert fields["stress_geometric_z_m"] is None and fields["stress_geometric_z_status"].startswith("UNAVAILABLE")
    assert len(fields["stress_integration_weights_m2"]) == 1060
    assert all(weight > 0 for weight in fields["stress_integration_weights_m2"])
    assert math.fsum(fields["stress_integration_weights_m2"]) == pytest.approx(4.0, abs=1e-13)
    provenance = fields["stress_integration_weight_provenance"]
    assert provenance["raw_table_column"] == "COOR_Z" and provenance["native_component"] == "EGGAU2D.W"
    assert provenance["unit"] == "m^2" and provenance["upstream_commit"] == "50ebc13c70ee9df62faf93ddcb746a3757b3042a"
    assert observed["boundary_reactions_n_per_m"]["top"] == pytest.approx([0.0, -2e5])
    assert observed["boundary_reactions_n_per_m"]["bottom"] == pytest.approx([0.0, 2e5])
    assert observed["boundary_reactions_n_per_m"]["all_nodes"] == pytest.approx([0.0, 0.0], abs=1e-9)
    assert observed["projected_gaps_m"] == pytest.approx([0.0] * 13, abs=1e-15)
    assert "DERIVED" in observed["projected_gap_method"] and observed["native_gap_m"] is None
    assert raw == before


def test_captured_native_no_solve_XY_W_format_is_preserved_without_claiming_stress_qualification(raw):
    """Only four format rows are captured; the completed result envelope is MOCK."""
    table = raw["native_tables"]["SIEF_ELGA"]
    assert "NUME_ORDRE" not in CAPTURED_NATIVE_ELGA_FORMAT and "INST" not in CAPTURED_NATIVE_ELGA_FORMAT
    for captured_row, point in enumerate(CAPTURED_NATIVE_ELGA_FORMAT["POINT"]):
        row = next(i for i, name in enumerate(table["MAILLE"])
                   if int(name) == 93 and table["POINT"][i] == point)
        for column, values in CAPTURED_NATIVE_ELGA_FORMAT.items():
            table[column][row] = values[captured_row]
    raw["mesh"]["native_node_names"] = None  # Actual runtime lacks optional Mesh.getNodeName.
    before = deepcopy(raw)
    fields = worker.parse_contact_tables(raw)["fields"]
    selected = [i for i, identity in enumerate(fields["stress_identifiers"]) if identity["cell_id"] == 92]
    assert len(selected) == 4
    for captured_row, row in enumerate(selected):
        assert fields["stress_identifiers"][row]["raw_element_identifier"] == "93"
        assert fields["stress_identifiers"][row]["point"] == captured_row + 1
        assert fields["stress_point_coordinates_m"][row] == [CAPTURED_NATIVE_ELGA_FORMAT[column][captured_row]
                                                            for column in ("COOR_X", "COOR_Y")]
        assert fields["stress_integration_weights_m2"][row] == CAPTURED_NATIVE_ELGA_FORMAT["COOR_Z"][captured_row]
        assert fields["stresses_pa"][row] == [101.0, 102.0, 103.0, 104.0]  # Explicitly synthetic native constants.
    assert fields["stress_geometric_z_m"] is None
    assert raw == before


@pytest.mark.parametrize("damage", ["missing", "none", "bool", "nan", "infinity", "zero", "negative", "wrong_positive"])
def test_native_stress_weight_must_be_genuine_finite_positive_and_match_the_actual_Jacobian(raw, damage):
    table = raw["native_tables"]["SIEF_ELGA"]
    if damage == "missing":
        del table["COOR_Z"]
    else:
        table["COOR_Z"][0] = {"none": None, "bool": True, "nan": math.nan, "infinity": math.inf,
                              "zero": 0.0, "negative": -0.01,
                              "wrong_positive": table["COOR_Z"][0] * 2.0}[damage]
    with pytest.raises(ValueError):
        worker.parse_contact_tables(raw)


@pytest.mark.parametrize("damage", ["missing_x", "missing_y", "none_x", "bool_y", "nan_x", "infinity_y", "wrong_y", "point_id_swap"])
def test_native_stress_XY_and_point_ID_must_match_the_actual_four_Gauss_locations(raw, damage):
    table = raw["native_tables"]["SIEF_ELGA"]
    if damage.startswith("missing_"):
        del table["COOR_X" if damage.endswith("x") else "COOR_Y"]
    elif damage == "point_id_swap":
        table["POINT"][0], table["POINT"][1] = table["POINT"][1], table["POINT"][0]
    elif damage == "wrong_y":
        table["COOR_Y"][0] += 0.01
    else:
        column = "COOR_X" if damage.endswith("x") else "COOR_Y"
        table[column][0] = {"none_x": None, "bool_y": False, "nan_x": math.nan, "infinity_y": math.inf}[damage]
    with pytest.raises(ValueError):
        worker.parse_contact_tables(raw)


@pytest.mark.parametrize("damage", ["missing_pressure", "missing_pressure_value", "stress_instead", "partial_depl", "partial_reaction",
    "partial_stress", "duplicate_node", "wrong_node_name", "node_coordinate", "point_coordinate", "duplicate_point", "unknown_cell",
    "wrong_point", "subpoint", "order", "instant", "order_mapping", "duplicate_order", "input_digest", "mesh_digest", "catalog_digest",
    "none", "bool", "nan", "infinity", "malformed", "column_length", "converged"])
def test_incomplete_or_malformed_native_tables_remain_unusable(raw, damage):
    tables = raw["native_tables"]
    if damage == "missing_pressure": del tables["LAGS_C"]
    elif damage == "missing_pressure_value": del tables["LAGS_C"]["LAGS_C"]
    elif damage == "stress_instead": tables["LAGS_C"]["SIYY"] = tables["LAGS_C"].pop("LAGS_C")
    elif damage.startswith("partial_"):
        name = {"partial_depl": "DEPL", "partial_reaction": "REAC_NODA", "partial_stress": "SIEF_ELGA"}[damage]
        for column in tables[name].values(): column.pop()
    elif damage == "duplicate_node": tables["DEPL"]["NOEUD"][1] = tables["DEPL"]["NOEUD"][0]
    elif damage == "wrong_node_name": tables["LAGS_C"]["NOEUD"][0] = "N14"
    elif damage == "node_coordinate": tables["REAC_NODA"]["COOR_X"][0] += 0.01
    elif damage == "point_coordinate": tables["SIEF_ELGA"]["COOR_X"][0] += 0.01
    elif damage == "duplicate_point": tables["SIEF_ELGA"]["POINT"][1] = tables["SIEF_ELGA"]["POINT"][0]
    elif damage == "unknown_cell": tables["SIEF_ELGA"]["MAILLE"][0] = "1"
    elif damage == "wrong_point": tables["SIEF_ELGA"]["POINT"][0] = 5
    elif damage == "subpoint": tables["SIEF_ELGA"]["SOUS_POINT"][0] = 2
    elif damage == "order": tables["LAGS_C"]["NUME_ORDRE"][0] = 0
    elif damage == "instant": tables["DEPL"]["INST"][0] = 0.0
    elif damage == "order_mapping": raw["access_parameters"]["INST"] = [1.0, 0.0]
    elif damage == "duplicate_order": raw["available_orders"] = [1, 1]
    elif damage == "input_digest": raw["input_sha256"] = None
    elif damage == "mesh_digest": raw["mesh_input_sha256"] = "1" * 64
    elif damage == "catalog_digest": raw["mesh_inspection_sha256"] = "1" * 64
    elif damage in ("none", "bool", "nan", "infinity"):
        tables["LAGS_C"]["LAGS_C"][0] = {"none": None, "bool": False, "nan": math.nan, "infinity": math.inf}[damage]
    elif damage == "malformed": tables["DEPL"]["DX"] = tuple(tables["DEPL"]["DX"])
    elif damage == "column_length": tables["LAGS_C"]["LAGS_C"].pop()
    elif damage == "converged": raw["converged"] = None
    with pytest.raises(ValueError):
        worker.parse_contact_tables(raw)


@pytest.mark.parametrize("location,value", [("young", True), ("young", "2000000"), ("young", 9999.0), ("nu", 0.3),
    ("delta", 0.0), ("delta", -0.201), ("delta", math.nan), ("limit", 0.02), ("extra", 1)])
def test_worker_input_does_not_admit_unbounded_or_nonfinite_scientific_controls(location, value):
    request = settings()
    if location == "young": request["material"]["youngs_modulus_pa"] = value
    elif location == "nu": request["material"]["poisson_ratio"] = value
    elif location == "delta": request["top_displacement_m"] = value
    elif location == "limit": request["limits"]["reference_relative"] = value
    else: request["native_code"] = value
    with pytest.raises(ValueError): worker.validate_settings(request)


class MockNativeMesh:
    def __init__(self, frozen): self.catalog = catalog(frozen, generated=False)
    def getCoordinates(self):
        return types.SimpleNamespace(toNumpy=lambda: types.SimpleNamespace(tolist=lambda: deepcopy(self.catalog["coordinates_m"])))
    def getNodes(self, name=None): return deepcopy(self.catalog["group_node_ids"][name] if name is not None else self.catalog["node_ids"])
    def getNumberOfNodes(self): return 313
    def getNumberOfCells(self): return 357
    def getConnectivity(self): return [deepcopy(cell["node_ids"]) for cell in self.catalog["cells"]]
    def getCellTypeName(self, index): return self.catalog["cells"][index]["cell_type"]
    def getGroupsOfCells(self): return list(self.catalog["group_cell_ids"])
    def getGroupsOfNodes(self): return list(self.catalog["group_node_ids"])
    def getCells(self, name): return deepcopy(self.catalog["group_cell_ids"][name])
    def getNodeName(self, index): return self.catalog["native_node_names"][index]


def prepare_input(tmp_path, monkeypatch):
    output = tmp_path / "level_00"
    output.mkdir()
    shutil.copyfile(ASSET_ROOT / "ssnp121a-17.4.0.mmed", output / "mesh.mmed")
    shutil.copyfile(ASSET_ROOT / "ssnp121a-17.4.0.mmed", tmp_path / "fort.20")
    shutil.copyfile(ASSET_ROOT / "ssnp121a-17.4.0.mesh.json", tmp_path / "frozen_mesh.json")
    config = {"settings": settings(), "mesh_sha256": worker.MESH_SHA256, "mesh_inspection_sha256": worker.MESH_INSPECTION_SHA256}
    input_path = output / "input.json"
    input_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return input_path


def install_commands(monkeypatch, commands):
    module = types.ModuleType("code_aster.Commands")
    for name, command in commands.items(): setattr(module, name, command)
    syntax = types.ModuleType("code_aster.Cata.Syntax")
    syntax._F = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "code_aster.Commands", module)
    monkeypatch.setitem(sys.modules, "code_aster.Cata.Syntax", syntax)
    monkeypatch.setattr(worker, "_runtime_versions", lambda: ({"code_aster": "17.4.0", "test_only": True}, {"version": "17.4.0"}))


def test_wrong_actual_mesh_blocks_all_model_contact_material_and_stat_commands(tmp_path, monkeypatch, frozen):
    input_path = prepare_input(tmp_path, monkeypatch)
    mesh, called = MockNativeMesh(frozen), []
    mesh.catalog["coordinates_m"][13][0] = 0.0

    def forbidden(**kwargs): pytest.fail("Mesh refusal must precede mechanical/contact execution")

    names = ("AFFE_CHAR_MECA", "AFFE_MATERIAU", "AFFE_MODELE", "CALC_CHAMP", "CREA_TABLE", "DEFI_CONTACT",
             "DEFI_FONCTION", "DEFI_GROUP", "DEFI_LIST_REEL", "DEFI_MATERIAU", "FIN", "IMPR_RESU", "STAT_NON_LINE")
    commands = dict.fromkeys(names, forbidden)
    commands.update({"DEBUT": lambda **kwargs: called.append("DEBUT"), "LIRE_MAILLAGE": lambda **kwargs: mesh})
    install_commands(monkeypatch, commands)
    with pytest.raises(RuntimeError, match="mesh guard rejected"):
        worker.solve_level(str(input_path))
    assert called == ["DEBUT"]
    refusal = json.loads((input_path.parent / "native_mesh_checks.json").read_text())
    assert refusal["status"] == "FAIL" and refusal["solver_status"] == "NOT_RUN"
    assert not (input_path.parent / "worker_result.json").exists()


@pytest.mark.parametrize("mutate_input", [False, True])
def test_mock_execution_preserves_original_native_policy_and_append_only_tables(tmp_path, monkeypatch, frozen, raw, mutate_input):
    input_path = prepare_input(tmp_path, monkeypatch)
    mesh, calls = MockNativeMesh(frozen), {}
    result = types.SimpleNamespace(getAccessParameters=lambda: deepcopy(raw["access_parameters"]),
                                   getIndexes=lambda: [0, 1])

    def record(name, value=None):
        def command(**kwargs):
            calls.setdefault(name, []).append(kwargs)
            if name == "STAT_NON_LINE" and mutate_input:
                input_path.write_bytes(input_path.read_bytes() + b" ")
            return value
        return command

    def groups(**kwargs):
        for item in kwargs["CREA_GROUP_NO"]:
            name = item["GROUP_MA"]
            mesh.catalog["group_node_ids"][name] = deepcopy(frozen["levels"]["-1"]["groups"][name]["node_ids"])
        return mesh

    def table(**kwargs):
        selection = kwargs["RESU"]
        name = "LAGS_C" if selection["NOM_CMP"] == ("LAGS_C",) else selection["NOM_CHAM"]
        return types.SimpleNamespace(EXTR_TABLE=lambda: types.SimpleNamespace(values=lambda: deepcopy(raw["native_tables"][name])))

    commands = {name: record(name, object()) for name in ("AFFE_CHAR_MECA", "AFFE_MATERIAU", "AFFE_MODELE",
        "DEFI_CONTACT", "DEFI_FONCTION", "DEFI_LIST_REEL", "DEFI_MATERIAU")}
    commands.update({"DEBUT": record("DEBUT"), "LIRE_MAILLAGE": record("LIRE_MAILLAGE", mesh), "DEFI_GROUP": groups,
        "STAT_NON_LINE": record("STAT_NON_LINE", result), "CALC_CHAMP": record("CALC_CHAMP", result),
        "CREA_TABLE": table, "FIN": record("FIN"), "IMPR_RESU": record("IMPR_RESU")})
    install_commands(monkeypatch, commands)
    if mutate_input:
        with pytest.raises(RuntimeError, match="input bytes changed"):
            worker.solve_level(str(input_path))
        assert all((input_path.parent / f"order_1_{name.lower()}.table.json").is_file() for name in raw["native_tables"])
        assert not (input_path.parent / "worker_result.json").exists()
        return
    worker.solve_level(str(input_path))
    native = json.loads((input_path.parent / "worker_result.json").read_text())
    assert native["input_sha256"] == hashlib.sha256(input_path.read_bytes()).hexdigest()
    assert native["native_tables"] == raw["native_tables"]
    assert native["native_policy"] == worker.NATIVE_POLICY
    contact = calls["DEFI_CONTACT"][0]
    assert contact["FROTTEMENT"] == "SANS" and contact["ZONE"]["NORMALE"] == "MAIT"
    assert contact["ZONE"]["INTEGRATION"] == "SIMPSON" and contact["ZONE"]["ORDRE_INT"] == 4
    assert contact["NB_ITER_GEOM"] == 2 and contact["ALGO_RESO_GEOM"] == "POINT_FIXE"
    stat = calls["STAT_NON_LINE"][0]
    assert stat["CONVERGENCE"] == {"ARRET": "OUI", "ITER_GLOB_MAXI": 30, "RESI_GLOB_MAXI": 2e-8}
    assert stat["SOLVEUR"] == {"METHODE": "LDLT"} and stat["COMPORTEMENT"]["DEFORMATION"] == "PETIT"
    assert [call["FORMAT"] for call in calls["IMPR_RESU"]] == ["MED", "RESULTAT"]
    assert calls["DEBUT"][0]["IGNORE_ALARM"] == "CONTACT3_16"
    existing = input_path.parent / "order_1_lags_c.table.json"
    old_bytes = existing.read_bytes()
    with pytest.raises(FileExistsError): worker._write_new(existing, {"replacement": True})
    assert existing.read_bytes() == old_bytes
