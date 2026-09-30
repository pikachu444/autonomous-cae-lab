"""Code_Aster input/mesh/table/process regressions, without running a solver.

The native-result fixtures are labelled mock data and are not acceptance proof.
Actual Code_Aster/container execution is owned by the primary session.
"""

from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest

from caelab import Lab
from caelab.adapters import codeaster_elasticity as adapter_module
from caelab.adapters.codeaster_elasticity import (CodeAsterElasticityAdapter, CONTAINER_SCRIPT,
                                                MeshRejected, OCI_MANIFEST_SHA256,
                                                _cleanup_scratch, _coordinates_equal, _expected_mesh,
                                                gmsh_source, parse_gmsh_mesh)
from caelab.adapters.codeaster_worker import (_json_safe, _native_mesh_catalog, parse_field_tables,
                                            solve_level, validate_native_mesh)
from caelab.storage import canonical_hash, load_json
from plugins.elasticity.reference import analytical_reference, model_declaration


def settings():
    return {"case": "uniaxial_block", "dimensions_mm": [40., 10., 10.],
            "material": {"youngs_modulus_mpa": 210000., "poisson_ratio": .3},
            "traction_mpa": 10., "mesh_sizes_mm": [5., 3.],
            "limits": {"displacement_relative": 1e-8, "displacement_absolute_mm": 1e-12,
                       "stress_relative": 1e-8, "reaction_relative": 1e-8, "mesh_agreement_relative": 1e-8}}


def test_domain_declaration_exposes_common_model_metadata_and_preserves_domain_fields():
    request = settings()
    original = deepcopy(request)
    domain = model_declaration(request)
    declaration = CodeAsterElasticityAdapter().describe_model(request)
    assert declaration["model"]["geometry"] == {"type": "block", "dimensions_mm": [40., 10., 10.],
                                                "unit": "mm", "origin": [0., 0., 0.]}
    assert declaration["model"]["materials"] == domain["materials"]
    assert declaration["model"]["mesh"] == domain["mesh"]
    assert declaration["case"] == "uniaxial_block"
    for field in ("boundary_conditions", "loads", "outputs"):
        assert declaration[field] == domain[field]
    assert not {"geometry", "materials", "mesh"}.intersection(declaration)
    assert request == original


def test_lab_model_proposal_keeps_real_adapter_declaration_and_revision_without_solver(tmp_path, monkeypatch):
    """Exercise actual declaration/Core metadata; deliberately execute no physics."""
    adapter = CodeAsterElasticityAdapter()
    request = settings()
    expected = adapter.describe_model(request)
    calls = []

    def metadata_only(output, observed_settings):
        calls.append(deepcopy(observed_settings))
        output.mkdir()
        (output / "test_only.json").write_text(json.dumps({"test_only": True, "native_solver_executed": False}))
        return {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                "checks": [{"code": "metadata_test_no_solver", "status": "FAIL",
                            "observed": "TEST ONLY: metadata path, no native numerical observation"}],
                "metrics": {}, "pending_validations": ["model_qualification", "physical_validation"],
                "provenance": {"test_only": True}, "raw_result": "simulation/test_only.json"}

    monkeypatch.setattr(adapter, "solve", metadata_only)
    monkeypatch.setattr("caelab.declared_model.source_identity", lambda _: {
        "core_commit": "TEST-ONLY-METADATA", "core_dirty": False, "core_source_sha256": "0" * 64})
    monkeypatch.setattr("caelab.adapters.codeaster_elasticity.subprocess.run",
                        lambda *a, **kw: pytest.fail("Metadata regression must execute no external command"))
    lab = Lab(tmp_path / "store", adapters={}, analysis_adapters={}, doe_adapters={},
              optimization_adapters={}, pde_adapters={}, model_analysis_adapters={adapter.backend: adapter})
    lab.create_study("S-metadata", "Test-only metadata", "Does the real adapter publish the common model?",
                     "Geometry/materials/mesh persist in proposal metadata", "Do not run a solver")
    result = lab.run_model_analysis(study_id="S-metadata", experiment_id="E-metadata",
                                    backend=adapter.backend, settings=request)
    proposal = load_json(lab.store / "experiments/E-metadata/proposal.json")
    assert calls == [request]
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert proposal["model"] == expected["model"]
    assert proposal["model"]["geometry"]["type"] == "block"
    assert proposal["model"]["materials"][0]["youngs_modulus"] == {"value": 210000., "unit": "MPa"}
    assert proposal["model"]["mesh"]["element_type"] == "TETRA10"
    for field in ("boundary_conditions", "loads"):
        assert proposal[field] == expected[field]
    assert proposal["outputs"]["fields"] == expected["outputs"]["fields"]
    assert proposal["outputs"]["metrics"] == adapter.default_metrics
    assert proposal["extensions"]["model_analysis"]["declaration"] == expected
    assert result["extensions"] == proposal["extensions"]
    assert result["model_revision"] == proposal["model_revision"] == canonical_hash({"settings": request, "declaration": expected})
    assert result["proposal_revision"] == canonical_hash(proposal)
    assert result["cad_revision"] is None and "parent_experiment_id" not in proposal
    assert result["decision"] == "NOT_RELEASED"
    assert lab.inspect_experiment("E-metadata") == result


