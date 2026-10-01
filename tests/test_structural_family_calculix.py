"""Source-only native parser and admission checks; no CalculiX is executed."""

from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess

import pytest

from caelab.adapters import structural_family_calculix as adapter
from caelab.outcomes import validate_outcome


_CORNERS = ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))
_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
          (0, 4), (1, 5), (2, 6), (3, 7))


def catalogue():
    # An independent affine 2x2x2 box with a translated origin; not a family
    # solver fixture. Distinct coordinates expose FRD edge/point permutations.
    local = list(_CORNERS) + [tuple((a + b) / 2 for a, b in zip(_CORNERS[i], _CORNERS[j]))
                              for i, j in _EDGES]
    rows = [{"id": i, "coordinates_mm": [1 + r, 4 + s, 8 + t]}
            for i, (r, s, t) in enumerate(local, 1)]
    loads = [{"node_id": i, "value": [2, 3, -4] if i == 1 else [0, 0, 0]} for i in range(1, 21)]
    return {"schema_version": "1", "case": "TEST_ONLY_AFFINE_PARSER", "cells": [1, 1, 1],
            "element_type": "HEXA20", "nodes": rows,
            "elements": [{"id": 1, "node_ids": list(range(1, 21))}],
            "groups": {"ALL_NODES": list(range(1, 21)), "ROOT": [1]},
            "supports": [{"node_id": 1, "components": [1, 2]}], "nodal_loads_n": loads}


def _native_values(mesh, loads):
    xyz = {row["id"]: list(row["coordinates_mm"]) for row in mesh["nodes"]}
    u = {node: [value * .001 for value in point] for node, point in xyz.items()}
    for support in mesh["supports"]:
        for axis in support["components"]:
            u[support["node_id"]][axis - 1] = 0
    rf = {node: list(value) for node, value in loads.items()}
    # Applied load overlaps two restrained components. The third RF component
    # is applied, and a free-node force must never enter the support resultant.
    rf[1] = [12, 23, -4]
    if 2 in rf:
        rf[2] = [-200, 50, 3]
    return xyz, u, rf


