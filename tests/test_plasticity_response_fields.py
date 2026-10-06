"""Portable synthetic J2 protocol controls; no native/physical proof or runs."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from caelab.adapters import plasticity_response_fields as reader
from caelab.adapters import codeaster_plasticity_worker as worker
from plugins.elasticity import plasticity_reference as domain


ADAPTER = reader.PlasticityResponseFieldsAdapter()


def payload(value):
    return value if type(value) is bytes else (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(payload(value)).hexdigest()


def settings(selected=False):
    request = {"case": "uniaxial_j2_isotropic_hardening", "dimensions_mm": [20., 4., 2.],
        "material": {"youngs_modulus_mpa": 210000., "poisson_ratio": .3, "yield_stress_mpa": 250., "plastic_modulus_mpa": 1000.},
        "history": {"times_s": list(range(10)), "axial_strain": [0., .0005, .001, .0015, .002, .003, .006, .0055, .005, .0045]},
        "mesh_sizes_mm": [2., 1.], "limits": {"displacement_relative": 1e-7, "displacement_absolute_mm": 1e-10,
            "stress_relative": 1e-7, "stress_absolute_mpa": 1e-8, "plastic_strain_absolute": 1e-9,
            "reaction_relative": 1e-7, "reaction_absolute_n": 1e-8, "mesh_agreement_relative": 1e-7,
            "plastic_dissipation_relative": 1e-6, "plastic_dissipation_absolute_mpa": 1e-8}}
    if selected:
        request.update(mode="selected_mesh", input_provenance={"origin": "SYNTHETIC", "reference": "  TEST_ONLY; no solver execution  "})
        request["mesh_sizes_mm"] = [2.]
        request["history"] = {"times_s": [0., .25, .5, 1.], "axial_strain": [0., .0001, .0001, -.0001]}
    return domain.validate_settings(request)


def original_mesh(dimensions):
    """Six positive straight TETRA10s; source and actual IDs differ deliberately."""
    x, y, z = dimensions
    corners = [[0., 0., 0.], [x, 0., 0.], [x, y, 0.], [0., y, 0.],
               [0., 0., z], [x, 0., z], [x, y, z], [0., y, z]]
    ids = [10 * (i + 1) for i in range(8)]
    coordinates = dict(zip(ids, corners))
    mids = {}
    tets = []
    for index, pattern in enumerate(((0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6))):
        nodes = [ids[i] for i in pattern]
        connectivity = list(nodes)
        for a, b in ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3)):
            edge = tuple(sorted((nodes[a], nodes[b])))
            if edge not in mids:
                mids[edge] = 100 + 7 * len(mids)
                coordinates[mids[edge]] = [(p + q) / 2 for p, q in zip(coordinates[edge[0]], coordinates[edge[1]])]
            connectivity.append(mids[edge])
        tets.append({"element_id": 1000 + index * 100, "node_ids": connectivity})
    groups = {name: sorted(node for node, point in coordinates.items() if point[axis] == target)
              for name, axis, target in (("X0", 0, 0.), ("XL", 0, x), ("Y0", 1, 0.), ("Z0", 2, 0.))}
    return {"schema_version": "1", "source_format": "GMSH2.2", "node_ids": sorted(coordinates),
        "coordinates_mm": [coordinates[node] for node in sorted(coordinates)], "tetrahedra": tets,
        "group_node_ids": groups, "total_cell_count": 14,
        "physical_groups": {"BODY": {"dimension": 3, "tag": 1001}, "X0": {"dimension": 2, "tag": 1002},
            "XL": {"dimension": 2, "tag": 1003}, "Y0": {"dimension": 2, "tag": 1004}, "Z0": {"dimension": 2, "tag": 1005}},
        "importer_policy": "TEST_ONLY synthetic original topology"}


def native_history(request, expected):
    source = dict(zip(expected["node_ids"], expected["coordinates_mm"]))
    mapping = list(reversed(expected["node_ids"]))
    native_id = {node: i + 1 for i, node in enumerate(mapping)}
    coordinates = {i + 1: source[node] for i, node in enumerate(mapping)}
    groups = {name: [native_id[node] for node in ids] for name, ids in expected["group_node_ids"].items()}
    bodies = list(range(9, 15))
    catalog = {"nodes": [{"node_id": node, "name": str(node), "coordinates_mm": coordinates[node]} for node in coordinates],
        "body_elements": [{"element_id": cell, "name": str(cell)} for cell in bodies], "group_node_ids": groups,
        "support_node_ids": sorted(set().union(*(set(groups[name]) for name in ("X0", "Y0", "Z0")))),
        "gauss_point_ids": [1, 2, 3, 4, 5], "name_api": "TEST_ONLY decimal native IDs"}
    states = []
    for index, time in enumerate(request["history"]["times_s"]):
        order = index * 3
        displacement = {key: [] for key in ("NOEUD", "NUME_ORDRE", "COOR_X", "COOR_Y", "COOR_Z", "DX", "DY", "DZ")}
        reaction = deepcopy(displacement)
        reactions = {}
        for node in reversed(coordinates):
            reactions[node] = [-10. * index / len(groups["X0"]) if node in groups["X0"] else
                               10. * index / len(groups["XL"]) if node in groups["XL"] else 0.,
                               -2. * index / len(groups["Y0"]) if node in groups["Y0"] else 0.,
                               3. * index / len(groups["Z0"]) if node in groups["Z0"] else 0.]
            for table, values in ((displacement, [index * node * .001, -index * node * .002, index * node * .003]), (reaction, reactions[node])):
                table["NOEUD"].append(str(node) + " ")
                table["NUME_ORDRE"].append(order)
                for key, value in zip(worker.COORDINATE_COMPONENTS, coordinates[node]):
                    table[key].append(value)
                for key, value in zip(worker.VECTOR_COMPONENTS, values):
                    table[key].append(value)
        stress = {key: [] for key in ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", *worker.COORDINATE_COMPONENTS, *worker.STRESS_COMPONENTS)}
        plastic = {key: [] for key in ("MAILLE", "POINT", "SOUS_POINT", "NUME_ORDRE", *worker.COORDINATE_COMPONENTS, "V1", "V2")}
        for cell, tet in reversed(list(zip(bodies, expected["tetrahedra"]))):
            centroid = [sum(source[node][axis] for node in tet["node_ids"][:4]) / 4 for axis in range(3)]
            for point in reversed(range(1, 6)):
                for table in (stress, plastic):
                    for key, value in (("MAILLE", str(cell) + " "), ("POINT", point), ("SOUS_POINT", 1), ("NUME_ORDRE", order)):
                        table[key].append(value)
                    for key, value in zip(worker.COORDINATE_COMPONENTS, centroid):
                        table[key].append(value)
                value = index * (10 * (point - 3) - cell)
                for key, value in zip(worker.STRESS_COMPONENTS, [value, -value, 2 * value, .1 * value, -.2 * value, .3 * value]):
                    stress[key].append(value)
                plastic["V1"].append(index * .001 * (point - 2))  # Negative finite native observation is retained.
                plastic["V2"].append(float(index > 0))
        post = {key: [] for key in ("INTITULE", "NUME_ORDRE", "INST", *worker.VECTOR_COMPONENTS)}
        for group in ("X0", "XL", "Y0", "Z0"):
            post["INTITULE"].append(group)
            post["NUME_ORDRE"].append(order)
            post["INST"].append(time)
            for axis, key in enumerate(worker.VECTOR_COMPONENTS):
                post[key].append(sum(reactions[node][axis] for node in groups[group]))
        states.append({"order": order, "time_s": time, "tables": {"DEPL": displacement, "REAC_NODA": reaction,
            "SIEF_ELGA": stress, "VARI_ELGA": plastic, "BOUNDARY_RESULTANTS": post}})
    orders = [state["order"] for state in states]
    material = request["material"]
    e, h = material["youngs_modulus_mpa"], material["plastic_modulus_mpa"]
    return {"schema_version": "1", "solver_status": "COMPLETED", "converged": True,
        "available_orders": list(reversed(orders)), "access_parameters": {"NUME_ORDRE": list(reversed(orders)),
            "INST": list(reversed(request["history"]["times_s"]))}, "mesh": catalog, "states": states,
        "versions": {"code_aster": "17.4.0", "python": "TEST_ONLY", "numpy": "TEST_ONLY"},
        "code_aster_runtime": {"version": "17.4.0", "parentid": "TEST_ONLY_UNSOLVED"},
        "native_mesh_checks": {"status": "PASS", "support_union_verified": True, "node_count": len(mapping),
            "volume_element_count": len(bodies), "total_cell_count": expected["total_cell_count"],
            "coordinate_tolerances": {"relative": 1e-12, "absolute": 1e-12}, "minimum_native_jacobian_mm3": 160.,
            "source_node_ids_by_native_index": mapping, "source_element_mapping": [
                {"native_cell_index": cell - 1, "source_element_id": tet["element_id"]} for cell, tet in zip(bodies, expected["tetrahedra"])],
            "native_group_node_indices": {name: [node - 1 for node in nodes] for name, nodes in groups.items()},
            "topology": "TEST_ONLY checked source topology", "solver_gate": "Verified before STAT_NON_LINE"},
        "numerical_libraries": None, "convergence_evidence": "TEST_ONLY native archived orders; no solver run",
        "nonlinear_policy": deepcopy(worker.NONLINEAR_POLICY), "native_material": {"ELAS": {"E": e, "NU": material["poisson_ratio"]},
            "ECRO_LINE": {"SY": material["yield_stress_mpa"], "D_SIGM_EPSI": e * (h / (e + h))}}, "measured_linear_residual": None}


class Fixture:
    def __init__(self, *, selected=False, version="1.2", rejected=False):
        self.files = {}
        self.settings = settings(selected)
        self.files["simulation/input.json"] = deepcopy(self.settings)
        sources = {name: ("TEST_ONLY_UNSOLVED_SOURCE " + name).encode() for name in reader._SOURCES[version]}
        self.files.update({"simulation/" + name: value for name, value in sources.items()})
        records = []
        for index, size in enumerate(self.settings["mesh_sizes_mm"]):
            prefix = f"simulation/level_{index}/"
            expected = original_mesh(self.settings["dimensions_mm"])
            raw = native_history(self.settings, expected)
            mesh = ("TEST_ONLY_UNSOLVED_MESH " + str(index)).encode()
            self.files[prefix + "mesh.msh"] = mesh
            self.files[prefix + "results.med"] = b"TEST_ONLY_UNSOLVED_MED"
            self.files[prefix + "expected_mesh.json"] = expected
            self.files[prefix + "mesh_catalog.json"] = deepcopy(raw["mesh"])
            config = {"settings": deepcopy(self.settings), "mesh_size_mm": size, "mesh_sha256": digest(mesh), "expected_mesh_sha256": digest(expected)}
            self.files[prefix + "input.json"] = config
            raw.update(input_sha256=digest(config), mesh_input_sha256=digest(mesh))
            raw["native_mesh_checks"].update(checked_msh_sha256=digest(mesh), expected_mesh_sha256=digest(expected))
            if selected:
                raw.update(mode="selected_mesh", input_provenance=deepcopy(self.settings["input_provenance"]))
            self.files[prefix + "worker_result.json"] = raw
            for state in raw["states"]:
                for name, table in state["tables"].items():
                    self.files[prefix + f"order_{state['order']}_{name.lower()}.table.json"] = deepcopy(table)
            record = worker.parse_history_tables(raw, size, self.settings["history"]["times_s"])
            record["nonlinear_convergence"] = {"status": "PASS", "native_limits": deepcopy(worker.NONLINEAR_POLICY),
                "initial_state": {"time_s": 0., "status": "INITIAL_STATE_NO_NEWTON_INCREMENT"},
                "increments": [{"time_s": t, "iterations": [{"iteration": 0}]} for t in self.settings["history"]["times_s"][1:]]}
            self.files[prefix + "parsed_history.json"] = record
            records.append(deepcopy(record))
        detail = {"adapter": reader.BACKEND, "adapter_version": version, "captured_source_sha256": {k: digest(v) for k, v in sources.items()},
            "domain_plugin": {"module": "plugins.elasticity.plasticity_reference", "version": "1",
                "source_artifact": "simulation/domain_reference.py", "source_sha256": digest(sources["domain_reference.py"])},
            "reused_native_guard": "caelab.adapters.codeaster_worker.validate_native_mesh", "oci_manifest_sha256": reader._OCI,
            "nonlinear_policy": deepcopy(worker.NONLINEAR_POLICY), "input_sha256": digest(self.settings),
            "versions": {"code_aster": "17.4.0", "python": "TEST_ONLY", "numpy": "TEST_ONLY", "gmsh": "TEST_ONLY"},
            "code_aster_runtime": {"version": "17.4.0", "parentid": "TEST_ONLY_UNSOLVED"}, "measured_linear_residual": None,
            "mesh": [f"simulation/level_{i}/mesh.msh" for i in range(len(records))],
            "native_fields": [f"simulation/level_{i}/results.med" for i in range(len(records))]}
        if selected:
            detail.update(mode="selected_mesh", scope=domain.SELECTED_SCOPE, input_provenance=deepcopy(self.settings["input_provenance"]),
                          declared_limits=deepcopy(self.settings["limits"]), units=deepcopy(reader._UNITS))
        metrics = {"final_stress": {"value": None, "unit": "MPa", "valid": False, "reason": "TEST_ONLY recorded invalid metric; never replace by point value"}}
        outcome = {"status": "REJECTED" if rejected else "COMPLETED", "solver_status": "COMPLETED", "converged": True,
            "checks": [{"code": "TEST_ONLY_RECORDED_VERDICT", "status": "FAIL" if rejected else "PASS"}],
            "metrics": deepcopy(metrics), "raw_result": "simulation/analysis_raw.json", "provenance": deepcopy(detail), "mesh_records": records,
            "reference": {"status": "UNKNOWN"}, "derived_energy": {"status": "UNKNOWN", "native_energy_field": False}}
        if selected:
            outcome.update(mode="selected_mesh", scope=domain.SELECTED_SCOPE, input_provenance=deepcopy(self.settings["input_provenance"]))
        self.files["simulation/analysis_raw.json"] = outcome
        self.result = {"status": "REJECTED" if rejected else "COMPLETED_REVIEW_REQUIRED", "solver_status": "COMPLETED", "converged": True,
            "decision": "NOT_RELEASED", "cad_revision": None, "experiment_id": "E-j2-test", "study": {"id": "S-j2-test"},
            "model_revision": "a" * 64, "proposal_revision": "b" * 64, "metrics": metrics,
            "provenance": {"adapter": reader.BACKEND, "adapter_version": version, "proposal_sha256": "b" * 64,
                "execution_settings": deepcopy(self.settings), "adapter_details": detail}}
        declaration = domain.model_declaration(self.settings)
        model = {name: declaration[name] for name in ("geometry", "materials", "mesh")}
        self.proposal = {"id": "E-j2-test", "study_id": "S-j2-test", "model_revision": "a" * 64, "cad_revision": None,
            "physics": {"backend": reader.BACKEND}, "execution": deepcopy(self.settings), "model": model}
        self.seal()

    def seal(self):
        self.result["artifacts"] = [{"path": path, "sha256": digest(value), "size_bytes": len(payload(value)),
            "revision": self.result["proposal_revision"]} for path, value in self.files.items()]

    def entry(self, path):
        return next(a for a in self.result["artifacts"] if a["path"] == path)

    def resource(self, policy):
        return {role: (self.files[spec["path"]], self.entry(spec["path"])) for role, spec in policy.items()}

    def headers(self):
        return self.resource(ADAPTER.field_response_resources(self.result))

    def selection(self, *, gauss=False, index=0, time=1, component=None):
        path = f"simulation/level_{index}/parsed_history.json"
        common = {"kind": "fe_gauss" if gauss else "fe_nodal", "artifact": path, "sha256": self.entry(path)["sha256"],
            "model_revision": self.result["model_revision"], "mesh_index": index, "time_index": time,
            "component": component or ("SIEF_ELGA.SIXX" if gauss else "DEPL.DY")}
        common.update({"element_id": 9, "point": 1, "subpoint": 1} if gauss else {"node_id": 1})
        return common

    def selected_resources(self, selection):
        headers = self.headers()
        return {**headers, **self.resource(ADAPTER.field_selection_resources(self.result, selection, headers))}

    def select(self, selection=None):
        selection = selection or self.selection()
        return ADAPTER.select_response_fields(self.result, self.proposal, self.selected_resources(selection), selection)

    def channels(self):
        return ADAPTER.response_history_channels(self.result, self.proposal, self.resource(ADAPTER.history_response_resources(self.result)))


@pytest.mark.parametrize("selected,version", [(False, "1"), (False, "1.2"), (True, "1.2")])
def test_current_and_original_producers_preserve_exact_node_gauss_and_source(selected, version):
    f = Fixture(selected=selected, version=version)
    before = deepcopy((f.result, f.proposal, f.files))
    display = ADAPTER.display_response_fields(f.result, f.proposal, f.headers())
    assert display["kind"] == "j2_fe_fields" and len(display["meshes"]) == (1 if selected else 2)
    assert "values" not in display["meshes"][0]
    assert display["meshes"][0]["gauss_ids"][0] == {"element_id": 9, "point": 1, "subpoint": 1}
    nodal, gauss = f.select(), f.select(f.selection(gauss=True))
    assert nodal["value"] == -.002 and nodal["unit"] == "mm"
    assert gauss["value"] == -29 and gauss["unit"] == "MPa"
    assert nodal["source_field"]["actual_result_order"] == 3
    assert nodal["source_field"]["coordinates_mm"] == f.files["simulation/level_0/mesh_catalog.json"]["nodes"][0]["coordinates_mm"]
    assert gauss["source_field"]["coordinates_mm"] != nodal["source_field"]["coordinates_mm"]
    assert gauss["source_field"]["component"] == "SIEF_ELGA.SIXX"
    assert gauss["qualification"]["physical"] == "UNKNOWN" and gauss["qualification"]["decision"] == "NOT_RELEASED"
    assert nodal["source_field"]["raw_sha256"] == f.entry("simulation/level_0/worker_result.json")["sha256"]
    assert (f.result, f.proposal, f.files) == before


@pytest.mark.parametrize("component,unit,quantity", [("DEPL.DX", "mm", "DISPLACEMENT"), ("DEPL.DZ", "mm", "DISPLACEMENT"),
    ("REAC_NODA.DX", "N", "NODAL_REACTION"), ("REAC_NODA.DY", "N", "NODAL_REACTION"), ("REAC_NODA.DZ", "N", "NODAL_REACTION"),
    ("SIEF_ELGA.SIXX", "MPa", "STRESS"), ("SIEF_ELGA.SIYY", "MPa", "STRESS"), ("SIEF_ELGA.SIZZ", "MPa", "STRESS"),
    ("SIEF_ELGA.SIXY", "MPa", "STRESS"), ("SIEF_ELGA.SIXZ", "MPa", "STRESS"), ("SIEF_ELGA.SIYZ", "MPa", "STRESS"),
    ("VARI_ELGA.V1", "1", "EQUIVALENT_PLASTIC_STRAIN")])
def test_components_are_original_signed_values_with_exact_units_and_locations(component, unit, quantity):
    f = Fixture(selected=True)
    selection = f.selection(gauss=component.startswith(("SIEF", "VARI")), component=component)
    value = f.select(selection)
    assert value["unit"] == unit and value["source_field"]["quantity"] == quantity
    assert value["source_field"]["value_origin"] == "NATIVE_COMPONENT"
    if component == "VARI_ELGA.V1":
        assert value["value"] == -.001  # Retain finite invalid observation without clipping.


def test_nodal_reaction_preserves_signed_force_and_never_becomes_pressure():
    f = Fixture(selected=True)
    record = f.files["simulation/level_0/parsed_history.json"]
    selection = f.selection(component="REAC_NODA.DX")
    selection["node_id"] = record["group_node_ids"]["X0"][0]
    value = f.select(selection)
    assert value["value"] < 0 and value["source_field"]["measure"] == "signed native nodal reaction"


def test_initial_actual_order_is_no_newton_increment_for_points_and_histories():
    f = Fixture(selected=True)
    for gauss in (False, True):
        value = f.select(f.selection(gauss=gauss, time=0))
        assert value["response_axis"] == {"quantity": "time", "value": 0., "unit": "s"}
        assert value["qualification"]["numeric"] == "INITIAL_STATE_NO_NEWTON_INCREMENT"
        assert value["source_field"]["initial_state"]["actual_result_order"] == 0
    assert "initial_state" not in f.select()["source_field"]
    assert all(channel["initial_state"]["kind"] == "INITIAL_STATE_NO_NEWTON_INCREMENT" for channel in f.channels())


def test_exact_finest_history_has_four_native_resultants_and_seven_explicit_unweighted_means():
    f = Fixture(version="1")
    channels = {channel["id"]: channel for channel in f.channels()}
    assert len(channels) == 11
    assert channels["j2-x0-fx"]["values"][1] == pytest.approx(-10.)
    assert channels["j2-xl-fx"]["values"][1] == pytest.approx(10.)
    assert channels["j2-y0-fy"]["values"][1] == pytest.approx(-2.)
    assert channels["j2-z0-fz"]["values"][1] == pytest.approx(3.)
    mean = channels["j2-gauss-mean-sixx"]
    assert mean["values"][1] == pytest.approx(-11.5)
    assert mean["origin"]["kind"] == "DERIVED" and mean["origin"]["aggregation"]["weighting"] == "UNWEIGHTED"
    assert mean["origin"]["aggregation"]["point_count"] == 30 and mean["origin"]["aggregation"]["volume_average"] is False
    assert mean["origin"]["mesh_index"] == 1 and mean["origin"]["artifact"] == "simulation/level_1/parsed_history.json"
    assert mean["origin"]["native_sha256"] == f.entry("simulation/level_1/worker_result.json")["sha256"]
    assert mean["origin"]["actual_result_orders"] == list(range(0, 30, 3))
    assert all(channel["metric"] is None and channel["axis"]["unit"] == "s" for channel in channels.values())
    assert not any("energy" in channel["id"] for channel in channels.values())


def test_resource_policy_is_two_headers_plus_exact_selected_level_or_finest_seven_bounded_jsons():
    f = Fixture()
    base = ADAPTER.field_response_resources(f.result)
    assert len(base) == 2
    additional = ADAPTER.field_selection_resources(f.result, f.selection(index=0), f.headers())
    assert len(additional) == 5 and not base.keys() & additional.keys()
    assert all(spec["path"].startswith("simulation/level_0/") for spec in additional.values())
    history = ADAPTER.history_response_resources(f.result)
    assert len(history) == 7 and all(spec["maximum_bytes"] <= 64 * 1024 * 1024 for spec in history.values())
    assert all(spec["path"].startswith("simulation/level_1/") for role, spec in history.items() if role not in base)


@pytest.mark.parametrize("gauss,key,value", [(False, "node_id", 0), (False, "node_id", True), (False, "node_id", 999),
    (False, "node_id", 1.), (False, "mesh_index", True), (False, "mesh_index", -1), (False, "mesh_index", 1),
    (False, "time_index", True), (False, "time_index", 99), (False, "component", "SIEF_ELGA.SIXX"),
    (False, "component", "DEPL.MAGNITUDE"), (False, "sha256", "0" * 64), (False, "model_revision", "0" * 64),
    (False, "artifact", "simulation/level_1/parsed_history.json"), (True, "element_id", 1), (True, "point", True),
    (True, "point", 6), (True, "subpoint", 2), (True, "component", "DEPL.DX"), (True, "component", "VARI_ELGA.V2")])
def test_selector_refuses_exact_identity_component_family_and_bool_errors(gauss, key, value):
    f = Fixture(selected=True)
    selection = f.selection(gauss=gauss)
    selection[key] = value
    with pytest.raises(ValueError):
        f.select(selection)


def test_exact_selector_keys_and_resource_tuple_manifest_are_required():
    f = Fixture(selected=True)
    selection = f.selection()
    selection["unit"] = "mm"
    with pytest.raises(ValueError):
        f.select(selection)
    selection = f.selection(gauss=True)
    selection["node_id"] = 1
    with pytest.raises(ValueError):
        f.select(selection)
    selection = f.selection()
    resources = f.selected_resources(selection)
    raw, entry = resources["parsed"]
    resources["parsed"] = (raw, {**entry, "sha256": "c" * 64})
    with pytest.raises(ValueError):
        ADAPTER.select_response_fields(f.result, f.proposal, resources, selection)
    resources = f.selected_resources(selection)
    resources["unadvertised"] = resources["native"]
    with pytest.raises(ValueError):
        ADAPTER.select_response_fields(f.result, f.proposal, resources, selection)


@pytest.mark.parametrize("corrupt", [
    lambda f: f.proposal.update(model_revision="0" * 64),
    lambda f: f.proposal.update(study_id="S-foreign"),
    lambda f: f.proposal["model"]["geometry"].update(unit="m"),
    lambda f: f.proposal["model"]["mesh"].update(order=True),
    lambda f: f.proposal["model"]["materials"][0]["yield_stress"].update(unit="Pa"),
    lambda f: f.proposal["model"]["materials"][0].update(kinematics="finite_strain"),
    lambda f: f.proposal["execution"]["history"]["times_s"].__setitem__(1, True),
    lambda f: f.result["provenance"]["adapter_details"]["captured_source_sha256"].update(unadvertised="0" * 64),
    lambda f: f.result["provenance"]["adapter_details"]["captured_source_sha256"].pop("domain_reference.py"),
    lambda f: f.result["provenance"]["adapter_details"].update(oci_manifest_sha256="0" * 64),
    lambda f: f.result["provenance"]["adapter_details"]["domain_plugin"].update(version="2"),
    lambda f: f.files.update({"simulation/domain_reference.py": b"CHANGED_CAPTURED_SOURCE"}),
])
def test_source_request_model_and_producer_identity_must_match(corrupt):
    f = Fixture(selected=True)
    corrupt(f)
    f.seal()
    with pytest.raises(ValueError):
        f.select()


@pytest.mark.parametrize("kind", ["mode", "source", "units", "limits", "worker_source"])
def test_selected_original_input_provenance_units_and_mode_remain_explicit(kind):
    f = Fixture(selected=True)
    assert f.settings["input_provenance"]["reference"].startswith("  ")
    if kind == "mode":
        f.files["simulation/analysis_raw.json"].pop("mode")
    elif kind == "source":
        f.files["simulation/analysis_raw.json"]["input_provenance"]["origin"] = "MEASURED_REPORTED"
    elif kind == "units":
        f.result["provenance"]["adapter_details"]["units"]["time"] = "1"
    elif kind == "limits":
        f.result["provenance"]["adapter_details"]["declared_limits"]["stress_relative"] *= 2
    else:
        f.files["simulation/level_0/worker_result.json"]["input_provenance"]["reference"] = "replaced"
    f.seal()
    with pytest.raises(ValueError):
        f.select()


@pytest.mark.parametrize("path,corrupt", [
    ("input.json", lambda v: v.update(mesh_size_mm=1.)),
    ("input.json", lambda v: v.update(expected_mesh_sha256="0" * 64)),
    ("worker_result.json", lambda v: v.update(input_sha256="0" * 64)),
    ("worker_result.json", lambda v: v.update(units={"time": "1", "stress": "Pa"})),
    ("worker_result.json", lambda v: v.update(coordinate_frame="sensor_world")),
    ("worker_result.json", lambda v: v.update(mesh_input_sha256="0" * 64)),
    ("worker_result.json", lambda v: v["versions"].update(code_aster="17.5.0")),
    ("worker_result.json", lambda v: v["native_material"]["ELAS"].update(NU=True)),
    ("worker_result.json", lambda v: v["nonlinear_policy"].update(maximum_iterations=50)),
    ("worker_result.json", lambda v: v["access_parameters"]["INST"].__setitem__(0, 1.1)),
    ("worker_result.json", lambda v: v["available_orders"].__setitem__(0, True)),
    ("worker_result.json", lambda v: v["states"][1]["tables"]["DEPL"]["DX"].__setitem__(0, -99.)),
    ("worker_result.json", lambda v: v["states"][1]["tables"]["REAC_NODA"]["DZ"].__setitem__(0, True)),
    ("worker_result.json", lambda v: v["states"][1]["tables"]["SIEF_ELGA"]["POINT"].__setitem__(0, 6)),
    ("worker_result.json", lambda v: v["states"][1]["tables"]["VARI_ELGA"]["V1"].pop()),
    ("worker_result.json", lambda v: v["native_mesh_checks"]["source_node_ids_by_native_index"].reverse()),
    ("worker_result.json", lambda v: v["native_mesh_checks"]["source_element_mapping"][0].update(native_cell_index=0)),
    ("worker_result.json", lambda v: v["native_mesh_checks"]["native_group_node_indices"]["X0"].pop()),
    ("worker_result.json", lambda v: v["native_mesh_checks"].update(support_union_verified=False)),
    ("mesh_catalog.json", lambda v: v["nodes"][0]["coordinates_mm"].__setitem__(0, -1.)),
    ("mesh_catalog.json", lambda v: v["body_elements"][0].update(element_id=999)),
    ("mesh_catalog.json", lambda v: v["gauss_point_ids"].pop()),
    ("expected_mesh.json", lambda v: v["node_ids"].pop()),
    ("expected_mesh.json", lambda v: v["tetrahedra"][0]["node_ids"].__setitem__(4, 999)),
    ("expected_mesh.json", lambda v: v["physical_groups"]["BODY"].update(tag=999)),
    ("parsed_history.json", lambda v: v["states"][1]["stresses_mpa"][0].__setitem__(0, -999.)),
])
def test_rehashed_level_tamper_is_not_silently_joined_to_other_source_or_recomputed(path, corrupt):
    f = Fixture(selected=True)
    corrupt(f.files["simulation/level_0/" + path])
    f.seal()
    with pytest.raises(ValueError):
        f.select()


@pytest.mark.parametrize("name,corrupt", [
    ("node_ids", lambda r: r["node_ids"].__setitem__(0, True)),
    ("node_ids", lambda r: r["node_ids"].__setitem__(0, r["node_ids"][1])),
    ("coordinates_mm", lambda r: r["coordinates_mm"].pop()),
    ("coordinates_mm", lambda r: r["coordinates_mm"][0].__setitem__(2, 3.)),
    ("stress_component_order", lambda r: r["stress_component_order"].reverse()),
    ("states", lambda r: r["states"].pop()),
    ("time", lambda r: r["states"][1].update(time_s=True)),
    ("order", lambda r: r["states"][1].update(actual_result_order=True)),
    ("gauss", lambda r: r["states"][1]["stress_identifiers"][0].update(point=True)),
    ("gauss", lambda r: r["states"][1]["stress_identifiers"].pop()),
    ("gauss", lambda r: r["states"][1]["stress_identifiers"][0].update(element_id=999)),
    ("value", lambda r: r["states"][1]["stresses_mpa"][0].__setitem__(0, True)),
    ("initial", lambda r: r["nonlinear_convergence"]["initial_state"].update(status="CONVERGED")),
])
def test_display_catalog_also_refuses_malformed_complete_metadata(name, corrupt):
    f = Fixture(selected=True)
    corrupt(f.files["simulation/analysis_raw.json"]["mesh_records"][0])
    f.seal()
    with pytest.raises(ValueError):
        ADAPTER.display_response_fields(f.result, f.proposal, f.headers())


def test_separate_native_table_artifacts_are_bound_to_the_embedded_raw_tables():
    f = Fixture(selected=True)
    f.files["simulation/level_0/order_3_sief_elga.table.json"]["SIXX"][0] *= 2
    f.seal()
    with pytest.raises(ValueError, match="table bytes"):
        f.select(f.selection(gauss=True))


@pytest.mark.parametrize("bad", [float("inf"), float("nan"), float("-inf")])
def test_nonfinite_supplied_json_is_refused_even_when_manifest_entry_is_preverified(bad):
    f = Fixture(selected=True)
    selection = f.selection()
    resources = f.selected_resources(selection)
    resources["native"][0]["states"][1]["tables"]["DEPL"]["DX"][0] = bad
    with pytest.raises(ValueError, match="Nonfinite"):
        ADAPTER.select_response_fields(f.result, f.proposal, resources, selection)


def test_bound_revision_alias_and_foreign_resource_entry_refusal():
    f = Fixture(selected=True)
    f.entry("simulation/analysis_raw.json")["size_bytes"] = reader.JSON_LIMIT + 1
    with pytest.raises(ValueError):
        f.headers()
    f = Fixture(selected=True)
    f.result["artifacts"].append({**f.entry("simulation/input.json"), "path": "Simulation/input.json"})
    with pytest.raises(ValueError):
        f.headers()
    f = Fixture(selected=True)
    f.entry("simulation/level_0/worker_result.json")["revision"] = "c" * 64
    with pytest.raises(ValueError):
        f.headers()


def test_numerically_rejected_native_values_are_read_without_releasing_or_revalidating_metrics():
    f = Fixture(selected=True, rejected=True)
    original = deepcopy(f.result)
    value = f.select(f.selection(gauss=True))
    assert value["value"] == -29 and value["qualification"]["reference"] == "RECORDED_DOMAIN_VERDICT_UNCHANGED"
    assert len(f.channels()) == 11
    assert f.result == original and f.result["metrics"]["final_stress"]["valid"] is False


@pytest.mark.parametrize("status,solver,converged", [("FAILED_EXECUTION", "FAILED", None), ("REJECTED", "NOT_RUN", None),
    ("CANCELLED", "CANCELLED", False), ("COMPLETED_REVIEW_REQUIRED", "COMPLETED", False)])
def test_execution_failure_is_not_a_numerically_rejected_usable_native_field(status, solver, converged):
    f = Fixture()
    f.result.update(status=status, solver_status=solver, converged=converged)
    with pytest.raises(ValueError):
        f.select()


@pytest.mark.parametrize("backend,version", [("structural.code_aster", "1.2"), ("structural.code_aster.geometric", "1.2"),
    ("structural.code_aster.plasticity", "1.1"), ("structural.code_aster.plasticity", "2")])
def test_unsupported_family_or_uninspected_producer_version_is_not_admitted(backend, version):
    f = Fixture()
    f.result["provenance"].update(adapter=backend, adapter_version=version)
    with pytest.raises(ValueError):
        f.headers()


def test_history_does_not_read_a_different_level_even_if_fields_and_coordinates_coincide():
    f = Fixture()
    resources = f.resource(ADAPTER.history_response_resources(f.result))
    resources["parsed"] = (f.files["simulation/level_0/parsed_history.json"], f.entry("simulation/level_0/parsed_history.json"))
    with pytest.raises(ValueError):
        ADAPTER.response_history_channels(f.result, f.proposal, resources)


def test_public_hooks_are_pure_after_verified_resources_are_supplied(monkeypatch):
    f = Fixture(selected=True)
    selection = f.selection(gauss=True)
    fields = f.selected_resources(selection)
    histories = f.resource(ADAPTER.history_response_resources(f.result))

    def forbidden(*args, **kwargs):
        pytest.fail("Pure retained J2 reader must never open files or launch native processes")

    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert ADAPTER.select_response_fields(f.result, f.proposal, fields, selection)["value"] == -29
    assert len(ADAPTER.response_history_channels(f.result, f.proposal, histories)) == 11
    assert ADAPTER.display_response_fields(f.result, f.proposal, f.headers())["kind"] == "j2_fe_fields"
