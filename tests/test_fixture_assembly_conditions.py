"""TEST_ONLY semantic catalogs; no CAD, native mesh, solver or physical evidence."""

from copy import deepcopy
import hashlib
import json

import pytest

from plugins.fixture_design.assembly_conditions import validate_declaration


ACTIVE = ["printed_base", "printed_support_left", "printed_support_right", "metal_roller_left",
          "metal_roller_right", "metal_loading_nose", "specimen"]
INACTIVE = [f"metal_bolt_{side}_{dx}_{y}"
            for side in ("left", "right") for dx in (-10, 10) for y in (-12, 12)]
CAD = "a" * 64
MESH = "b" * 64
BASIS = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def _catalog():
    selections = []
    for component in ACTIVE + INACTIVE:
        geometry = {"bounds_mm": {"min_mm": [0, 0, 0], "max_mm": [2, 3, 4], "size_mm": [2, 3, 4]},
                    "center_mm": [1, 1.5, 2], "coordinate_system": "global",
                    "native_coordinate_system": "global_assembly_cartesian_mm"}
        selections.append({"id": "B-" + component, "kind": "native_assembly_body", "component_id": component,
                           "roles": ["material"], **deepcopy(geometry)})
        for ordinal in (1, 2):
            digest = hashlib.sha256(f"TEST_ONLY {component} {ordinal}".encode()).hexdigest()
            selections.append({"id": f"S-{component}-{ordinal}", "kind": "native_assembly_face", "component_id": component,
                "roles": ["boundary", "load", "contact"], "local_ordinal": ordinal, "native_ordinal": ordinal,
                "catalog_face_id": f"{component}:face:{ordinal}:{digest}", "area_mm2": 10.0, **deepcopy(geometry)})
    return {"schema_version": "1.0", "cad_backend": "fixture.assembly", "model": "bending_assembly",
        "cad_revision": CAD, "integrity": "VERIFIED",
        "retained_mesh": {"mesh_revision": MESH, "profile": "coarse3", "active_components": list(ACTIVE),
                          "cad_revision": CAD},
        "coordinate_systems": [{"id": "global", "type": "cartesian", "unit": "mm",
                                "basis": deepcopy(BASIS), "origin": [0, 0, 0]}],
        "native_frame_mapping": {"source": "global_assembly_cartesian_mm", "target": "global",
            "basis": deepcopy(BASIS), "origin": [0, 0, 0], "sensor_world_alignment": "UNKNOWN"},
        "selections": selections, "limitations": ["TEST_ONLY fabricated catalog for semantic controls"]}


def _declaration():
    return {"analysis_type": "nonlinear_static", "coordinate_system": "global",
        "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "materials": [{"id": f"M{index}", "selection_id": "B-" + component, "law": "isotropic_linear_elastic",
            "young_modulus_MPa": 2000 if component.startswith("printed") else 210000.0, "poisson_ratio": .3,
            "source": {"category": "ASSUMED", "description": "TEST_ONLY assumed material; not measured"}}
            for index, component in enumerate(ACTIVE, 1)],
        "boundary_conditions": [{"id": "BC1", "selection_id": "S-printed_base-2", "type": "displacement",
            "components": {"UZ": -0.0}, "coordinate_system": "global", "unit": "mm",
            "source": "TEST_ONLY partial support; no implicit other DOFs or mount qualification"}],
        "loads": [{"id": "L1", "selection_id": "S-metal_loading_nose-1", "type": "resultant_force",
            "components": {"FX": -2.5, "FY": 0.0, "FZ": -100.0}, "coordinate_system": "global", "unit": "N",
            "source": "TEST_ONLY signed global resultant, not an observed load"}],
        "contact": {"mode": "mixed", "source": "TEST_ONLY explicit contact assumptions", "pairs": [
            {"selection_a": "S-printed_base-1", "selection_b": "S-printed_support_left-1", "law": "bonded",
             "master": "a", "source": "TEST_ONLY declared bond", "distance_max_mm": .05},
            {"selection_a": "S-metal_roller_left-1", "selection_b": "S-specimen-1", "law": "frictionless",
             "master": "b", "source": "TEST_ONLY declared frictionless interface"}]},
        "mesh": {"mode": "retained", "mesh_revision": MESH}}