def native_files(folder, mesh, loads, *, affine=True):
    """Synthetic official-format text, expressly not a native numerical run."""
    folder.mkdir(parents=True, exist_ok=True)
    xyz, u, rf = _native_values(mesh, loads)
    points = {}
    for element in mesh["elements"]:
        coordinates = [xyz[node] for node in element["node_ids"]]
        for point, local in enumerate(adapter.CCX_GAUSS27, 1):
            # Parser's affine positive control is independent of its geometry
            # helper. Admission tests use the actual shared preflight catalogue.
            position = [1 + local[0], 4 + local[1], 8 + local[2]] if affine else adapter._mesh.hexa20_point_coordinates(coordinates, local)
            points[element["id"], point] = position
    dat = []
    for descriptor, values in (("displacements (vx,vy,vz)", u), ("forces (fx,fy,fz)", rf)):
        dat += [f"\n {descriptor} for set ALL_NODES and time 0.1000000E+01\n"]
        dat += [f"{node:10d}" + "".join(f" {value:13.6E}" for value in row) for node, row in sorted(values.items())]
    dat += ["\n stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set SOLID and time 0.1000000E+01\n"]
    dat += [f"{element:10d} {point:3d}" + "".join(f" {value:13.6E}" for value in (point, point + .1, point + .2, point + .3, point + .4, point + .5))
            for element, point in points]
    dat += ["\n global coordinates (elem, integ.pnt.,x,y,z) for set SOLID and time 0.1000000E+01\n"]
    dat += [f"{element:10d} {point:3d}" + "".join(f" {value:13.6E}" for value in position)
            for (element, point), position in points.items()]
    (folder / "family.dat").write_text("\n".join(dat) + "\n", encoding="ascii")
    frd = ["    1C", "    1UVERSION           Version 2.21", f"    2C{len(xyz):24d}{1:38d}"]
    frd += [f" -1{node:10d}" + "".join(f"{value:12.5E}" for value in row) for node, row in sorted(xyz.items())]
    frd += [" -3", f"    3C{len(mesh['elements']):24d}{1:38d}"]
    # Explicit official FRD order: bottom midsides, vertical midsides, top.
    for element in mesh["elements"]:
        canonical = element["node_ids"]
        native = canonical[:12] + canonical[16:20] + canonical[12:16]
        frd += [f" -1{element['id']:10d}{4:5d}{0:5d}{1:5d}",
                " -2" + "".join(f"{node:10d}" for node in native[:10]),
                " -2" + "".join(f"{node:10d}" for node in native[10:])]
    frd += [" -3"]
    labels = {"DISP": ("D1 1 2 1 0", "D2 1 2 2 0", "D3 1 2 3 0", "ALL 1 2 0 0 1ALL"),
              "STRESS": ("SXX 1 4 1 1", "SYY 1 4 2 2", "SZZ 1 4 3 3", "SXY 1 4 1 2", "SYZ 1 4 2 3", "SZX 1 4 3 1"),
              "FORC": ("F1 1 2 1 0", "F2 1 2 2 0", "F3 1 2 3 0", "ALL 1 2 0 0 1ALL")}
    for counter, (name, rows) in enumerate((("DISP", u), ("STRESS", {node: [1, 2, 3, 4, 5, 6] for node in xyz}), ("FORC", rf)), 1):
        step = list("    1PSTEP" + " " * 60)
        for a, b, value in ((24, 36, counter), (36, 48, 1), (48, 60, 1)):
            step[a:b] = f"{value:12d}"
        header = list(" " * 75)
        header[0:7] = "  100CL"
        header[7:12] = f"{101:5d}"
        header[12:24] = f"{1.0:12.9f}"
        header[24:36] = f"{len(xyz):12d}"
        header[58:63] = f"{1:5d}"
        header[74] = "1"
        frd += ["".join(step), "".join(header), f" -4  {name} {len(labels[name])} 1"]
        frd += [" -5 " + label for label in labels[name]]
        frd += [f" -1{node:10d}" + "".join(f"{value:12.5E}" for value in row) for node, row in sorted(rows.items())]
        frd += [" -3"]
    frd += [" 9999"]
    (folder / "family.frd").write_text("\n".join(frd) + "\n", encoding="ascii")
    return xyz


@pytest.fixture
def native(tmp_path):
    mesh = catalogue()
    loads = {row["node_id"]: list(row["value"]) for row in mesh["nodal_loads_n"]}
    folder = tmp_path / "level_0"
    nodes = native_files(folder, mesh, loads)
    return folder, mesh, loads, nodes


def test_full_native_field_identity_and_signed_overlap_reaction(native):
    folder, mesh, loads, nodes = native
    record, metadata = adapter.parse_fields(folder, mesh, loads, nodes)
    assert record["node_ids"] == list(range(1, 21))
    assert record["reaction_n"] == [10, 20, 0]
    assert record["reaction_moment_n_mm"] == [-140, 70, -30]
    assert record["applied_force_n"] == [2, 3, -4]
    assert record["applied_moment_n_mm"] == [-33, 14, -6]
    assert metadata["raw_internal_forces_n"][1] == [-200, 50, 3]
    assert metadata["reaction_by_node_n"][1] == [0, 0, 0]
    assert metadata["restrained_component_masks"][0] == [True, True, False]
    assert record["field_completeness"] == {"displacement": True, "stress": True, "reaction": True, "native_mesh": True}
    assert record["native_fields_artifact"] == "simulation/level_0/family.frd"
    # All 27 full integration points, no nearest-point or averaged substitution.
    assert len(record["stress_points"]) == 27
    assert record["stress_points"][0]["coordinates_mm"] == pytest.approx([1 - adapter._G, 4 - adapter._G, 8 - adapter._G])
    assert record["stress_points"][13]["coordinates_mm"] == pytest.approx([1, 4, 8])
    assert record["stress_points"][26]["coordinates_mm"] == pytest.approx([1 + adapter._G, 4 + adapter._G, 8 + adapter._G])
    assert record["stress_points"][1]["components_mpa"] == [2, 2.1, 2.2, 2.3, 2.4, 2.5]


