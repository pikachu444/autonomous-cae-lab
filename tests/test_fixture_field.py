"""TEST_ONLY native-looking TET10 sources: parser controls, never a native solve.

The optional saved-run probes require an explicit local path and remain outside
portable CI. They read historical bytes without adding missing displacements.
"""

import hashlib
import json
import os
from pathlib import Path
import struct

import pytest

from caelab.adapters import fixture_field as field
from caelab.adapters.fixture_calculix import FixtureCalculiXAdapter, _screen
from caelab.storage import artifact_manifest, save_json


IDS = (7, 11, 21, 43, 54, 67, 81, 102, 145, 209)
XYZ = ((0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2), (1, 0, 0),
       (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1))
NODES = dict(zip(IDS, XYZ))
FACES = ((2, "BOTTOM", (7, 11, 21, 54, 67, 81)),
         (3, "SADDLE_SIDE", (7, 43, 11, 102, 145, 54)),
         (5, "WALL_A", (11, 43, 21, 145, 209, 67)),
         (17, "WALL_B", (21, 43, 7, 209, 102, 81)))
FORCES = {43: -.123456789123456, 145: -1.876543210876544}
U = {node: [0.0, 0.0, 0.0] for node in IDS}
U.update({43: [.00123456789, -.00023456789, -.010987654],
          102: [.00078312345, .004312345, -.12345678],
          145: [.00045678123, .00012345678, -.0087654321],
          209: [-.00078312345, -.004312345, -.003141592]})
FIXED = [7, 11, 21, 54, 67, 81]
REVISION = "a" * 64


def _single(value):
    return struct.unpack("f", struct.pack("f", value))[0]


def _row(node, vector):
    return f" -1{node:10d}" + "".join(f"{_single(value):12.5E}" for value in vector)


def _native_field(name, counter, vectors):
    step = "    1PSTEP" + " " * 14 + f"{counter:12d}{1:12d}{1:12d}" + " " * 10
    header = "  100CL" + f"{101:5d}{1.:12.9f}{len(IDS):12d}{0:22d}{1:5d}" + " " * 11 + "1"
    labels = {"DISP": ["D1 1 2 1 0", "D2 1 2 2 0", "D3 1 2 3 0", "ALL 1 2 0 0 1ALL"],
              "STRESS": ["SXX 1 4 1 1", "SYY 1 4 2 2", "SZZ 1 4 3 3",
                         "SXY 1 4 1 2", "SYZ 1 4 2 3", "SZX 1 4 3 1"],
              "ERROR": ["STR(%) 1 1 0 0"]}[name]
    return [step, header, f" -4  {name} {len(labels)} 1",
            *(" -5  " + label for label in labels),
            *(_row(node, vectors[node]) for node in reversed(IDS)), " -3"]