@pytest.mark.parametrize("state", ["OPEN", "GEOMETRIC", "CLOSED_ASSUMED"])
def test_explicit_initial_contact_state_is_preserved_without_qualification(state):
    declaration = _declaration()
    declaration["contact"]["initial_state"] = state
    snapshot = validate_declaration(_catalog(), declaration)
    assert snapshot["declaration"] == declaration
    assert snapshot["engineering"] == "UNKNOWN" and snapshot["decision"] == "NOT_RELEASED"


def test_open_contact_refuses_provably_free_initial_translation():
    from plugins.fixture_design.assembly_conditions import require_initial_translation_support
    declaration = _declaration()
    with pytest.raises(ValueError, match="OPEN contact cannot restrain free rigid translation"):
        require_initial_translation_support(_catalog(), declaration)
    for state in ("GEOMETRIC", "CLOSED_ASSUMED"):
        declaration["contact"]["initial_state"] = state
        # This only defers to actual contact/solver evidence; it is not a stability verdict.
        assert require_initial_translation_support(_catalog(), declaration) is None


@pytest.mark.parametrize("state", ["AUTO", True, [], None])
def test_unsupported_contact_initialization_is_refused(state):
    declaration = _declaration()
    declaration["contact"]["initial_state"] = state
    with pytest.raises(ValueError, match="Initial contact state"):
        validate_declaration(_catalog(), declaration)


def test_bonded_component_graph_transfers_declared_translation_constraints():
    from plugins.fixture_design.assembly_conditions import require_initial_translation_support
    catalog, declaration = _catalog(), _declaration()
    declaration["contact"] = {"mode": "bonded", "source": "TEST_ONLY connected guide graph", "pairs": [
        {"selection_a": f"S-{ACTIVE[0]}-1", "selection_b": f"S-{component}-1", "law": "bonded", "master": "a",
         "source": "TEST_ONLY tie", "distance_max_mm": .05} for component in ACTIVE[1:]]}
    declaration["boundary_conditions"][0]["components"] = {"UX": 0, "UY": 0, "UZ": 0}
    validate_declaration(catalog, declaration)
    assert require_initial_translation_support(catalog, declaration) is None
    del declaration["boundary_conditions"][0]["components"]["UZ"]
    with pytest.raises(ValueError, match="UZ"):
        require_initial_translation_support(catalog, declaration)


def _put(value, path, replacement):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


def test_snapshot_preserves_every_declared_value_source_and_independent_mutable_branch():
    catalog, declaration = _catalog(), _declaration()
    before = deepcopy((catalog, declaration))
    snapshot = validate_declaration(catalog, declaration)
    assert snapshot["catalog"] == catalog and snapshot["declaration"] == declaration
    assert snapshot["cad_revision"] == CAD and snapshot["mesh_revision"] == MESH
    assert snapshot["active_components"] == ACTIVE and snapshot["inactive_components"] == INACTIVE
    assert snapshot["engineering"] == "UNKNOWN" and snapshot["decision"] == "NOT_RELEASED"
    assert snapshot["scope"] == "USER_DECLARED_UNVERIFIED"
    assert "actual material" in " ".join(snapshot["limitations"])
    assert "mounting" in " ".join(snapshot["limitations"]) and "Eight original fasteners" in " ".join(snapshot["limitations"])
    assert snapshot["declaration"]["boundary_conditions"][0]["components"] == {"UZ": -0.0}
    assert json.dumps(snapshot["declaration"]["boundary_conditions"][0]["components"]) == '{"UZ": -0.0}'
    assert snapshot["declaration"]["loads"][0]["components"] == {"FX": -2.5, "FY": 0.0, "FZ": -100.0}
    assert type(snapshot["declaration"]["materials"][0]["young_modulus_MPa"]) is int
    snapshot["declaration"]["materials"][0]["source"]["description"] = "changed"
    snapshot["catalog"]["selections"][0]["bounds_mm"]["min_mm"][0] = 99
    snapshot["active_components"].clear()
    snapshot["inactive_components"].clear()
    snapshot["limitations"].clear()
    assert (catalog, declaration) == before
    assert validate_declaration(*before)["declaration"] == declaration