@pytest.mark.parametrize("change", ["missing_u", "duplicate_u", "foreign_u", "missing_rf", "nonfinite",
                                  "missing_s", "duplicate_s", "extra_gp", "reduced8", "missing_coord",
                                  "wrong_time", "wrong_set", "wrong_components", "duplicate_table", "extra_column"])
def test_incomplete_or_foreign_native_dat_is_refused(native, change):
    folder, mesh, loads, nodes = native
    path = folder / "family.dat"
    lines = path.read_text().splitlines()
    header = next(i for i, line in enumerate(lines) if "stresses (" in line)
    coord = next(i for i, line in enumerate(lines) if "global coordinates (" in line)
    rf = next(i for i, line in enumerate(lines) if "forces (" in line)
    urow = next(i for i, line in enumerate(lines) if line.split() and line.split()[0] == "1")
    if change == "missing_u": del lines[urow]
    elif change == "duplicate_u": lines.insert(urow, lines[urow])
    elif change == "foreign_u": lines[urow] = lines[urow].replace("         1", "      9999", 1)
    elif change == "missing_rf": del lines[rf + 2]
    elif change == "nonfinite": lines[urow] = "1 NaN 0 0"
    elif change == "missing_s": del lines[header + 2]
    elif change == "duplicate_s": lines.insert(header + 2, lines[header + 2])
    elif change == "extra_gp": lines[header + 2] = "1 28 1 2 3 4 5 6"
    elif change == "reduced8": lines[header + 10:coord] = []
    elif change == "missing_coord": del lines[coord + 2]
    elif change == "wrong_time": lines[header] = lines[header].replace("0.1000000E+01", "0.5000000E+00")
    elif change == "wrong_set": lines[rf] = lines[rf].replace("ALL_NODES", "ROOT")
    elif change == "wrong_components": lines[header] = lines[header].replace("sxz,syz", "syz,sxz")
    elif change == "duplicate_table": lines += lines[rf:header]
    elif change == "extra_column": lines[urow] += " 42"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError):
        adapter.parse_fields(folder, mesh, loads, nodes)


def test_all_native_point_coordinates_corroborate_native_point_order(native):
    folder, mesh, loads, nodes = native
    path = folder / "family.dat"
    lines = path.read_text().splitlines()
    header = next(i for i, line in enumerate(lines) if "global coordinates (" in line)
    rows = [i for i in range(header + 1, len(lines)) if lines[i].strip()]
    left, right = rows[1], rows[3]  # x-fastest versus y-fastest POINT confusion.
    a, b = lines[left].split(), lines[right].split()
    lines[left], lines[right] = " ".join(a[:2] + b[2:]), " ".join(b[:2] + a[2:])
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="COORD"):
        adapter.parse_fields(folder, mesh, loads, nodes)


def test_native_text_precision_is_separate_from_numerical_limits():
    # Two printed tables can have independent rounding, and FRD explicitly
    # casts to float. This allowance is not the domain's equilibrium tolerance.
    assert adapter._printed_close(1.00001, 1.0000049, 6, float32=True, reference_digits=7)
    assert not adapter._printed_close(1.00002, 1.0000049, 6, float32=True, reference_digits=7)
    assert adapter._printed_close(0, 0, 7)
    assert not adapter._printed_close(1e-20, 0, 7)