def _fixture_sources(tmp_path, *, transform=True):
    """One tetrahedron with actual gapped element/face IDs and four CPS6 faces."""
    folder = tmp_path / "support_0"
    folder.mkdir()
    geometry = ["*HEADING", "TEST_ONLY explicit TET10 parser fixture; no native execution", "*NODE",
                *(f"{node}, " + ", ".join(f"{value:.10g}" for value in NODES[node]) for node in reversed(IDS))]
    volume = ["*ELEMENT, TYPE=C3D10, ELSET=SUPPORT", "31, " + ", ".join(map(str, IDS))]
    mesh = geometry + [line for element, group, ids in FACES for line in
                       (f"*ELEMENT, TYPE=CPS6, ELSET={group}", f"{element}, " + ", ".join(map(str, ids)))] + volume
    (folder / "gmsh.inp").write_text("\n".join(mesh) + "\n", encoding="ascii")
    deck = geometry + volume + ["*NSET, NSET=BASE_FIXED", ", ".join(map(str, FIXED)),
        "*NSET, NSET=ROLLER_NODES", "43, 145", "*MATERIAL, NAME=PRINT_INPUT", "*ELASTIC", "1000, 0.3",
        "*SOLID SECTION, ELSET=SUPPORT, MATERIAL=PRINT_INPUT", "*STEP", "*STATIC", "*BOUNDARY",
        "BASE_FIXED, 1, 3", "*CLOAD", *(f"{node}, 3, {force:.12g}" for node, force in FORCES.items()),
        "*NODE PRINT, NSET=ROLLER_NODES", "U", "*NODE FILE, NSET=ROLLER_NODES", "U",
        "*EL FILE", "S", "*NODE PRINT, NSET=BASE_FIXED", "RF", "*END STEP"]
    (folder / "support_0.inp").write_text("\n".join(deck) + "\n", encoding="ascii")
    save_json(folder / "saddle_load.json", {"nodal_loads": FORCES, "loaded_node_ids": [43, 145],
        "loaded_node_count": 2, "total_applied_force_N": 2., "surface_group": "SADDLE_SIDE", "face_count": 1})
    frd = ["    1C", "    1UTEST_ONLY explicit fixture; no native solve", "    1UVERSION Version 2.21",
           f"    2C {len(IDS)} 1", *(_row(node, NODES[node]) for node in reversed(IDS)), " -3", "    3C 1 1",
           f" -1{31:10d}{6:5d}{0:5d}{1:5d}", " -2" + "".join(f"{node:10d}" for node in IDS), " -3"]
    frd += _native_field("DISP", 1, U)
    frd += _native_field("STRESS", 2, {node: [1., 2., 3., .1, .2, .3] for node in IDS})
    frd += _native_field("ERROR", 3, {node: [.7] for node in IDS}) + ["9999"]
    (folder / "support_0.frd").write_text("\n".join(frd) + "\n", encoding="ascii")
    dat = [" S T E P 1", " INCREMENT 1", "",
           " displacements (vx,vy,vz) for set ROLLER_NODES and time 0.1000000E+01", "",
           *(f" {node} " + " ".join(f"{value:.6E}" for value in U[node]) for node in FORCES), "",
           " forces (fx,fy,fz) for set BASE_FIXED and time 0.1000000E+01", "",
           *(f" {node} 0.000000E+00 0.000000E+00 3.333333E-01" for node in FIXED), ""]
    (folder / "support_0.dat").write_text("\n".join(dat) + "\n", encoding="ascii")
    if transform:
        field.request_complete_displacement(folder / "support_0.inp", NODES)
    return folder


def _extract(folder, expected=None, **overrides):
    values = {"mesh_index": 0, "mesh_size_max_mm": 2, "parent_experiment_id": "TEST_ONLY-parent",
              "cad_revision": REVISION, "expected_inputs": expected or field.capture_fixture_field_inputs(folder, 0)}
    values.update(overrides)
    return field.extract_fixture_field(folder, **values)


def _edit(path, transform):
    path.write_text(transform(path.read_text(encoding="ascii")), encoding="ascii")


def _field_edit(text, name, transform):
    marker = f" -4  {name}"
    before, rest = text.split(marker, 1)
    block, after = rest.split("\n -3", 1)
    lines = block.splitlines()
    return before + marker + "\n".join(transform(lines)) + "\n -3" + after


