"""Analytical, topology and serialization tests; no native solver is invoked."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from caelab.adapters import structural_family_mesh as mesh_api
from plugins.structural_families.reference import specification


CASES = ("ansys_vmd1_regular", "lame_cylinder_plane_strain", "scordelis_lo_solid")


@pytest.fixture(scope="module")
def family_meshes():
    return {(case, tuple(cells)): mesh_api.build_mesh(settings, cells)
            for case in CASES for settings in [specification(case)]
            for cells in settings["mesh_cells"]}


def _coordinates(mesh):
    return {row["id"]: row["coordinates_mm"] for row in mesh["nodes"]}


def _norm(vector):
    return math.hypot(*vector)


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


@pytest.mark.parametrize("index,point", enumerate(mesh_api.HEXA20_NATURAL_NODES))
def test_hexa20_nodal_kronecker_property(index, point):
    weights, gradients = mesh_api.hexa20_shape(point)
    assert weights == tuple(float(i == index) for i in range(20))
    assert len(gradients) == 20
    assert all(len(row) == 3 for row in gradients)


@pytest.mark.parametrize("point", [(0, 0, 0), (0.19, -0.42, 0.61), (-0.7, 0.8, -0.2), (1, 1, 1)])
def test_hexa20_partition_and_analytical_derivatives(point):
    weights, gradients = mesh_api.hexa20_shape(point)
    assert math.fsum(weights) == pytest.approx(1, abs=3e-15)
    for axis in range(3):
        assert math.fsum(row[axis] for row in gradients) == pytest.approx(0, abs=3e-15)
        plus, minus = list(point), list(point)
        plus[axis] += 1e-6
        minus[axis] -= 1e-6
        numerical = [(a - b) / 2e-6 for a, b in zip(mesh_api.hexa20_shape(plus)[0], mesh_api.hexa20_shape(minus)[0])]
        assert [row[axis] for row in gradients] == pytest.approx(numerical, abs=3e-10)


def test_hexa20_complete_serendipity_polynomial_space():
    # Independent monomial basis: exponents0/1 in allaxes plus one squaredaxis.
    powers = [(a, b, c) for a in range(3) for b in range(3) for c in range(3)
              if sum(p > 1 for p in (a, b, c)) <= 1 and not (a == b == c == 2)]
    assert len(powers) == 20
    point = (0.213, -0.381, 0.549)
    weights, gradients = mesh_api.hexa20_shape(point)
    for powers_row in powers:
        nodal = [math.prod(v ** p for v, p in zip(node, powers_row))
                 for node in mesh_api.HEXA20_NATURAL_NODES]
        expected = math.prod(v ** p for v, p in zip(point, powers_row))
        assert math.fsum(w * n for w, n in zip(weights, nodal)) == pytest.approx(expected, abs=4e-16)
        for axis, power in enumerate(powers_row):
            expected_derivative = 0 if power == 0 else power * math.prod(
                v ** (p - int(i == axis)) for i, (v, p) in enumerate(zip(point, powers_row)))
            assert math.fsum(g[axis] * n for g, n in zip(gradients, nodal)) == pytest.approx(expected_derivative, abs=5e-16)


def test_gauss27_exact_polynomial_integrals_and_declared_order():
    assert len(mesh_api.GAUSS27) == 27
    assert len(set(p[:3] for p in mesh_api.GAUSS27)) == 27
    assert mesh_api.GAUSS27[0][:3] == pytest.approx([-math.sqrt(3 / 5)] * 3)
    assert mesh_api.GAUSS27[1][:3] == pytest.approx([0, -math.sqrt(3 / 5), -math.sqrt(3 / 5)])
    for a in range(6):
        for b in range(6):
            for c in range(6):
                measured = math.fsum(x ** a * y ** b * z ** c * w for x, y, z, w in mesh_api.GAUSS27)
                exact = math.prod(0 if p % 2 else 2 / (p + 1) for p in (a, b, c))
                assert measured == pytest.approx(exact, abs=2e-15)


def test_gauss27_preserves_negative_consistent_corner_body_weights():
    integrated = [math.fsum(mesh_api.hexa20_shape(point[:3])[0][i] * point[3]
                            for point in mesh_api.GAUSS27) for i in range(20)]
    assert integrated[:8] == pytest.approx([-1.0] * 8, abs=8e-16)
    assert integrated[8:] == pytest.approx([4 / 3] * 12, abs=8e-16)
    assert math.fsum(integrated) == pytest.approx(8)


@pytest.mark.parametrize("index,point", enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1), (0, -1), (1, 0), (0, 1), (-1, 0))))
def test_quad8_nodal_kronecker_property(index, point):
    weights, gradients = mesh_api.quad8_shape(point)
    assert weights == tuple(float(i == index) for i in range(8))
    assert len(gradients) == 8


def test_quad8_derivatives_and_negative_face_weights():
    point = [0.37, -0.22]
    weights, gradients = mesh_api.quad8_shape(point)
    assert math.fsum(weights) == pytest.approx(1)
    for axis in range(2):
        plus, minus = list(point), list(point)
        plus[axis] += 1e-6
        minus[axis] -= 1e-6
        numerical = [(a - b) / 2e-6 for a, b in zip(mesh_api.quad8_shape(plus)[0], mesh_api.quad8_shape(minus)[0])]
        assert [row[axis] for row in gradients] == pytest.approx(numerical, abs=2e-10)
    integral = [math.fsum(mesh_api.quad8_shape(point[:2])[0][i] * point[2]
                         for point in mesh_api.GAUSS9) for i in range(8)]
    assert integral[:4] == pytest.approx([-1 / 3] * 4, abs=5e-16)
    assert integral[4:] == pytest.approx([4 / 3] * 4, abs=5e-16)
    assert math.fsum(integral) == pytest.approx(4)


def test_coordinate_interpolation_of_independent_affine_map():
    def affine(point):
        r, s, t = point
        return [3 + 2 * r - s + t / 2, -5 + r + s * 4, 7 - s / 3 + 6 * t]

    coordinates = [affine(point) for point in mesh_api.HEXA20_NATURAL_NODES]
    point = [0.123, -0.456, 0.789]
    assert mesh_api.hexa20_point_coordinates(coordinates, point) == pytest.approx(affine(point), abs=2e-15)


@pytest.mark.parametrize("value", [[True, 0, 0], [0, math.nan, 0], [0, math.inf, 0], [0, 1], "0,0,0", [10 ** 400, 0, 0], [1e308, 0, 0]])
def test_shape_helpers_refuse_nonfinite_malformed_or_unrepresentable(value):
    with pytest.raises(ValueError):
        mesh_api.hexa20_shape(value)


@pytest.mark.parametrize("rows", [[], [[0, 0, 0]] * 19, [[True, 0, 0]] * 20, [[0, 0]] * 20])
def test_coordinate_helper_refuses_incomplete_coordinate_catalogue(rows):
    with pytest.raises(ValueError):
        mesh_api.hexa20_point_coordinates(rows, [0, 0, 0])


def test_pure_helpers_import_in_isolation_without_domain_numpy_or_filesystem_reads(tmp_path):
    source = Path(mesh_api.__file__).read_bytes()
    standalone = tmp_path / "standalone_mesh.py"
    standalone.write_bytes(source)
    code = """