@pytest.mark.parametrize("change", ["native_coordinates", "serialized_load", "fixed_displacement"])
def test_native_field_inputs_remain_bound_to_catalogue_and_zero_supports(native, change):
    folder, mesh, loads, nodes = native
    if change == "native_coordinates": nodes[1][0] = .1
    elif change == "serialized_load": loads[1][0] = 9
    else:
        path = folder / "family.dat"
        lines = path.read_text().splitlines()
        row = next(i for i, line in enumerate(lines) if line.split() and line.split()[0] == "1")
        lines[row] = "1 1e-10 0 0.008"
        path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError):
        adapter.parse_fields(folder, mesh, loads, nodes)


@pytest.mark.parametrize("change", ["wrong_top_midsides", "unknown_node", "missing_node", "duplicate_node",
                                  "foreign_element", "wrong_type", "wrong_label", "wrong_label_index",
                                  "wrong_time", "missing_force", "force_drift", "coordinate_drift", "missing_end",
                                  "wrong_version", "duplicate_version"])
def test_native_frd_identity_and_full_fields_fail_closed(native, change):
    folder, mesh, loads, nodes = native
    path = folder / "family.frd"
    lines = path.read_text().splitlines()
    meshrow = next(i for i, line in enumerate(lines) if line.startswith(" -1"))
    element = next(i for i, line in enumerate(lines) if line.startswith(" -1") and len(line) == 28)
    forc = next(i for i, line in enumerate(lines) if line.startswith(" -4") and "FORC" in line)
    if change == "wrong_top_midsides":
        lines[element + 2] = " -2" + "".join(f"{i:10d}" for i in range(11, 21))
    elif change == "unknown_node": lines[meshrow] = " -1      9999" + lines[meshrow][13:]
    elif change == "missing_node": del lines[meshrow]
    elif change == "duplicate_node": lines.insert(meshrow, lines[meshrow])
    elif change == "foreign_element": lines[element] = " -1         2" + lines[element][13:]
    elif change == "wrong_type": lines[element] = lines[element][:13] + f"{1:5d}" + lines[element][18:]
    elif change == "wrong_label": lines = [line.replace("SXY 1 4 1 2", "SYZ 1 4 2 3") for line in lines]
    elif change == "wrong_label_index": lines = [line.replace("D1 1 2 1 0", "D1 1 2 2 0") for line in lines]
    elif change == "wrong_time":
        index = next(i for i, line in enumerate(lines) if "100CL" in line)
        lines[index] = lines[index][:12] + f"{.5:12.9f}" + lines[index][24:]
    elif change == "missing_force": del lines[forc + 5]
    elif change == "force_drift": lines[forc + 5] = lines[forc + 5][:13] + f"{999:12.5E}" + lines[forc + 5][25:]
    elif change == "coordinate_drift": lines[meshrow] = lines[meshrow][:13] + f"{.1:12.5E}" + lines[meshrow][25:]
    elif change == "missing_end": lines.pop()
    elif change == "wrong_version": lines[1] = "    1UVERSION           Version 2.22"
    elif change == "duplicate_version": lines.insert(1, "    1UVERSION           Version 2.22")
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError):
        adapter.parse_fields(folder, mesh, loads, nodes)


@pytest.mark.parametrize("change", ["duplicate_support", "duplicate_dof", "missing_zero_load", "duplicate_load", "nonfinite_load"])
def test_reaction_catalogue_cannot_double_count_or_omit_loads(native, change):
    folder, mesh, loads, nodes = native
    if change == "duplicate_support": mesh["supports"].append(deepcopy(mesh["supports"][0]))
    elif change == "duplicate_dof": mesh["supports"][0]["components"].append(1)
    elif change == "missing_zero_load": mesh["nodal_loads_n"].pop()
    elif change == "duplicate_load": mesh["nodal_loads_n"].append(deepcopy(mesh["nodal_loads_n"][0]))
    elif change == "nonfinite_load": mesh["nodal_loads_n"][0]["value"][0] = math.inf
    with pytest.raises(ValueError):
        adapter.parse_fields(folder, mesh, loads, nodes)


