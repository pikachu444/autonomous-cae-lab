"""Cold beam syntax/parser/identity controls; no native solver is invoked.

Mock fields are explicitly transport fixtures, never native qualification.
The independent Domain suite owns scientific oracle/verdict tests.
"""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import types

import pytest

from caelab.adapters import codeaster_geometric as adapter
from caelab.adapters import codeaster_geometric_worker as worker
from caelab.storage import load_json, save_json
from caelab.execution_control import ExecutionCancelled, ExecutionCleanupFailed
from plugins.geometric_nonlinearity import reference as domain


class NativeMesh:
    """Small exact Mesh API fixture, with optionally permuted native indices."""
    def __init__(self, expected, permutation=None):
        self.expected = expected
        self.permutation = permutation or list(range(len(expected["nodes"])))
        self.source_ids = [expected["nodes"][index]["node_id"] for index in self.permutation]
        inverse = {source: index for index, source in enumerate(self.source_ids)}
        self.points = [expected["nodes"][index]["coordinates_mm"] for index in self.permutation]
        self.cells = [[inverse[node] for node in cell["node_ids"]] for cell in expected["beam_elements"]]
        self.groups = {name: [inverse[node] for node in nodes] for name, nodes in expected["group_node_ids"].items()}

    def getCoordinates(self): return self
    def toNumpy(self): return self
    def tolist(self): return deepcopy(self.points)
    def getNodes(self, group=None): return list(range(len(self.points))) if group is None else self.groups[group]
    def getNumberOfNodes(self): return len(self.points)
    def getNumberOfCells(self): return len(self.cells)
    def getConnectivity(self): return self.cells
    def getCellTypeName(self, index): return "SEG2"
    def getCells(self, group): return list(range(len(self.cells))) if group == "BEAM" else []
    def getGroupsOfCells(self): return ["BEAM"]
    def getGroupsOfNodes(self): return list(self.groups)