def brick_msh(dimensions=(40., 10., 10.)) -> str:
    """Six known positive tetrahedra tile a brick; IDs are intentionally sparse."""
    length, breadth, height = dimensions
    vertices = [[0, 0, 0], [length, 0, 0], [length, breadth, 0], [0, breadth, 0],
                [0, 0, height], [length, 0, height], [length, breadth, height], [0, breadth, height]]
    corner_ids = [(index + 1) * 10 for index in range(8)]
    nodes = dict(zip(corner_ids, vertices))
    patterns = [(0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6),
                (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6)]
    midpoint_ids = {}

    def midpoint(a, b):
        key = tuple(sorted((a, b)))
        if key not in midpoint_ids:
            identifier = 100 + 7 * len(midpoint_ids)
            midpoint_ids[key] = identifier
            nodes[identifier] = [(x + y) / 2 for x, y in zip(nodes[a], nodes[b])]
        return midpoint_ids[key]

    tets, faces = [], {}
    edges = [(0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3)]
    for index, pattern in enumerate(patterns):
        corners = [corner_ids[i] for i in pattern]
        connectivity = [*corners, *(midpoint(corners[a], corners[b]) for a, b in edges)]
        tets.append((1000 + 100 * index, 11, 1001, connectivity))
        for face in itertools.combinations(corners, 3):
            key = tuple(sorted(face))
            faces[key] = faces.get(key, 0) + 1
    triangles = []
    for face, count in faces.items():
        if count != 1:
            continue
        coordinates = [nodes[node] for node in face]
        if all(coord[0] == 0 for coord in coordinates):
            group = 1002
        elif all(coord[0] == length for coord in coordinates):
            group = 1003
        elif all(coord[1] == 0 for coord in coordinates):
            group = 1004
        elif all(coord[2] == 0 for coord in coordinates):
            group = 1005
        else:
            continue
        connectivity = [*face, midpoint(face[0], face[1]), midpoint(face[1], face[2]), midpoint(face[2], face[0])]
        triangles.append((2000 + 11 * len(triangles), 9, group, connectivity))
    # Reversed node and element rows catch accidental nodeid-1 indexing.
    node_rows = [f"{node} " + " ".join(f"{coord:.17g}" for coord in coords)
                 for node, coords in reversed(list(nodes.items()))]
    element_rows = [f"{identifier} {kind} 2 {physical} 1 " + " ".join(map(str, connectivity))
                    for identifier, kind, physical, connectivity in reversed([*tets, *triangles])]
    return ("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$PhysicalNames\n5\n"
            '3 1001 "BODY"\n2 1002 "X0"\n2 1003 "XL"\n2 1004 "Y0"\n2 1005 "Z0"\n$EndPhysicalNames\n'
            f"$Nodes\n{len(node_rows)}\n" + "\n".join(node_rows) + "\n$EndNodes\n"
            f"$Elements\n{len(element_rows)}\n" + "\n".join(element_rows) + "\n$EndElements\n")


def mesh_fixture(tmp_path):
    path = tmp_path / "mesh.msh"
    path.write_text(brick_msh(), encoding="utf-8")
    return path, parse_gmsh_mesh(path, settings()["dimensions_mm"])


def native_fixture(mesh, request=None, *, order=7):
    """A strict-table mock with exact affine fields and a non-default order."""
    request = request or settings()
    reference = analytical_reference(request)
    node_ids = sorted(mesh["nodes"])
    native_ids = {source: index + 1 for index, source in enumerate(node_ids)}
    names = {source: str(native_ids[source]) for source in node_ids}
    catalog = {"nodes": [{"node_id": native_ids[source], "name": names[source],
                           "coordinates_mm": mesh["nodes"][source]} for source in node_ids],
               "body_elements": [{"element_id": index + 1, "name": str(index + 1)}
                                 for index in range(mesh["element_count"])],
               "group_node_ids": {name: [native_ids[node] for node in group]
                                  for name, group in mesh["group_node_ids"].items()},
               "gauss_point_ids": [1, 2, 3, 4, 5]}
    support = set(catalog["group_node_ids"]["X0"]) | set(catalog["group_node_ids"]["Y0"]) | set(catalog["group_node_ids"]["Z0"])
    catalog["support_node_ids"] = sorted(support)
    displacement = {key: [] for key in ("NOEUD", "NUME_ORDRE", "COOR_X", "COOR_Y", "COOR_Z", "DX", "DY", "DZ")}
    reactions = deepcopy(displacement)
    for source in reversed(node_ids):
        coordinate = mesh["nodes"][source]
        exact = [slope * position for slope, position in zip(reference["displacement_gradient"], coordinate)]
        reaction = [reference["reaction_n"][0] / len(mesh["group_node_ids"]["X0"]), 0., 0.] if source in mesh["group_node_ids"]["X0"] else [0., 0., 0.]
        for table, value in ((displacement, exact), (reactions, reaction)):
            table["NOEUD"].append(names[source] + " ")
            table["NUME_ORDRE"].append(order)
            for key, item in zip(("COOR_X", "COOR_Y", "COOR_Z"), coordinate):
                table[key].append(item)
            for key, item in zip(("DX", "DY", "DZ"), value):
                table[key].append(item)
    stress = {key: [] for key in ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", "COOR_X", "COOR_Y", "COOR_Z",
                                  "SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ")}
    for index, tet in enumerate(mesh["tetrahedra"]):
        centroid = [sum(mesh["nodes"][node][axis] for node in tet["node_ids"][:4]) / 4 for axis in range(3)]
        for point in (1, 2, 3, 4, 5):
            stress["MAILLE"].append(str(index + 1))
            stress["POINT"].append(point)
            stress["SOUS_POINT"].append(1)
            stress["NUME_ORDRE"].append(order)
            for key, value in zip(("COOR_X", "COOR_Y", "COOR_Z"), centroid):
                stress[key].append(value)
            for key, value in zip(("SIXX", "SIYY", "SIZZ", "SIXY", "SIXZ", "SIYZ"), reference["stress_components_mpa"]):
                stress[key].append(value)
    post = {"INTITULE": ["SUPPORT"], "NUME_ORDRE": [order],
            "DX": [reference["reaction_n"][0]], "DY": [0.], "DZ": [0.]}
    return {"schema_version": "1", "solver_status": "COMPLETED", "converged": True,
            "order": order, "available_orders": [order], "access_parameters": {"NUME_ORDRE": [order]},
            "versions": {"code_aster": "17.4.0", "python": "TEST-MOCK", "numpy": "TEST-MOCK"},
            "code_aster_runtime": {"version": "17.4.0", "parentid": "TEST-MOCK", "branch": "TEST-MOCK", "uncommitted": []},
            "numerical_libraries": [{"name": "mumps", "version": "TEST-MOCK", "hash": "TEST-MOCK"}],
            "mesh": catalog, "tables": {"DEPL": displacement, "SIEF_ELGA": stress,
                                         "REAC_NODA": reactions, "SUPPORT_RESULTANT": post}}


def test_checked_straight_quadratic_mesh_has_exact_volume_areas_and_sparse_ids(tmp_path):
    _, mesh = mesh_fixture(tmp_path)
    assert mesh["element_count"] == 6
    assert mesh["volume_mm3"] == pytest.approx(4000.)
    assert mesh["volume_relative_error"] < 1e-14
    assert mesh["minimum_jacobian_mm3"] > 0
    assert mesh["boundary_areas_mm2"] == {"X0": 100., "XL": 100., "Y0": 400., "Z0": 400.}
    assert sorted(mesh["nodes"])[0] == 10
    # Loaded/support intersections are physically expected here.
    assert set(mesh["group_node_ids"]["XL"]) & set(mesh["group_node_ids"]["Y0"])
    assert set(mesh["group_node_ids"]["XL"]) & set(mesh["group_node_ids"]["Z0"])