def test_complete_observed_field_binds_actual_ids_vectors_sources_and_manifest(tmp_path):
    folder = _fixture_sources(tmp_path)
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    result = _extract(folder)
    assert (result["schema_version"], result["kind"], result["backend"], result["adapter_version"]) == (
        "1.0", "fixture_calculix_nodal_displacement", "fixture.calculix", "5")
    assert result["static"] == {"step": 1, "increment": 1, "load_parameter": 1.0}
    assert result["coverage"] == "ALL_MESH_NODES" and result["qualification"] == "UNKNOWN"
    assert result["engineering_valid"] is False
    assert (result["parent_experiment_id"], result["cad_revision"], result["mesh_index"], result["mesh_size_max_mm"]) == (
        "TEST_ONLY-parent", REVISION, 0, 2)
    assert (result["coordinate_frame"], result["position_unit"], result["displacement_unit"], result["force_unit"]) == (
        "SOLVER_GLOBAL_CARTESIAN", "mm", "mm", "N")
    assert (result["node_count"], result["element_count"], result["boundary_face_count"]) == (10, 1, 4)
    assert [row["node_id"] for row in result["nodes"]] == list(IDS)
    for row in result["nodes"]:
        node = row["node_id"]
        assert row["position_mm"] == list(NODES[node])
        assert row["displacement_tokens"] == [f"{_single(value):.5E}" for value in U[node]]
        assert row["displacement_mm"] == [float(token) for token in row["displacement_tokens"]]
    assert result["elements"] == [{"element_id": 31, "type": "C3D10", "node_ids": list(IDS)}]
    assert result["boundary_faces"] == [{"element_id": element, "group": group, "type": "CPS6", "node_ids": list(ids)}
                                        for element, group, ids in FACES]
    assert result["fixed_node_ids"] == FIXED and result["fixed_dofs"] == [1, 2, 3]
    assert result["loads"] == [{"node_id": node, "force_N": [0., 0., float(f"{force:.12g}")],
                                "dof": 3, "force_token": f"{force:.12g}"} for node, force in FORCES.items()]
    save_json(folder / "fea_field.json", result)
    manifest = {row["path"]: row for row in artifact_manifest(tmp_path, revision=REVISION)}
    assert "support_0/fea_field.json" in manifest
    for name, source in result["sources"].items():
        assert source == {"path": source["path"], "bytes": len(before[source["path"]]),
                          "sha256": hashlib.sha256(before[source["path"]]).hexdigest()}
        assert manifest[f"support_0/{source['path']}"]["sha256"] == source["sha256"]
    assert {path.name: path.read_bytes() for path in folder.iterdir() if path.name != "fea_field.json"} == before


def test_request_is_output_only_and_loaded_dat_remains_the_numeric_response(tmp_path):
    folder = _fixture_sources(tmp_path, transform=False)
    deck = folder / "support_0.inp"
    original = deck.read_bytes()
    dat_original = (folder / "support_0.dat").read_bytes()
    field.request_complete_displacement(deck, NODES)
    output_set = "*NSET, NSET=FIELD_ALL_NODES\n" + ", ".join(map(str, IDS)) + "\n"
    restored = deck.read_text().replace(output_set, "").replace(
        "*NODE FILE, NSET=FIELD_ALL_NODES\nU\n", "*NODE FILE, NSET=ROLLER_NODES\nU\n")
    assert restored.encode("ascii") == original
    assert (folder / "support_0.dat").read_bytes() == dat_original
    assert deck.read_text().index(output_set) < deck.read_text().index("*MATERIAL")
    screen = _screen()  # Actual pinned parser, no native calls.
    loaded = screen.extract_vertical_displacements(folder / "support_0.dat", set(FORCES))
    assert loaded == {"min_vertical_displacement_mm": -.01098765, "max_abs_vertical_displacement_mm": .01098765}
    complete = _extract(folder)
    assert min(row["displacement_mm"][2] for row in complete["nodes"]) == -.123457
    assert FixtureCalculiXAdapter.default_metrics == ["max_displacement", "peak_stress", "displacement_mesh_change_ratio",
        "applied_force_per_support", "reaction_force", "reaction_balance_ratio", "mesh_size_max_mm", "loaded_saddle_min_global_uz"]