def raw_fixture(count=8, permutation=None):
    settings = domain.default_settings()
    expected = worker.beam_mesh(settings["beam"]["length_mm"], count)
    guard, catalog = worker.validate_native_mesh(NativeMesh(expected, permutation), expected)
    raw = {"schema_version": "1", "solver_status": "COMPLETED", "converged": True,
           "mesh": catalog, "nonlinear_policy": deepcopy(worker.NONLINEAR_POLICY),
           "field_semantics": deepcopy(worker.FIELD_SEMANTICS), "states": [],
           "versions": {"code_aster": "17.4.0", "python": "MOCK_PYTHON", "numpy": "MOCK_NUMPY"},
           "code_aster_runtime": {"version": "17.4.0", "branch": "MOCK_COLD_NOT_NATIVE", "parentid": "fixture"},
           "native_mesh_checks": guard,
           "native_material": {"ELAS": {"E": settings["material"]["youngs_modulus_mpa"], "NU": settings["material"]["poisson_ratio"]}},
           "native_section": worker.native_section(settings), "numerical_libraries": None,
           "native_global_energy": {"status": "UNKNOWN", "reason": "Cold fixture is not native evidence"},
           "measured_linear_residual": None}
    times = settings["history"]["times_s"]
    orders = [2 * index for index in range(len(times))]
    raw["available_orders"] = list(reversed(orders))
    raw["access_parameters"] = {"NUME_ORDRE": orders, "INST": times}
    coordinates = {item["node_id"]: item["coordinates_mm"] for item in catalog["nodes"]}
    clamp = catalog["group_node_ids"]["CLAMP"][0]
    young = settings["material"]["youngs_modulus_mpa"]
    iz = settings["beam"]["width_z_mm"] * settings["beam"]["height_y_mm"]**3 / 12
    for order, instant, moment in zip(orders, times, settings["history"]["moments_n_mm"]):
        kappa = moment / (young * iz)
        tables = {}
        for name in ("DEPL", "REAC_NODA"):
            rows = {"NOEUD": [], "NUME_ORDRE": [], **{key: [] for key in (*worker.COORDINATE_COMPONENTS, *worker.DOF_COMPONENTS)}}
            for node in reversed(catalog["nodes"]):
                identifier, xyz = node["node_id"], node["coordinates_mm"]
                x = xyz[0]
                if name == "DEPL":
                    displacement_x = math.sin(kappa*x) / kappa - x if kappa else 0.
                    displacement_y = 2 * math.sin(kappa*x/2)**2 / kappa if kappa else 0.
                    # A declared nonzero O(h^2) cold error exercises all-pair
                    # mesh-rate transport, not a fabricated native solution.
                    displacement_y += (0.1 * (8/count)**2 * x / settings["beam"]["length_mm"]) if moment else 0.
                    values = [displacement_x, displacement_y, 0., 0., 0., kappa*x]
                else:
                    values = [0., 0., 0., 0., 0., -moment if identifier == clamp else 0.]
                rows["NOEUD"].append(f" {identifier}")
                rows["NUME_ORDRE"].append(order)
                for key, value in zip(worker.COORDINATE_COMPONENTS, xyz): rows[key].append(value)
                for key, value in zip(worker.DOF_COMPONENTS, values): rows[key].append(value)
            tables[name] = rows
            rows["RESULTAT"] = ["MOCK_RESULT"] * len(rows["NOEUD"])
            rows["NOM_CHAM"] = [name] * len(rows["NOEUD"])
        for name, components in (("SIEF_ELGA", worker.WRENCH_COMPONENTS), ("VARI_ELGA", worker.CURVATURE_COMPONENTS)):
            rows = {key: [] for key in ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", *worker.COORDINATE_COMPONENTS, *components)}
            for cell in reversed(catalog["beam_elements"]):
                pair = cell["node_ids"]
                midpoint = [(coordinates[pair[0]][axis] + coordinates[pair[1]][axis])/2 for axis in range(3)]
                rows["MAILLE"].append(f" {cell['element_id']}")
                rows["POINT"].append(1)
                rows["SOUS_POINT"].append(1)
                rows["NUME_ORDRE"].append(order)
                for key, value in zip(worker.COORDINATE_COMPONENTS, midpoint): rows[key].append(value)
                values = [0., 0., 0., 0., 0., moment] if name == "SIEF_ELGA" else [0., 0., kappa]
                for key, value in zip(components, values): rows[key].append(value)
            tables[name] = rows
            rows["RESULTAT"] = ["MOCK_RESULT"] * len(rows["MAILLE"])
            rows["NOM_CHAM"] = [name] * len(rows["MAILLE"])
        tables["BOUNDARY_WRENCHES"] = {"INTITULE": ["CLAMP", "SUPPORT"], "NUME_ORDRE": [order]*2, "INST": [instant]*2,
                                     **{key: [0., 0.] for key in worker.COMBINED_COMPONENTS}}
        tables["BOUNDARY_WRENCHES"]["MOMENT_Z"] = [-moment, -moment]
        raw["states"].append({"order": order, "time_s": instant, "tables": tables})
    return raw


def convergence_fixture():
    return "\n".join(f"Instant de calcul: {instant:.12e}\n"
        "|                 | RESI_GLOB_RELA | RESI_GLOB_MAXI | OPTION |\n"
        "| 0             X | 1.0          X | 1.0          X | TANG   |\n"
        "| 1               | 1.0E-13        | 1.0E-11        | TANG   |\n"
        "Le résidu de type <RESI_GLOB_RELA> vaut 1.000000000000e-13 au noeud\n"
        "Le résidu de type <RESI_GLOB_MAXI> vaut 1.000000000000e-11 au noeud"
        for instant in domain.default_settings()["history"]["times_s"][1:])


def measure_fixture():
    return ", ,Count,Time,Count, ,Memory,\n,INST,Newt_Iter,Solve,Solve,State,VmPeak,\n" + "\n".join(
        f",{instant:.5E},2,1.0E-3,2,CONV,793," for instant in domain.default_settings()["history"]["times_s"][1:])


def write_native_fixture(level, settings, budgets, raw=None):
    config = load_json(level / "input.json")
    expected = load_json(level / "expected_mesh.json")
    raw = raw or raw_fixture(config["element_count"])
    raw.update(input_sha256=adapter.elastic._sha256(level / "input.json"), mesh_input_sha256=config["mesh_sha256"])
    raw["native_mesh_checks"].update(expected_mesh_sha256=config["expected_mesh_sha256"], checked_mail_sha256=config["mesh_sha256"])
    for name, value in (("worker_result.json", raw), ("native_mesh_checks.json", raw["native_mesh_checks"]),
                        ("mesh_catalog.json", raw["mesh"]), ("native_material.json", raw["native_material"]),
                        ("native_section.json", raw["native_section"]), ("nonlinear_policy.json", raw["nonlinear_policy"]),
                        ("runtime.json", {"versions": raw["versions"], "code_aster_runtime": raw["code_aster_runtime"]}),
                        ("native_access_parameters.json", {"available_orders": raw["available_orders"], "access_parameters": raw["access_parameters"]})):
        save_json(level / name, value)
    for state in raw["states"]:
        for name, table in state["tables"].items():
            save_json(level / f"order_{state['order']}_{name.lower()}.table.json", table)
    (level / "results.med").write_bytes(b"MOCK_UNSOLVED_MED_NOT_NATIVE")
    (level / "aster.mess").write_text(convergence_fixture(), encoding="utf-8")
    (level / "aster.resu").write_text("MOCK raw native report", encoding="utf-8")
    (level / "convergence.measure").write_text(measure_fixture(), encoding="utf-8")
    return raw


def mock_execution(monkeypatch, tmp_path, *, solver=None):
    image = tmp_path / "mock.sif"
    image.write_bytes(b"MOCK_NOT_VENDOR_IMAGE")
    monkeypatch.setattr(adapter.elastic, "_image_identity", lambda output: (image, adapter.elastic._sha256(image), "mock-container", "unused-gmsh", "unused-prlimit"))
    calls = []
    def process(argv, folder, label, *, timeout=None):
        calls.append({"argv": argv, "folder": folder, "label": label, "timeout": timeout})
        if label == "solver":
            if solver:
                solver(folder, calls)
            else:
                write_native_fixture(folder, load_json(folder / "input.json")["settings"], adapter.elastic.process_budgets())
        return "MOCK_COLD_NOT_NATIVE"
    monkeypatch.setattr(adapter.elastic, "_process", process)
    return image, calls


def test_complete_six_dof_mixed_units_signed_global_curvature_and_actual_zero_archive():
    raw = raw_fixture()
    result = worker.parse_history_tables(raw, domain.default_settings()["history"]["times_s"])
    assert len(result["states"]) == 5 and result["states"][0]["actual_result_order"] == 0
    assert result["states"][2]["actual_result_order"] == 4 and result["states"][2]["time_s"] == 2
    assert result["states"][-1]["rotations_rad"][-1] == [0., 0., 1.]
    assert result["states"][-1]["nodal_moments_n_mm"][0] == [0., 0., -140.]
    assert result["states"][-1]["section_wrenches"][0] == [0., 0., 0., 0., 0., 140.]
    assert result["states"][-1]["curvatures_per_mm"][0] == [0., 0., .001]
    assert result["states"][0]["curvatures_per_mm"] == [[0., 0., 0.]] * 8
    assert result["field_semantics"]["reaction_units"][-1] == "N.mm"
    assert result["field_semantics"]["displacement_units"][-1] == "rad"


def test_native_zero_index_and_permuted_source_identity_are_not_assumed_to_be_source_order():
    raw = raw_fixture(permutation=list(reversed(range(9))))
    result = worker.parse_history_tables(raw, domain.default_settings()["history"]["times_s"])
    assert raw["native_mesh_checks"]["source_node_ids_by_native_index"] == list(reversed(range(1, 10)))
    assert result["segments"][0] == [9, 8] and result["group_node_ids"]["CLAMP"] == [9]
    assert result["states"][-1]["nodal_moments_n_mm"][-1] == [0., 0., -140.]


def test_planar_support_union_component_masks_and_combined_moment_include_lever_arm():
    raw = raw_fixture()
    state = raw["states"][-1]
    table = state["tables"]["REAC_NODA"]
    index = [int(value) for value in table["NOEUD"]].index(2)
    table["DZ"][index] = 5.
    combined = state["tables"]["BOUNDARY_WRENCHES"]
    combined["RESULT_Z"][1] = 5.
    combined["MOMENT_Y"][1] = -625.  # original x125 * force_z5
    result = worker.parse_history_tables(raw, domain.default_settings()["history"]["times_s"])
    assert result["support_node_ids"] == list(range(1, 10))
    assert result["support_dof_masks"]["2"] == [False, False, True, False, False, False]
    assert result["states"][-1]["clamp_wrench"] == [0., 0., 0., 0., 0., -140.]
    assert result["states"][-1]["masked_support_wrench"] == [0., 0., 5., 0., -625., -140.]


@pytest.mark.parametrize("mutation", [
    lambda raw: raw["states"].pop(0),
    lambda raw: raw["available_orders"].pop(0),
    lambda raw: raw["access_parameters"]["INST"].__setitem__(2, 2.1),
    lambda raw: raw["states"][1].__setitem__("order", 1),
    lambda raw: raw["states"][1]["tables"]["DEPL"].pop("DRZ"),
    lambda raw: raw["states"][1]["tables"]["DEPL"].pop("NOM_CHAM"),
    lambda raw: raw["states"][1]["tables"]["DEPL"]["NOM_CHAM"].__setitem__(0, "REAC_NODA"),
    lambda raw: raw["states"][1]["tables"]["SIEF_ELGA"].__setitem__("RESULTAT", ["FOREIGN_RESULT"] * 8),
    lambda raw: raw["states"][1]["tables"]["REAC_NODA"].pop("DRY"),
    lambda raw: raw["states"][1]["tables"]["DEPL"]["NOEUD"].__setitem__(0, "1"),
    lambda raw: raw["states"][1]["tables"]["DEPL"]["DRZ"].__setitem__(0, float("nan")),
    lambda raw: raw["states"][1]["tables"]["DEPL"]["COOR_X"].__setitem__(0, 999.),
    lambda raw: raw["states"][1]["tables"]["SIEF_ELGA"]["POINT"].__setitem__(0, 2),
    lambda raw: raw["states"][1]["tables"]["VARI_ELGA"]["SOUS_POINT"].__setitem__(0, 2),
    lambda raw: raw["states"][1]["tables"]["SIEF_ELGA"]["MAILLE"].__setitem__(0, "1"),
    lambda raw: raw["states"][1]["tables"]["SIEF_ELGA"].pop("MFZ"),
    lambda raw: raw["states"][1]["tables"]["VARI_ELGA"].pop("V3"),
    lambda raw: raw["states"][1]["tables"]["VARI_ELGA"]["COOR_X"].__setitem__(0, 0.),
    lambda raw: raw["states"][1]["tables"]["BOUNDARY_WRENCHES"].pop("RESULT_X"),
    lambda raw: raw["states"][1]["tables"]["BOUNDARY_WRENCHES"]["INTITULE"].__setitem__(1, "CLAMP"),
    lambda raw: raw["states"][1]["tables"]["BOUNDARY_WRENCHES"]["MOMENT_Z"].__setitem__(0, 7.),
    lambda raw: raw["mesh"]["beam_elements"][0].__setitem__("type", "TETRA10"),
    lambda raw: raw["mesh"]["beam_elements"][0]["node_ids"].reverse(),
    lambda raw: raw["mesh"]["nodes"][0].__setitem__("name", "N1"),
    lambda raw: raw["mesh"]["support_node_ids"].append(1),
    lambda raw: raw["mesh"]["support_dof_masks"]["2"].__setitem__(0, True),
    lambda raw: raw["mesh"]["support_dof_masks"]["2"].__setitem__(2, 1),
    lambda raw: raw["field_semantics"].__setitem__("curvatures_basis", "LOCAL"),
    lambda raw: raw["field_semantics"].__setitem__("section_wrenches_basis", "GLOBAL"),
    lambda raw: raw["nonlinear_policy"].__setitem__("relation", "VMIS_ISOT_LINE"),
    lambda raw: raw.__setitem__("solver_status", "FAILED"),
])
def test_malformed_missing_duplicate_wrong_basis_and_failed_histories_refuse(mutation):
    raw = raw_fixture()
    mutation(raw)
    with pytest.raises(ValueError):
        worker.parse_history_tables(raw, domain.default_settings()["history"]["times_s"])


@pytest.mark.parametrize("mutation", [
    lambda native: native.points.__setitem__(1, native.points[0]),
    lambda native: native.cells[0].reverse(),
    lambda native: native.cells.__setitem__(1, native.cells[0]),
    lambda native: native.groups["TIP"].__setitem__(0, 1),
    lambda native: native.groups["SUPPORT"].append(0),
])
def test_actual_mesh_api_guard_refuses_before_solver(mutation):
    expected = worker.beam_mesh(1000., 8)
    native = NativeMesh(expected)
    mutation(native)
    with pytest.raises(ValueError): worker.validate_native_mesh(native, expected)


def test_rectangular_section_axis_and_editable_deck_with_explicit_policy_and_configured_budget():
    expected = worker.beam_mesh(1000., 8)
    text = worker.mail_source(expected)
    assert "COOR_3D" in text and "S1 N1 N2" in text and "S8 N8 N9" in text and "GROUP_NO\nSUPPORT" in text
    section = worker.native_section(domain.default_settings())
    assert section["POUTRE"] == {"GROUP_MA": "BEAM", "SECTION": "RECTANGLE", "CARA": ["HY", "HZ"], "VALE": [2., 1.]}
    assert section["ORIENTATION"]["VALE"] == [0., 1., 0.]
    assert section["native_computed_properties"]["status"] == "UNKNOWN"
    budgets = {"solver_memory_mb": 1024, "solver_time_seconds": 86400}
    export = adapter.export_source("level_0", budgets)
    assert "P time_limit 86400" in export and "F mail /work/level_0/mesh.mail D 20" in export
    assert "F resu /work/level_0/convergence.measure R 81" in export
    assert "codeaster_geometric_worker" in adapter.comm_source("level_0")
    assert worker.NONLINEAR_POLICY["relation"] == "ELAS_POUTRE_GR" and not worker.NONLINEAR_POLICY["automatic_subdivision"]
    with pytest.raises(ValueError): adapter.comm_source("../foreign")
    with pytest.raises(ValueError): adapter.export_source("level_0", {"solver_memory_mb": 1024, "solver_time_seconds": 0})


def test_complete_full_precision_newton_history_with_explicit_beam_policy_not_j2():
    times = domain.default_settings()["history"]["times_s"]
    parsed = adapter.parse_convergence_log(convergence_fixture(), times)
    assert parsed["status"] == "PASS" and len(parsed["increments"]) == 4
    assert parsed["native_limits"]["relation"] == "ELAS_POUTRE_GR"
    assert parsed["initial_state"]["status"] == "INITIAL_STATE_NO_NEWTON_INCREMENT"
    measure = adapter.parse_measure_statistics(measure_fixture(), parsed, times)
    assert len(measure["rows"]) == 4 and measure["column_names"].count("Solve") == 2


def test_returned_metadata_does_not_alias_future_fixed_policy_or_field_basis():
    times = domain.default_settings()["history"]["times_s"]
    record = worker.parse_history_tables(raw_fixture(), times)
    convergence = adapter.parse_convergence_log(convergence_fixture(), times)
    record["field_semantics"]["curvatures_basis"] = "LOCAL"
    convergence["native_limits"]["relative_residual_limit"] = 1.
    assert worker.FIELD_SEMANTICS["curvatures_basis"] == "GLOBAL"
    assert worker.NONLINEAR_POLICY["relative_residual_limit"] == 1e-10


@pytest.mark.parametrize("mutation", [
    lambda text: text.replace("Instant de calcul: 2.000000000000e+00", "Instant de calcul: 2.5"),
    lambda text: text.replace("RESI_GLOB_MAXI", "UNKNOWN_HEADER", 1),
    lambda text: text.replace("| 1               |", "| 3               |", 1),
    lambda text: text.replace("1.0E-13", "NaN", 1),
    lambda text: text.replace("1.000000000000e-13", "2.000000000000e-13", 1),
    lambda text: text.replace("Le résidu de type <RESI_GLOB_MAXI> vaut 1.000000000000e-11 au noeud", "", 1),
])
def test_incomplete_inconsistent_newton_history_cannot_be_completion(mutation):
    with pytest.raises(ValueError): adapter.parse_convergence_log(mutation(convergence_fixture()), domain.default_settings()["history"]["times_s"])


def test_native_full_precision_failure_is_retained_even_when_rounded_cell_equals_limit():
    text = convergence_fixture().replace("1.0E-13", "1.0E-10").replace("1.000000000000e-13", "1.000000000001e-10")
    result = adapter.parse_convergence_log(text, domain.default_settings()["history"]["times_s"])
    assert result["status"] == "FAIL" and result["checks"][0]["observed"]["value"] > 1e-10


def test_pure_declaration_does_not_execute_native_and_does_not_mutate_settings(monkeypatch):
    settings = domain.default_settings()
    before = deepcopy(settings)
    monkeypatch.setattr(adapter.elastic, "_process", lambda *args, **kwargs: pytest.fail("Pure declaration invoked process"))
    declaration = adapter.CodeAsterGeometricAdapter().describe_model(settings)
    assert settings == before and set(declaration["model"]) == {"geometry", "materials", "mesh"}
    assert "minimum_mesh_rate" in adapter.CodeAsterGeometricAdapter.default_metrics


def test_invalid_request_refuses_before_runtime_and_retains_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(adapter.elastic, "_image_identity", lambda *args: pytest.fail("Invalid request reached runtime"))
    settings = domain.default_settings()
    settings["beam"]["length_mm"] = True
    result = adapter.CodeAsterGeometricAdapter().solve(tmp_path / "simulation", settings)
    assert result["solver_status"] == "NOT_RUN" and result["status"] == "REJECTED" and result["metrics"] == {}
    assert "native_global_energy" in result["pending_validations"]
    assert all((tmp_path / "simulation" / name).is_file() for name in adapter._SOURCE_SHA)


def test_existing_evidence_or_symlink_is_never_overwritten(tmp_path):
    output = tmp_path / "simulation"
    output.mkdir()
    original = output / "old.json"
    original.write_bytes(b"retained original")
    with pytest.raises(ValueError): adapter.CodeAsterGeometricAdapter().solve(output, domain.default_settings())
    assert original.read_bytes() == b"retained original"


def test_mock_only_complete_pipeline_keeps_unknowns_and_exact_source_budget_isolation(monkeypatch, tmp_path):
    image, calls = mock_execution(monkeypatch, tmp_path)
    result = adapter.CodeAsterGeometricAdapter().solve(tmp_path / "simulation", domain.default_settings())
    assert result["solver_status"] == "COMPLETED" and result["status"] == "COMPLETED"
    assert result["provenance"]["native_global_energy"] == "UNKNOWN"
    assert result["provenance"]["native_section_property_coverage"] == "UNKNOWN"
    assert result["provenance"]["measured_linear_residual"] is None
    assert result["derived_stress"]["native_cauchy_stress"] is False
    assert {"native_global_energy", "physical_validation", "static_strength"} <= set(result["pending_validations"])
    solver_calls = [call for call in calls if call["label"] == "solver"]
    assert len(solver_calls) == 3 and all(call["timeout"] is None for call in solver_calls)
    assert all("--containall" in call["argv"] and "--cleanenv" in call["argv"] and "--no-home" in call["argv"] for call in solver_calls)
    assert all(hashlib.sha256((tmp_path / "simulation" / name).read_bytes()).hexdigest() == digest for name, digest in adapter._SOURCE_SHA.items())
    assert (tmp_path / "simulation" / "level_0" / "order_0_depl.table.json").is_file()
    assert result["provenance"]["versions"]["python"] == "MOCK_PYTHON"  # expressly not native proof


@pytest.mark.parametrize("mutation", [
    lambda folder: (folder / "runtime.json").write_text("{}", encoding="utf-8"),
    lambda folder: (folder / "order_0_depl.table.json").unlink(),
    lambda folder: (folder / "native_section.json").write_text("{}", encoding="utf-8"),
    lambda folder: (folder / "model.comm").write_text("foreign code", encoding="utf-8"),
    lambda folder: (folder / "mesh_catalog.json").write_text("{}", encoding="utf-8"),
    lambda folder: (folder / "results.med").write_bytes(b""),
])
def test_checked_worker_refuses_tampered_or_missing_native_capture(monkeypatch, tmp_path, mutation):
    def solver(folder, calls):
        write_native_fixture(folder, domain.default_settings(), adapter.elastic.process_budgets())
        mutation(folder)
    mock_execution(monkeypatch, tmp_path, solver=solver)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError, match="Incomplete/malformed"):
        adapter.CodeAsterGeometricAdapter().solve(output, domain.default_settings())
    assert not (output / "analysis_raw.json").exists()
    assert (output / "scratch" / "level_0").is_dir()
    assert (output / "level_0" / "worker_result.json").is_file()


