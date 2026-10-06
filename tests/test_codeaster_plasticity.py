"""Nonlinear transport/field contract tests; these mocks execute no native solver."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import types

import pytest

from caelab import Lab
from caelab.adapters import codeaster_elasticity as elastic
from caelab.adapters import codeaster_plasticity as adapter_module
from caelab.adapters import codeaster_plasticity_worker as worker
from caelab.adapters.codeaster_plasticity import CodeAsterPlasticityAdapter
from caelab.storage import canonical_hash, load_json, save_json
from plugins.elasticity import plasticity_reference as domain
from scripts.verify_plasticity import changed_nonzero_reference, changed_specification
from test_codeaster_adapter import brick_msh, native_fixture, GuardNativeMesh


def settings():
    return {"case": "uniaxial_j2_isotropic_hardening", "dimensions_mm": [20., 4., 2.],
        "material": {"youngs_modulus_mpa": 210000., "poisson_ratio": .3,
                     "yield_stress_mpa": 250., "plastic_modulus_mpa": 1000.},
        "history": {"times_s": list(range(10)),
                    "axial_strain": [0., .0005, .001, .0015, .002, .003, .006, .0055, .005, .0045]},
        "mesh_sizes_mm": [2., 1.],
        "limits": {"displacement_relative": 1e-7, "displacement_absolute_mm": 1e-10,
                   "stress_relative": 1e-7, "stress_absolute_mpa": 1e-8, "plastic_strain_absolute": 1e-9,
                   "reaction_relative": 1e-7, "reaction_absolute_n": 1e-8, "mesh_agreement_relative": 1e-7,
                   "plastic_dissipation_relative": 1e-6, "plastic_dissipation_absolute_mpa": 1e-8}}


def test_separate_changed_case_is_frozen_before_native_with_independent_nonzero_stress_history():
    request = changed_specification()
    assert request["material"]["yield_stress_mpa"] == 225.
    assert request["material"]["plastic_modulus_mpa"] == 1500.
    assert request["history"] == settings()["history"] and request["limits"] == settings()["limits"]
    reference = changed_nonzero_reference(request)
    assert reference["stress_history_mpa"][6] == pytest.approx(232.340425531915)
    assert reference["stress_history_mpa"][8] == pytest.approx(22.340425531915)
    assert reference["stress_history_mpa"][9] == pytest.approx(-82.6595744680851)
    assert reference["eq_plastic_strain_history"][6] == pytest.approx(.004893617021276595)
    failed_case = deepcopy(request)
    failed_case["material"].update(yield_stress_mpa=200., plastic_modulus_mpa=2000.)
    with pytest.raises(ValueError, match="nonzero post-initial"):
        changed_nonzero_reference(failed_case)


def convergence_fixture(request=None):
    request = request or settings()
    return "\n".join(f"Instant de calcul: {instant:.12e}\n"
        "|                 | RESI_GLOB_RELA | RESI_GLOB_MAXI | OPTION |\n"
        "| 0             X | 1.0          X | 1.0          X | TANG   |\n"
        "| 1               | 1.0E-13        | 1.0E-11        | TANG   |\n"
        "Le résidu de type <RESI_GLOB_RELA> vaut 1.000000000000e-13 au noeud\n"
        "Le résidu de type <RESI_GLOB_MAXI> vaut 1.000000000000e-11 au noeud"
        for instant in request["history"]["times_s"][1:])


def measure_fixture(request=None):
    request = request or settings()
    return ", ,Count,Time,Count, ,Memory,\n,INST,Newt_Iter,Solve,Solve,State,VmPeak,\n" + "\n".join(
        f",{instant:.5E},2,1.0E-3,2,CONV,793," for instant in request["history"]["times_s"][1:])


def test_native_iteration_history_is_separate_from_measure_statistics_and_initial_state():
    result = adapter_module.parse_convergence_log(convergence_fixture(), settings()["history"]["times_s"])
    assert result["status"] == "PASS"
    assert result["initial_state"]["status"] == "INITIAL_STATE_NO_NEWTON_INCREMENT"
    assert len(result["increments"]) == 9
    assert result["increments"][3]["iterations"][-1]["RESI_GLOB_RELA"] == 1e-13
    assert all(result["increments"][3]["iterations"][0]["failed_criterion_flags"].values())
    assert not any(result["increments"][3]["iterations"][-1]["failed_criterion_flags"].values())
    measure = adapter_module.parse_measure_statistics(measure_fixture(), result, settings()["history"]["times_s"])
    assert measure["status"] == "PASS" and len(measure["rows"]) == 9
    assert measure["column_names"].count("Solve") == 2  # Time and Count columns retain separate identity.
    assert measure["rows"][2]["newton_iteration_count"] == 2


@pytest.mark.parametrize("corrupt", [
    lambda text: text.replace("Instant de calcul: 9.000000000000e+00", "Instant de calcul: 9.5"),
    lambda text: text.replace("1.0E-13", "1.0E-3", 1),
    lambda text: text.replace("1.0E-11", "NaN", 1),
    lambda text: text.replace("| 1               |", "| 3               |", 1),
    lambda text: text.replace("RESI_GLOB_RELA", "UNVERIFIED_HEADER", 1),
    lambda text: text.replace("1.000000000000e-13", "NaN", 1),
    lambda text: text.replace("1.000000000000e-13", "2.000000000000e-13", 1),
])
def test_missing_or_failed_native_convergence_history_is_not_completion(corrupt):
    with pytest.raises(ValueError):
        adapter_module.parse_convergence_log(corrupt(convergence_fixture()), settings()["history"]["times_s"])


def test_full_precision_final_residual_above_limit_cannot_pass_rounded_iteration_cell():
    text = convergence_fixture().replace("1.0E-13", "1.00000E-10", 1)
    text = text.replace("1.000000000000e-13", "1.000000000001e-10", 1)
    result = adapter_module.parse_convergence_log(text, settings()["history"]["times_s"])
    assert result["status"] == "FAIL"
    assert result["checks"][0]["observed"]["value"] == 1.000000000001e-10
    assert result["checks"][0]["limit"] == 1e-10


def test_complete_final_row_with_native_failure_flag_retains_numerical_failure():
    text = convergence_fixture().replace("| 1               |", "| 1             X |", 1)
    result = adapter_module.parse_convergence_log(text, settings()["history"]["times_s"])
    assert result["status"] == "FAIL"
    assert result["increments"][0]["iterations"][-1]["failed_criterion_flags"]["iteration"] is True


@pytest.mark.parametrize("corrupt", [
    lambda text: text.replace("Newt_Iter", "Unknown_Iter"),
    lambda text: text.replace("CONV", "NOCONV", 1),
    lambda text: text.replace(",2,1.0E-3", ",1,1.0E-3", 1),
    lambda text: text.replace("1.00000E+00", "1.50000E+00", 1),
    lambda text: text.replace("1.0E-3", "NaN", 1),
    lambda text: "\n".join(text.splitlines()[:-1]),
    lambda text: text.replace(",CONV,793,", ",CONV,", 1),
])
def test_native_measure_statistics_require_complete_time_count_and_converged_state(corrupt):
    convergence = adapter_module.parse_convergence_log(convergence_fixture(), settings()["history"]["times_s"])
    with pytest.raises(ValueError):
        adapter_module.parse_measure_statistics(corrupt(measure_fixture()), convergence, settings()["history"]["times_s"])


def mesh_fixture(tmp_path, request=None):
    request = request or settings()
    path = tmp_path / "mesh.msh"
    path.write_text(brick_msh(request["dimensions_mm"]), encoding="utf-8")
    return elastic.parse_gmsh_mesh(path, request["dimensions_mm"])


def history_fixture(mesh, request=None):
    """Complete native tables with zero and non-consecutive positive orders."""
    request = request or settings()
    legacy = {"case": "uniaxial_block", "dimensions_mm": request["dimensions_mm"],
              "material": {"youngs_modulus_mpa": 210000., "poisson_ratio": .3}, "traction_mpa": 10.,
              "mesh_sizes_mm": [2., 1.], "limits": {"displacement_relative": 1e-8,
              "displacement_absolute_mm": 1e-12, "stress_relative": 1e-8, "reaction_relative": 1e-8,
              "mesh_agreement_relative": 1e-8}}
    base = native_fixture(mesh, legacy)
    catalog = base["mesh"]
    coordinates = {item["node_id"]: item["coordinates_mm"] for item in catalog["nodes"]}
    groups = catalog["group_node_ids"]
    states = []
    peak_plastic = 0.
    signed_plastic = 0.
    selected = request.get("mode") == "selected_mesh"
    for index, (instant, strain) in enumerate(zip(request["history"]["times_s"], request["history"]["axial_strain"])):
        # Independent scalar fixture arithmetic rather than calling the plugin.
        material = request["material"]
        young, hardening, yield_stress = material["youngs_modulus_mpa"], material["plastic_modulus_mpa"], material["yield_stress_mpa"]
        if selected:
            # TEST_ONLY signed scalar return map for complete synthetic tables.
            # It never calls the product analytical reference or a native solver.
            trial = young * (strain - signed_plastic)
            increment = max(0., (abs(trial) - yield_stress - hardening * peak_plastic) / (young + hardening))
            signed_plastic += (-1. if trial < 0. else 1.) * increment
            peak_plastic += increment
            stress = young * (strain - signed_plastic)
            axial_plastic = signed_plastic
        else:
            peak_plastic = max(peak_plastic, (young * strain - yield_stress) / (young + hardening))
            stress = young * (strain - peak_plastic)
            axial_plastic = peak_plastic
        gradient = [strain, -material["poisson_ratio"] * stress / young - .5 * axial_plastic,
                    -material["poisson_ratio"] * stress / young - .5 * axial_plastic]
        force = stress * request["dimensions_mm"][1] * request["dimensions_mm"][2]
        order = index * 3
        tables = deepcopy(base["tables"])
        del tables["SUPPORT_RESULTANT"]
        nodal_reactions = {node: [-force / len(groups["X0"]) if node in groups["X0"] else
                                  force / len(groups["XL"]) if node in groups["XL"] else 0., 0., 0.]
                           for node in coordinates}
        for name in ("DEPL", "REAC_NODA"):
            table = tables[name]
            table["NUME_ORDRE"] = [order] * len(table["NOEUD"])
            for row, name_value in enumerate(table["NOEUD"]):
                node = int(name_value)
                values = [slope * coord for slope, coord in zip(gradient, coordinates[node])] if name == "DEPL" else nodal_reactions[node]
                for axis, component in enumerate(worker.VECTOR_COMPONENTS):
                    table[component][row] = values[axis]
        stress_table = tables["SIEF_ELGA"]
        count = len(stress_table["MAILLE"])
        stress_table["NUME_ORDRE"] = [order] * count
        for component in worker.STRESS_COMPONENTS:
            stress_table[component] = [stress if component == "SIXX" else 0.] * count
        plastic = {key: deepcopy(values) for key, values in stress_table.items() if key not in worker.STRESS_COMPONENTS}
        plastic.update(V1=[peak_plastic] * count, V2=[1. if index <= 6 and peak_plastic > 0 else 0.] * count)
        tables["VARI_ELGA"] = plastic
        post = {key: [] for key in ("INTITULE", "NUME_ORDRE", "INST", *worker.VECTOR_COMPONENTS)}
        for group in ("X0", "XL", "Y0", "Z0"):
            post["INTITULE"].append(group)
            post["NUME_ORDRE"].append(order)
            post["INST"].append(float(instant))
            for axis, component in enumerate(worker.VECTOR_COMPONENTS):
                post[component].append(sum(nodal_reactions[node][axis] for node in groups[group]))
        tables["BOUNDARY_RESULTANTS"] = post
        states.append({"order": order, "time_s": float(instant), "tables": tables})
    raw = {"schema_version": "1", "solver_status": "COMPLETED", "converged": True,
            "available_orders": [state["order"] for state in states],
            "access_parameters": {"NUME_ORDRE": [state["order"] for state in states],
                                  "INST": [state["time_s"] for state in states]},
            "mesh": catalog, "states": states}
    if selected:
        raw.update(mode="selected_mesh", input_provenance=deepcopy(request["input_provenance"]))
    return raw


def test_complete_actual_histories_keep_initial_zero_and_component_specific_reactions(tmp_path):
    mesh = mesh_fixture(tmp_path)
    raw = history_fixture(mesh)
    before = deepcopy(raw)
    record = worker.parse_history_tables(raw, 2., settings()["history"]["times_s"])
    assert [state["actual_result_order"] for state in record["states"]] == list(range(0, 30, 3))
    assert record["states"][0]["eq_plastic_strain"] == [0.] * (5 * mesh["element_count"])
    peak = record["states"][6]
    assert peak["reaction_n"][0] == pytest.approx(-2038.29383886256)
    assert peak["drive_reaction_x_n"] == pytest.approx(2038.29383886256)
    support = set(raw["mesh"]["support_node_ids"])
    wrong_union_sum = sum(row[0] for node, row in zip(record["node_ids"], peak["nodal_reactions_n"]) if node in support)
    assert abs(wrong_union_sum - peak["reaction_n"][0]) > 100
    assert record["states"][-1]["eq_plastic_strain"] == peak["eq_plastic_strain"]
    assert record["states"][-1]["stresses_mpa"][0][0] == pytest.approx(-60.21327014218)
    assert raw == before
    assert "INST" not in raw["states"][0]["tables"]["DEPL"]
    assert "INST" not in raw["states"][0]["tables"]["VARI_ELGA"]


@pytest.mark.parametrize("field,column", [("DEPL", "NUME_ORDRE"), ("VARI_ELGA", "NUME_ORDRE"),
    ("REAC_NODA", "COOR_Z"), ("SIEF_ELGA", "SIYZ"), ("VARI_ELGA", "V1"),
    ("VARI_ELGA", "V2"), ("BOUNDARY_RESULTANTS", "INST")])
def test_history_fields_require_complete_identity_and_all_components(tmp_path, field, column):
    raw = history_fixture(mesh_fixture(tmp_path))
    del raw["states"][4]["tables"][field][column]
    with pytest.raises(ValueError, match="missing required columns"):
        worker.parse_history_tables(raw, 2., settings()["history"]["times_s"])


@pytest.mark.parametrize("corrupt", [
    lambda raw: raw["states"].pop(),
    lambda raw: raw["states"][0].update(order=1),
    lambda raw: raw["access_parameters"]["INST"].__setitem__(5, 5.01),
    lambda raw: raw["access_parameters"].pop("INST"),
    lambda raw: raw["access_parameters"]["NUME_ORDRE"].__setitem__(1, 0),
    lambda raw: raw["states"][7]["tables"]["VARI_ELGA"]["V1"].__setitem__(2, None),
    lambda raw: raw["states"][7]["tables"]["VARI_ELGA"]["V2"].__setitem__(2, float("inf")),
    lambda raw: raw["states"][7]["tables"]["VARI_ELGA"]["POINT"].__setitem__(2, 1),
    lambda raw: raw["states"][7]["tables"]["VARI_ELGA"]["MAILLE"].__setitem__(2, "M1"),
    lambda raw: raw["states"][7]["tables"]["VARI_ELGA"]["SOUS_POINT"].__setitem__(2, 2),
    lambda raw: raw["states"][2]["tables"]["DEPL"]["DX"].__setitem__(1, float("nan")),
    lambda raw: raw["states"][2]["tables"]["DEPL"]["NOEUD"].__setitem__(1, "0"),
    lambda raw: raw["states"][8]["tables"]["SIEF_ELGA"].update(INST=[7.] * len(raw["states"][8]["tables"]["SIEF_ELGA"]["MAILLE"])),
    lambda raw: raw["states"][8]["tables"]["VARI_ELGA"]["COOR_X"].__setitem__(1, 1e9),
    lambda raw: raw["states"][8]["tables"]["BOUNDARY_RESULTANTS"]["DX"].__setitem__(1, 999.),
    lambda raw: raw["mesh"]["support_node_ids"].pop(),
])
def test_malformed_native_history_never_filters_or_fabricates_missing_observations(tmp_path, corrupt):
    raw = history_fixture(mesh_fixture(tmp_path))
    corrupt(raw)
    before = repr(raw)
    with pytest.raises(ValueError):
        worker.parse_history_tables(raw, 2., settings()["history"]["times_s"])
    assert repr(raw) == before


@pytest.mark.parametrize("field,key", [("DEPL", "NOEUD"), ("REAC_NODA", "NOEUD"),
    ("SIEF_ELGA", "MAILLE"), ("VARI_ELGA", "MAILLE")])
def test_explicit_native_field_time_when_present_must_match_actual_access_parameters(tmp_path, field, key):
    raw = history_fixture(mesh_fixture(tmp_path))
    table = raw["states"][4]["tables"][field]
    table["INST"] = [4.] * len(table[key])
    assert worker.parse_history_tables(raw, 2., settings()["history"]["times_s"])["states"][4]["time_s"] == 4.
    table["INST"][0] = 4.01
    with pytest.raises(ValueError, match="Wrong native instant"):
        worker.parse_history_tables(raw, 2., settings()["history"]["times_s"])


def configure_process_mock(tmp_path, monkeypatch, mutate=None):
    image = tmp_path / "test-only.sif"
    image.write_bytes(b"MOCK IMAGE: no native solver")
    image_sha = hashlib.sha256(image.read_bytes()).hexdigest()
    monkeypatch.setattr(elastic, "_image_identity", lambda output: (image, image_sha, "singularity", "gmsh", "prlimit"))
    calls = []

    def process(command, folder, label, **kwargs):
        calls.append((command, folder, label))
        if label == "gmsh_version":
            return "4.12.1 TEST ONLY"
        if label == "container_version":
            return "singularity 4.1.1 TEST ONLY"
        if label == "gmsh":
            request = load_json(folder.parent / "input.json")
            (folder / "mesh.msh").write_text(brick_msh(request["dimensions_mm"]), encoding="utf-8")
            return "MOCK meshing"
        assert label == "solver"
        assert "OMP_NUM_THREADS=2" in command
        assert "--cleanenv" in command and "--containall" in command and "--no-home" in command
        assert str(folder.parent / "preferences") + ":" + str(Path.home()) + ":rw" in command
        assert str(folder.parent / "scratch" / folder.name) + ":/tmp:rw" in command
        assert command[-1] == "/work/" + folder.name + "/model.export"
        config = load_json(folder / "input.json")
        mesh = elastic.parse_gmsh_mesh(folder / "mesh.msh", config["settings"]["dimensions_mm"])
        raw = history_fixture(mesh, config["settings"])
        native = GuardNativeMesh(mesh, {"mesh": raw["mesh"]})
        guard = worker.validate_native_mesh(native, elastic._expected_mesh(mesh))
        guard.update(support_union_verified=True, expected_mesh_sha256=config["expected_mesh_sha256"], checked_msh_sha256=config["mesh_sha256"])
        material = config["settings"]["material"]
        young, hardening = material["youngs_modulus_mpa"], material["plastic_modulus_mpa"]
        raw.update(versions={"code_aster": "17.4.0", "python": "3.11.14", "numpy": "1.26.4"},
            code_aster_runtime={"version": "17.4.0", "parentid": "TEST ONLY"}, native_mesh_checks=guard,
            input_sha256=elastic._sha256(folder / "input.json"), mesh_input_sha256=config["mesh_sha256"],
            nonlinear_policy=worker.NONLINEAR_POLICY,
            native_material={"ELAS": {"E": young, "NU": material["poisson_ratio"]},
                             "ECRO_LINE": {"SY": material["yield_stress_mpa"], "D_SIGM_EPSI": young * (hardening / (young + hardening))}})
        save_json(folder / "native_mesh_checks.json", guard)
        save_json(folder / "native_material.json", raw["native_material"])
        for name in ("results.med", "aster.mess", "convergence.measure"):
            (folder / name).write_text("TEST ONLY no native solver", encoding="utf-8")
        (folder / "aster.mess").write_text(convergence_fixture(config["settings"]), encoding="utf-8")
        (folder / "convergence.measure").write_text(measure_fixture(config["settings"]), encoding="utf-8")
        if mutate:
            mutate(raw, folder)
        save_json(folder / "worker_result.json", raw)
        return "MOCK solver process"

    monkeypatch.setattr(elastic, "_process", process)
    return calls


def test_real_adapter_metadata_and_common_runner_keep_history_material_revision_without_native(tmp_path, monkeypatch):
    adapter = CodeAsterPlasticityAdapter()
    request = settings()
    declaration = adapter.describe_model(request)
    assert declaration["model"]["geometry"]["dimensions_mm"] == [20., 4., 2.]
    assert declaration["model"]["materials"]
    assert declaration["boundary_conditions"] and declaration["outputs"]["fields"]
    calls = configure_process_mock(tmp_path, monkeypatch)
    lab = Lab(tmp_path / "store", adapters={}, analysis_adapters={}, pde_adapters={}, doe_adapters={},
              optimization_adapters={}, model_analysis_adapters={adapter.backend: adapter})
    lab.create_study("S-plastic", "Test-only contract", "Does typed history persist?", "An independent material path", "No actual solver")
    result = lab.run_model_analysis(study_id="S-plastic", experiment_id="E-plastic", backend=adapter.backend, settings=request)
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED", result["validations"]
    proposal = load_json(lab.store / "experiments/E-plastic/proposal.json")
    assert proposal["model"] == declaration["model"]
    assert result["model_revision"] == canonical_hash({"settings": request, "declaration": declaration})
    assert result["cad_revision"] is None and "parent_experiment_id" not in result
    assert result["decision"] == "NOT_RELEASED"
    assert lab.inspect_experiment("E-plastic") == result
    assert len([call for call in calls if call[2] == "solver"]) == 2
    assert result["metrics"]["peak_stress"]["value"] == pytest.approx(254.78672985782)
    assert result["metrics"]["final_stress"]["value"] == pytest.approx(-60.21327014218)


@pytest.mark.parametrize("mutation", [
    lambda request: request["material"].update(yield_stress_mpa=0),
    lambda request: request["material"].update(plastic_modulus_mpa=True),
    lambda request: request["material"].update(poisson_ratio=.5),
    lambda request: request["history"]["axial_strain"].__setitem__(-1, 0.),
    lambda request: request["history"]["times_s"].__setitem__(3, 2),
    lambda request: request.update(executable="bad"),
    lambda request: request.update(mesh_sizes_mm=[1e-6, 5e-7]),
])
def test_invalid_material_history_or_workload_blocks_every_process(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(elastic, "_process", lambda *a, **kw: pytest.fail("Rejected inputs must start no external process"))
    monkeypatch.setattr(elastic, "_image_identity", lambda *a: pytest.fail("Rejected inputs must start no runtime preflight"))
    request = settings()
    mutation(request)
    before = deepcopy(request)
    result = CodeAsterPlasticityAdapter().solve(tmp_path / "simulation", request)
    assert result["status"] == "REJECTED" and result["solver_status"] == "NOT_RUN"
    assert result["metrics"] == {} and request == before
    assert (tmp_path / "simulation/analysis_raw.json").is_file()


def test_wrong_hardening_tangent_is_execution_failure_without_adjusting_reference(tmp_path, monkeypatch):
    def corrupt(raw, folder):
        raw["native_material"]["ECRO_LINE"]["D_SIGM_EPSI"] = 1000.
        save_json(folder / "native_material.json", raw["native_material"])
    configure_process_mock(tmp_path, monkeypatch, corrupt)
    with pytest.raises(RuntimeError, match="material/tangent"):
        CodeAsterPlasticityAdapter().solve(tmp_path / "simulation", settings())
    assert (tmp_path / "simulation/scratch/level_0").is_dir()
    assert (tmp_path / "simulation/level_0/worker_result.json").is_file()
    assert not (tmp_path / "simulation/analysis_raw.json").exists()


def test_complete_but_wrong_numerical_fields_remain_evidence_and_invalid_metrics(tmp_path, monkeypatch):
    def perturb(raw, folder):
        raw["states"][7]["tables"]["VARI_ELGA"]["V1"][0] += .0001
    configure_process_mock(tmp_path, monkeypatch, perturb)
    result = CodeAsterPlasticityAdapter().solve(tmp_path / "simulation", settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED" and result["converged"] is True
    assert all(metric["valid"] is False and metric["value"] is not None for metric in result["metrics"].values())
    assert result["mesh_records"][0]["states"][7]["eq_plastic_strain"][0] > .0048
    assert (tmp_path / "simulation/level_0/parsed_history.json").is_file()


def test_large_relative_residual_with_small_absolute_residual_cannot_become_success(tmp_path, monkeypatch):
    def perturb(raw, folder):
        text = convergence_fixture().replace("1.0E-13", "7.30000E-1", 1)
        text = text.replace("1.000000000000e-13", "7.300000000000e-1", 1)
        (folder / "aster.mess").write_text(text, encoding="utf-8")
    configure_process_mock(tmp_path, monkeypatch, perturb)
    result = CodeAsterPlasticityAdapter().solve(tmp_path / "simulation", settings())
    assert result["status"] == "REJECTED" and result["solver_status"] == "COMPLETED"
    assert result["converged"] is True  # Native completion is distinct from the strict numerical verdict.
    assert all(metric["valid"] is False for metric in result["metrics"].values())
    assert all(metric["value"] is not None for metric in result["metrics"].values())
    assert len(result["mesh_records"]) == 2 and len(result["mesh_records"][0]["states"]) == 10
    assert result["mesh_records"][0]["nonlinear_convergence"]["checks"][0]["observed"]["value"] == .73
    failures = [check["code"] for check in result["checks"] if check["status"] == "FAIL"]
    assert failures == ["native_nonlinear_convergence_0", "native_nonlinear_convergence_1"]
    assert "native_nonlinear_convergence_0" in result["metrics"]["peak_stress"]["reason"]


@pytest.mark.parametrize("failure", ["missing_V1", "missing_time", "missing_MED", "missing_guard", "source_drift", "nonzero_process"])
def test_incomplete_processes_or_drift_cannot_become_numerical_success(tmp_path, monkeypatch, failure):
    def mutate(raw, folder):
        if failure == "missing_V1":
            del raw["states"][2]["tables"]["VARI_ELGA"]["V1"]
        elif failure == "missing_time":
            raw["states"].pop()
        elif failure == "missing_MED":
            (folder / "results.med").unlink()
        elif failure == "missing_guard":
            raw["native_mesh_checks"]["status"] = "FAIL"
        elif failure == "source_drift":
            (folder.parent / "codeaster_worker.py").write_text("drift")
        else:
            (folder / "solver.stderr.log").write_text("TEST process failure")
            raise RuntimeError("TEST process nonzero")
    configure_process_mock(tmp_path, monkeypatch, mutate)
    with pytest.raises(RuntimeError):
        CodeAsterPlasticityAdapter().solve(tmp_path / "simulation", settings())
    assert (tmp_path / "simulation/scratch/level_0").exists()


def test_missing_actual_runtime_and_preserved_outputs_are_not_success(tmp_path, monkeypatch):
    monkeypatch.setattr(elastic, "_image_identity", lambda *a: (_ for _ in ()).throw(RuntimeError("missing image")))
    output = tmp_path / "simulation"
    with pytest.raises(RuntimeError, match="missing image"):
        CodeAsterPlasticityAdapter().solve(output, settings())
    assert (output / "runtime_preflight.stderr.log").is_file()
    with pytest.raises(ValueError, match="new or empty"):
        CodeAsterPlasticityAdapter().solve(output, settings())


def test_reused_native_guard_blocks_material_and_nonlinear_commands_on_wrong_import(tmp_path, monkeypatch):
    request = settings()
    mesh = mesh_fixture(tmp_path, request)
    raw = history_fixture(mesh)
    native = GuardNativeMesh(mesh, {"mesh": raw["mesh"]})
    native.catalog["group_node_ids"]["X0"] += native.catalog["group_node_ids"]["XL"]
    save_json(tmp_path / "expected_mesh.json", elastic._expected_mesh(mesh))
    save_json(tmp_path / "input.json", {"settings": request, "mesh_sha256": elastic._sha256(tmp_path / "mesh.msh"),
                                      "expected_mesh_sha256": elastic._sha256(tmp_path / "expected_mesh.json")})
    monkeypatch.chdir(tmp_path)
    started = []
    commands = types.ModuleType("code_aster.Commands")
    def debut():
        (tmp_path / "fort.20").write_bytes((tmp_path / "mesh.msh").read_bytes())
        started.append("DEBUT")
    commands.DEBUT = debut
    commands.LIRE_MAILLAGE = lambda **kw: native
    for name in ("AFFE_CHAR_MECA", "AFFE_MATERIAU", "AFFE_MODELE", "CALC_CHAMP", "CREA_TABLE", "DEFI_FONCTION",
                 "DEFI_GROUP", "DEFI_LIST_REEL", "DEFI_MATERIAU", "FIN", "IMPR_RESU", "POST_RELEVE_T", "STAT_NON_LINE"):
        setattr(commands, name, lambda **kw: pytest.fail("Invalid native groups must block model/material/nonlinear work"))
    syntax = types.ModuleType("code_aster.Cata.Syntax")
    syntax._F = lambda **kw: kw
    monkeypatch.setitem(sys.modules, "code_aster.Commands", commands)
    monkeypatch.setitem(sys.modules, "code_aster.Cata.Syntax", syntax)
    monkeypatch.setattr(worker, "_runtime_versions", lambda: ({"code_aster": "17.4.0"}, {"version": "17.4.0"}))
    with pytest.raises(RuntimeError, match="guard rejected"):
        worker.solve_level(str(tmp_path / "input.json"))
    assert started == ["DEBUT"]
    assert load_json(tmp_path / "native_mesh_checks.json")["status"] == "FAIL"


def selected_request(count=7):
    request = domain.selected_settings()
    request["history"] = {"times_s": [index * .25 for index in range(count)],
                          "axial_strain": [0., *([.003, .003, -.003, -.003, .002, 0.][(index - 1) % 6]
                                                for index in range(1, count))]}
    request["input_provenance"] = {"origin": "MEASURED_REPORTED", "reference": "  TEST_ONLY reported signed history; no native/physical qualification  "}
    return request


@pytest.mark.parametrize("count", [2, 32])
def test_selected_common_core_mock_executes_one_mesh_and_preserves_full_signed_history_and_unknowns(tmp_path, monkeypatch, count):
    request = selected_request(count)
    before = deepcopy(request)
    adapter = CodeAsterPlasticityAdapter()
    original_defaults = list(adapter.default_metrics)
    declaration = adapter.describe_model(request)
    calls = configure_process_mock(tmp_path, monkeypatch)
    monkeypatch.setattr(domain, "_reference", lambda *a: pytest.fail("selected FE must not invoke the tensile oracle"))
    lab = Lab(tmp_path / "store", adapters={}, analysis_adapters={}, pde_adapters={}, doe_adapters={},
              optimization_adapters={}, model_analysis_adapters={adapter.backend: adapter},
              response_field_adapters={}, response_history_adapters={})
    lab.create_study("S-selected-j2", "TEST_ONLY selected J2", "Does the signed source persist?", "Numerical metadata only", "No native execution")
    result = lab.run_model_analysis(study_id="S-selected-j2", experiment_id="E-selected-j2", backend=adapter.backend, settings=request)
    assert result["status"] == "COMPLETED_REVIEW_REQUIRED", result["validations"]
    assert result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None and "parent_experiment_id" not in result
    assert result["model_revision"] == canonical_hash({"settings": request, "declaration": declaration})
    folder = lab.store / "experiments/E-selected-j2"
    proposal = load_json(folder / "proposal.json")
    assert proposal["execution"] == before and request == before
    assert adapter.default_metrics == original_defaults and "stress_xx_min" not in adapter.default_metrics
    assert "stress_xx_min" in proposal["outputs"]["metrics"]
    raw = load_json(folder / "simulation/analysis_raw.json")
    native = load_json(folder / "simulation/level_0/worker_result.json")
    parsed = load_json(folder / "simulation/level_0/parsed_history.json")
    assert raw["mode"] == native["mode"] == "selected_mesh"
    for output in (raw, native, raw["provenance"]):
        assert output["input_provenance"] == before["input_provenance"]
    assert raw["provenance"]["declared_limits"] == request["limits"]
    assert raw["provenance"]["units"] == {"time": "s", "strain": "1", "displacement": "mm", "stress": "MPa", "reaction": "N"}
    assert raw["provenance"]["nonlinear_policy"] == worker.NONLINEAR_POLICY
    assert [state["time_s"] for state in parsed["states"]] == request["history"]["times_s"]
    assert [state["actual_result_order"] for state in parsed["states"]] == [index * 3 for index in range(count)]
    assert len(raw["mesh_records"]) == len(raw["mesh_studies"]) == 1
    assert all(len(state["displacements_mm"]) == len(parsed["node_ids"]) for state in parsed["states"])
    assert all(len(state["nodal_reactions_n"]) == len(parsed["node_ids"]) for state in parsed["states"])
    assert all(len(state["stresses_mpa"]) == len(state["eq_plastic_strain"]) == 5 * parsed["element_count"] for state in parsed["states"])
    assert not (folder / "simulation/analytical_reference.json").exists() and not (folder / "simulation/level_1").exists()
    assert len([call for call in calls if call[2] == "solver"]) == 1
    assert len([call for call in calls if call[2] == "gmsh"]) == 1
    assert len(parsed["nonlinear_convergence"]["increments"]) == count - 1
    assert raw["reference"]["status"] == "UNKNOWN" and raw["reference"]["history"] is None
    assert raw["derived_energy"]["method"] is None and raw["derived_energy"]["native_energy_field"] is False
    assert result["metrics"]["final_stress"]["valid"] is True
    assert result["metrics"]["stress_xx_min"]["value"] <= 0.0
    assert result["metrics"]["stress_xx_max"]["value"] >= 0.0
    for name in ("peak_stress", "peak_eq_plastic_strain", "mesh_agreement_relative", "plastic_work_density", "reaction_relative_error"):
        assert result["metrics"][name]["value"] is None and result["metrics"][name]["valid"] is False
    unknown = {item["type"] for item in result["validations"] if item["status"] == "UNKNOWN"}
    assert {"reference_agreement", "mesh_convergence", "material_qualification", "model_qualification",
            "physical_validation", "static_strength", "fatigue_durability"} <= unknown
    assert lab.inspect_experiment("E-selected-j2") == result


@pytest.mark.parametrize("mutation", [
    lambda request: request.pop("input_provenance"),
    lambda request: request["input_provenance"].update(origin="QUALIFIED"),
    lambda request: request["input_provenance"].update(reference=" "),
    lambda request: request.update(mesh_sizes_mm=[2., 1.]),
    lambda request: request["history"].update(times_s=[0.], axial_strain=[0.]),
    lambda request: request["history"]["axial_strain"].__setitem__(1, -.01001),
    lambda request: request["history"]["times_s"].__setitem__(1, 0.),
    lambda request: request["material"].update(plastic_modulus_mpa=False),
])
def test_selected_invalid_input_never_reaches_native_runtime_or_mesher(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(elastic, "_image_identity", lambda *a: pytest.fail("Invalid selected input must not inspect runtime"))
    monkeypatch.setattr(elastic, "_process", lambda *a, **kw: pytest.fail("Invalid selected input must not start a process"))
    request = selected_request()
    mutation(request)
    before = deepcopy(request)
    outcome = CodeAsterPlasticityAdapter().solve(tmp_path / "simulation", request)
    assert outcome["status"] == "REJECTED" and outcome["solver_status"] == "NOT_RUN" and outcome["metrics"] == {}
    assert request == before and "reference_agreement" in outcome["pending_validations"]


@pytest.mark.parametrize("identity", ["mode", "input_provenance"])
def test_selected_native_source_identity_must_exactly_match_the_request(tmp_path, monkeypatch, identity):
    def corrupt(raw, folder):
        if identity == "mode":
            raw.pop("mode")
        else:
            raw["input_provenance"]["reference"] = "different source"
    configure_process_mock(tmp_path, monkeypatch, corrupt)
    with pytest.raises(RuntimeError, match="selected mode/input provenance"):
        CodeAsterPlasticityAdapter().solve(tmp_path / "simulation", selected_request())
    assert (tmp_path / "simulation/level_0/worker_result.json").is_file()
    assert not (tmp_path / "simulation/analysis_raw.json").exists()


@pytest.mark.parametrize("field,column", [("DEPL", "DZ"), ("REAC_NODA", "DY"),
                                          ("SIEF_ELGA", "SIXZ"), ("VARI_ELGA", "V1")])
def test_selected_full_native_coverage_is_required_at_every_interior_time(tmp_path, monkeypatch, field, column):
    def corrupt(raw, folder):
        raw["states"][3]["tables"][field].pop(column)
    configure_process_mock(tmp_path, monkeypatch, corrupt)
    with pytest.raises(RuntimeError, match="missing required columns"):
        CodeAsterPlasticityAdapter().solve(tmp_path / "simulation", selected_request())


def test_selected_failed_native_residual_retains_values_and_does_not_validate_absent_references(tmp_path, monkeypatch):
    def corrupt(raw, folder):
        text = (folder / "aster.mess").read_text(encoding="utf-8")
        text = text.replace("1.0E-13", "7.30000E-1", 1).replace("1.000000000000e-13", "7.300000000000e-1", 1)
        (folder / "aster.mess").write_text(text, encoding="utf-8")
    configure_process_mock(tmp_path, monkeypatch, corrupt)
    outcome = CodeAsterPlasticityAdapter().solve(tmp_path / "simulation", selected_request())
    assert outcome["status"] == "REJECTED" and outcome["solver_status"] == "COMPLETED" and outcome["converged"] is True
    assert outcome["metrics"]["final_stress"]["value"] is not None and outcome["metrics"]["final_stress"]["valid"] is False
    assert outcome["metrics"]["plastic_work_density"]["value"] is None
    assert "Not evaluated" in outcome["metrics"]["plastic_work_density"]["reason"]
    assert outcome["mesh_records"][0]["nonlinear_convergence"]["checks"][0]["observed"]["value"] == .73


def test_selected_real_worker_wires_original_signed_history_and_source_with_mocked_commands(tmp_path, monkeypatch):
    request = selected_request()
    mesh = mesh_fixture(tmp_path, request)
    raw = history_fixture(mesh, request)
    native = GuardNativeMesh(mesh, {"mesh": raw["mesh"]})
    save_json(tmp_path / "expected_mesh.json", elastic._expected_mesh(mesh))
    save_json(tmp_path / "input.json", {"settings": request, "mesh_sha256": elastic._sha256(tmp_path / "mesh.msh"),
                                      "expected_mesh_sha256": elastic._sha256(tmp_path / "expected_mesh.json")})
    monkeypatch.chdir(tmp_path)
    captured = {}
    commands = types.ModuleType("code_aster.Commands")
    result = types.SimpleNamespace(getAccessParameters=lambda: deepcopy(raw["access_parameters"]),
                                   getIndexes=lambda: list(raw["available_orders"]))

    def table(values):
        return types.SimpleNamespace(EXTR_TABLE=lambda: types.SimpleNamespace(values=lambda: deepcopy(values)))

    def debut():
        (tmp_path / "fort.20").write_bytes((tmp_path / "mesh.msh").read_bytes())

    def record(name, value):
        captured[name] = deepcopy(value)
        return value

    commands.DEBUT = debut
    commands.LIRE_MAILLAGE = lambda **kw: native
    commands.DEFI_GROUP = lambda **kw: native
    commands.AFFE_MODELE = lambda **kw: kw
    commands.DEFI_MATERIAU = lambda **kw: record("material", kw)
    commands.AFFE_MATERIAU = lambda **kw: kw
    commands.AFFE_CHAR_MECA = lambda **kw: kw
    commands.DEFI_FONCTION = lambda **kw: record("history", kw)
    commands.DEFI_LIST_REEL = lambda **kw: record("instants", kw)
    commands.STAT_NON_LINE = lambda **kw: result
    commands.CALC_CHAMP = lambda **kw: result
    commands.CREA_TABLE = lambda **kw: table(next(state for state in raw["states"] if state["order"] == kw["RESU"]["NUME_ORDRE"])["tables"][kw["RESU"]["NOM_CHAM"]])
    commands.POST_RELEVE_T = lambda **kw: table(next(state for state in raw["states"] if state["order"] == kw["ACTION"][0]["NUME_ORDRE"])["tables"]["BOUNDARY_RESULTANTS"])
    commands.IMPR_RESU = lambda **kw: captured.update(archived=kw["RESU"]["TOUT_ORDRE"])
    commands.FIN = lambda: captured.update(finished=True)
    syntax = types.ModuleType("code_aster.Cata.Syntax")
    syntax._F = lambda **kw: kw
    monkeypatch.setitem(sys.modules, "code_aster.Commands", commands)
    monkeypatch.setitem(sys.modules, "code_aster.Cata.Syntax", syntax)
    monkeypatch.setattr(worker, "_runtime_versions", lambda: ({"code_aster": "17.4.0"}, {"version": "17.4.0"}))
    worker.solve_level(str(tmp_path / "input.json"))
    saved = load_json(tmp_path / "worker_result.json")
    assert captured["history"]["ABSCISSE"] == request["history"]["times_s"]
    assert captured["history"]["ORDONNEE"] == request["history"]["axial_strain"]
    assert captured["history"]["INTERPOL"] == "LIN" and captured["history"]["PROL_DROITE"] == "EXCLU"
    assert captured["instants"]["VALE"] == request["history"]["times_s"]
    assert captured["material"]["ECRO_LINE"]["D_SIGM_EPSI"] == 210000. * (1000. / 211000.)
    assert saved["mode"] == "selected_mesh" and saved["input_provenance"] == request["input_provenance"]
    assert saved["nonlinear_policy"] == worker.NONLINEAR_POLICY and captured["archived"] == "OUI" and captured["finished"]
    parsed = worker.parse_history_tables(saved, request["mesh_sizes_mm"][0], request["history"]["times_s"])
    assert len(parsed["states"]) == len(request["history"]["times_s"])
    assert any(state["stresses_mpa"][0][0] < 0 for state in parsed["states"])