@pytest.mark.parametrize("fault", ["missing_marker", "duplicate_marker", "renamed_marker", "material", "repeat", "foreign_mesh", "nonfinite_mesh", "duplicate_node"])
def test_request_rejects_ambiguous_or_changed_decks_without_writing(tmp_path, fault):
    folder = _fixture_sources(tmp_path, transform=False)
    deck = folder / "support_0.inp"
    nodes = dict(NODES)
    if fault == "missing_marker":
        _edit(deck, lambda text: text.replace("*NODE FILE, NSET=ROLLER_NODES\nU\n", ""))
    elif fault == "duplicate_marker":
        _edit(deck, lambda text: text + "*NODE FILE, NSET=ROLLER_NODES\nU\n")
    elif fault == "renamed_marker":
        _edit(deck, lambda text: text.replace("*NODE FILE, NSET=ROLLER_NODES", "*NODE FILE, NSET=OTHER"))
    elif fault == "material":
        _edit(deck, lambda text: text.replace("NAME=PRINT_INPUT", "NAME=CHANGED"))
    elif fault == "repeat":
        field.request_complete_displacement(deck, nodes)
    elif fault == "foreign_mesh":
        nodes[999] = (0., 0., 0.)
    elif fault == "nonfinite_mesh":
        nodes[43] = (0., 0., float("nan"))
    elif fault == "duplicate_node":
        _edit(deck, lambda text: text.replace("*NODE\n", "*NODE\n7, 0, 0, 0\n"))
    before = deck.read_bytes()
    with pytest.raises(ValueError):
        field.request_complete_displacement(deck, nodes)
    assert deck.read_bytes() == before


@pytest.mark.parametrize("fault", ["missing_u", "duplicate_u", "foreign_u", "missing_component", "extra_component", "nonfinite", "bad_token", "labels", "derived_label", "duplicate_field", "missing_field", "foreign_field", "step", "increment", "parameter", "count", "version", "binary", "missing_end", "trailing", "geometry_xyz", "geometry_id", "element_order", "element_type", "missing_element"])
def test_native_reader_rejects_partial_changed_or_malformed_frd(tmp_path, fault):
    folder = _fixture_sources(tmp_path)
    path = folder / "support_0.frd"
    text = path.read_text()
    rows = lambda lines: [i for i, line in enumerate(lines) if line.startswith(" -1")]
    def mutate(lines):
        index = rows(lines)[0]
        if fault == "missing_u":
            del lines[index]
        elif fault == "duplicate_u":
            lines.insert(index, lines[index])
        elif fault == "foreign_u":
            lines[index] = " -1" + f"{999:10d}" + lines[index][13:]
        elif fault == "missing_component":
            lines[index] = lines[index][:-12]
        elif fault == "extra_component":
            lines[index] += " 0.00000E+00"
        elif fault in ("nonfinite", "bad_token"):
            lines[index] = lines[index][:13] + ("         NaN" if fault == "nonfinite" else " 1.00000D-03") + lines[index][25:]
        elif fault == "labels":
            lines[1], lines[2] = lines[2], lines[1]
        elif fault == "derived_label":
            lines[4] = " -5 ALL 1 2 0 0"
        return lines
    if fault in {"missing_u", "duplicate_u", "foreign_u", "missing_component", "extra_component", "nonfinite", "bad_token", "labels", "derived_label"}:
        text = _field_edit(text, "DISP", mutate)
    elif fault == "duplicate_field":
        text = text.replace(" -4  STRESS", " -4  DISP")
    elif fault == "missing_field":
        text = text[:text.index("    1PSTEP", text.index(" -4  STRESS"))] + "9999\n"
    elif fault == "foreign_field":
        text = text.replace(" -4  DISP", " -4  FORC")
    elif fault in {"step", "increment"}:
        line = next(line for line in text.splitlines() if "1PSTEP" in line)
        start = 48 if fault == "step" else 36
        text = text.replace(line, line[:start] + f"{2:12d}" + line[start + 12:], 1)
    elif fault in {"parameter", "count", "binary"}:
        line = next(line for line in text.splitlines() if "100CL" in line)
        changed = line[:12] + f"{2.:12.9f}" + line[24:] if fault == "parameter" else (
            line[:24] + f"{9:12d}" + line[36:] if fault == "count" else line[:-1] + "3")
        text = text.replace(line, changed, 1)
    elif fault == "version":
        text = text.replace("Version 2.21", "Version 2.22")
    elif fault == "missing_end":
        text = text.replace("9999\n", "")
    elif fault == "trailing":
        text += "9999\n"
    elif fault == "geometry_xyz":
        text = text.replace(_row(209, NODES[209]), _row(209, [0., 1.02, 1.]), 1)
    elif fault == "geometry_id":
        text = text.replace(_row(209, NODES[209]), _row(999, NODES[209]), 1)
    elif fault == "element_order":
        text = text.replace(" -2" + "".join(f"{node:10d}" for node in IDS), " -2" + "".join(f"{node:10d}" for node in (*IDS[:4], IDS[5], IDS[4], *IDS[6:])))
    elif fault == "element_type":
        text = text.replace(f" -1{31:10d}{6:5d}{0:5d}{1:5d}", f" -1{31:10d}{4:5d}{0:5d}{1:5d}")
    elif fault == "missing_element":
        text = text.replace("    3C 1 1\n", "    3C 2 1\n")
    path.write_text(text, encoding="ascii")
    with pytest.raises(ValueError):
        _extract(folder)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "foreign", "nonfinite", "vector_mismatch", "unprinted_precision", "step", "increment", "parameter", "set", "extra_u_table", "rf_missing"])
