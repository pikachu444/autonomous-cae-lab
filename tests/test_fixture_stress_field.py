"""Nodal tensor extraction and synthetic artifact plumbing, without a solver.

The small ASCII blocks are public protocol fixtures, not engineering evidence.
The adapter plumbing test uses a real parent STEP, a valid unit C3D10 mesh and
explicit mesh/deck/load I/O doubles; it does not verify fixture physics.
"""

import hashlib
import json
import math
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from caelab.adapters import fixture_calculix as adapter
from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.storage import artifact_manifest


COMPONENTS = ("SXX 1 4 1 1", "SYY 1 4 2 2", "SZZ 1 4 3 3",
              "SXY 1 4 1 2", "SYZ 1 4 2 3", "SZX 1 4 3 1")


def stress_row(node, values):
    return f" -1{node:10d}" + "".join(f"{value:12.5E}" for value in values)


def stress_text(rows):
    return "\n".join([" -4  STRESS      6    1",
                       *(" -5  " + component for component in COMPONENTS),
                       *(stress_row(node, values) for node, values in rows),
                       " -3", " 9999", ""])


@pytest.fixture(scope="module")
def screen():
    return adapter._screen()


def extract(tmp_path, screen, rows, nodes=None):
    frd = tmp_path / "support.frd"
    frd.write_text(stress_text(rows), encoding="ascii")
    if nodes is None:
        nodes = {node: (float(node), -.25, 2.) for node, _ in rows}
    return frd, adapter._extract_stress_field(frd, nodes, screen)


@pytest.mark.parametrize("tensor,expected", [
    ([7, 7, 7, 0, 0, 0], 0),
    ([-7, -7, -7, 0, 0, 0], 0),
    ([0, 0, 0, 0, 0, 0], 0),
    ([12, 0, 0, 0, 0, 0], 12),
    ([0, -12, 0, 0, 0, 0], 12),
    ([0, 0, 12, 0, 0, 0], 12),
    ([0, 0, 0, 5, 0, 0], math.sqrt(3) * 5),
    ([0, 0, 0, 0, -5, 0], math.sqrt(3) * 5),
    ([0, 0, 0, 0, 0, 5], math.sqrt(3) * 5),
    # An orthogonal 45-degree rotation of diag(12,0,0).
    ([6, 6, 0, 6, 0, 0], 12),
])
def test_analytical_tensor_invariants(tmp_path, screen, tensor, expected):
    frd, (field, diagnostic) = extract(tmp_path, screen, [(11, tensor)])
    assert field == {
        "schema_version": "1.0", "field": "stress", "representation": "AVERAGED_NODAL",
        "unit": "MPa", "coordinate_frame": "SOLVER_GLOBAL_CARTESIAN",
        "component_order": ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"],
        "tensor_shear_components": True, "engineering_valid": False,
        "qualification": "UNKNOWN",
        "source_frd": {"path": "support.frd", "sha256": hashlib.sha256(frd.read_bytes()).hexdigest()},
        "nodes": [{"node_id": 11, "position_mm": [11., -.25, 2.],
                   "stress_MPa": tensor, "von_mises_MPa": pytest.approx(expected)}],
        "node_count": 1,
    }
    assert diagnostic == screen.extract_stress_diagnostic(frd, {11: (11., -.25, 2.)})


def test_all_components_positions_and_pinned_diagnostic_are_preserved(tmp_path, screen):
    nodes = {19: (.123456789, -3., 8.), 2: (1., 2., 3.), 8: (-1., -2., 4.)}
    rows = [(19, [1, 2, 3, -4, 5, -6]), (8, [6, -5, 4, -3, 2, -1]),
            (2, [2, 2, 2, 0, 0, 0])]
    frd, (field, diagnostic) = extract(tmp_path, screen, rows, nodes)
    assert [row["node_id"] for row in field["nodes"]] == [2, 8, 19]
    expected = dict(rows)
    for row in field["nodes"]:
        assert row["stress_MPa"] == expected[row["node_id"]]
        assert row["position_mm"] == list(nodes[row["node_id"]])
    assert diagnostic == screen.extract_stress_diagnostic(frd, nodes)
    assert frd.read_text(encoding="ascii") == stress_text(rows)