def test_native_input_and_serialized_loads_use_trusted_material_and_signed_weights(tmp_path):
    mesh = catalogue()
    mesh["nodal_loads_n"][0]["value"] = [-1.23456789123456, 0, 9.87654321234567]
    adapter._mesh.write_calculix_mesh(mesh, tmp_path / "mesh.inc")
    assert adapter.parse_input_mesh(tmp_path / "mesh.inc", mesh) == {row["id"]: row["coordinates_mm"] for row in mesh["nodes"]}
    declaration = adapter._domain.model_declaration(adapter._domain.specification("ansys_vmd1_regular", "Fx"))
    loads = adapter._deck(mesh, declaration, tmp_path / "family.inp")
    deck = (tmp_path / "family.inp").read_text()
    assert "1,1,-1.234567891235" in deck
    assert "1,3,9.876543212346" in deck
    assert "1,2,0" not in deck
    assert loads[1] == [-1.234567891235, 0, 9.876543212346]
    assert "*EL PRINT,ELSET=SOLID,GLOBAL=YES\nS,COORD" in deck
    assert "*EL FILE,ELSET=" not in deck  # Official noelfiles.f has no ELSET parameter.
    assert "*ELASTIC" in deck and "*STATIC" in deck and "NLGEOM" not in deck


@pytest.mark.parametrize("change", ["reduced", "foreign_group", "coordinate", "input_width", "connectivity", "extra_field"])
def test_actual_native_mesh_cannot_drift_from_checked_catalogue(tmp_path, change):
    mesh = catalogue()
    path = tmp_path / "mesh.inc"
    adapter._mesh.write_calculix_mesh(mesh, path)
    text = path.read_text()
    lines = text.splitlines()
    row = lines.index("*NODE") + 1
    if change == "reduced": text = text.replace("TYPE=C3D20", "TYPE=C3D20R")
    elif change == "foreign_group": text = text.replace("NSET=ROOT", "NSET=FOREIGN")
    elif change == "coordinate":
        lines[row] = "1,0.1,3,7"; text = "\n".join(lines)
    elif change == "input_width":
        lines[row] = "1,0.00000000000000000000,3,7"; text = "\n".join(lines)
    elif change == "connectivity":
        row = next(i for i, line in enumerate(lines) if line.startswith("*ELEMENT")) + 1
        lines[row] = "1, 2, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,"
        text = "\n".join(lines)
    elif change == "extra_field": lines[row] = "1,0,3,7,99"; text = "\n".join(lines)
    path.write_text(text)
    with pytest.raises(ValueError):
        adapter.parse_input_mesh(path, mesh)


def _request():
    settings = adapter._domain.specification("ansys_vmd1_regular", "Fx")
    settings["mesh_cells"] = [[1, 1, 1], [2, 1, 1]]
    return settings


@pytest.mark.parametrize("change", ["unknown", "nan", "bool", "unsupported", "budget", "unrefined"])
def test_settings_refuse_before_any_native_process(tmp_path, monkeypatch, change):
    settings = _request()
    if change == "unknown": settings["tolerance"] = 1
    elif change == "nan": settings["load_factor"] = math.nan
    elif change == "bool": settings["load_factor"] = True
    elif change == "unsupported": settings["load_case"] = "torsion"
    elif change == "budget": settings["mesh_cells"] = [[48, 48, 48], [49, 49, 49]]
    elif change == "unrefined": settings["mesh_cells"][1] = [1, 1, 1]
    monkeypatch.setattr(adapter, "_process", lambda *args, **kw: pytest.fail("No native call permitted"))
    monkeypatch.setattr(adapter, "_runtime_identity", lambda: pytest.fail("No native runtime probe permitted"))
    result = adapter.StructuralFamilyCalculiXAdapter().solve(tmp_path / "simulation", settings)
    assert result["solver_status"] == "NOT_RUN" and result["status"] == "REJECTED"
    validate_outcome(result)