@pytest.mark.parametrize("source", ["ASSUMED", "MEASURED_REPORTED", "PUBLISHED_REFERENCE"])
def test_source_categories_and_auxetic_constants_never_gain_physical_qualification(source):
    declaration = _declaration()
    declaration["materials"][0]["source"] = {"category": source, "description": "TEST_ONLY <script>source</script>"}
    declaration["materials"][0]["poisson_ratio"] = -.25
    snapshot = validate_declaration(_catalog(), declaration)
    assert snapshot["declaration"] == declaration
    assert snapshot["engineering"] == "UNKNOWN" and snapshot["scope"] == "USER_DECLARED_UNVERIFIED"


@pytest.mark.parametrize("mode", ["none", "bonded", "frictionless"])
def test_contact_modes_use_only_the_explicit_pairs_and_master_sides(mode):
    declaration = _declaration()
    declaration["contact"]["mode"] = mode
    declaration["contact"]["pairs"] = [] if mode == "none" else [declaration["contact"]["pairs"][0 if mode == "bonded" else 1]]
    snapshot = validate_declaration(_catalog(), declaration)
    assert snapshot["declaration"]["contact"] == declaration["contact"]
    if mode == "none":
        declaration["contact"].pop("pairs")
        assert "pairs" not in validate_declaration(_catalog(), declaration)["declaration"]["contact"]
    declaration["contact"]["master_union_same_slave"] = False
    assert validate_declaration(_catalog(), declaration)["declaration"]["contact"] == declaration["contact"]


def test_partial_prescribed_components_and_balanced_load_vectors_are_not_replaced():
    declaration = _declaration()
    declaration["boundary_conditions"][0]["components"] = {"UX": .02, "UZ": -.01}
    second = deepcopy(declaration["loads"][0])
    second.update(id="L2", selection_id="S-specimen-2", components={"FX": 2.5, "FY": 0.0, "FZ": 100.0})
    declaration["loads"].append(second)
    # IDs are unique within their kind; cross-kind coincidence is not a wire pair ID.
    declaration["loads"][0]["id"] = declaration["materials"][0]["id"]
    snapshot = validate_declaration(_catalog(), declaration)
    assert snapshot["declaration"] == declaration
    assert all(sum(item["components"][axis] for item in snapshot["declaration"]["loads"]) == 0 for axis in ("FX", "FY", "FZ"))


def test_displacement_control_is_explicit_and_has_no_fabricated_load_or_automatic_support():
    declaration = _declaration()
    declaration["loads"] = []
    declaration["boundary_conditions"][0]["components"] = {"UX": 0, "UZ": -.01}
    before = deepcopy(declaration)
    snapshot = validate_declaration(_catalog(), declaration)
    assert snapshot["declaration"] == before == declaration
    assert snapshot["engineering"] == "UNKNOWN" and snapshot["decision"] == "NOT_RELEASED"
    declaration["boundary_conditions"][0]["components"]["UZ"] = 0
    with pytest.raises(ValueError, match="nonzero"): validate_declaration(_catalog(), declaration)


@pytest.mark.parametrize("master", ["a", "b"])
@pytest.mark.parametrize("flag", [None, False, True])
def test_same_slave_master_union_is_explicit_and_preserves_each_original_pair(master, flag):
    catalog, declaration = _catalog(), _declaration()
    contact = declaration["contact"]
    left = contact["pairs"][1]
    left["master"] = "a"
    right = deepcopy(left)
    right.update(selection_a="S-metal_roller_right-1", source="TEST_ONLY separate right roller assumption")
    contact["pairs"].append(right)
    if master == "b":
        for pair in (left, right):
            pair["selection_a"], pair["selection_b"] = pair["selection_b"], pair["selection_a"]
            pair["master"] = "b"
    if flag is not None:
        contact["master_union_same_slave"] = flag
    before = deepcopy((catalog, declaration))
    snapshot = validate_declaration(catalog, declaration)
    assert snapshot["declaration"] == declaration and (catalog, declaration) == before
    assert len(snapshot["declaration"]["contact"]["pairs"]) == 3
    assert ("master_union_same_slave" in snapshot["declaration"]["contact"]) == (flag is not None)
    assert snapshot["engineering"] == "UNKNOWN" and snapshot["decision"] == "NOT_RELEASED"
    snapshot["declaration"]["contact"]["pairs"][1]["source"] = "changed"
    assert (catalog, declaration) == before