def test_curved_midside_mesh_is_rejected_before_affine_jacobian_claim(tmp_path):
    source = brick_msh().replace("100 20 0 0", "100 20 0.01 0")
    path = tmp_path / "curved.msh"
    path.write_text(source)
    with pytest.raises(MeshRejected, match="Nonstraight"):
        parse_gmsh_mesh(path, settings()["dimensions_mm"])


def test_inverted_tetrahedron_and_missing_boundary_group_are_rejected(tmp_path):
    path = tmp_path / "bad.msh"
    lines = brick_msh().splitlines()
    for index, line in enumerate(lines):
        fields = line.split()
        if len(fields) == 15 and fields[1] == "11":
            connectivity = list(map(int, fields[5:]))
            # Swap corners and their corresponding midsides, retaining straight edges.
            permutation = [0, 2, 1, 3, 6, 5, 4, 7, 9, 8]
            fields[5:] = [str(connectivity[i]) for i in permutation]
            lines[index] = " ".join(fields)
            break
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(MeshRejected, match="Nonpositive"):
        parse_gmsh_mesh(path, settings()["dimensions_mm"])


@pytest.mark.parametrize("extra_tag", [False, True])
def test_every_nonphysical_gmsh_tag_must_be_disjoint_from_same_dimension_physical_ids(tmp_path, extra_tag):
    lines = brick_msh().splitlines()
    for index, line in enumerate(lines):
        fields = line.split()
        if len(fields) == 11 and fields[1] == "9":
            if extra_tag:
                fields[2] = "3"
                fields.insert(5, "1004")
            else:
                fields[4] = "1003"
            lines[index] = " ".join(fields)
            break
    path = tmp_path / "collision.msh"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(MeshRejected, match="nonphysical tags collide"):
        parse_gmsh_mesh(path, settings()["dimensions_mm"])
    path.write_text(brick_msh().replace('2 1003 "XL"', '2 1003 "UNEXPECTED"'))
    with pytest.raises(MeshRejected, match="physical groups"):
        parse_gmsh_mesh(path, settings()["dimensions_mm"])


def test_field_parser_requires_complete_nodes_points_and_deduplicates_supports(tmp_path):
    _, mesh = mesh_fixture(tmp_path)
    raw = native_fixture(mesh)
    record = parse_field_tables(raw, 5.)
    assert record["actual_result_order"] == 7
    assert len(record["stresses_mpa"]) == 5 * mesh["element_count"]
    assert len(record["stress_identifiers"]) == len(record["stresses_mpa"])
    assert record["reaction_n"] == pytest.approx([-1000., 0., 0.])
    assert record["native_support_resultant_n"] == pytest.approx(record["reaction_n"])
    assert len(record["support_node_ids"]) < sum(len(record["group_node_ids"][name]) for name in ("X0", "Y0", "Z0"))
    assert record["stress_component_order"] == ["xx", "yy", "zz", "xy", "xz", "yz"]


@pytest.mark.parametrize("mutate", [
    lambda raw: raw["tables"]["DEPL"]["NOEUD"].pop(),
    lambda raw: raw["tables"]["DEPL"]["NOEUD"].__setitem__(1, raw["tables"]["DEPL"]["NOEUD"][0]),
    lambda raw: raw["tables"]["DEPL"]["DX"].__setitem__(0, None),
    lambda raw: raw["tables"]["DEPL"]["COOR_Z"].__setitem__(0, float("nan")),
    lambda raw: raw["tables"]["REAC_NODA"]["DZ"].__setitem__(0, float("inf")),
    lambda raw: raw["tables"]["SIEF_ELGA"]["POINT"].__setitem__(0, 2),
    lambda raw: raw["tables"]["SIEF_ELGA"]["SOUS_POINT"].__setitem__(0, None),
    lambda raw: raw["tables"]["SIEF_ELGA"]["SOUS_POINT"].__setitem__(0, 2),
    lambda raw: raw["tables"]["SIEF_ELGA"]["SIYZ"].__setitem__(0, None),
    lambda raw: raw["tables"]["SIEF_ELGA"]["COOR_Y"].__setitem__(0, float("nan")),
    lambda raw: raw["tables"]["SIEF_ELGA"]["MAILLE"].__setitem__(0, "boundary_TRI6"),
    lambda raw: raw["tables"]["SIEF_ELGA"]["NUME_ORDRE"].__setitem__(0, 1),
    lambda raw: raw["tables"]["SUPPORT_RESULTANT"]["DX"].__setitem__(0, -2000.),
    lambda raw: raw["tables"]["SUPPORT_RESULTANT"]["INTITULE"].__setitem__(0, "wrong group"),
    lambda raw: raw["mesh"]["support_node_ids"].append(raw["mesh"]["support_node_ids"][0]),
    lambda raw: raw["mesh"]["gauss_point_ids"].pop(),
])
def test_partial_nonfinite_or_misidentified_native_tables_fail_without_filtering(tmp_path, mutate):
    _, mesh = mesh_fixture(tmp_path)
    raw = native_fixture(mesh)
    mutate(raw)
    before = deepcopy(raw)
    with pytest.raises(ValueError):
        parse_field_tables(raw, 5.)
    assert raw == before or repr(raw) == repr(before)  # NaN is not equality-comparable.


@pytest.mark.parametrize("field", ["DEPL", "REAC_NODA", "SIEF_ELGA"])
def test_actual_order_column_is_required_in_every_native_field_table(tmp_path, field):
    _, mesh = mesh_fixture(tmp_path)
    raw = native_fixture(mesh)
    del raw["tables"][field]["NUME_ORDRE"]
    with pytest.raises(ValueError, match="missing required columns"):
        parse_field_tables(raw, 5.)