@pytest.mark.parametrize("mutation", [
    "duplicate", "missing", "foreign", "bad_id", "zero_id", "negative_id",
    "truncated_row", "extra_component", "component_missing", "component_reordered",
    "component_axes", "header_count", "header_kind", "malformed_number", "plain_number",
    "nan", "inf", "end_marker", "terminator", "double_block", "continuation", "non_ascii",
])
def test_malformed_or_incomplete_stress_fails_closed(tmp_path, screen, mutation):
    first = stress_row(1, [10, 0, 0, 0, 0, 0])
    second = stress_row(2, [5, 0, 0, 0, 0, 0])
    text = stress_text([(1, [10, 0, 0, 0, 0, 0]), (2, [5, 0, 0, 0, 0, 0])])
    if mutation == "duplicate":
        text = text.replace(second, first)
    elif mutation == "missing":
        text = text.replace(second + "\n", "")
    elif mutation == "foreign":
        text = text.replace(second, stress_row(3, [5, 0, 0, 0, 0, 0]))
    elif mutation in ("bad_id", "zero_id", "negative_id"):
        label = {"bad_id": "x", "zero_id": "0", "negative_id": "-2"}[mutation]
        text = text.replace(second, " -1" + label.rjust(10) + second[13:])
    elif mutation == "truncated_row":
        text = text.replace(second, second[:-1])
    elif mutation == "extra_component":
        text = text.replace(second, second + " 0.00000E+00")
    elif mutation == "component_missing":
        text = text.replace(" -5  SYZ 1 4 2 3\n", "")
    elif mutation == "component_reordered":
        text = text.replace("SXY 1 4 1 2", "SWAP").replace("SYZ 1 4 2 3", "SXY 1 4 1 2").replace("SWAP", "SYZ 1 4 2 3")
    elif mutation == "component_axes":
        text = text.replace("SZX 1 4 3 1", "SZX 1 4 1 3")
    elif mutation == "header_count":
        text = text.replace("STRESS      6", "STRESS      5")
    elif mutation == "header_kind":
        text = text.replace("STRESS      6    1", "STRESS      6    2")
    elif mutation in ("malformed_number", "plain_number", "nan", "inf"):
        token = {"malformed_number": "BAD", "plain_number": "5.0", "nan": "NaN", "inf": "Inf"}[mutation]
        text = text.replace(second, second[:25] + token.rjust(12) + second[37:])
    elif mutation == "end_marker":
        text = text.replace(" 9999\n", "")
    elif mutation == "terminator":
        text = text.replace(" -3\n", "")
    elif mutation == "double_block":
        text = text.replace(" 9999\n", text)
    elif mutation == "continuation":
        text = text.replace(second, second.replace(" -1", " -2", 1))
    elif mutation == "non_ascii":
        text = text.replace(" 9999", "\u00e9 9999")
    frd = tmp_path / "malformed.frd"
    original = text.encode("utf-8")
    frd.write_bytes(original)
    with pytest.raises(RuntimeError):
        adapter._extract_stress_field(frd, {1: (0., 0., 0.), 2: (1., 2., 3.)}, screen)
    assert frd.read_bytes() == original
    assert not (tmp_path / "stress_field.json").exists()


@pytest.mark.parametrize("nodes", [
    {}, {0: (0., 0., 0.)}, {True: (0., 0., 0.)}, {"1": (0., 0., 0.)},
    {1: (0., 0.)}, {1: (0., 0., float("nan"))}, {1: (0., float("inf"), 0.)},
    {1: (0., "1", 0.)}, {1: (0., False, 0.)},
])
def test_invalid_mesh_positions_or_ids_are_not_published(tmp_path, screen, nodes):
    frd = tmp_path / "support.frd"
    frd.write_text(stress_text([(1, [1, 0, 0, 0, 0, 0])]), encoding="ascii")
    with pytest.raises(RuntimeError, match="mesh"):
        adapter._extract_stress_field(frd, nodes, screen)


@pytest.mark.parametrize("tensor", [[1e308, 0, 0, 0, 0, 0], [0, 0, 0, 1e200, 0, 0]])
def test_finite_tensors_with_nonfinite_computed_invariant_are_rejected(tmp_path, screen, tensor):
    with pytest.raises(RuntimeError, match="Nonfinite computed von Mises"):
        extract(tmp_path, screen, [(1, tensor)])


@pytest.mark.parametrize("drift", [
    "max_averaged_nodal_von_mises_MPa", "p95_averaged_nodal_von_mises_MPa",
    "maximum_node_id", "maximum_node_xyz_mm", "node_count", "nonfinite", "extra", "missing", "not_mapping",
])
def test_pinned_stress_diagnostic_drift_is_rejected(tmp_path, screen, drift):
    frd = tmp_path / "support.frd"
    nodes = {1: (0., 0., 0.), 2: (1., 2., 3.)}
    frd.write_text(stress_text([(1, [10, 0, 0, 0, 0, 0]), (2, [5, 0, 0, 0, 0, 0])]), encoding="ascii")
    diagnostic = screen.extract_stress_diagnostic(frd, nodes)
    if drift == "maximum_node_xyz_mm":
        diagnostic[drift] = (0., 0., 1.)
    elif drift == "nonfinite":
        diagnostic["p95_averaged_nodal_von_mises_MPa"] = float("nan")
    elif drift == "extra":
        diagnostic["unreviewed"] = 1
    elif drift == "missing":
        diagnostic.pop("node_count")
    elif drift == "not_mapping":
        diagnostic = None
    else:
        diagnostic[drift] += 1
    changed = SimpleNamespace(extract_stress_diagnostic=lambda *_: diagnostic)
    with pytest.raises(RuntimeError, match="differs from pinned stress diagnostic"):
        adapter._extract_stress_field(frd, nodes, changed)