def test_every_loaded_vector_and_dat_identity_is_corroborated(tmp_path, fault):
    folder = _fixture_sources(tmp_path)
    path = folder / "support_0.dat"
    text = path.read_text()
    row = next(line for line in text.splitlines() if line.startswith(" 43 "))
    if fault == "missing":
        text = text.replace(row + "\n", "")
    elif fault == "duplicate":
        text = text.replace(row, row + "\n" + row)
    elif fault == "foreign":
        text = text.replace(row, row.replace(" 43 ", " 999 ", 1))
    elif fault == "nonfinite":
        text = text.replace(row, " 43 NaN 0 -0.01")
    elif fault == "vector_mismatch":
        # UZ/statistic unchanged: a wrong nonextreme X component must still fail.
        text = text.replace(row, row.replace("1.234568E-03", "1.734568E-03"))
    elif fault == "unprinted_precision":
        text = text.replace(row, row.replace("1.234568E-03", "0.001234568"))
    elif fault in {"step", "increment"}:
        text = text.replace("S T E P 1" if fault == "step" else "INCREMENT 1", "S T E P 2" if fault == "step" else "INCREMENT 2")
    elif fault == "parameter":
        text = text.replace("0.1000000E+01", "0.2000000E+01")
    elif fault == "set":
        text = text.replace("ROLLER_NODES", "FOREIGN")
    elif fault == "extra_u_table":
        text += " displacements (vx,vy,vz) for set FIELD_ALL_NODES and time 0.1000000E+01\n" + row + "\n"
    elif fault == "rf_missing":
        text = text.replace(" 7 0.000000E+00 0.000000E+00 3.333333E-01\n", "")
    path.write_text(text, encoding="ascii")
    with pytest.raises(ValueError):
        _extract(folder)