class NumericNativeMesh:
    """Mock only actual verified numeric API; optional name arrays stay absent."""
    def __init__(self, raw):
        self.catalog = deepcopy(raw["mesh"])
        self.coordinates = [item["coordinates_mm"] for item in sorted(self.catalog["nodes"], key=lambda row: row["node_id"])]

    @property
    def sdj(self):
        pytest.fail("Optional legacy NOMNOE/NOMMAI must not be read for numeric CREA_TABLE identifiers")

    def getNumberOfNodes(self):
        return len(self.coordinates)

    def getNumberOfCells(self):
        return max(item["element_id"] for item in self.catalog["body_elements"]) + 20

    def getCoordinates(self):
        return types.SimpleNamespace(toNumpy=lambda: types.SimpleNamespace(tolist=lambda: self.coordinates))

    def getNodes(self, group=None):
        ids = self.catalog["support_node_ids"] if group == "SUPPORT" else [item["node_id"] for item in self.catalog["nodes"]]
        return list(reversed([value - 1 for value in ids]))

    def getCells(self, group):
        assert group == "BODY"
        return [item["element_id"] - 1 for item in self.catalog["body_elements"]]

    def getNodesFromCells(self, group):
        return [value - 1 for value in self.catalog["group_node_ids"][group]]


class GuardNativeMesh(NumericNativeMesh):
    """Mock pinned Gmsh->Aster local-node permutation and physical groups."""
    def __init__(self, source, raw):
        super().__init__(raw)
        source_to_native = {node: index for index, node in enumerate(sorted(source["nodes"]))}
        permutation = [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]
        self.connectivity = [[source_to_native[tet["node_ids"][slot]] for slot in permutation]
                             for tet in source["tetrahedra"]]
        self.volume_count = len(self.connectivity)
        self.connectivity.extend([source_to_native[node] for node in face["node_ids"]]
                                 for faces in source["surfaces"].values() for face in faces)

    def getNumberOfCells(self):
        return len(self.connectivity)

    def getConnectivity(self):
        return self.connectivity

    def getCellTypeName(self, index):
        return "TETRA10" if index < self.volume_count else "TRIA6"


def test_native_preflight_proves_source_bijection_and_each_aster_tet10_midpoint_role(tmp_path):
    _, source = mesh_fixture(tmp_path)
    raw = native_fixture(source)
    native = GuardNativeMesh(source, raw)
    checks = validate_native_mesh(native, _expected_mesh(source))
    assert checks["status"] == "PASS"
    assert checks["source_node_ids_by_native_index"] == sorted(source["nodes"])
    assert checks["volume_element_count"] == source["element_count"]
    assert checks["minimum_native_jacobian_mm3"] > 0
    assert {row["source_element_id"] for row in checks["source_element_mapping"]} == {tet["element_id"] for tet in source["tetrahedra"]}
    assert checks["coordinate_tolerances"] == {"relative": 1e-12, "absolute": 1e-12}


@pytest.mark.parametrize("failure", ["wrong_group", "coordinate_drift", "duplicate_coordinates", "wrong_body_count",
                                     "wrong_type", "duplicate_cell_node", "corner_mid_swap", "wrong_midpoint_edge", "negative_jacobian"])
def test_native_preflight_rejects_semantic_geometry_group_or_midpoint_corruption(tmp_path, failure):
    _, source = mesh_fixture(tmp_path)
    raw = native_fixture(source)
    native = GuardNativeMesh(source, raw)
    if failure == "wrong_group":
        native.catalog["group_node_ids"]["X0"] = sorted(set(native.catalog["group_node_ids"]["X0"]) | set(native.catalog["group_node_ids"]["XL"]))
    elif failure == "coordinate_drift":
        native.coordinates[0][0] += 1e-10
    elif failure == "duplicate_coordinates":
        native.coordinates[1] = list(native.coordinates[0])
    elif failure == "wrong_body_count":
        native.catalog["body_elements"].pop()
    elif failure == "wrong_type":
        native.getCellTypeName = lambda index: "TETRA4"
    elif failure == "duplicate_cell_node":
        native.connectivity[0][0] = native.connectivity[0][1]
    elif failure == "corner_mid_swap":
        native.connectivity[0][0], native.connectivity[0][4] = native.connectivity[0][4], native.connectivity[0][0]
    elif failure == "wrong_midpoint_edge":
        native.connectivity[0][4], native.connectivity[0][5] = native.connectivity[0][5], native.connectivity[0][4]
    else:
        native.connectivity[0] = [native.connectivity[0][slot] for slot in (0, 2, 1, 3, 6, 5, 4, 7, 9, 8)]
    with pytest.raises(ValueError):
        validate_native_mesh(native, _expected_mesh(source))


def test_native_numeric_catalog_keeps_actual_decimal_ids_without_optional_names(tmp_path):
    _, mesh = mesh_fixture(tmp_path)
    raw = native_fixture(mesh)
    remapping = {str(index + 1): str(43 + index * 7) for index in range(mesh["element_count"])}
    for element in raw["mesh"]["body_elements"]:
        element["name"] = remapping[element["name"]]
        element["element_id"] = int(element["name"])
    for field in ("DEPL", "REAC_NODA"):
        raw["tables"][field]["NOEUD"] = [f"{int(name):8d}" for name in raw["tables"][field]["NOEUD"]]
    raw["tables"]["SIEF_ELGA"]["MAILLE"] = [f"{int(remapping[name]):8d}" for name in raw["tables"]["SIEF_ELGA"]["MAILLE"]]
    catalog = _native_mesh_catalog(NumericNativeMesh(raw), raw["tables"], raw["order"])
    assert {item["element_id"] for item in catalog["body_elements"]} == {int(name) for name in remapping.values()}
    assert all(item["name"].strip() == str(item["node_id"]) and len(item["name"]) == 8 for item in catalog["nodes"])
    raw["mesh"] = catalog
    record = parse_field_tables(raw, 5.)
    assert record["reaction_n"] == pytest.approx([-1000., 0., 0.])
    assert record["native_element_names"] == list(remapping.values())
    assert "decimal internal indices" in catalog["name_api"]


@pytest.mark.parametrize("failure", ["invented_node_prefix", "invented_element_prefix", "wrong_node_index",
                                     "wrong_body_index", "missing_body", "duplicate_node", "wrong_xyz"])
