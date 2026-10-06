"""Portable fake-native controls, not solver/contact/physical acceptance.

The existing public synthetic mesh/table fixture supplies IDs and full-field
shape only. These artificial observations are not a mechanics reference solve.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

import test_fixture_assembly_affine_field as existing


BASE = Path(__file__).resolve().parents[1]
PACKAGE = "_assembly_mechanics_source_tests"
package = ModuleType(PACKAGE)
package.__path__ = [str(BASE / "caelab/adapters")]
sys.modules[PACKAGE] = package
path = BASE / "caelab/adapters/fixture_assembly_mechanics_worker.py"
w = ModuleType(PACKAGE + ".fixture_assembly_mechanics_worker")
w.__file__, w.__package__ = str(path), PACKAGE
sys.modules[w.__name__] = w
exec(compile(path.read_bytes(), str(path), "exec", dont_inherit=True), w.__dict__)
from plugins.fixture_design import assembly_mesh


def pin(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def save(path, value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    path.write_bytes(data)
    return pin(data)


def packet(e, *, interfaces=False):
    source = w.importer.source_catalog(e.mapping)
    components = list(assembly_mesh.ACTIVE)
    def nodes(face):
        return sorted(source["group_nodes"][face])
    return {"schema_version": "1.0", "components": components,
        "materials": [{"component_id": component, "volume_group": source["bodies"][component],
                       "young_modulus_MPa": 1000.+number, "poisson_ratio": .3}
                      for number, component in enumerate(components)],
        "boundary_conditions": [{"id": "support", "node_group": "BC001", "face_group": "F0001",
                                 "source_node_ids": nodes("F0001"), "components": {"DX": 0., "DZ": .1}}],
        "loads": [{"id": "drive", "node_group": "LD001", "face_group": "F0077",
                   "source_node_ids": nodes("F0077"), "components_N": {"FX": 0., "FY": 0., "FZ": -100.}}],
        "ties": ([{"id": "bond", "master_face_group": "F0002", "master_volume_group": "V0001",
                    "slave_face_group": "F0012", "distance_max_mm": .2}] if interfaces else []),
        "contacts": ([{"id": "touch", "master_face_group": "F0023", "slave_face_group": "F0056"}]
                     if interfaces else []),
        "solver_policy": deepcopy(w._POLICY)}


@pytest.fixture
def e():
    return existing.synthetic()


def projected(e, settings=None):
    return w.validate_conditions(settings or packet(e), e.mapping, e.catalog, assembly_mesh.ACTIVE)


def test_exact_original_source_ids_bind_this_import_and_equal_force_rule(e):
    settings = packet(e, interfaces=True)
    before = deepcopy(settings)
    result = projected(e, settings)
    assert settings == before
    comparison = w.importer.validate_native_catalog(e.mapping, e.catalog)
    load = result["loads"][0]
    assert load["node_indices"] == sorted(e.catalog["group_node_indices"]["F0077"])
    assert load["source_node_ids"] == [comparison["source_node_ids_by_native_index"][i] for i in load["node_indices"]]
    assert load["node_indices"] != load["source_node_ids"]
    assert load["per_node_components_N"]["FZ"] == -100. / load["node_count"]
    assert math.isclose(load["applied_resultant_components_N"]["FZ"], -100., rel_tol=1e-15)
    tie = result["ties"][0]
    assert tie["native_master_volume_group"] == "TM001"
    assert set(tie["master_volume_cell_indices"]) < set(e.catalog["group_cell_indices"]["V0001"])
    assert all(e.catalog["cells"][i]["type"] == "TETRA10" for i in tie["master_volume_cell_indices"])
    assert result["axis"] == w._AXIS and result["engineering"] == "UNKNOWN"


def test_pure_prescribed_displacement_projects_exact_native_dof_without_dummy_force(e):
    settings = packet(e)
    settings["loads"] = []
    before = deepcopy(settings)
    observed = projected(e, settings)
    assert settings == before and observed["loads"] == []
    assert observed["boundary_conditions"][0]["components"] == {"DX": 0., "DZ": .1}
    settings["boundary_conditions"][0]["components"] = {"DX": 0., "DZ": 0.}
    with pytest.raises(ValueError, match="nonzero"): projected(e, settings)


@pytest.mark.parametrize("fault", ["source_missing", "source_extra", "bool_source", "index_instead",
    "material_missing", "material_body", "material_bool", "nu_half", "nu_minus_one", "nonfinite",
    "policy_bool", "policy_threshold", "user_code", "path", "foreign_group", "overwrite_group", "zero_force",
    "dof_overlap", "load_on_bc", "tie_bc_collision", "contact_bc_collision", "slave_intersection",
    "tie_master_body", "tie_distance", "partial_force"])
def test_conditions_refuse_unbound_or_unsupported_native_inputs(e, fault):
    s = packet(e, interfaces=True)
    bc, load, tie = s["boundary_conditions"][0], s["loads"][0], s["ties"][0]
    if fault == "source_missing": load["source_node_ids"].pop()
    elif fault == "source_extra": load["source_node_ids"].append(9999999)
    elif fault == "bool_source": load["source_node_ids"][0] = True
    elif fault == "index_instead": load["source_node_ids"] = e.catalog["group_node_indices"]["F0077"]
    elif fault == "material_missing": s["materials"].pop()
    elif fault == "material_body": s["materials"][0]["volume_group"] = "V0002"
    elif fault == "material_bool": s["materials"][0]["young_modulus_MPa"] = True
    elif fault == "nu_half": s["materials"][0]["poisson_ratio"] = .5
    elif fault == "nu_minus_one": s["materials"][0]["poisson_ratio"] = -1
    elif fault == "nonfinite": load["components_N"]["FZ"] = math.inf
    elif fault == "policy_bool": s["solver_policy"]["load_parameters"][0] = False
    elif fault == "policy_threshold": s["solver_policy"]["residual_relative"] = 1e-5
    elif fault == "user_code": s["code"] = "repair()"
    elif fault == "path": load["path"] = "foreign.msh"
    elif fault == "foreign_group": bc["face_group"] = "V0001"
    elif fault == "overwrite_group": load["node_group"] = "F0077"
    elif fault == "zero_force": load["components_N"]["FZ"] = 0
    elif fault == "dof_overlap": s["boundary_conditions"].append({**deepcopy(bc), "id": "other", "node_group": "BC002"})
    elif fault == "load_on_bc":
        load.update(face_group=bc["face_group"], source_node_ids=deepcopy(bc["source_node_ids"]))
    elif fault == "tie_bc_collision":
        tie.update(master_face_group="F0012", master_volume_group="V0002", slave_face_group="F0001")
    elif fault == "contact_bc_collision":
        bc.update(face_group=s["contacts"][0]["slave_face_group"],
                  source_node_ids=sorted(w.importer.source_catalog(e.mapping)["group_nodes"][s["contacts"][0]["slave_face_group"]]))
    elif fault == "slave_intersection": s["contacts"][0]["slave_face_group"] = tie["slave_face_group"]
    elif fault == "tie_master_body": tie["master_volume_group"] = "V0002"
    elif fault == "tie_distance": tie["distance_max_mm"] = 0
    elif fault == "partial_force": del load["components_N"]["FX"]
    with pytest.raises(ValueError):
        projected(e, s)


def test_partial_dofs_keep_unmentioned_axis_free_and_allow_other_axis_force(e):
    s = packet(e)
    s["boundary_conditions"][0]["components"] = {"DX": 0.}
    s["loads"][0].update(face_group="F0001", source_node_ids=s["boundary_conditions"][0]["source_node_ids"][:])
    result = projected(e, s)
    assert result["boundary_conditions"][0]["components"] == {"DX": 0.}
    assert set(result["loads"][0]["components_N"]) == {"FX", "FY", "FZ"}


def test_explicit_face_interior_uses_original_topological_difference_not_conflict_repair(e):
    source = w.importer.source_catalog(e.mapping)
    selected = set(source["group_nodes"]["F0011"])
    for name, record in source["groups"].items():
        if record["dim"] == 2 and record["component_id"] == assembly_mesh.ACTIVE[0] and name != "F0011":
            selected.difference_update(source["group_nodes"][name])
    assert selected
    s = packet(e)
    boundary = s["boundary_conditions"][0]
    boundary.update(face_group="F0011", source_node_ids=sorted(selected))
    with pytest.raises(ValueError, match="source node IDs"):
        projected(e, s)
    boundary["node_scope"] = "FACE_INTERIOR_EXCLUDING_OTHER_FACE_BOUNDARIES"
    result = projected(e, s)
    assert set(result["boundary_conditions"][0]["source_node_ids"]) == selected
    assert result["node_groups"]["BC001"] == result["boundary_conditions"][0]["node_indices"]
    assert len(result["node_groups"]["BC001"]) < len(e.catalog["group_node_indices"]["F0011"])
    empty = packet(e)
    empty["boundary_conditions"][0]["node_scope"] = boundary["node_scope"]
    with pytest.raises(ValueError, match="scope is empty"):
        projected(e, empty)


def test_explicit_contact_master_union_preserves_pairs_and_original_groups(e):
    s = packet(e, interfaces=True)
    single = projected(e, s)["contacts"][0]
    assert single["native_master_face_group"] == "F0023"
    s["contacts"][0] = {"id": "explicit_union", "master_face_groups": ["F0023", "F0034"],
                       "slave_face_group": "F0056", "source_pair_ids": ["CP01", "CP02"]}
    before = deepcopy(e.catalog)
    result = projected(e, s)
    contact = result["contacts"][0]
    assert e.catalog == before and contact["source_pair_ids"] == ["CP01", "CP02"]
    assert contact["native_master_face_group"] == "CM001"
    assert result["cell_groups"]["CM001"] == sorted(set(e.catalog["group_cell_indices"]["F0023"] +
                                                       e.catalog["group_cell_indices"]["F0034"]))
    assert [row["face_group"] for row in contact["master_faces"]] == ["F0023", "F0034"]
    for fault in ("missing_pair", "duplicate_master", "same_body", "ambiguous_shape"):
        damaged = deepcopy(s)
        record = damaged["contacts"][0]
        if fault == "missing_pair": record["source_pair_ids"].pop()
        elif fault == "duplicate_master": record["master_face_groups"][1] = record["master_face_groups"][0]
        elif fault == "same_body": record["master_face_groups"][1] = "F0057"
        else: record["master_face_group"] = "F0023"
        with pytest.raises(ValueError): projected(e, damaged)


def test_exact_six_surface_permutations_volume_and_xyz_stay_original(e):
    surface = next(c for c in e.catalog["cells"] if c["type"] == "TRIA6")
    assert len(set(w.TRIA6_ORIENTATION_PERMUTATIONS)) == 6
    for permutation in w.TRIA6_ORIENTATION_PERMUTATIONS:
        oriented = deepcopy(e.catalog)
        oriented["cells"][surface["index"]]["node_indices"] = [surface["node_indices"][i] for i in permutation]
        receipt = w.validate_orientation(e.catalog, oriented)
        assert receipt["status"] == "PASS"
    for fault in ("edge", "volume", "xyz", "group", "index", "labels", "duplicate"):
        oriented = deepcopy(e.catalog)
        if fault == "edge":
            conn = oriented["cells"][surface["index"]]["node_indices"]; conn[3], conn[4] = conn[4], conn[3]
        elif fault == "volume":
            cell = next(c for c in oriented["cells"] if c["type"] == "TETRA10")
            cell["node_indices"][0], cell["node_indices"][1] = cell["node_indices"][1], cell["node_indices"][0]
        elif fault == "xyz": oriented["coordinates_mm"][0][0] += 1e-13
        elif fault == "group": oriented["group_cell_indices"]["F0001"].append(9999)
        elif fault == "index": oriented["node_indices"].reverse()
        elif fault == "labels": oriented["labels"]["nodes"]["values"] = ["renamed"]
        else: oriented["cells"].append(deepcopy(oriented["cells"][0]))
        with pytest.raises(ValueError): w.validate_orientation(e.catalog, oriented)


def test_generated_groups_are_additive_exact_receipt_and_no_overwrite(e):
    receipt = projected(e, packet(e, interfaces=True))
    after = deepcopy(e.catalog)
    after["standalone_node_groups"] = deepcopy(receipt["node_groups"])
    for name, indices in receipt["cell_groups"].items():
        after["group_names"].append(name)
        after["group_cell_indices"][name] = indices[:]
        after["group_node_indices"][name] = sorted({node for i in indices for node in e.catalog["cells"][i]["node_indices"]})
    w.validate_orientation(e.catalog, after, receipt["node_groups"], receipt["cell_groups"])
    with pytest.raises(ValueError): w.validate_orientation(e.catalog, after)
    after["standalone_node_groups"]["LD001"].pop()
    with pytest.raises(ValueError): w.validate_orientation(e.catalog, after, receipt["node_groups"], receipt["cell_groups"])


@pytest.mark.parametrize("parameters", [[0., .25, .5, .75, 1.], [.25, .5, .75, 1.]])
def test_orders_preserve_actual_saved_initial_state_and_parameter_axis(parameters):
    orders = list(range(1, len(parameters)+1))
    assert w.result_orders(orders, {"NUME_ORDRE": orders, "INST": parameters}, w._POLICY) == orders[-1]
    for bad in ([0., .5, 1.], [0., .25, .5, .75, .99], [False, .25, .5, .75, 1.]):
        with pytest.raises(ValueError): w.result_orders(orders, {"NUME_ORDRE": orders, "INST": bad}, w._POLICY)


def test_nullable_contact_observation_checks_exact_selected_nodes_orders_and_values(e):
    nodes = e.catalog["group_node_indices"]["F0056"]
    table = {"NOEUD": [], "NUME_ORDRE": [], "LAGS_C": []}
    for order in (1, 2):
        for node in nodes:
            table["NOEUD"].append(str(node+1).rjust(8))
            table["NUME_ORDRE"].append(order)
            table["LAGS_C"].append(-.1)
    w.validate_contact_observation(table, e.catalog, [1, 2], nodes, ("LAGS_C",), "DEPL.LAGS_C")
    for fault in ("missing", "duplicate", "wrong_node", "wrong_order", "bool", "nonfinite"):
        value = deepcopy(table)
        if fault == "missing":
            for column in value.values(): column.pop()
        elif fault == "duplicate": value["NOEUD"][1] = value["NOEUD"][0]
        elif fault == "wrong_node": value["NOEUD"][0] = "999999"
        elif fault == "wrong_order": value["NUME_ORDRE"][0] = 3
        elif fault == "bool": value["LAGS_C"][0] = True
        else: value["LAGS_C"][0] = math.nan
        with pytest.raises(ValueError):
            w.validate_contact_observation(value, e.catalog, [1, 2], nodes, ("LAGS_C",), "DEPL.LAGS_C")


def test_capsule_exact_sources_private_load_and_foreign_membership_refusal(tmp_path):
    paths = {name: BASE / ("plugins/fixture_design/" if name == "assembly_mesh.py" else "caelab/adapters/") / name
             for name in w._CAPSULE}
    pins = {}
    for name, path in paths.items():
        data = path.read_bytes(); (tmp_path / name).write_bytes(data); pins[name] = pin(data)
    package = "_assembly_mechanics_capsule"
    try:
        loaded = w._capsule_modules(tmp_path, pins)
        assert set(loaded) == set(w._CAPSULE)
        assert loaded[w._WORKER].shared is loaded["fixture_assembly_affine_field_worker.py"]
        assert loaded["assembly_mesh.py"].ACTIVE == assembly_mesh.ACTIVE
        with pytest.raises(RuntimeError, match="preloaded"): w._capsule_modules(tmp_path, pins)
    finally:
        for name in list(sys.modules):
            if name == package or name.startswith(package + "."): del sys.modules[name]
    (tmp_path / "unowned.py").write_text("raise Exception('must not execute')")
    with pytest.raises(RuntimeError, match="membership"): w._capsule_modules(tmp_path, pins)
    (tmp_path / "unowned.py").unlink()
    (tmp_path / "codeaster_worker.py").write_bytes(b"raise Exception('must not execute')\n")
    with pytest.raises(RuntimeError, match="byte drift"): w._capsule_modules(tmp_path, pins)


def fake_run(tmp_path, monkeypatch, e, *, fault=None, interfaces=True, initial_state=None, displacement_only=False):
    native, capsule, capture = (tmp_path / name for name in ("native", "capsule", "mesh-reuse"))
    for folder in (native, capsule, capture): folder.mkdir()
    modules = {w._WORKER: w, "codeaster_worker.py": w.foundation,
               "fixture_assembly_native_import_worker.py": w.importer,
               "fixture_assembly_affine_field_worker.py": w.shared,
               "fixture_assembly_field_geometry.py": sys.modules[w.shared.__package__ + ".fixture_assembly_field_geometry"],
               "assembly_mesh.py": assembly_mesh}
    pins = {}
    for name, module in modules.items():
        data = Path(module.__file__).read_bytes(); (capsule / name).write_bytes(data); pins[name] = pin(data)
    transport_input = native / "mesh-transport.msh"
    transport_input.write_bytes(b"TEST_ONLY_TRANSPORT_NOT_A_NATIVE_MESH\n")
    config = {"schema_version": 1, "settings": packet(e, interfaces=interfaces), "mesh_revision": "a"*64,
              "parent": {"experiment_id": "E-test-only", "cad_revision": "b"*64},
              "profile": {"name": "coarse3", "mesh_size_mm": 3.}, "native_sources": pins,
              "mapping_entry": save(capture / "mapping.json", e.mapping),
              "quality_entry": save(capture / "quality.json", e.quality),
              "transport_entry": pin(transport_input.read_bytes())}
    if initial_state is not None:
        for contact_record in config["settings"]["contacts"]:
            contact_record["initial_state"] = initial_state
    if displacement_only:
        config["settings"]["loads"] = []
    if fault == "master_union":
        config["settings"]["contacts"][0] = {"id": "touch", "master_face_groups": ["F0023", "F0034"],
             "slave_face_group": "F0056", "source_pair_ids": ["CP01", "CP02"]}
    input_path = native / "input.json"
    save(input_path, config)
    if fault == "source_before": (capsule / "codeaster_worker.py").write_bytes(b"FOREIGN\n")
    if fault == "input_before":
        config["schema_version"] = True; save(input_path, config)
    if fault == "transport_before": transport_input.write_bytes(b"WRONG_TRANSPORT_BEFORE_DEBUT")
    catalog = deepcopy(e.catalog)
    if fault == "import_connectivity":
        cell = next(c for c in catalog["cells"] if c["type"] == "TETRA10")
        cell["node_indices"][8], cell["node_indices"][9] = cell["node_indices"][9], cell["node_indices"][8]
    node_groups, cell_groups, calls, arguments = {}, {}, [], {}
    class Mesh:
        sdj = SimpleNamespace(NOMNOE=SimpleNamespace(get=lambda: None), NOMMAI=SimpleNamespace(get=lambda: None))
        def getNumberOfNodes(self): return catalog["node_count"]
        def getNumberOfCells(self): return catalog["cell_count"]
        def getGroupsOfCells(self): return catalog["group_names"] + list(cell_groups)
        def getGroupsOfNodes(self): return list(node_groups)
        def getConnectivity(self): return [c["node_indices"] for c in catalog["cells"]]
        def getCellTypeName(self, index): return catalog["cells"][index]["type"]
        def getCoordinates(self): return SimpleNamespace(toNumpy=lambda: SimpleNamespace(tolist=lambda: catalog["coordinates_mm"]))
        def getCells(self, group): return cell_groups[group] if group in cell_groups else catalog["group_cell_indices"][group]
        def getNodesFromCells(self, group):
            return sorted({n for i in self.getCells(group) for n in catalog["cells"][i]["node_indices"]})
        def getNodes(self, group=None): return list(range(catalog["node_count"])) if group is None else node_groups[group]
        def setGroupOfCells(self, name, indices):
            assert name not in self.getGroupsOfCells()
            cell_groups[name] = list(indices); calls.append("cell-group")
        def setGroupOfNodes(self, name, indices):
            assert name not in self.getGroupsOfNodes() and name not in self.getGroupsOfCells()
            node_groups[name] = list(indices); calls.append("NODE_GROUPS")
            if fault == "wrong_node_group" and name == "LD001": node_groups[name].pop()
    mesh = Mesh()
    class Table:
        def __init__(self, value): self.value = value
        def EXTR_TABLE(self): return self
        def values(self): return deepcopy(self.value)
    class Result:
        def getIndexes(self): return [1, 2, 3, 4, 5]
        def getAccessParameters(self):
            return {"NUME_ORDRE": self.getIndexes(), "INST": [0., .25, .5, .75, 1.]}
    result = Result()
    vendor = ModuleType("code_aster.Commands")
    def debut():
        calls.append("DEBUT")
        # run_aster's --link is materialized during DEBUT, never beforehand.
        if calls.count("DEBUT") == 1:
            assert not (native / "fort.20").exists()
            (native / "fort.20").write_bytes(transport_input.read_bytes())
        if fault == "source_after_debut": (capsule / "assembly_mesh.py").write_bytes(b"DRIFT\n")
        if fault == "unit_after_debut": (native / "fort.20").write_bytes(b"WRONG_LINKED_UNIT20")
    def read_mesh(**kwargs):
        assert kwargs == {"FORMAT": "GMSH", "UNITE": 20}
        calls.append("IMPORT"); return mesh
    def orient(**kwargs):
        calls.append("ORIENTATION")
        assert kwargs["reuse"] is mesh and kwargs["MAILLAGE"] is mesh
        assert len(kwargs["ORIE_PEAU"]) == 77
        for cell in catalog["cells"]:
            if cell["type"] == "TRIA6":
                cell["node_indices"] = [cell["node_indices"][i] for i in (0, 2, 1, 5, 4, 3)]
        if fault == "orientation_edge":
            cell = next(c for c in catalog["cells"] if c["type"] == "TRIA6")
            cell["node_indices"][3], cell["node_indices"][4] = cell["node_indices"][4], cell["node_indices"][3]
        return object() if fault == "replacement_mesh" else mesh
    def groups(**kwargs):
        calls.append("NODE_GROUPS")
        assert kwargs["reuse"] is mesh and kwargs["MAILLAGE"] is mesh
        for declaration in kwargs["CREA_GROUP_NO"]:
            assert declaration["NOM"] not in node_groups
            node_groups[declaration["NOM"]] = mesh.getNodesFromCells(declaration["GROUP_MA"])
        if fault == "wrong_node_group": node_groups["LD001"].pop()
        return mesh
    def model(**kwargs):
        calls.append("MODEL"); arguments["model"] = kwargs
        assert kwargs["MAILLAGE"] is mesh
        return object()
    def charge(**kwargs):
        calls.append("CHARGE"); arguments.setdefault("charges", []).append(kwargs)
        if fault == "mapping_before_solve": (capture / "mapping.json").write_bytes(b"DRIFT\n")
        return kwargs
    def contact(**kwargs):
        calls.append("CONTACT"); arguments["contact"] = kwargs
        return object()
    def nonlinear(**kwargs):
        calls.append("STAT_NON_LINE"); arguments["nonlinear"] = kwargs
        if fault == "source_after_solve": (capsule / "codeaster_worker.py").write_bytes(b"DRIFT\n")
        return result
    def table(**kwargs):
        selection = kwargs["RESU"]
        name = selection.get("NOM_CHAM", "COOR_ELGA")
        if name == "CONT_NOEU" or selection.get("NOM_CMP") == ["LAGS_C"]:
            if fault not in ("contact_observed", "contact_partial"):
                raise RuntimeError("SYNTHETIC_OPTIONAL_NATIVE_CHANNEL_ABSENT")
            components = selection["NOM_CMP"]
            values = {key: [] for key in ("NOEUD", "NUME_ORDRE", *components)}
            for order in selection["NUME_ORDRE"]:
                for node in mesh.getNodes(selection["GROUP_NO"]):
                    values["NOEUD"].append(str(node+1).rjust(8)); values["NUME_ORDRE"].append(order)
                    for component in components: values[component].append(-.1 if component == "LAGS_C" else 0.)
            if fault == "contact_partial":
                for column in values.values(): column.pop()
            return Table(values)
        values = deepcopy(e.raw["tables"][name])
        selected = selection.get("NUME_ORDRE")
        if "NUME_ORDRE" in values:
            orders = list(selected) if isinstance(selected, tuple) else [selected]
            values = {key: [order if key == "NUME_ORDRE" else value
                            for order in orders for value in column] for key, column in values.items()}
        if fault == "history_missing" and isinstance(selected, tuple) and name == "DEPL":
            for column in values.values(): column.pop()
        if fault == "stress_missing" and name == "SIEF_ELGA":
            for column in values.values(): column.pop()
        return Table(values)
    def energy(**kwargs):
        if fault == "energy_absent": raise RuntimeError("SYNTHETIC_ENERGY_ABSENT")
        return Table({"TOTALE": [0.], "NUME_ORDRE": [kwargs["NUME_ORDRE"]], "LIEU": [kwargs["ENER_POT"]["GROUP_MA"]]})
    def export(**kwargs):
        calls.append("EXPORT"); arguments["export"] = kwargs
        if fault == "input_after_export": input_path.write_bytes(input_path.read_bytes()+b" ")
    vendor.DEBUT, vendor.LIRE_MAILLAGE, vendor.MODI_MAILLAGE = debut, read_mesh, orient
    vendor.DEFI_GROUP, vendor.AFFE_MODELE, vendor.AFFE_CHAR_MECA = groups, model, charge
    vendor.DEFI_CONTACT, vendor.STAT_NON_LINE, vendor.CREA_TABLE = contact, nonlinear, table
    vendor.DEFI_MATERIAU = lambda **kwargs: kwargs
    vendor.AFFE_MATERIAU = lambda **kwargs: kwargs
    vendor.DEFI_FONCTION = lambda **kwargs: kwargs
    vendor.DEFI_LIST_REEL = lambda **kwargs: kwargs
    vendor.CALC_CHAMP = lambda **kwargs: kwargs["RESULTAT"]
    vendor.CALC_CHAM_ELEM = lambda **kwargs: object()
    vendor.POST_ELEM, vendor.IMPR_RESU, vendor.FIN = energy, export, lambda: calls.append("FIN")
    syntax = ModuleType("code_aster.Cata.Syntax"); syntax._F = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "code_aster", ModuleType("code_aster"))
    monkeypatch.setitem(sys.modules, "code_aster.Commands", vendor)
    monkeypatch.setitem(sys.modules, "code_aster.Cata", ModuleType("code_aster.Cata"))
    monkeypatch.setitem(sys.modules, "code_aster.Cata.Syntax", syntax)
    monkeypatch.setattr(w.foundation, "_runtime_versions", lambda: ({"code_aster": "17.4.0", "qualification": "SYNTHETIC"}, {}))
    monkeypatch.chdir(native)
    return SimpleNamespace(native=native, modules=modules, config=config, input=input_path, calls=calls, arguments=arguments)


@pytest.mark.parametrize("state,native", [("OPEN", "NON"), ("GEOMETRIC", "INTERPENETRE"), ("CLOSED_ASSUMED", "OUI")])
def test_declared_contact_initialization_is_translated_without_changing_numerical_policy(tmp_path, monkeypatch, e, state, native):
    fixture = fake_run(tmp_path, monkeypatch, e, initial_state=state)
    observed = w.run_mechanics(fixture.input, fixture.modules)
    assert fixture.arguments["contact"]["ZONE"][0]["CONTACT_INIT"] == native
    assert fixture.arguments["contact"]["ZONE"][0]["COEF_CONT"] == 1000.
    assert observed["decision"] == "NOT_RELEASED"


@pytest.mark.parametrize("state", ["AUTO", True, [], None])
def test_native_contact_initialization_rejects_unsupported_values(e, state):
    settings = packet(e, interfaces=True)
    settings["contacts"][0]["initial_state"] = state
    with pytest.raises(ValueError, match="initialization state"):
        projected(e, settings)


def test_fake_native_mechanics_commands_constant_ties_ramp_force_and_full_protocol(tmp_path, monkeypatch, e):
    f = fake_run(tmp_path, monkeypatch, e)
    raw = w.run_mechanics(f.input, f.modules)
    assert f.calls.count("IMPORT") == 1 and f.calls.index("ORIENTATION") < f.calls.index("MODEL") < f.calls.index("STAT_NON_LINE")
    native = f.arguments["nonlinear"]
    assert native["SOLVEUR"] == {"METHODE": "MUMPS", "STOP_SINGULIER": "OUI"}
    assert native["CONVERGENCE"] == {"ARRET": "OUI", "RESI_GLOB_RELA": 1e-6, "ITER_GLOB_MAXI": 50}
    assert native["COMPORTEMENT"]["RELATION"] == "ELAS" and native["COMPORTEMENT"]["DEFORMATION"] == "PETIT"
    constant, nonzero_displacement, force = native["EXCIT"]
    assert "FONC_MULT" not in constant and constant["CHARGE"]["DDL_IMPO"] == ({"GROUP_NO": "BC001", "DX": 0.},)
    tie = constant["CHARGE"]["LIAISON_MAIL"][0]
    assert tie["TYPE_RACCORD"] == "MASSIF" and tie["GROUP_MA_MAIT"] == "TM001" and tie["DISTANCE_MAX"] == .2
    assert tie["DDL"] == ("DX", "DY", "DZ") and tie["ELIM_MULT"] == "OUI"
    assert "DDL_MAIT" not in tie and "DDL_ESCL" not in tie
    assert nonzero_displacement["CHARGE"]["DDL_IMPO"] == ({"GROUP_NO": "BC001", "DZ": .1},)
    assert nonzero_displacement["FONC_MULT"] == force["FONC_MULT"]
    contact = f.arguments["contact"]
    assert contact["FORMULATION"] == "CONTINUE" and contact["FROTTEMENT"] == "SANS" and contact["VERI_NORM"] == "OUI"


    assert contact["ZONE"][0]["CONTACT_INIT"] == "NON" and contact["ZONE"][0]["COEF_CONT"] == 1000.
    assert contact["ZONE"][0]["INTEGRATION"] == "AUTO" and contact["ZONE"][0]["ALGO_CONT"] == "STANDARD"
    assert raw["status"] == "ASSEMBLY_MECHANICS_NATIVE_OBSERVED" and raw["order"] == 5
    assert raw["available_orders"] == [1, 2, 3, 4, 5] and raw["load_parameter"] == 1.0
    assert raw["geometry_context"]["selected_result_order"] == 5
    assert raw["decision"] == "NOT_RELEASED" and raw["linear_residual"]["status"] == "UNKNOWN"
    assert set(raw["table_entries"]) == {"DEPL", "REAC_NODA", "SIEF_ELGA", "COOR_ELGA"}
    assert raw["field_completeness"]["geometry_checks"]["point_weight_relative_limit"] == 1e-8
    for name, entry in raw["table_entries"].items(): assert pin((f.native / (name.lower()+".table.json")).read_bytes()) == entry
    assert len(raw["history_tables"]["DEPL"]["NOEUD"]) == 5 * e.catalog["node_count"]
    assert raw["native_energy"][assembly_mesh.ACTIVE[0]]["table"]["TOTALE"] == [0.]
    for observation in raw["native_contact"]["touch"].values():
        assert observation["status"] == "UNKNOWN" and observation["table"] is None and observation["reason"]
    assert (f.native / "native-catalog.json").exists() and (f.native / "oriented-catalog.json").exists()
    pre = json.loads((f.native / "native-catalog.json").read_bytes())
    oriented = json.loads((f.native / "oriented-catalog.json").read_bytes())
    assert w.validate_orientation(pre, oriented, raw["nodal_application_receipt"]["node_groups"],
                                  raw["nodal_application_receipt"]["cell_groups"]) == raw["orientation_receipt"]
    assert len(raw["orientation_commands"]) == 77
    assert not (f.native / "native-failure.json").exists()


def test_fake_native_displacement_drive_has_no_empty_force_command_or_dummy_force(tmp_path, monkeypatch, e):
    f = fake_run(tmp_path, monkeypatch, e, displacement_only=True)
    w.run_mechanics(f.input, modules=f.modules)
    excitations = f.arguments["nonlinear"]["EXCIT"]
    assert len(excitations) == 2
    assert all("FORCE_NODALE" not in row["CHARGE"] for row in excitations)
    assert excitations[1]["CHARGE"]["DDL_IMPO"] == ({"GROUP_NO": "BC001", "DZ": .1},)
    assert excitations[1]["FONC_MULT"]["VALE"] == (0., 0., 1., 1.)


@pytest.mark.parametrize("fault,phase,native_allowed", [
    ("source_before", "SOURCE_GUARD", False), ("input_before", "SOURCE_GUARD", False),
    ("transport_before", "SOURCE_GUARD", False), ("unit_after_debut", "BEFORE_DEBUT", False),
    ("source_after_debut", "BEFORE_DEBUT", False), ("import_connectivity", "PRE_MODEL_IDENTITY", False),
    ("orientation_edge", "ORIENTATION", False), ("replacement_mesh", "ORIENTATION", False),
    ("wrong_node_group", "GENERATED_GROUPS", False), ("mapping_before_solve", "MODEL", False),
    ("source_after_solve", "FIELDS", True), ("history_missing", "FIELDS", True),
    ("stress_missing", "FIELDS", True), ("input_after_export", "EXPORT", True)])
def test_fake_native_drift_and_completeness_fail_closed(tmp_path, monkeypatch, e, fault, phase, native_allowed):
    f = fake_run(tmp_path, monkeypatch, e, fault=fault)
    with pytest.raises((RuntimeError, ValueError)):
        w.run_mechanics(f.input, f.modules)
    failure = json.loads((f.native / "native-failure.json").read_bytes())
    assert failure["phase"] == phase and failure["numerical_verdict"] == "UNKNOWN"
    assert failure["decision"] == "NOT_RELEASED" and not (f.native / "worker-result.json").exists()
    assert ("STAT_NON_LINE" in f.calls) is native_allowed
    if fault in ("source_before", "input_before"): assert "DEBUT" not in f.calls
    if fault in ("source_before", "input_before", "source_after_debut", "import_connectivity", "orientation_edge",
                 "replacement_mesh", "wrong_node_group"): assert "MODEL" not in f.calls


def test_no_contact_no_ties_and_missing_native_energy_are_explicit_unknown(tmp_path, monkeypatch, e):
    f = fake_run(tmp_path, monkeypatch, e, fault="energy_absent", interfaces=False)
    raw = w.run_mechanics(f.input, f.modules)
    assert "CONTACT" not in f.calls and "CONTACT" not in f.arguments["nonlinear"]
    assert raw["native_contact"] == {} and raw["nodal_application_receipt"]["ties"] == []
    assert all(observation["status"] == "UNKNOWN" and observation["table"] is None for observation in raw["native_energy"].values())
    before = (f.native / "worker-result.json").read_bytes()
    with pytest.raises(FileExistsError): w.run_mechanics(f.input, f.modules)
    assert (f.native / "worker-result.json").read_bytes() == before


@pytest.mark.parametrize("fault,status", [("contact_observed", "OBSERVED"), ("contact_partial", "UNKNOWN")])
def test_fake_native_contact_keeps_original_channels_and_incomplete_raw(tmp_path, monkeypatch, e, fault, status):
    f = fake_run(tmp_path, monkeypatch, e, fault=fault)
    raw = w.run_mechanics(f.input, f.modules)
    observations = raw["native_contact"]["touch"]
    assert observations["DEPL.LAGS_C"]["status"] == status and observations["CONT_NOEU"]["status"] == status
    assert observations["DEPL.LAGS_C"]["native_component_units"] == {"LAGS_C": "MPa"}
    assert observations["CONT_NOEU"]["native_component_units"]["RNZ"] == "N"
    assert observations["CONT_NOEU"]["native_component_units"]["PROJ_Z"] == "mm"
    for observation in observations.values():
        assert observation["table"] and observation["pressure_from_reaction_or_area"] == "NOT_CONSTRUCTED"
        if status == "UNKNOWN": assert "incomplete" in observation["reason"]


def test_fake_native_explicit_union_uses_one_generated_zone_group(tmp_path, monkeypatch, e):
    f = fake_run(tmp_path, monkeypatch, e, fault="master_union")
    raw = w.run_mechanics(f.input, f.modules)
    zone = f.arguments["contact"]["ZONE"][0]
    assert zone["GROUP_MA_MAIT"] == "CM001" and isinstance(zone["GROUP_MA_MAIT"], str)
    receipt = raw["nodal_application_receipt"]
    assert receipt["contacts"][0]["source_pair_ids"] == ["CP01", "CP02"]
    pre = json.loads((f.native / "native-catalog.json").read_bytes())
    oriented = json.loads((f.native / "oriented-catalog.json").read_bytes())
    w.validate_orientation(pre, oriented, receipt["node_groups"], receipt["cell_groups"])
    assert set(oriented["group_names"]) - set(pre["group_names"]) == {"CM001", "TM001"}


def test_stored_orientation_receipt_comes_from_final_generated_group_validation(tmp_path, monkeypatch, e):
    """Distinguish final admission from the earlier orientation-only receipt.

    Current receipt values agree; this fake validator witness ensures an added
    final-group admission field cannot silently disappear from retained proof.
    """
    validate = w.validate_orientation
    def observed_final(before, after, node_groups=None, cell_groups=None):
        receipt = validate(before, after, node_groups, cell_groups)
        if node_groups is not None and cell_groups is not None:
            receipt["TEST_ONLY_FINAL_GROUP_WITNESS"] = {
                "nodes": sorted(node_groups), "cells": sorted(cell_groups)}
        return receipt
    monkeypatch.setattr(w, "validate_orientation", observed_final)
    f = fake_run(tmp_path, monkeypatch, e, fault="master_union")
    raw = w.run_mechanics(f.input, f.modules)
    application = raw["nodal_application_receipt"]
    witness = {"nodes": sorted(application["node_groups"]), "cells": sorted(application["cell_groups"])}
    assert raw["orientation_receipt"]["TEST_ONLY_FINAL_GROUP_WITNESS"] == witness
    assert json.loads((f.native / "orientation-receipt.json").read_bytes()) == raw["orientation_receipt"]