@pytest.mark.parametrize("flag", [None, 0, 1, "true", [], {}])
def test_master_union_flag_must_be_boolean(flag):
    declaration = _declaration()
    declaration["contact"]["master_union_same_slave"] = flag
    with pytest.raises(ValueError, match="boolean"):
        validate_declaration(_catalog(), declaration)


@pytest.mark.parametrize("mode", ["none", "bonded", "mixed"])
def test_master_union_refuses_no_contact_and_bonded_shared_slaves(mode):
    declaration = _declaration()
    contact = declaration["contact"]
    contact.update(mode=mode, master_union_same_slave=True)
    contact["pairs"] = [] if mode == "none" else [contact["pairs"][0]]
    if mode == "mixed":
        contact["pairs"].append({"selection_a": "S-metal_roller_left-1", "selection_b": "S-printed_support_left-1",
                                 "law": "frictionless", "master": "a", "source": "TEST_ONLY same bonded slave"})
    with pytest.raises(ValueError, match="union"):
        validate_declaration(_catalog(), declaration)


def _add_interior(catalog, face_id="S-printed_base-2"):
    face = next(row for row in catalog["selections"] if row["id"] == face_id)
    row = deepcopy(face)
    row.update(id="I-" + face_id[2:], kind="assembly_face_interior_nodes", roles=["boundary", "load"],
               node_scope="FACE_INTERIOR_EXCLUDING_OTHER_FACE_BOUNDARIES",
               geometry_metadata_scope="ORIGINAL_SOURCE_FACE_NOT_SUBSET")
    # Deliberately precede the source face: reference checks must run after all rows.
    catalog["selections"].insert(0, row)
    return row


def test_explicit_source_face_interior_preserves_partial_dofs_signed_loads_and_original_geometry():
    catalog, declaration = _catalog(), _declaration()
    interior = _add_interior(catalog)
    declaration["boundary_conditions"][0].update(selection_id=interior["id"], components={"UX": .02, "UZ": -.01})
    declaration["loads"][0]["selection_id"] = interior["id"]
    before = deepcopy((catalog, declaration))
    snapshot = validate_declaration(catalog, declaration)
    assert snapshot["catalog"] == catalog and snapshot["declaration"] == declaration
    assert snapshot["declaration"]["loads"][0]["components"] == {"FX": -2.5, "FY": 0.0, "FZ": -100.0}
    assert snapshot["engineering"] == "UNKNOWN" and snapshot["scope"] == "USER_DECLARED_UNVERIFIED"
    snapshot["catalog"]["selections"][0]["center_mm"][0] = 99
    assert (catalog, declaration) == before


@pytest.mark.parametrize("fault", ["wrong-reference", "missing-face", "wrong-id", "scope", "contact-role",
                                   "material-role", "center", "area", "bounds", "metadata-scope"])
def test_face_interior_must_join_exact_original_face_metadata_and_roles(fault):
    catalog = _catalog()
    row = _add_interior(catalog)
    if fault == "wrong-reference":
        row["catalog_face_id"] = "printed_base:face:2:" + "c" * 64
    elif fault == "missing-face":
        catalog["selections"] = [item for item in catalog["selections"] if item["id"] != "S-printed_base-2"]
    elif fault == "wrong-id":
        row["id"] = "I-printed_base-1"
    elif fault == "scope":
        row["node_scope"] = "AUTOMATIC_GUIDE"
    elif fault in ("contact-role", "material-role"):
        row["roles"].append(fault.split("-")[0])
    elif fault == "center":
        row["center_mm"][0] = .5
    elif fault == "area":
        row["area_mm2"] = 9.0
    elif fault == "bounds":
        row["bounds_mm"]["size_mm"][0] = 1.0
    else:
        row["geometry_metadata_scope"] = "SUBSET_GEOMETRY"
    with pytest.raises(ValueError):
        validate_declaration(catalog, _declaration())