def test_all_requested_meshes_preflight_before_first_native_call(tmp_path, monkeypatch):
    original = adapter._mesh.check_mesh
    def fail_last(mesh, settings):
        if mesh["cells"] == settings["mesh_cells"][-1]:
            raise ValueError("TEST_ONLY_LAST_MESH_REJECTED")
        return original(mesh, settings)
    monkeypatch.setattr(adapter._mesh, "check_mesh", fail_last)
    monkeypatch.setattr(adapter, "_process", lambda *args, **kw: pytest.fail("All-level preflight must precede native calls"))
    result = adapter.StructuralFamilyCalculiXAdapter().solve(tmp_path / "simulation", _request())
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert (tmp_path / "simulation/level_0/mesh.inc").is_file()


def _mock_execution(monkeypatch):
    runtime = {"executable": "TEST_ONLY_NOT_EXECUTED", "sha256": "a" * 64, "required_version": "2.21"}
    monkeypatch.setattr(adapter, "_runtime_identity", lambda: deepcopy(runtime))
    calls = []
    def process(command, folder, label, **kwargs):
        calls.append(label)
        if label == "ccx_version":
            return "This is Version 2.21"
        mesh = json.loads((folder / "mesh.json").read_text())
        loads = {row["node_id"]: row["value"] for row in json.loads((folder / "serialized_loads_n.json").read_text())}
        native_files(folder, mesh, loads, affine=False)
        return "TEST_ONLY_SYNTHETIC_FIELDS\nJob finished"
    monkeypatch.setattr(adapter, "_process", process)
    return process, calls, runtime


def test_complete_synthetic_execution_retains_uniform_records_and_failed_metrics(tmp_path, monkeypatch):
    _mock_execution(monkeypatch)
    result = adapter.StructuralFamilyCalculiXAdapter().solve(tmp_path / "simulation", _request())
    # Synthetic fields deliberately violate the benchmark. Process completion
    # and complete tables must not turn those failed measurements into PASS.
    assert result["status"] == "REJECTED"
    assert result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert result["metrics"]["primary_response"]["valid"] is False
    validate_outcome(result)
    records = json.loads((tmp_path / "simulation/mesh_records.json").read_text())
    assert len(records) == 2 and records[1]["element_count"] == 2
    assert (tmp_path / "simulation/level_1/parsed_fields.json").is_file()
    assert (tmp_path / "simulation/level_0/family.frd").is_file()
    assert (tmp_path / "simulation/level_0/gauss_stress_samples.vtk").is_file()
    assert any(key.endswith("structural-families-v1.json") for key in result["provenance"]["input_sources"])


@pytest.mark.parametrize("change", ["input", "snapshot", "runtime", "version", "nontermination", "native_error"])
def test_inflight_runtime_input_source_drift_or_bad_termination_retains_and_refuses(tmp_path, monkeypatch, change):
    process, calls, runtime = _mock_execution(monkeypatch)
    def changed(command, folder, label, **kwargs):
        text = process(command, folder, label, **kwargs)
        if change == "version" and label == "ccx_version": return "This is Version 2.22"
        if label == "solver":
            if change == "input": (folder / "family.inp").write_text("TEST_ONLY_CHANGED_INPUT")
            elif change == "snapshot":
                snapshot = next((folder.parent / "source_snapshot").rglob("*.py"))
                snapshot.write_text("TEST_ONLY_CHANGED_SOURCE")
            elif change == "runtime": runtime["sha256"] = "b" * 64
            elif change == "nontermination": return "exit0 WITHOUT native termination"
            elif change == "native_error": return "*ERROR native failure\nJob finished"
        return text
    monkeypatch.setattr(adapter, "_process", changed)
    with pytest.raises(RuntimeError):
        adapter.StructuralFamilyCalculiXAdapter().solve(tmp_path / "simulation", _request())
    assert calls.count("solver") <= 1
    assert (tmp_path / "simulation/level_0/family.inp").is_file()
    assert (tmp_path / "simulation/input.json").is_file()
    assert not (tmp_path / "simulation/analysis_raw.json").exists()