def test_numeric_mesh_catalog_rejects_unverified_names_indices_and_coordinates(tmp_path, failure):
    _, mesh = mesh_fixture(tmp_path)
    raw = native_fixture(mesh)
    native = NumericNativeMesh(raw)
    tables = raw["tables"]
    if failure == "invented_node_prefix":
        tables["DEPL"]["NOEUD"][0] = "N27"
    elif failure == "invented_element_prefix":
        tables["SIEF_ELGA"]["MAILLE"][0] = "M1"
    elif failure == "wrong_node_index":
        tables["DEPL"]["NOEUD"][0] = "123456"
    elif failure == "wrong_body_index":
        tables["SIEF_ELGA"]["MAILLE"][0] = "123456"
    elif failure == "missing_body":
        tables["SIEF_ELGA"]["MAILLE"] = ["1"] * len(tables["SIEF_ELGA"]["MAILLE"])
    elif failure == "duplicate_node":
        tables["DEPL"]["NOEUD"][1] = tables["DEPL"]["NOEUD"][0]
    else:
        tables["DEPL"]["COOR_X"][0] += .01
    with pytest.raises(ValueError):
        _native_mesh_catalog(native, tables, raw["order"])


def test_coordinate_bijection_handles_roundoff_in_tied_sort_axes_and_permutations():
    native = [[9., 0., 0.], [9., 2.00071374070477, 0.], [9., 0., 1.]]
    source = [[8.999999999999998, 2.000713740704772, 0.], [9., 0., 0.], [9., 0., 1.]]
    assert not all(first == second for first, second in zip(sorted(native), sorted(source)))
    assert _coordinates_equal(native, source)
    assert _coordinates_equal(list(reversed(source)), native)


@pytest.mark.parametrize("a,b", [
    ([[0., 0., 0.]], [[1.01e-12, 0., 0.]]),
    ([[1e6, 0., 0.]], [[1e6 + 1.01e-6, 0., 0.]]),
    ([[1e6, 0., 0.]], [[1e6, 1.01e-12, 0.]]),
    ([[0., 0., 0.], [0., 0., 0.]], [[0., 0., 0.], [0., 0., 0.]]),
    ([[0., 0., 0.], [0., 0., 0.]], [[0., 0., 0.], [1., 0., 0.]]),
    ([[0., 0., 0.], [2., 0., 0.]], [[-.75e-12, 0., 0.], [.75e-12, 0., 0.]]),
    ([[0., 0., 0.]], [[0., 0., 0.], [1., 0., 0.]]),
])
def test_coordinate_bijection_rejects_drift_duplicates_ambiguity_and_size_mismatch(a, b):
    assert not _coordinates_equal(a, b)
    assert not _coordinates_equal(b, a)


def test_coordinate_bijection_preserves_both_original_component_tolerances():
    assert _coordinates_equal([[0., 0., 0.]], [[.99e-12, -.99e-12, .99e-12]])
    assert _coordinates_equal([[1e6, 0., 0.]], [[1e6 + .99e-6, .99e-12, 0.]])


def test_nonfinite_raw_serialization_keeps_explicit_observation_tokens():
    raw = {"component": [1., None, float("nan"), float("inf")]}
    safe = _json_safe(raw)
    assert safe["component"] == [1., None, {"invalid_numeric": "nan"}, {"invalid_numeric": "inf"}]
    assert json.loads(json.dumps(safe, allow_nan=False)) == safe


@pytest.mark.parametrize("matching_hash", [True, False])
def test_run_aster_deferred_mesh_link_is_checked_after_initialization(tmp_path, monkeypatch, matching_hash):
    """Reproduce the real runner's deferred --link lifecycle without Code_Aster."""
    command_module = types.ModuleType("code_aster.Commands")
    syntax_module = types.ModuleType("code_aster.Cata.Syntax")
    syntax_module._F = lambda **kwargs: kwargs
    call_order = []
    actual_mesh = b"MOCK deferred unit 20 file"

    class StopBeforeRealSolver(RuntimeError):
        pass

    def initialize():
        call_order.append("DEBUT")
        (tmp_path / "fort.20").write_bytes(actual_mesh)

    def mesh_reader(**kwargs):
        call_order.append("LIRE_MAILLAGE")
        raise StopBeforeRealSolver("Unit 20 verified; no real solver is installed or executed")

    for name in ("AFFE_CHAR_MECA", "AFFE_MATERIAU", "AFFE_MODELE", "CALC_CHAMP", "CREA_TABLE",
                 "DEFI_GROUP", "DEFI_MATERIAU", "FIN", "IMPR_RESU", "MECA_STATIQUE", "POST_RELEVE_T"):
        setattr(command_module, name, lambda *a, **kw: pytest.fail("No actual solver command may run"))
    command_module.DEBUT = initialize
    command_module.LIRE_MAILLAGE = mesh_reader
    monkeypatch.setitem(sys.modules, "code_aster", types.ModuleType("code_aster"))
    monkeypatch.setitem(sys.modules, "code_aster.Commands", command_module)
    monkeypatch.setitem(sys.modules, "code_aster.Cata", types.ModuleType("code_aster.Cata"))
    monkeypatch.setitem(sys.modules, "code_aster.Cata.Syntax", syntax_module)
    monkeypatch.setattr("caelab.adapters.codeaster_worker._runtime_versions", lambda: ({"code_aster": "17.4.0"}, {}))
    monkeypatch.chdir(tmp_path)
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"settings": settings(),
                                     "mesh_sha256": hashlib.sha256(actual_mesh).hexdigest()
                                     if matching_hash else "unexpected mesh"}))
    expected = StopBeforeRealSolver if matching_hash else RuntimeError
    message = "Unit 20 verified" if matching_hash else "differs from the checked"
    with pytest.raises(expected, match=message):
        solve_level(str(input_file))
    assert call_order == ["DEBUT", "LIRE_MAILLAGE"] if matching_hash else call_order == ["DEBUT"]