def test_frd_byte_drift_during_extraction_is_rejected(tmp_path, screen):
    frd = tmp_path / "support.frd"
    frd.write_text(stress_text([(1, [1, 0, 0, 0, 0, 0])]), encoding="ascii")

    def changed(path, nodes):
        diagnostic = screen.extract_stress_diagnostic(path, nodes)
        path.write_bytes(path.read_bytes() + b"\n")
        return diagnostic

    with pytest.raises(RuntimeError, match="FRD changed"):
        adapter._extract_stress_field(frd, {1: (0., 0., 0.)},
                                     SimpleNamespace(extract_stress_diagnostic=changed))


def test_recorded_native_ascii_format_is_compatible_without_execution(screen):
    fixture = Path(__file__).parent / "fixtures/calculix_221_structural_family"
    # This existing HEX20 fixture checks the ASCII tensor encoding only. It is
    # not a new fixture-support solve or a C3D10 qualification.
    mesh = json.loads((fixture / "mesh.json").read_text())
    nodes = {row["id"]: tuple(row["coordinates_mm"]) for row in mesh["nodes"]}
    field, diagnostic = adapter._extract_stress_field(fixture / "family.frd", nodes, screen)
    assert field["node_count"] == len(nodes) == 80
    assert diagnostic == screen.extract_stress_diagnostic(fixture / "family.frd", nodes)


UNIT_NODES = {1: (0., 0., 0.), 2: (1., 0., 0.), 3: (0., 1., 0.), 4: (0., 0., 1.),
              5: (.5, 0., 0.), 6: (.5, .5, 0.), 7: (0., .5, 0.),
              8: (0., 0., .5), 9: (.5, 0., .5), 10: (0., .5, .5)}
FIXED = (1, 2, 3, 5, 6, 7)
LOADED = (4, 8, 9, 10)


def synthetic_adapter_run(tmp_path, monkeypatch, screen, *, malformed_index=None):
    parent_root = tmp_path / "parent"
    cad = FixtureCadQueryAdapter().regenerate("roller_support", {"support_width_mm": 38}, parent_root / "cad")
    assert cad.generated
    parent = {"experiment_id": "synthetic-parent", "status": "COMPLETED_REVIEW_REQUIRED",
              "decision": "NOT_RELEASED", "cad_revision": "a" * 64,
              "provenance": {"adapter": "fixture.cadquery"},
              "artifacts": artifact_manifest(parent_root, revision="a" * 64)}
    parent_bytes = {path: path.read_bytes() for path in parent_root.rglob("*") if path.is_file()}
    material = json.loads((adapter.UPSTREAM / "examples/printed_material_ASSUMED.json").read_text())
    settings = {"load": {"force_per_support_N": 100., "source": "synthetic I/O fixture: unqualified"},
                "material": material, "mesh": {"max_sizes_mm": [4., 3., 2.]}}

    def deck_double(path, nodes, elements, support, material, force):
        assert nodes == UNIT_NODES and len(elements) == 1 and force == 100.
        path.write_text("*HEADING\nSynthetic artifact I/O only\n*NSET, NSET=BASE_FIXED\n" +
                        ", ".join(map(str, FIXED)) + "\n*NSET, NSET=ROLLER_NODES\n" +
                        ", ".join(map(str, LOADED)) + "\n*MATERIAL, NAME=PRINT_INPUT\n" +
                        "\n".join(screen.elastic_material_lines(material)) +
                        "\n*STEP\n*STATIC\n*BOUNDARY\nBASE_FIXED, 1, 3\n*CLOAD\n" +
                        "".join(f"{node}, 3, -25\n" for node in LOADED) +
                        "*NODE PRINT, NSET=ROLLER_NODES\nU\n*EL FILE\nS\n*END STEP\n")
        return {"fixed_node_count": len(FIXED), "loaded_node_count": len(LOADED),
                "loaded_node_ids": list(LOADED), "per_node_force_N": -25.,
                "mesh_volume_relative_error": 0.}

    # Only these boundary/volume/load fixture doubles bypass physics. The
    # pinned node parser, C3D10 Jacobian, U/stress extraction, reaction checker,
    # STEP preflight, artifact hashes and new field writer execute normally.
    io_screen = SimpleNamespace(**{name: getattr(screen, name) for name in
                                  ("elastic_material_lines", "parse_gmsh_inp", "quadratic_tet_jacobian_quality",
                                   "extract_vertical_displacements", "extract_stress_diagnostic")},
                                write_deck=deck_double)
    monkeypatch.setattr(adapter, "_screen", lambda: io_screen)
    monkeypatch.setattr(adapter, "saddle_nodal_forces", lambda *_args, **_kwargs: {
        "nodal_loads": {node: -25. for node in LOADED}, "loaded_node_ids": list(LOADED),
        "total_applied_force_N": 100.})
    monkeypatch.setattr(adapter.shutil, "which", lambda name: f"synthetic://{name}")
    monkeypatch.setattr(adapter, "_version", lambda _: "synthetic I/O fixture; no native process")
    calls = []

    def process_double(command, *, cwd, **kwargs):
        calls.append(command)
        folder = Path(cwd)
        if command[0] == "gmsh":
            mesh = folder / "gmsh.inp"
            mesh.write_text("*NODE\n" + "".join(f"{node}, {x}, {y}, {z}\n" for node, (x, y, z) in UNIT_NODES.items()) +
                            "*ELEMENT, TYPE=C3D10\n1, 1,2,3,4,5,6,7,8,9,10\n")
        elif command[0] == "ccx":
            job = command[1]
            tensor = stress_text([(node, [node, 0, 0, 0, 0, 0]) for node in UNIT_NODES])
            if job == f"support_{malformed_index}":
                tensor = tensor.replace(stress_row(10, [10, 0, 0, 0, 0, 0]) + "\n", "")
            (folder / f"{job}.frd").write_text(tensor, encoding="ascii")
            (folder / f"{job}.dat").write_text(
                "displacements (vx,vy,vz) for set ROLLER_NODES\n" +
                "".join(f"{node} 0 0 -0.01\n" for node in LOADED) +
                "\nforces (fx,fy,fz) for set BASE_FIXED\n" +
                "".join(f"{node} 0 0 {100 if node == 1 else 0}\n" for node in FIXED) + "\n")
        else:
            pytest.fail(f"Unexpected external execution: {command}")
        return subprocess.CompletedProcess(command, 0, "synthetic I/O fixture", "")

    monkeypatch.setattr(adapter.subprocess, "run", process_double)
    experiment = tmp_path / "synthetic-experiment"
    output = experiment / "simulation"
    try:
        result = adapter.FixtureCalculiXAdapter().solve(parent, parent_root, output, settings)
    finally:
        assert {path: path.read_bytes() for path in parent_root.rglob("*") if path.is_file()} == parent_bytes
    return experiment, output, result, calls