@pytest.mark.parametrize("fault", ["missing_face", "duplicate_face", "interior_face", "nonmanifold", "midside_order", "foreign_face_node", "duplicate_volume", "foreign_volume_node", "duplicate_node", "unused_node", "nonfinite_node"])
def test_actual_mesh_boundary_and_node_element_topology_are_required(tmp_path, fault):
    folder = _fixture_sources(tmp_path)
    path = folder / "gmsh.inp"
    text = path.read_text()
    face = "2, 7, 11, 21, 54, 67, 81"
    volume = "31, " + ", ".join(map(str, IDS))
    if fault == "missing_face":
        text = text.replace(face + "\n", "")
    elif fault == "duplicate_face":
        text = text.replace(face, face + "\n" + face.replace("2, ", "19, ", 1))
    elif fault == "interior_face":
        # A shared tetrahedron face cannot remain an exterior CPS6 face.
        text += "*ELEMENT, TYPE=C3D10, ELSET=SUPPORT\n" + volume.replace("31,", "32,", 1) + "\n"
    elif fault == "nonmanifold":
        text += "*ELEMENT, TYPE=C3D10, ELSET=SUPPORT\n" + volume.replace("31,", "32,", 1) + "\n" + volume.replace("31,", "33,", 1) + "\n"
    elif fault == "midside_order":
        text = text.replace(face, "2, 7, 11, 21, 67, 54, 81")
    elif fault == "foreign_face_node":
        text = text.replace(face, "2, 7, 11, 21, 54, 67, 999")
    elif fault == "duplicate_volume":
        text = text.replace(volume, volume + "\n" + volume)
    elif fault == "foreign_volume_node":
        text = text.replace(volume, volume.replace("209", "999"))
    elif fault == "duplicate_node":
        text = text.replace("*NODE\n", "*NODE\n7, 0, 0, 0\n")
    elif fault == "unused_node":
        text = text.replace("*NODE\n", "*NODE\n999, 0, 0, 3\n")
    elif fault == "nonfinite_node":
        text = text.replace("209, 0, 1, 1", "209, 0, NaN, 1")
    path.write_text(text, encoding="ascii")
    with pytest.raises(ValueError):
        _extract(folder)


@pytest.mark.parametrize("fault", ["xyz", "connectivity", "fixed_dof", "fixed_set", "foreign_set", "partial_output_set", "force_axis", "force_value", "load_membership", "duplicate_cload", "all_node_dat", "extra_step"])
def test_serialized_deck_is_the_authoritative_model_and_boundary(tmp_path, fault):
    folder = _fixture_sources(tmp_path)
    path = folder / "support_0.inp"
    text = path.read_text()
    if fault == "xyz":
        text = text.replace("209, 0, 1, 1", "209, 0, 1.001, 1")
    elif fault == "connectivity":
        text = text.replace("31, " + ", ".join(map(str, IDS)), "31, " + ", ".join(map(str, (*IDS[:4], IDS[5], IDS[4], *IDS[6:]))))
    elif fault == "fixed_dof":
        text = text.replace("BASE_FIXED, 1, 3", "BASE_FIXED, 3, 3")
    elif fault == "fixed_set":
        text = text.replace("7, 11, 21, 54, 67, 81", "7, 11, 21, 54, 67")
    elif fault == "foreign_set":
        text = text.replace("*NSET, NSET=BASE_FIXED\n", "*NSET, NSET=BASE_FIXED\n999, ")
    elif fault == "partial_output_set":
        text = text.replace("*NSET, NSET=FIELD_ALL_NODES\n" + ", ".join(map(str, IDS)), "*NSET, NSET=FIELD_ALL_NODES\n7, 11")
    elif fault in {"force_axis", "force_value"}:
        text = text.replace(f"43, 3, {FORCES[43]:.12g}", f"43, 2, {FORCES[43]:.12g}" if fault == "force_axis" else "43, 3, -0.5")
    elif fault == "load_membership":
        text = text.replace("*NSET, NSET=ROLLER_NODES\n43, 145", "*NSET, NSET=ROLLER_NODES\n43")
    elif fault == "duplicate_cload":
        text = text.replace("*CLOAD\n", f"*CLOAD\n43, 3, {FORCES[43]:.12g}\n")
    elif fault == "all_node_dat":
        text = text.replace("*NODE PRINT, NSET=ROLLER_NODES", "*NODE PRINT, NSET=FIELD_ALL_NODES")
    elif fault == "extra_step":
        text += "*STEP\n*STATIC\n*END STEP\n"
    path.write_text(text, encoding="ascii")
    with pytest.raises(ValueError):
        _extract(folder)