import importlib.util, pathlib, sys
path = sys.argv[1]
def forbidden(*args, **kwargs):
    raise AssertionError('helper attempted filesystem read')
pathlib.Path.read_text = forbidden
pathlib.Path.read_bytes = forbidden
spec = importlib.util.spec_from_file_location('standalone_mesh', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert not any(name == 'numpy' or name.startswith('plugins') for name in sys.modules)
assert abs(sum(module.hexa20_shape([0.1, 0.2, 0.3])[0]) - 1) < 1e-14
assert module.hexa20_point_coordinates(module.HEXA20_NATURAL_NODES, [0, 0, 0]) == [0, 0, 0]
"""
    completed = subprocess.run([sys.executable, "-I", "-c", code, str(standalone)], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("case,grid", [(case, i) for case in CASES for i in range(3)])
def test_all_frozen_grids_connectivity_bounds_analytic_volume_and_load_integrals(case, grid, family_meshes):
    settings = specification(case)
    cells = settings["mesh_cells"][grid]
    mesh = family_meshes[(case, tuple(cells))]
    nx, ny, nz = cells
    expected_count = ((nx + 1) * (ny + 1) * (nz + 1) + nx * (ny + 1) * (nz + 1)
                      + (nx + 1) * ny * (nz + 1) + (nx + 1) * (ny + 1) * nz)
    assert len(mesh["nodes"]) == expected_count
    assert len(mesh["elements"]) == math.prod(cells)
    assert [row["id"] for row in mesh["nodes"]] == list(range(1, expected_count + 1))
    assert {node_id for row in mesh["elements"] for node_id in row["node_ids"]} == set(range(1, expected_count + 1))
    assert all(len(row["node_ids"]) == len(set(row["node_ids"])) == 20 for row in mesh["elements"])
    assert len({tuple(row["coordinates_mm"]) for row in mesh["nodes"]}) == expected_count
    checks = mesh["checks"]
    assert checks["jacobian_sample_count_per_element"] == 54
    assert checks["minimum_sampled_jacobian_mm3"] > 0
    assert checks["volume_relative_error"] <= 1e-3
    assert checks["applied_force_relative_error"] <= 1e-3
    assert checks["applied_moment_relative_error"] <= 1e-3
    assert "not a proof" in checks["jacobian_limitation"]
    coordinates = _coordinates(mesh)
    resultant = [math.fsum(row["value"][i] for row in mesh["nodal_loads_n"]) for i in range(3)]
    moments = [_cross(coordinates[row["node_id"]], row["value"]) for row in mesh["nodal_loads_n"]]
    assert resultant == checks["applied_force_n"]
    assert [math.fsum(row[i] for row in moments) for i in range(3)] == checks["applied_moment_n_mm"]
    assert [row["node_id"] for row in mesh["nodal_loads_n"]] == list(range(1, expected_count + 1))
    assert json.loads(json.dumps(mesh, allow_nan=False)) == mesh


@pytest.mark.parametrize("load_case,axis", [("Fx", 0), ("Fy", 1), ("Fz", 2)])
def test_beam_force_moment_exact_response_nodes_and_face_corner_weights(load_case, axis):
    settings = specification("ansys_vmd1_regular", load_case=load_case, load_factor=1.4)
    mesh = mesh_api.build_mesh(settings, settings["mesh_cells"][0])
    coordinates = _coordinates(mesh)
    assert [coordinates[i] for i in mesh["response_node_ids"]["tip"]] == [[152.39999999999998, 0.0, 0.0], [152.39999999999998, 5.08, 0.0]]
    expected_force = [0, 0, 0]
    expected_force[axis] = 4.4482216152605 * 1.4
    expected_moment = _cross([6 * 25.4, 0.1 * 25.4, 0.05 * 25.4], expected_force)
    assert mesh["checks"]["applied_force_n"] == pytest.approx(expected_force, abs=1e-14)
    assert mesh["checks"]["applied_moment_n_mm"] == pytest.approx(expected_moment, rel=3e-15, abs=1e-13)
    assert all(row["components"] == [1, 2, 3] and coordinates[row["node_id"]][0] == 0 for row in mesh["supports"])
    loaded = [row["value"][axis] for row in mesh["nodal_loads_n"] if row["node_id"] in mesh["groups"]["TIP"]]
    assert sorted(loaded) == pytest.approx(sorted([-expected_force[axis] / 12] * 4 + [expected_force[axis] / 3] * 4), rel=3e-15)
    assert all(row["value"] == [0.0, 0.0, 0.0] for row in mesh["nodal_loads_n"] if row["node_id"] not in mesh["groups"]["TIP"])


def test_cylinder_polar_midsides_plane_strain_and_outward_pressure(family_meshes):
    mesh = family_meshes[("lame_cylinder_plane_strain", (2, 4, 1))]
    coordinates = _coordinates(mesh)
    for name, radius in [("INNER", 100), ("OUTER", 200)]:
        assert all(math.hypot(*coordinates[node_id][:2]) == pytest.approx(radius, abs=3e-14) for node_id in mesh["groups"][name])
    first = [coordinates[node_id] for node_id in mesh["elements"][0]["node_ids"]]
    # Angular edge on outer radial boundary: its midpoint stays on the circle,
    # unlike the chord midpoint of its corners.
    radius = math.hypot(*first[9][:2])
    assert radius == pytest.approx(150, abs=3e-14)
    chord = [(a + b) / 2 for a, b in zip(first[1], first[2])]
    assert math.hypot(*chord[:2]) < radius
    by_node = {row["node_id"]: row["components"] for row in mesh["supports"]}
    assert set(by_node) == set(coordinates)
    assert all(3 in components for components in by_node.values())
    assert all(1 in by_node[node_id] and coordinates[node_id][0] == 0 for node_id in mesh["groups"]["X_SYMMETRY"])
    assert all(2 in by_node[node_id] and coordinates[node_id][1] == 0 for node_id in mesh["groups"]["Y_SYMMETRY"])
    assert mesh["response_node_ids"]["inner"] == mesh["groups"]["INNER"]
    assert mesh["response_node_ids"]["outer"] == mesh["groups"]["OUTER"]
    assert mesh["checks"]["applied_force_n"] == pytest.approx([200000, 200000, 0], rel=2e-14, abs=2e-9)
    assert mesh["checks"]["applied_moment_n_mm"] == pytest.approx([-2000000, 2000000, 0], rel=2e-14, abs=2e-8)
    radial_dot = [sum(coordinates[row["node_id"]][i] * row["value"][i] for i in range(2))
                  for row in mesh["nodal_loads_n"]]
    assert min(radial_dot) < 0  # Consistent corner weights are not clamped.
    assert math.fsum(radial_dot) > 0


def test_roof_radius_exact_point_b_supports_and_independent_total_weight(family_meshes):
    mesh = family_meshes[("scordelis_lo_solid", (4, 4, 1))]
    coordinates = _coordinates(mesh)
    radius, thickness, length = 25 * 304.8, 0.25 * 304.8, 25 * 304.8
    for name, r in [("INNER", radius - thickness / 2), ("OUTER", radius + thickness / 2)]:
        assert all(math.hypot(*coordinates[node_id][1:]) == pytest.approx(r, abs=2e-12) for node_id in mesh["groups"][name])
    point_b = mesh["response_node_ids"]["point_b"]
    assert len(point_b) == 1
    r = radius - thickness / 2
    assert coordinates[point_b[0]] == pytest.approx([length, r * math.sin(math.radians(40)), r * math.cos(math.radians(40))])
    supports = {row["node_id"]: row["components"] for row in mesh["supports"]}
    assert all(2 in supports[node_id] and 3 in supports[node_id] for node_id in mesh["groups"]["DIAPHRAGM"])
    assert all(1 in supports[node_id] for node_id in mesh["groups"]["LONGITUDINAL_SYMMETRY"])
    assert all(2 in supports[node_id] for node_id in mesh["groups"]["CROWN"])
    expected_weight = 12500 * math.pi * 4.4482216152605
    assert mesh["checks"]["analytical_force_n"] == pytest.approx([0, 0, -expected_weight], rel=2e-14)
    assert mesh["checks"]["applied_force_n"] == pytest.approx([0, 0, -expected_weight], rel=1e-5)
    zloads = [row["value"][2] for row in mesh["nodal_loads_n"]]
    assert min(zloads) < 0 < max(zloads)


@pytest.mark.parametrize("case", CASES)
def test_load_factor_scaling_preserves_geometry_and_exact_selections(case, family_meshes):
    original_settings = specification(case)
    cells = original_settings["mesh_cells"][0]
    original = family_meshes[(case, tuple(cells))]
    scaled = mesh_api.build_mesh(specification(case, load_factor=2), cells)
    for key in ("nodes", "elements", "groups", "supports", "response_node_ids"):
        assert original[key] == scaled[key]
    assert [row["value"] for row in scaled["nodal_loads_n"]] == [[v * 2 for v in row["value"]] for row in original["nodal_loads_n"]]
    assert scaled["checks"]["applied_force_n"] == [v * 2 for v in original["checks"]["applied_force_n"]]


@pytest.mark.parametrize("cells", [[True, 1, 1], [0, 1, 1], [1.0, 1, 1], [49, 1, 1], [48, 48, 1], [1, 1], [1, 1, 1], None])
def test_invalid_or_undeclared_cells_refuse_before_quadrature(cells, monkeypatch):
    def forbidden(*args):
        raise AssertionError("invalid workload reached quadrature")
    monkeypatch.setattr(mesh_api, "_integrate", forbidden)
    with pytest.raises(ValueError):
        mesh_api.build_mesh(specification(CASES[0]), cells)


@pytest.mark.parametrize("change", [lambda s: s.update(unknown=1), lambda s: s.update(case="unknown"),
                                   lambda s: s.update(load_factor=True), lambda s: s.update(load_factor=math.nan),
                                   lambda s: s.update(load_factor=2.01), lambda s: s.update(load_case="torsion"),
                                   lambda s: s.update(mesh_cells=[[48, 48, 48], [48, 48, 48]])])
def test_invalid_settings_refuse_before_mesh_allocation(change, monkeypatch):
    settings = specification(CASES[0])
    change(settings)
    monkeypatch.setattr(mesh_api, "_topology", lambda *args: pytest.fail("invalid settings reached allocation"))
    with pytest.raises(ValueError):
        mesh_api.build_mesh(settings, [6, 1, 1])


@pytest.mark.parametrize("case", CASES)
def test_check_recomputes_json_roundtrip_and_returns_independent_checks(case, family_meshes):
    settings = specification(case)
    mesh = family_meshes[(case, tuple(settings["mesh_cells"][0]))]
    recovered = json.loads(json.dumps(mesh, allow_nan=False))
    checks = mesh_api.check_mesh(recovered, settings)
    assert checks == mesh["checks"]
    checks["positive_sampled_jacobians"] = False
    assert mesh["checks"]["positive_sampled_jacobians"] is True


@pytest.mark.parametrize("change", [
    lambda m: m["nodes"][0].update(id=True),
    lambda m: m["nodes"][0]["coordinates_mm"].__setitem__(0, False),
    lambda m: m["nodes"][1]["coordinates_mm"].__setitem__(0, 99.0),
    lambda m: m["nodes"].append(m["nodes"][0]),
    lambda m: m["elements"][0]["node_ids"].__setitem__(0, m["elements"][0]["node_ids"][1]),
    lambda m: m["elements"].pop(),
    lambda m: m["groups"]["ROOT"].append(m["groups"]["ROOT"][0]),
    lambda m: m["supports"][0]["components"].pop(),
    lambda m: m["response_node_ids"]["tip"].reverse(),
    lambda m: m["nodal_loads_n"][-1]["value"].__setitem__(0, 1.0),
    lambda m: m["nodal_loads_n"].pop(),
    lambda m: m["checks"].update(minimum_sampled_jacobian_mm3=math.inf),
    lambda m: m["checks"].update(positive_sampled_jacobians=1),
    lambda m: m.update(unapproved=True),
])
def test_check_refuses_catalogue_tampering_including_bool_aliases(change, family_meshes):
    settings = specification(CASES[0])
    altered = copy.deepcopy(family_meshes[(CASES[0], (6, 1, 1))])
    change(altered)
    with pytest.raises(ValueError):
        mesh_api.check_mesh(altered, settings)


def test_inverted_curved_midside_is_detected_by_quadratic_jacobians(family_meshes):
    settings = specification("lame_cylinder_plane_strain")
    from plugins.structural_families.reference import case_definition
    definition = json.loads((Path(__file__).resolve().parents[1] / "benchmarks/specifications/structural-families-v1.json").read_text())
    source = family_meshes[(settings["case"], (2, 4, 1))]
    nodes = copy.deepcopy(source["nodes"])
    # A corner-only volume check would miss a displaced quadratic midside.
    node_id = source["elements"][0]["node_ids"][9]
    nodes[node_id - 1]["coordinates_mm"] = [10000.0, -10000.0, 0.0]
    raw = case_definition(settings["case"])
    _, geometry = mesh_api._geometry(settings["case"], raw, definition["unit_conversion"])
    indices = [(i, j, k) for k in range(1) for j in range(4) for i in range(2)]
    with pytest.raises(ValueError, match="Jacobian"):
        mesh_api._integrate(dict(settings, _cells=(2, 4, 1)), raw, definition, nodes, source["elements"], indices, geometry)


def test_coarse_curved_grid_retains_failed_analytic_metrics_and_frozen_limit():
    settings = specification("lame_cylinder_plane_strain")
    settings["mesh_cells"] = [[1, 1, 1], [2, 2, 1]]
    with pytest.raises(ValueError, match="frozen analytic limit") as error:
        mesh_api.build_mesh(settings, [1, 1, 1])
    text = str(error.value)
    assert "volume_relative_error=" in text
    assert "applied_force_n=" in text
    assert "applied_moment_n_mm=" in text
    assert "limit=0.001" in text


def test_official_gmsh_order_maps_each_exact_edge():
    # Official diagram https://gmsh.info/doc/texinfo/#Node-ordering.
    edges = [(0, 1), (0, 3), (0, 4), (1, 2), (1, 5), (2, 3),
             (2, 6), (3, 7), (4, 5), (4, 7), (5, 6), (6, 7)]
    reordered = [mesh_api.HEXA20_NATURAL_NODES[i] for i in mesh_api.GMSH_HEXA20_FROM_CANONICAL]
    assert sorted(mesh_api.GMSH_HEXA20_FROM_CANONICAL) == list(range(20))
    for offset, (a, b) in enumerate(edges, 8):
        assert reordered[offset] == tuple((x + y) / 2 for x, y in zip(reordered[a], reordered[b]))


@pytest.mark.parametrize("case", CASES)
def test_gmsh_serialization_exact_node_cell_group_bijection(case, family_meshes, tmp_path):
    mesh = family_meshes[(case, tuple(specification(case)["mesh_cells"][0]))]
    path = tmp_path / "mesh.msh"
    metadata = mesh_api.write_gmsh(mesh, path)
    lines = path.read_text().splitlines()
    assert lines[:3] == ["$MeshFormat", "2.2 0 8", "$EndMeshFormat"]
    node_start = lines.index("$Nodes") + 1
    assert int(lines[node_start]) == len(mesh["nodes"])
    parsed_nodes = [[float(v) for v in line.split()[1:]] for line in lines[node_start + 1:lines.index("$EndNodes")]]
    assert parsed_nodes == [node["coordinates_mm"] for node in mesh["nodes"]]
    element_start = lines.index("$Elements") + 1
    rows = [[int(v) for v in line.split()] for line in lines[element_start + 1:lines.index("$EndElements")]]
    assert int(lines[element_start]) == len(rows)
    assert [row[0] for row in rows] == list(range(1, len(rows) + 1))
    volume = rows[:len(mesh["elements"])]
    for row, element in zip(volume, mesh["elements"]):
        assert row[:5] == [element["id"], 17, 2, 1, 1]
        assert row[5:] == [element["node_ids"][i] for i in mesh_api.GMSH_HEXA20_FROM_CANONICAL]
    points = {row[0]: row for row in rows[len(volume):]}
    for name, node_ids in mesh["groups"].items():
        tag = metadata["physical_tags"][name]["tag"]
        selected = [points[point_id] for point_id in metadata["point_element_ids"][name]]
        assert [row[5] for row in selected] == node_ids
        assert all(row[1:5] == [15, 2, tag, tag] for row in selected)
        assert f'0 {tag} "{name}"' in lines
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        mesh_api.write_gmsh(mesh, path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("case", CASES)
def test_calculix_serialization_canonical_connectivity_and_bounded_coordinate_fields(case, family_meshes, tmp_path):
    mesh = family_meshes[(case, tuple(specification(case)["mesh_cells"][0]))]
    path = tmp_path / "mesh.inc"
    metadata = mesh_api.write_calculix_mesh(mesh, path)
    lines = path.read_text().splitlines()
    start = lines.index("*NODE") + 1
    stop = lines.index("*ELEMENT, TYPE=C3D20, ELSET=SOLID")
    node_rows = [[v.strip() for v in line.split(",")] for line in lines[start:stop]]
    for fields, node in zip(node_rows, mesh["nodes"]):
        assert int(fields[0]) == node["id"]
        assert all(len(v) <= 20 for v in fields[1:])
        assert [float(v) for v in fields[1:]] == pytest.approx(node["coordinates_mm"], rel=5e-14, abs=1e-13)
    for i, element in enumerate(mesh["elements"]):
        first, second = lines[stop + 1 + 2 * i:stop + 3 + 2 * i]
        assert first.endswith(",")
        parsed = [int(v.strip()) for line in (first, second) for v in line.split(",") if v.strip()]
        assert parsed == [element["id"], *element["node_ids"]]
    for name, ids in mesh["groups"].items():
        index = lines.index(f"*NSET, NSET={name}") + 1
        found = []
        while index < len(lines) and not lines[index].startswith("*"):
            found.extend(int(v) for v in lines[index].split(","))
            index += 1
        assert found == ids == metadata["node_groups"][name]
    assert not any(line.startswith(("*CLOAD", "*BOUNDARY", "*STEP", "*MATERIAL")) for line in lines)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        mesh_api.write_calculix_mesh(mesh, path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("change", [lambda m: m["nodes"][0].update(id=True),
                                   lambda m: m["nodes"][0]["coordinates_mm"].__setitem__(0, math.nan),
                                   lambda m: m["elements"][0]["node_ids"].__setitem__(0, 999999),
                                   lambda m: m["groups"].update(CAE_ALL=[1]),
                                   lambda m: m["groups"].update(SOLID=[1]),
                                   lambda m: m["groups"]["ROOT"].append(1)])
@pytest.mark.parametrize("writer", [mesh_api.write_gmsh, mesh_api.write_calculix_mesh])
def test_writers_refuse_malformed_or_reserved_data_before_file_creation(change, writer, family_meshes, tmp_path):
    mesh = copy.deepcopy(family_meshes[(CASES[0], (6, 1, 1))])
    change(mesh)
    path = tmp_path / "invalid.txt"
    with pytest.raises(ValueError):
        writer(mesh, path)
    assert not path.exists()