def test_each_mesh_field_is_manifested_and_stays_unqualified(tmp_path, monkeypatch, screen):
    experiment, output, result, calls = synthetic_adapter_run(tmp_path, monkeypatch, screen)
    assert [command[0] for command in calls] == ["gmsh", "ccx"] * 3
    assert result["status"] == "COMPLETED"  # Synthetic plumbing, not a native verdict.
    assert result["metrics"]["peak_stress"]["valid"] is False
    assert {"static_strength", "physical_load_test", "material_qualification", "stress_convergence"} <= set(result["pending_validations"])
    assert result["provenance"]["adapter_version"] == "3"
    manifest = {record["path"]: record for record in artifact_manifest(experiment, revision="b" * 64)}
    for index, study in enumerate(result["mesh_studies"]):
        name = f"support_{index}/stress_field.json"
        assert study["files"]["stress_field"] == name
        assert "nodes" not in study["stress_diagnostic"]
        path = output / name
        field = json.loads(path.read_text())
        assert field["node_count"] == 10
        assert field["qualification"] == "UNKNOWN" and field["engineering_valid"] is False
        assert field["source_frd"] == {"path": f"support_{index}.frd", "sha256": hashlib.sha256(
            (output / study["files"]["field_results"]).read_bytes()).hexdigest()}
        assert manifest[f"simulation/{name}"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    common_json = json.dumps(result)
    assert '"stress_MPa":' not in common_json and '"von_mises_MPa":' not in common_json


def test_incomplete_new_mesh_retains_raw_results_and_prior_mesh_field(tmp_path, monkeypatch, screen):
    with pytest.raises(RuntimeError, match="Incomplete nodal stress field"):
        synthetic_adapter_run(tmp_path, monkeypatch, screen, malformed_index=1)
    output = tmp_path / "synthetic-experiment/simulation"
    assert (output / "support_0/stress_field.json").is_file()
    first = json.loads((output / "support_0/stress_field.json").read_text())
    assert first["source_frd"]["sha256"] == hashlib.sha256((output / "support_0/support_0.frd").read_bytes()).hexdigest()
    assert (output / "support_1/support_1.frd").is_file()
    assert (output / "support_1/support_1.dat").is_file()
    assert not (output / "support_1/stress_field.json").exists()
    assert not (output / "result.json").exists()