@pytest.mark.parametrize("fault", ["force", "ids", "count", "surface", "faces", "total", "duplicate_key"])
def test_saddle_source_forces_ids_and_actual_group_are_bound(tmp_path, fault):
    folder = _fixture_sources(tmp_path)
    path = folder / "saddle_load.json"
    data = json.loads(path.read_text())
    if fault == "force":
        data["nodal_loads"]["43"] = -.5
    elif fault == "ids":
        data["loaded_node_ids"] = [43, 209]
    elif fault == "count":
        data["loaded_node_count"] = True
    elif fault == "surface":
        data["surface_group"] = "WALL_B"
    elif fault == "faces":
        data["face_count"] = 2
    elif fault == "total":
        data["total_applied_force_N"] = 3.
    save_json(path, data)
    if fault == "duplicate_key":
        _edit(path, lambda text: text.replace('"loaded_node_count": 2', '"loaded_node_count": 2, "loaded_node_count": 2'))
    with pytest.raises(ValueError):
        _extract(folder)


@pytest.mark.parametrize("source", ["mesh", "deck", "saddle"])
def test_pre_native_inputs_cannot_change_after_binding(tmp_path, source):
    folder = _fixture_sources(tmp_path)
    expected = field.capture_fixture_field_inputs(folder, 0)
    path = folder / expected[source]["path"]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="changed since the pre-execution binding"):
        _extract(folder, expected)


@pytest.mark.parametrize("source", ["gmsh.inp", "support_0.inp", "saddle_load.json", "support_0.frd", "support_0.dat"])
def test_every_source_must_remain_unchanged_during_extraction(tmp_path, monkeypatch, source):
    folder = _fixture_sources(tmp_path)
    original = field._dat
    def changed_after_parse(*args):
        original(*args)
        path = folder / source
        path.write_bytes(path.read_bytes() + b"\n")
    monkeypatch.setattr(field, "_dat", changed_after_parse)
    with pytest.raises(ValueError, match="changed during field extraction"):
        _extract(folder)


@pytest.mark.parametrize("fault", ["missing", "symlink_file", "symlink_parent", "traversal", "wrong_level", "nonascii", "oversized"])
def test_sources_have_bounded_normalized_local_associations(tmp_path, monkeypatch, fault):
    folder = _fixture_sources(tmp_path)
    if fault == "missing":
        (folder / "support_0.frd").unlink()
    elif fault == "symlink_file":
        original = folder / "support_0.frd"
        target = tmp_path / "foreign.frd"
        original.rename(target)
        original.symlink_to(target)
    elif fault == "symlink_parent":
        parent = tmp_path / "linked"
        parent.symlink_to(tmp_path, target_is_directory=True)
        folder = parent / "support_0"
    elif fault == "traversal":
        folder = str(folder) + "/../support_0"
    elif fault == "wrong_level":
        with pytest.raises(ValueError, match="mesh index"):
            _extract(folder, mesh_index=1)
        return
    elif fault == "nonascii":
        path = folder / "support_0.frd"
        path.write_bytes(path.read_bytes() + b"\xff")
    elif fault == "oversized":
        monkeypatch.setattr(field, "MAX_SOURCE_BYTES", 100)
    with pytest.raises(ValueError):
        _extract(folder)


def test_print_precision_is_tight_and_not_an_engineering_tolerance():
    assert field._printed_close("1.23457E-03", .00123456789, reference_token="1.234568E-03")
    assert not field._printed_close("1.23467E-03", .00123456789, reference_token="1.234568E-03")
    assert not field._printed_close("0.00000E+00", .01)
    assert not field._printed_close("0.00000E+00", 1e-9, reference_token="1.000000E-09")


@pytest.mark.parametrize("identity", [{"parent_experiment_id": "../foreign"}, {"cad_revision": "a" * 63},
    {"mesh_size_max_mm": float("nan")}, {"mesh_size_max_mm": True}, {"mesh_index": True}, {"expected_inputs": {}}])
def test_field_requires_canonical_experiment_revision_mesh_and_input_identity(tmp_path, identity):
    folder = _fixture_sources(tmp_path)
    with pytest.raises(ValueError):
        _extract(folder, **identity)