@pytest.mark.parametrize("kind", ["contact", "materials"])
def test_valid_interior_selection_cannot_be_used_as_contact_or_material(kind):
    catalog, declaration = _catalog(), _declaration()
    row = _add_interior(catalog)
    if kind == "contact":
        declaration["contact"]["pairs"][0]["selection_a"] = row["id"]
    else:
        declaration["materials"][0]["selection_id"] = row["id"]
    with pytest.raises(ValueError, match="role"):
        validate_declaration(catalog, declaration)


@pytest.mark.parametrize("component", INACTIVE)
@pytest.mark.parametrize("kind", ["materials", "boundary_conditions", "loads", "contact"])
def test_each_omitted_fastener_cannot_receive_any_condition(component, kind):
    declaration = _declaration()
    if kind == "contact":
        declaration["contact"]["pairs"][0]["selection_b"] = f"S-{component}-1"
    else:
        declaration[kind][0]["selection_id"] = ("B-" if kind == "materials" else "S-") + component + ("" if kind == "materials" else "-1")
    with pytest.raises(ValueError, match="active"):
        validate_declaration(_catalog(), declaration)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "reassigned", "missing-body", "duplicate-selection", "duplicate-pair"])
def test_material_coverage_and_selection_contact_ambiguity_refuse(fault):
    catalog, declaration = _catalog(), _declaration()
    if fault == "missing":
        declaration["materials"].pop()
    elif fault == "duplicate":
        declaration["materials"].append(deepcopy(declaration["materials"][0]))
    elif fault == "reassigned":
        declaration["materials"][1]["selection_id"] = declaration["materials"][0]["selection_id"]
    elif fault == "missing-body":
        catalog["selections"].pop(0)
    elif fault == "duplicate-selection":
        catalog["selections"].append(deepcopy(catalog["selections"][0]))
    else:
        duplicate = deepcopy(declaration["contact"]["pairs"][0])
        duplicate["selection_a"], duplicate["selection_b"] = duplicate["selection_b"], duplicate["selection_a"]
        declaration["contact"]["pairs"].append(duplicate)
    with pytest.raises(ValueError):
        validate_declaration(catalog, declaration)


@pytest.mark.parametrize("group", ["boundary_conditions", "loads"])
def test_duplicate_ids_within_each_boundary_or_load_kind_are_refused(group):
    declaration = _declaration()
    declaration[group].append(deepcopy(declaration[group][0]))
    with pytest.raises(ValueError, match="unique per kind"):
        validate_declaration(_catalog(), declaration)


@pytest.mark.parametrize("path,value", [
    (("analysis_type",), "linear_static"), (("analysis_type",), "transient"),
    (("coordinate_system",), "local"), (("units", "force"), "kN"),
    (("mesh", "mesh_revision"), "c" * 64), (("mesh", "mode"), "selected"),
    (("materials", 0, "law"), "orthotropic"), (("materials", 0, "young_modulus_MPa"), 0),
    (("materials", 0, "young_modulus_MPa"), True), (("materials", 0, "young_modulus_MPa"), float("inf")),
    (("materials", 0, "poisson_ratio"), -1.0), (("materials", 0, "poisson_ratio"), .5),
    (("materials", 0, "source", "category"), "QUALIFIED"), (("materials", 0, "source", "description"), " "),
    (("boundary_conditions", 0, "components"), {}), (("boundary_conditions", 0, "components"), {"RZ": 0}),
    (("boundary_conditions", 0, "components"), {"UX": True}), (("boundary_conditions", 0, "components"), {"UZ": float("nan")}),
    (("boundary_conditions", 0, "coordinate_system"), "local"), (("boundary_conditions", 0, "source"), ""),
    (("loads", 0, "components"), {"FX": 0, "FY": 0, "FZ": 0}), (("loads", 0, "components"), {"FZ": -100}),
    (("loads", 0, "components"), {"FX": False, "FY": 0, "FZ": -100}), (("loads", 0, "unit"), "kN"),
    (("loads", 0, "source"), " "), (("loads", 0, "selection_id"), "B-metal_loading_nose"),
    (("contact", "mode"), "none"), (("contact", "mode"), "bonded"), (("contact", "mode"), "friction"),
    (("contact", "pairs"), []), (("contact", "source"), ""),
    (("contact", "pairs", 0, "law"), "frictional"), (("contact", "pairs", 0, "master"), "auto"),
    (("contact", "pairs", 0, "source"), " "), (("contact", "pairs", 0, "distance_max_mm"), 0),
    (("contact", "pairs", 0, "distance_max_mm"), True), (("contact", "pairs", 0, "distance_max_mm"), float("inf")),
    (("contact", "pairs", 0, "selection_b"), "S-printed_base-2"),
    (("contact", "pairs", 0, "selection_b"), "S-printed_base-1"),
    (("contact", "pairs", 1, "distance_max_mm"), .01)])