@pytest.mark.parametrize("failure", ["wrong_group", "source_drift"])
def test_native_import_guard_blocks_solver_commands_and_preserves_failure_evidence(tmp_path, monkeypatch, failure):
    path, source = mesh_fixture(tmp_path)
    raw = native_fixture(source)
    native = GuardNativeMesh(source, raw)
    if failure == "wrong_group":
        native.catalog["group_node_ids"]["X0"] = sorted(set(native.catalog["group_node_ids"]["X0"]) | set(native.catalog["group_node_ids"]["XL"]))
    command_module = types.ModuleType("code_aster.Commands")
    syntax_module = types.ModuleType("code_aster.Cata.Syntax")
    syntax_module._F = lambda **kwargs: kwargs
    calls = []

    def initialize():
        calls.append("DEBUT")
        (tmp_path / "fort.20").write_bytes(path.read_bytes())

    def reader(**kwargs):
        calls.append("LIRE_MAILLAGE")
        return native

    for name in ("AFFE_CHAR_MECA", "AFFE_MATERIAU", "AFFE_MODELE", "CALC_CHAMP", "CREA_TABLE",
                 "DEFI_GROUP", "DEFI_MATERIAU", "FIN", "IMPR_RESU", "MECA_STATIQUE", "POST_RELEVE_T"):
        setattr(command_module, name, lambda *a, **kw: pytest.fail("Invalid native import must block every solver/model command"))
    command_module.DEBUT = initialize
    command_module.LIRE_MAILLAGE = reader
    monkeypatch.setitem(sys.modules, "code_aster", types.ModuleType("code_aster"))
    monkeypatch.setitem(sys.modules, "code_aster.Commands", command_module)
    monkeypatch.setitem(sys.modules, "code_aster.Cata", types.ModuleType("code_aster.Cata"))
    monkeypatch.setitem(sys.modules, "code_aster.Cata.Syntax", syntax_module)
    monkeypatch.setattr("caelab.adapters.codeaster_worker._runtime_versions",
                        lambda: ({"code_aster": "17.4.0"}, {"version": "17.4.0"}))
    monkeypatch.chdir(tmp_path)
    expected_file = tmp_path / "expected_mesh.json"
    expected_file.write_text(json.dumps(_expected_mesh(source)))
    expected_sha = hashlib.sha256(expected_file.read_bytes()).hexdigest()
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"settings": settings(), "mesh_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                     "expected_mesh_sha256": expected_sha}))
    if failure == "source_drift":
        expected_file.write_text(expected_file.read_text() + "\n")
    with pytest.raises(RuntimeError, match="pre-MECA guard rejected"):
        solve_level(str(input_file))
    assert calls == ["DEBUT", "LIRE_MAILLAGE"]
    failed = json.loads((tmp_path / "native_mesh_checks.json").read_text())
    assert failed["status"] == "FAIL" and failed["solver_status"] == "NOT_RUN"
    assert failed["expected_mesh_sha256"] == expected_sha
    assert not (tmp_path / "worker_result.json").exists()


def configure_runtime(tmp_path, monkeypatch):
    image = tmp_path / "vendor.sif"
    image.write_bytes(b"MOCK container identity, not a real image")
    monkeypatch.setenv("CAELAB_CODEASTER_IMAGE", str(image))
    monkeypatch.setenv("CAELAB_CODEASTER_IMAGE_SHA256", hashlib.sha256(image.read_bytes()).hexdigest())
    monkeypatch.setattr("caelab.adapters.codeaster_elasticity.shutil.which",
                        lambda name: {"gmsh": "/mock/gmsh", "prlimit": "/mock/prlimit"}.get(name, "/mock/singularity"))
    return image


def mock_processes(monkeypatch, mutate=None, *, mesh_text=None):
    calls = []

    def process(command, *, cwd, capture_output, text, timeout, check):
        calls.append(command)
        assert capture_output and text and not check and timeout <= 180
        level = Path(cwd)
        if command[1] == "-version":
            return subprocess.CompletedProcess(command, 0, "", "4.12.1\n")
        if command[1] == "--version":
            return subprocess.CompletedProcess(command, 0, "singularity-ce version 4.1.1\n", "")
        if command[0] == "/mock/prlimit":
            assert command[1:5] == ["--as=2147483648", "--cpu=120", "--", "/mock/gmsh"]
            (level / "mesh.msh").write_text(mesh_text or brick_msh())
        else:
            assert command[1] == "exec" and "--cleanenv" in command and "--containall" in command
            assert "--no-home" in command and CONTAINER_SCRIPT in command
            assert command[-1] == f"/work/{level.name}/model.export"
            assert "P time_limit 120" in (level / "model.export").read_text()
            assert "P memory_limit 1024" in (level / "model.export").read_text()
            binds = [command[index + 1] for index, value in enumerate(command) if value == "--bind"]
            scratch = (level.parent / "scratch" / level.name).resolve()
            assert str(scratch) + ":/tmp:rw" in binds
            assert str((level.parent / "preferences").resolve()) + ":" + str(Path.home()) + ":rw" in binds
            assert scratch.is_dir()
            database = scratch / "run_aster" / "proc.0"
            database.mkdir(parents=True)
            (database / "glob.1").write_bytes(b"MOCK native scratch database")
            mesh = parse_gmsh_mesh(level / "mesh.msh", settings()["dimensions_mm"])
            raw = native_fixture(mesh)
            raw["input_sha256"] = hashlib.sha256((level / "input.json").read_bytes()).hexdigest()
            raw["mesh_input_sha256"] = hashlib.sha256((level / "mesh.msh").read_bytes()).hexdigest()
            native_checks = validate_native_mesh(GuardNativeMesh(mesh, raw), json.loads((level / "expected_mesh.json").read_text()))
            native_checks.update({"expected_mesh_sha256": hashlib.sha256((level / "expected_mesh.json").read_bytes()).hexdigest(),
                                  "checked_msh_sha256": raw["mesh_input_sha256"], "support_union_verified": True})
            raw["native_mesh_checks"] = native_checks
            (level / "native_mesh_checks.json").write_text(json.dumps(native_checks))
            if mutate:
                mutate(raw, level)
            (level / "worker_result.json").write_text(json.dumps(raw))
            (level / "results.med").write_bytes(b"MOCK native MED artifact; not solver evidence")
        return subprocess.CompletedProcess(command, 0, "MOCK successful process contract\n", "")

    monkeypatch.setattr("caelab.adapters.codeaster_elasticity.subprocess.run", process)
    return calls


@pytest.mark.parametrize("path,value", [
    (("case",), "unknown"), (("dimensions_mm",), [40., 10.]),
    (("dimensions_mm",), [40., True, 10.]), (("traction_mpa",), 0.),
    (("material", "poisson_ratio"), .5), (("material", "youngs_modulus_mpa"), float("inf")),
    (("mesh_sizes_mm",), [3., 5.]), (("limits", "stress_relative"), 0.),
])
def test_input_preflight_blocks_every_external_command(tmp_path, monkeypatch, path, value):
    monkeypatch.setattr("caelab.adapters.codeaster_elasticity.subprocess.run",
                        lambda *a, **kw: pytest.fail("Invalid settings must block process execution"))
    request = settings()
    target = request
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    result = CodeAsterElasticityAdapter().solve(tmp_path / "simulation", request)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert result["metrics"] == {} and result["converged"] is None
    assert (tmp_path / "simulation/analysis_raw.json").is_file()