@pytest.mark.parametrize("artifact", ["family.dat", "family.frd", "parsed_fields.json", "gauss_stress_samples.vtk", "../mesh_records.json"])
def test_later_mesh_cannot_change_earlier_verified_native_evidence(tmp_path, monkeypatch, artifact):
    process, calls, _ = _mock_execution(monkeypatch)
    def changed(command, folder, label, **kwargs):
        text = process(command, folder, label, **kwargs)
        if label == "solver" and folder.name == "level_1":
            earlier = folder.parent / "level_0" / artifact
            earlier.write_text("TEST_ONLY_MUTATED_PREVIOUS_EVIDENCE")
        return text
    monkeypatch.setattr(adapter, "_process", changed)
    with pytest.raises(RuntimeError, match="input/result changed"):
        adapter.StructuralFamilyCalculiXAdapter().solve(tmp_path / "simulation", _request())
    assert calls.count("solver") == 2
    assert (tmp_path / "simulation/level_1/family.dat").is_file()
    assert not (tmp_path / "simulation/analysis_raw.json").exists()


def test_source_drift_before_capture_never_runs_native(tmp_path, monkeypatch):
    source = tmp_path / "fake_source.py"
    source.write_bytes(b"changed")
    monkeypatch.setattr(adapter, "_SOURCE_BYTES", {source: b"original"})
    monkeypatch.setattr(adapter, "_SOURCE_HASHES", {source: "a" * 64})
    monkeypatch.setattr(adapter, "_ROOT", tmp_path)
    monkeypatch.setattr(adapter, "_process", lambda *args, **kw: pytest.fail("No native work permitted"))
    with pytest.raises(RuntimeError, match="source changed"):
        adapter.StructuralFamilyCalculiXAdapter().solve(tmp_path / "simulation", _request())


def test_process_timeout_kills_group_and_preserves_partial_files(tmp_path, monkeypatch):
    killed = []
    class Process:
        pid, returncode = 91, None
        def wait(self, timeout=None):
            if timeout is not None: raise subprocess.TimeoutExpired(["TEST_ONLY"], timeout)
            self.returncode = -9
        def kill(self): killed.append("process")
    def popen(argv, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["start_new_session"] is True
        kwargs["stdout"].write(b"partial stdout")
        kwargs["stderr"].write(b"partial stderr")
        return Process()
    monkeypatch.setattr(adapter.subprocess, "Popen", popen)
    monkeypatch.setattr(adapter.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    with pytest.raises(RuntimeError, match="timed out"):
        adapter._process(["TEST_ONLY"], tmp_path, "solver")
    assert killed == [(91, adapter.signal.SIGKILL)]
    assert (tmp_path / "solver.stdout.log").read_text() == "partial stdout"
    assert (tmp_path / "solver.stderr.log").read_text() == "partial stderr"
    assert json.loads((tmp_path / "solver.exit.json").read_text())["timed_out"] is True


def test_output_never_overwrites_historical_evidence(tmp_path, monkeypatch):
    output = tmp_path / "simulation"
    output.mkdir()
    original = output / "old_result.json"
    original.write_bytes(b"HISTORICAL_IMMUTABLE")
    monkeypatch.setattr(adapter, "_process", lambda *args, **kw: pytest.fail("Existing evidence must reject first"))
    with pytest.raises(ValueError, match="new or empty"):
        adapter.StructuralFamilyCalculiXAdapter().solve(output, _request())
    assert original.read_bytes() == b"HISTORICAL_IMMUTABLE"