def test_runtime_identity_drift_between_meshes_is_not_a_complete_result(monkeypatch, tmp_path):
    def solver(folder, calls):
        raw = raw_fixture(load_json(folder / "input.json")["element_count"])
        if folder.name == "level_1": raw["code_aster_runtime"]["parentid"] = "foreign-runtime"
        write_native_fixture(folder, domain.default_settings(), adapter.elastic.process_budgets(), raw)
    mock_execution(monkeypatch, tmp_path, solver=solver)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError, match="runtime identity changed"):
        adapter.CodeAsterGeometricAdapter().solve(output, domain.default_settings())
    assert not (output / "analysis_raw.json").exists() and (output / "level_2" / "worker_result.json").is_file()


def test_captured_source_drift_is_not_published_and_failed_bytes_remain(monkeypatch, tmp_path):
    def solver(folder, calls):
        write_native_fixture(folder, domain.default_settings(), adapter.elastic.process_budgets())
        (folder.parent / "codeaster_geometric_worker.py").write_bytes(b"foreign captured source")
    mock_execution(monkeypatch, tmp_path, solver=solver)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError, match="source drifted"):
        adapter.CodeAsterGeometricAdapter().solve(output, domain.default_settings())
    assert (output / "codeaster_geometric_worker.py").read_bytes() == b"foreign captured source"
    assert (output / "scratch" / "level_0").is_dir() and not (output / "analysis_raw.json").exists()