def test_trusted_version6_keeps_complete_observation_and_parent_binding(tmp_path):
    folder = _fixture_sources(tmp_path)
    original = {path.name: path.read_bytes() for path in folder.iterdir()}
    previous = _extract(folder)
    current = _extract(folder, adapter_version="6")
    assert previous["adapter_version"] == "5" and current["adapter_version"] == "6"
    assert current["parent_experiment_id"] == "TEST_ONLY-parent" and current["cad_revision"] == REVISION
    assert current["coverage"] == "ALL_MESH_NODES" and current["engineering_valid"] is False
    previous["adapter_version"] = "6"
    assert current == previous
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == original


@pytest.mark.parametrize("version", [4, 5, 6, 7, True, None, "4", "7", "6.0", "", ["6"]])
def test_untrusted_producer_version_is_refused_before_source_read(tmp_path, monkeypatch, version):
    folder = _fixture_sources(tmp_path)
    expected = field.capture_fixture_field_inputs(folder, 0)
    def prohibited(_path):
        pytest.fail("Invalid producer version reached native source read")
    monkeypatch.setattr(field, "_read_bytes", prohibited)
    with pytest.raises(ValueError, match="producer adapter version"):
        _extract(folder, expected, adapter_version=version)


@pytest.mark.parametrize("index,counts,probe", [(0, (7715, 123), 314), (1, (13259, 228), 183), (2, (31376, 438), 546)])
def test_optional_legacy_saved_bytes_refuse_full_u_and_retain_probes(index, counts, probe):
    root = os.environ.get("CAELAB_TEST_LEGACY_FIXTURE_SIMULATION")
    if not root:
        pytest.skip("Optional read-only local human07 probe; not portable/native CI")
    folder = Path(root) / f"support_{index}"
    paths = field._paths(folder, index)
    before = {key: field._read_bytes(path) for key, path in paths.items()}
    mesh_nodes, elements, boundary = field._geometry(field._sections(field._ascii(before["mesh"])), mesh=True)
    assert len(mesh_nodes) == counts[0]
    assert len(field._exterior(elements, boundary)) > counts[1]
    deck_nodes, deck_elements, _ = field._geometry(field._sections(field._ascii(before["deck"])), mesh=False)
    assert elements == deck_elements
    text = field._ascii(before["frd"])
    start = text.index(" -4  DISP")
    block = text[start:].split("\n -3", 1)[0]
    records = {node: (vector, tokens) for node, vector, tokens in
               (field._frd_record(line, 3) for line in block.splitlines() if line.startswith(" -1"))}
    assert len(records) == counts[1] and probe in records
    assert set(records) != set(deck_nodes)
    dat = field._ascii(before["dat"])
    row = next(line.split() for line in dat.splitlines() if line.split() and line.split()[0] == str(probe))
    for token, native in zip(records[probe][1], row[1:]):
        assert field._printed_close(token, float(native), reference_token=native)
    sections = field._sections(field._ascii(before["deck"]))
    native_loads = []
    fixed = []
    for keyword, options, lines in sections:
        if keyword == "*CLOAD":
            for line in lines:
                node, dof, token = field._csv(line, 3)
                assert dof == "3"
                native_loads.append({"node_id": int(node), "dof": 3, "force_N": [0., 0., float(token)], "force_token": token})
        elif keyword == "*NSET" and options == {"NSET": "BASE_FIXED"}:
            fixed = [int(token.strip()) for line in lines for token in line.split(",")]
    # Corroborate every saved loaded vector and saddle force, never missing U.
    field._dat(dat, native_loads, fixed, records)
    field._saddle(field._ascii(before["saddle"]), native_loads, boundary)
    with pytest.raises(ValueError, match="coverage"):
        field._frd(text, deck_nodes, elements)
    assert {key: field._read_bytes(path) for key, path in paths.items()} == before