def test_unknown_settings_cannot_control_backend_command(tmp_path, monkeypatch):
    monkeypatch.setattr("caelab.adapters.codeaster_elasticity.subprocess.run",
                        lambda *a, **kw: pytest.fail("Unknown settings must block processes"))
    request = settings()
    request["script"] = "arbitrary shell"
    result = CodeAsterElasticityAdapter().solve(tmp_path / "simulation", request)
    assert result["checks"][-1]["code"] == "elasticity_preflight"


@pytest.mark.parametrize("sizes", [[1e-299, 1e-300], [.8, .5], [.25, .2]])
def test_mesh_workload_budget_blocks_mesher_before_any_external_command(tmp_path, monkeypatch, sizes):
    monkeypatch.setattr("caelab.adapters.codeaster_elasticity.subprocess.run",
                        lambda *a, **kw: pytest.fail("Unbounded mesh workload must block every external command"))
    request = settings()
    request["mesh_sizes_mm"] = sizes
    original = deepcopy(request)
    output = tmp_path / "simulation"
    result = CodeAsterElasticityAdapter().solve(output, request)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert result["checks"][-1]["code"] == "mesh_workload_preflight"
    assert request == original
    assert json.loads((output / "input.json").read_text())["limits"] == request["limits"]
    assert not (output / "level_0").exists()


def test_scratch_cleanup_rejects_external_or_symlink_targets(tmp_path):
    output = tmp_path / "simulation"
    (output / "scratch").mkdir(parents=True)
    foreign = tmp_path / "level_0"
    foreign.mkdir()
    retained = foreign / "glob.1"
    retained.write_bytes(b"Must not be deleted")
    with pytest.raises(RuntimeError, match="Refusing cleanup"):
        _cleanup_scratch(output, foreign)
    linked = output / "scratch/level_0"
    linked.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(RuntimeError, match="Refusing cleanup"):
        _cleanup_scratch(output, linked)
    assert retained.read_bytes() == b"Must not be deleted"


@pytest.mark.parametrize("stage", ["before_execution", "during_worker", "copied_source", "during_assessment"])
def test_domain_source_drift_cannot_be_published_as_a_numerical_outcome(tmp_path, monkeypatch, stage):
    configure_runtime(tmp_path, monkeypatch)
    domain_source = tmp_path / "reference.py"
    domain_source.write_bytes(adapter_module._DOMAIN_SOURCE_BYTES)
    monkeypatch.setattr(adapter_module, "_DOMAIN_SOURCE", domain_source)
    output = tmp_path / "simulation"

    def drift_source(raw=None, level=None):
        target = output / "domain_reference.py" if stage == "copied_source" else domain_source
        target.write_bytes(target.read_bytes() + b"\n# MOCK source drift during process regression\n")

    calls = mock_processes(monkeypatch, drift_source if stage in ("during_worker", "copied_source") else None)
    if stage == "before_execution":
        drift_source()
    elif stage == "during_assessment":
        original_assess = adapter_module.assess

        def changed_assess(*args):
            result = original_assess(*args)
            drift_source()
            return result

        monkeypatch.setattr(adapter_module, "assess", changed_assess)
    with pytest.raises(RuntimeError, match="domain source changed"):
        CodeAsterElasticityAdapter().solve(output, settings())
    assert not (output / "analysis_raw.json").exists()
    assert (output / "domain_reference.py").is_file()
    if stage == "before_execution":
        assert not calls
    elif stage in ("during_worker", "copied_source"):
        assert sum(command[1] == "exec" for command in calls) == 1
        assert (output / "level_0/parsed_fields.json").is_file()
        assert (output / "scratch/level_0/run_aster/proc.0/glob.1").is_file()


def test_existing_evidence_is_not_overwritten(tmp_path):
    output = tmp_path / "simulation"
    output.mkdir()
    (output / "retained.med").write_bytes(b"old native evidence")
    with pytest.raises(ValueError, match="cannot be overwritten"):
        CodeAsterElasticityAdapter().solve(output, settings())
    assert list(output.iterdir()) == [output / "retained.med"]


@pytest.mark.parametrize("failure", ["missing_image", "image_drift", "missing_runtime"])
def test_missing_or_drifted_runtime_does_not_become_numerical_success(tmp_path, monkeypatch, failure):
    image = configure_runtime(tmp_path, monkeypatch)
    if failure == "missing_image":
        image.unlink()
    elif failure == "image_drift":
        image.write_bytes(b"drifted container")
    else:
        monkeypatch.setattr("caelab.adapters.codeaster_elasticity.shutil.which", lambda _: None)
    monkeypatch.setattr("caelab.adapters.codeaster_elasticity.subprocess.run",
                        lambda *a, **kw: pytest.fail("Runtime preflight must block processes"))
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError):
        CodeAsterElasticityAdapter().solve(output, settings())
    assert (output / "runtime_preflight.stderr.log").is_file()
    assert not (output / "analysis_raw.json").exists()
    assert (output / "codeaster_worker.py").is_file()


def test_runtime_image_drift_mid_execution_preserves_completed_level(tmp_path, monkeypatch):
    image = configure_runtime(tmp_path, monkeypatch)

    def drift(raw, level):
        image.write_bytes(b"changed while a process ran")

    calls = mock_processes(monkeypatch, drift)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError, match="image changed"):
        CodeAsterElasticityAdapter().solve(output, settings())
    assert sum(command[1] == "exec" for command in calls) == 1
    assert (output / "level_0/worker_result.json").is_file()
    assert (output / "level_0/parsed_fields.json").is_file()
    assert not (output / "analysis_raw.json").exists()