def test_pinned_image_drift_after_execution_refuses_publication_and_retains_scratch(monkeypatch, tmp_path):
    def solver(folder, calls):
        write_native_fixture(folder, domain.default_settings(), adapter.elastic.process_budgets())
        (tmp_path / "mock.sif").write_bytes(b"FOREIGN image")
    mock_execution(monkeypatch, tmp_path, solver=solver)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError, match="image drifted during"):
        adapter.CodeAsterGeometricAdapter().solve(output, domain.default_settings())
    assert (output / "level_0" / "worker_result.json").is_file()
    assert (output / "scratch" / "level_0").is_dir() and not (output / "analysis_raw.json").exists()


@pytest.mark.parametrize("exception", [RuntimeError("MOCK solver failed"), ExecutionCancelled("MOCK cancellation"), ExecutionCleanupFailed("MOCK cleanup unconfirmed")])
def test_execution_failure_cancellation_or_cleanup_pending_retains_partial_no_result(monkeypatch, tmp_path, exception):
    def solver(folder, calls):
        (folder / "solver.stdout.log").write_text("MOCK partial actual-command slot", encoding="utf-8")
        raise exception
    mock_execution(monkeypatch, tmp_path, solver=solver)
    output = tmp_path / "simulation"
    with pytest.raises(type(exception)):
        adapter.CodeAsterGeometricAdapter().solve(output, domain.default_settings())
    assert (output / "level_0" / "solver.stdout.log").is_file()
    assert (output / "scratch" / "level_0").is_dir() and not (output / "analysis_raw.json").exists()