def test_unsupported_or_incomplete_declarations_refuse_without_mutation(path, value):
    catalog, declaration = _catalog(), _declaration()
    _put(declaration, path, value)
    before = deepcopy((catalog, declaration))
    with pytest.raises(ValueError):
        validate_declaration(catalog, declaration)
    assert (catalog, declaration) == before


@pytest.mark.parametrize("path,value", [
    (("cad_backend",), "fixture.cadquery"), (("model",), "roller_support"), (("integrity",), "UNKNOWN"),
    (("cad_revision",), "C" * 64), (("retained_mesh", "cad_revision"), "c" * 64),
    (("retained_mesh", "profile"), "fine1_5"), (("retained_mesh", "mesh_revision"), "bad"),
    (("retained_mesh", "active_components"), ACTIVE[:-1]),
    (("retained_mesh", "active_components"), ACTIVE[:-1] + [INACTIVE[0]]),
    (("coordinate_systems", 0, "origin"), [1, 0, 0]), (("coordinate_systems", 0, "basis", 0, 0), True),
    (("native_frame_mapping", "source"), "local_print_frame"), (("native_frame_mapping", "sensor_world_alignment"), "PASS"),
    (("native_frame_mapping", "basis", 1, 1), 2),
    (("selections", 1, "component_id"), "printed_support_left"), (("selections", 1, "native_ordinal"), 2),
    (("selections", 1, "local_ordinal"), True), (("selections", 1, "catalog_face_id"), "display-triangle-1"),
    (("selections", 1, "native_coordinate_system"), "local_print_frame"), (("selections", 1, "cad_revision"), "c" * 64),
    (("selections", 1, "area_mm2"), 0), (("selections", 1, "area_mm2"), float("nan")),
    (("selections", 1, "bounds_mm", "size_mm"), [2, -3, 4]), (("selections", 1, "center_mm"), [1, 2, float("inf")]),
    (("selections", 1, "roles"), ["display_only"])])
def test_foreign_revision_frame_native_geometry_or_mesh_catalog_refuse(path, value):
    catalog = _catalog()
    _put(catalog, path, value)
    with pytest.raises(ValueError):
        validate_declaration(catalog, _declaration())


@pytest.mark.parametrize("path,key", [
    (("contact", "pairs", 0), "law"), (("contact", "pairs", 0), "master"),
    (("contact", "pairs", 0), "source"), (("contact", "pairs", 0), "distance_max_mm"),
    (("materials", 0), "source"), (("boundary_conditions", 0), "source")])
def test_required_sources_laws_masters_and_bond_distance_have_no_defaults(path, key):
    declaration = _declaration()
    value = declaration
    for part in path:
        value = value[part]
    value.pop(key)
    with pytest.raises(ValueError):
        validate_declaration(_catalog(), declaration)


@pytest.mark.parametrize("path,key,value", [
    ((), "guide", "automatic"), (("boundary_conditions", 0), "spring", 1000),
    (("loads", 0), "preload", 200), (("contact", "pairs", 0), "id", "CP1"),
    (("contact", "pairs", 1), "friction_coefficient", .2), (("mesh",), "max_size_mm", 3)])
def test_unrequested_guides_springs_preload_pair_ids_friction_and_remesh_are_not_inferred(path, key, value):
    declaration = _declaration()
    target = declaration
    for part in path:
        target = target[part]
    target[key] = value
    with pytest.raises(ValueError):
        validate_declaration(_catalog(), declaration)