def test_successful_process_contract_keeps_settings_provenance_and_unknowns(tmp_path, monkeypatch):
    image = configure_runtime(tmp_path, monkeypatch)
    request = settings()
    before = deepcopy(request)
    calls = mock_processes(monkeypatch)
    output = tmp_path / "simulation"
    adapter = CodeAsterElasticityAdapter()
    result = adapter.solve(output, request)
    assert request == before
    assert result["status"] == "COMPLETED" and result["converged"] is True
    assert result["provenance"]["image_sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()
    assert result["provenance"]["oci_manifest_sha256"] == OCI_MANIFEST_SHA256
    assert result["raw_result"] == "simulation/analysis_raw.json"
    assert all(metric["valid"] for metric in result["metrics"].values())
    assert result["metrics"]["reaction_x"]["value"] == pytest.approx(-1000.)
    assert "model_qualification" in result["pending_validations"] and "static_strength" in result["pending_validations"]
    assert result["provenance"]["solver"]["measured_linear_residual"] is None
    assert "compatibility patch" in result["provenance"]["distribution"]
    assert result["provenance"]["domain_plugin"]["source_sha256"] == hashlib.sha256((output / "domain_reference.py").read_bytes()).hexdigest()
    assert result["provenance"]["domain_plugin"]["version_status"] == "UNKNOWN"
    assert not list((output / "scratch").iterdir())
    assert all(json.loads((output / f"level_{index}/scratch.json").read_text())["retention_status"] ==
               "REMOVED_AFTER_VALID_EXTRACTION" for index in (0, 1))
    assert adapter.describe_model(request)["model"]["geometry"]["origin"] == [0., 0., 0.]
    # Meshes are all checked before any solver runs.
    assert [command[0] == "/mock/prlimit" for command in calls[2:]] == [True, True, False, False]
    assert json.loads((output / "analysis_raw.json").read_text())["metrics"] == result["metrics"]


def test_process_field_gate_accepts_unique_harmless_roundoff_on_tied_coordinate_axes(tmp_path, monkeypatch):
    configure_runtime(tmp_path, monkeypatch)

    def roundoff(raw, level):
        node = next(item for item in raw["mesh"]["nodes"] if item["coordinates_mm"] == [20., 0., 0.])
        node["coordinates_mm"][0] += 1e-14
        for field in ("DEPL", "REAC_NODA"):
            table = raw["tables"][field]
            row = next(index for index, value in enumerate(table["NOEUD"]) if int(value) == node["node_id"])
            table["COOR_X"][row] = node["coordinates_mm"][0]

    mock_processes(monkeypatch, roundoff)
    result = CodeAsterElasticityAdapter().solve(tmp_path / "simulation", settings())
    assert result["status"] == "COMPLETED"
    assert all(metric["valid"] for metric in result["metrics"].values())


def test_mesh_failure_blocks_all_solver_execution(tmp_path, monkeypatch):
    configure_runtime(tmp_path, monkeypatch)
    calls = mock_processes(monkeypatch, mesh_text=brick_msh().replace('2 1003 "XL"', '2 1003 "WRONG"'))
    result = CodeAsterElasticityAdapter().solve(tmp_path / "simulation", settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert not any(command[1] == "exec" for command in calls)
    assert (tmp_path / "simulation/level_0/mesh.msh").is_file()


def test_numerical_failure_preserves_actual_field_values_and_invalid_metrics(tmp_path, monkeypatch):
    configure_runtime(tmp_path, monkeypatch)

    def wrong_stress(raw, level):
        raw["tables"]["SIEF_ELGA"]["SIXX"][0] = 9.

    mock_processes(monkeypatch, wrong_stress)
    output = tmp_path / "simulation"
    result = CodeAsterElasticityAdapter().solve(output, settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED"
    assert result["converged"] is True
    assert result["mesh_records"][0]["stresses_mpa"][0][0] == 9.
    assert all(not metric["valid"] and metric["reason"] for metric in result["metrics"].values())
    assert result["metrics"]["stress_relative_error"]["value"] == .1
    assert (output / "level_0/results.med").is_file()
    assert not list((output / "scratch").iterdir())
    assert json.loads((output / "input.json").read_text())["limits"] == settings()["limits"]


@pytest.mark.parametrize("failure", ["nonzero", "timeout", "malformed_field", "wrong_version", "outside_point", "mesh_drift", "expected_mesh_drift", "missing_native_guard", "input_drift"])
def test_worker_execution_and_partial_fields_fail_without_numerical_outcome(tmp_path, monkeypatch, failure):
    configure_runtime(tmp_path, monkeypatch)

    def mutation(raw, level):
        if failure == "malformed_field":
            raw["tables"]["SIEF_ELGA"]["SIXY"][0] = None
        elif failure == "wrong_version":
            raw["versions"]["code_aster"] = "17.6.0"
        elif failure == "outside_point":
            raw["tables"]["SIEF_ELGA"]["COOR_X"][0] = 1000.
        elif failure == "mesh_drift":
            raw["mesh_input_sha256"] = "unexpected mesh hash"
        elif failure == "expected_mesh_drift":
            expected_file = level / "expected_mesh.json"
            expected_file.write_text(expected_file.read_text() + "\n")
        elif failure == "missing_native_guard":
            del raw["native_mesh_checks"]
        elif failure == "input_drift":
            input_file = level / "input.json"
            input_file.write_text(input_file.read_text() + "\n")

    mock_processes(monkeypatch, mutation)
    original = subprocess.run

    def failure_process(command, **kwargs):
        if command[1] == "exec" and failure in ("nonzero", "timeout"):
            scratch = Path(kwargs["cwd"]).parent / "scratch" / Path(kwargs["cwd"]).name
            (scratch / "glob.1").write_bytes(b"MOCK incomplete native database retained on failure")
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, 180, output=b"solver started\n", stderr=b"partial log\n")
            return subprocess.CompletedProcess(command, 4, "raw stdout\n", "runtime failure\n")
        return original(command, **kwargs)

    monkeypatch.setattr("caelab.adapters.codeaster_elasticity.subprocess.run", failure_process)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError):
        CodeAsterElasticityAdapter().solve(output, settings())
    assert not (output / "analysis_raw.json").exists()
    assert (output / "level_0/solver.stdout.log").is_file()
    assert (output / "level_0/solver.stderr.log").is_file()
    assert (output / "level_0/model.comm").is_file() and (output / "level_0/model.export").is_file()
    assert (output / "scratch/level_0").is_dir()
    assert any((output / "scratch/level_0").rglob("glob.1"))
    if failure == "malformed_field":
        assert json.loads((output / "level_0/worker_result.json").read_text())["tables"]["SIEF_ELGA"]["SIXY"][0] is None


def test_generated_model_uses_coordinate_constraints_and_fixed_shell_code():
    source = gmsh_source(settings(), 5.)
    assert 'Physical Volume("BODY",1001)' in source
    assert "Mesh.SecondOrderLinear=1" in source and "Mesh.MshFileVersion=2.2" in source
    assert CONTAINER_SCRIPT == 'source /opt/activate.sh; exec run_aster "$1"'