def test_numerical_rejection_keeps_completed_raw_fields_and_invalid_metrics(monkeypatch, tmp_path):
    def solver(folder, calls):
        raw = raw_fixture(load_json(folder / "input.json")["element_count"])
        # Signed curvature corruption is finite and structurally complete.
        raw["states"][-1]["tables"]["VARI_ELGA"]["V3"][0] *= -1
        write_native_fixture(folder, domain.default_settings(), adapter.elastic.process_budgets(), raw)
    mock_execution(monkeypatch, tmp_path, solver=solver)
    result = adapter.CodeAsterGeometricAdapter().solve(tmp_path / "simulation", domain.default_settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED"
    assert any(check["status"] == "FAIL" for check in result["checks"])
    assert result["metrics"] and all(metric["valid"] is False for metric in result["metrics"].values())
    assert (tmp_path / "simulation" / "level_2" / "order_8_vari_elga.table.json").is_file()


def test_worker_input_source_mesh_and_deck_hash_guards_use_exact_captured_bytes(tmp_path):
    root = tmp_path / "simulation"
    level = root / "level_0"
    level.mkdir(parents=True)
    for name in ("mesh.mail", "expected_mesh.json", "model.comm", "model.export"): (level / name).write_bytes(name.encode())
    (root / "owned.py").write_bytes(b"source")
    config = {"captured_source_sha256": {"owned.py": hashlib.sha256(b"source").hexdigest()},
              **{key: adapter.elastic._sha256(level / name) for name, key in (("mesh.mail", "mesh_sha256"),
                    ("expected_mesh.json", "expected_mesh_sha256"), ("model.comm", "comm_sha256"), ("model.export", "export_sha256"))}}
    save_json(level / "input.json", config)
    input_sha = adapter.elastic._sha256(level / "input.json")
    worker._assert_inputs(level / "input.json", input_sha, config)
    (level / "model.comm").write_bytes(b"foreign")
    with pytest.raises(RuntimeError): worker._assert_inputs(level / "input.json", input_sha, config)


def test_worker_wrong_imported_topology_refuses_before_any_stat_non_line(monkeypatch, tmp_path):
    """Mock only Code_Aster command bindings; neither initialization nor solve is real."""
    root = tmp_path / "simulation"
    level = root / "level_0"
    level.mkdir(parents=True)
    expected = worker.beam_mesh(1000., 8)
    (level / "mesh.mail").write_text(worker.mail_source(expected), encoding="utf-8")
    save_json(level / "expected_mesh.json", expected)
    (level / "model.comm").write_text(adapter.comm_source("level_0"), encoding="utf-8")
    (level / "model.export").write_text(adapter.export_source("level_0", adapter.elastic.process_budgets()), encoding="utf-8")
    config = {"settings": domain.default_settings(), "element_count": 8, "captured_source_sha256": {},
              **{key: adapter.elastic._sha256(level / name) for name, key in (("mesh.mail", "mesh_sha256"),
                    ("expected_mesh.json", "expected_mesh_sha256"), ("model.comm", "comm_sha256"), ("model.export", "export_sha256"))}}
    save_json(level / "input.json", config)
    native = NativeMesh(expected)
    native.cells[0].reverse()
    names = ("AFFE_CARA_ELEM", "AFFE_CHAR_MECA", "AFFE_MATERIAU", "AFFE_MODELE", "CALC_CHAMP", "CREA_TABLE",
             "DEBUT", "DEFI_FONCTION", "DEFI_LIST_REEL", "DEFI_MATERIAU", "FIN", "IMPR_RESU", "LIRE_MAILLAGE", "POST_RELEVE_T", "STAT_NON_LINE")
    commands = types.ModuleType("code_aster.Commands")
    for name in names: setattr(commands, name, lambda *args, **kwargs: pytest.fail("Unsupported mesh reached native commands"))
    commands.DEBUT = lambda: (Path.cwd() / "fort.20").write_bytes((level / "mesh.mail").read_bytes())
    commands.LIRE_MAILLAGE = lambda **kwargs: native
    syntax = types.ModuleType("code_aster.Cata.Syntax")
    syntax._F = lambda **kwargs: kwargs
    for name, module in (("code_aster", types.ModuleType("code_aster")), ("code_aster.Commands", commands),
                         ("code_aster.Cata", types.ModuleType("code_aster.Cata")), ("code_aster.Cata.Syntax", syntax)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(worker, "_runtime_versions", lambda: ({"code_aster": "17.4.0"}, {"version": "17.4.0"}))
    monkeypatch.chdir(level)
    with pytest.raises(RuntimeError, match="mesh rejected before nonlinear solve"):
        worker.solve_level(str(level / "input.json"))
    assert load_json(level / "native_mesh_checks.json")["solver_status"] == "NOT_RUN"
    assert not (level / "worker_result.json").exists()


def test_mock_worker_command_graph_archives_real_fixture_zero_and_exact_beam_policy(monkeypatch, tmp_path):
    """Run only Python extraction with mock command objects, never a solver."""
    root = tmp_path / "simulation"
    level = root / "level_0"
    level.mkdir(parents=True)
    expected = worker.beam_mesh(1000., 8)
    (level / "mesh.mail").write_text(worker.mail_source(expected), encoding="utf-8")
    save_json(level / "expected_mesh.json", expected)
    (level / "model.comm").write_text(adapter.comm_source("level_0"), encoding="utf-8")
    (level / "model.export").write_text(adapter.export_source("level_0", adapter.elastic.process_budgets()), encoding="utf-8")
    config = {"settings": domain.default_settings(), "element_count": 8, "captured_source_sha256": {},
        **{key: adapter.elastic._sha256(level / name) for name, key in (("mesh.mail", "mesh_sha256"),
              ("expected_mesh.json", "expected_mesh_sha256"), ("model.comm", "comm_sha256"), ("model.export", "export_sha256"))}}
    save_json(level / "input.json", config)
    fixture = raw_fixture()
    calls = []
    class Result:
        def getAccessParameters(self): return fixture["access_parameters"]
        def getIndexes(self): return fixture["available_orders"]
    class Table:
        def __init__(self, values): self.data = values
        def EXTR_TABLE(self): return self
        def values(self): return self.data
    commands = types.ModuleType("code_aster.Commands")
    def command(name):
        def execute(**kwargs):
            calls.append((name, kwargs))
            if name == "DEBUT": (Path.cwd() / "fort.20").write_bytes((level / "mesh.mail").read_bytes())
            if name == "LIRE_MAILLAGE": return NativeMesh(expected)
            if name in ("STAT_NON_LINE", "CALC_CHAMP"): return Result()
            if name == "IMPR_RESU":
                if kwargs["FORMAT"] == "MED":
                    (level / "results.med").write_bytes(b"MOCK_UNSOLVED_MED_NOT_NATIVE")
                elif kwargs["FORMAT"] == "RESULTAT":
                    (level / "aster.resu").write_bytes(b"MOCK_UNSOLVED_RESULTAT_NOT_NATIVE")
                else:
                    pytest.fail("Unsupported native output format")
            if name == "CREA_TABLE":
                selection = kwargs["RESU"]
                state = next(item for item in fixture["states"] if item["order"] == selection["NUME_ORDRE"])
                return Table(state["tables"][selection["NOM_CHAM"]])
            if name == "POST_RELEVE_T":
                order = kwargs["ACTION"][0]["NUME_ORDRE"]
                return Table(next(item for item in fixture["states"] if item["order"] == order)["tables"]["BOUNDARY_WRENCHES"])
            return {"mock_command": name}
        return execute
    for name in ("AFFE_CARA_ELEM", "AFFE_CHAR_MECA", "AFFE_MATERIAU", "AFFE_MODELE", "CALC_CHAMP", "CREA_TABLE",
                 "DEBUT", "DEFI_FONCTION", "DEFI_LIST_REEL", "DEFI_MATERIAU", "FIN", "IMPR_RESU", "LIRE_MAILLAGE", "POST_RELEVE_T", "STAT_NON_LINE"):
        setattr(commands, name, command(name))
    syntax = types.ModuleType("code_aster.Cata.Syntax")
    syntax._F = lambda **kwargs: kwargs
    for name, module in (("code_aster", types.ModuleType("code_aster")), ("code_aster.Commands", commands),
                         ("code_aster.Cata", types.ModuleType("code_aster.Cata")), ("code_aster.Cata.Syntax", syntax)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(worker, "_runtime_versions", lambda: (fixture["versions"], fixture["code_aster_runtime"]))
    monkeypatch.chdir(level)
    worker.solve_level(str(level / "input.json"))
    nonlinear = next(kwargs for name, kwargs in calls if name == "STAT_NON_LINE")
    assert nonlinear["COMPORTEMENT"] == {"GROUP_MA": "BEAM", "RELATION": "ELAS_POUTRE_GR", "DEFORMATION": "GROT_GDEP"}
    assert nonlinear["CONVERGENCE"] == {"RESI_GLOB_RELA": 1e-10, "RESI_GLOB_MAXI": 1e-8, "ITER_GLOB_MAXI": 40, "ARRET": "OUI", "VERIF": "TOUT"}
    assert nonlinear["SOLVEUR"] == {"METHODE": "MUMPS"} and "ARCHIVAGE" in nonlinear and "DEFI_LIST_INST" not in [name for name, _ in calls]
    prescribed = next(kwargs for name, kwargs in calls if name == "AFFE_CHAR_MECA" and "DDL_IMPO" in kwargs)
    assert prescribed["DDL_IMPO"] == ({"GROUP_NO": "BEAM", "DZ": 0.}, {"GROUP_NO": "CLAMP", "DX": 0., "DY": 0., "DRX": 0., "DRY": 0., "DRZ": 0.})
    section = next(kwargs for name, kwargs in calls if name == "AFFE_CARA_ELEM")
    assert section["POUTRE"]["CARA"] == ["HY", "HZ"] and section["POUTRE"]["VALE"] == [2., 1.]
    outputs = [kwargs for name, kwargs in calls if name == "IMPR_RESU"]
    assert [(output["FORMAT"], output["UNITE"]) for output in outputs] == [("MED", 80), ("RESULTAT", 8)]
    assert outputs[0]["RESU"]["RESULTAT"] is outputs[1]["RESU"]["RESULTAT"]
    for output in outputs:
        assert output["RESU"]["NOM_CHAM"] == ("DEPL", "REAC_NODA", "SIEF_ELGA", "VARI_ELGA")
        assert output["RESU"]["TOUT_ORDRE"] == "OUI"
    assert (level / "results.med").read_bytes() == b"MOCK_UNSOLVED_MED_NOT_NATIVE"
    assert (level / "aster.resu").read_bytes() == b"MOCK_UNSOLVED_RESULTAT_NOT_NATIVE"
    saved = load_json(level / "worker_result.json")
    assert len(saved["states"]) == 5 and saved["states"][0]["order"] == 0
    assert saved["states"][0]["tables"]["DEPL"] == fixture["states"][0]["tables"]["DEPL"]
    assert (level / "order_0_vari_elga.table.json").is_file() and (level / "native_history.partial.json").is_file()


@pytest.mark.parametrize("missing", [False, True], ids=["empty-resultat", "missing-resultat"])
def test_missing_or_empty_native_resultat_refuses_completion_and_retains_partial(monkeypatch, tmp_path, missing):
    """Cold completed-field fixture cannot replace the required native text file."""
    retained = {}

    def solver(folder, calls):
        write_native_fixture(folder, load_json(folder / "input.json")["settings"], adapter.elastic.process_budgets())
        retained["worker_result"] = (folder / "worker_result.json").read_bytes()
        if missing:
            (folder / "aster.resu").unlink()
        else:
            (folder / "aster.resu").write_bytes(b"")

    _, calls = mock_execution(monkeypatch, tmp_path, solver=solver)
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError, match="Required native beam evidence is missing: aster.resu"):
        adapter.CodeAsterGeometricAdapter().solve(output, domain.default_settings())
    assert not (output / "analysis_raw.json").exists()
    assert len([call for call in calls if call["label"] == "solver"]) == 1
    level = output / "level_0"
    assert (level / "worker_result.json").read_bytes() == retained["worker_result"]
    assert (level / "results.med").read_bytes() == b"MOCK_UNSOLVED_MED_NOT_NATIVE"
    assert (output / "scratch" / "level_0").is_dir()
    assert not (output / "level_1").exists()
    if missing:
        assert not (level / "aster.resu").exists()
    else:
        assert (level / "aster.resu").stat().st_size == 0
