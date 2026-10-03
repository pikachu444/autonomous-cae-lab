"""Pure topology/input fidelity; retained MED read-back is not mechanics."""
from copy import deepcopy
import ast
import hashlib
import json
from pathlib import Path
import struct

import pytest

from caelab.adapters import codeaster_contact_mesh as mesh
from caelab.adapters import codeaster_contact_worker as worker
from plugins.contact_patch import reference as domain

STAGE = Path(__file__).resolve().parents[1]
ASSETS = STAGE / "benchmarks/input-data/codeaster"


@pytest.fixture(scope="module")
def original():
    return json.loads((ASSETS / "ssnp121a-17.4.0.mesh.json").read_text())


@pytest.fixture(scope="module")
def plan(original):
    return mesh.subdivide_original_catalog(original)


def settings():
    return {"case": worker.CASE, "material": {"youngs_modulus_pa": 2e6, "poisson_ratio": 0.0},
            "top_displacement_m": -0.1, "limits": {"reference_relative": 0.01, "force_balance_relative": 1e-6}}


def test_default_normalized_settings_declaration_and_reference_are_exactly_the_original_source_contract():
    # Frozen fd41 producer snapshots are independent of the candidate import path.
    golden = {
        (2e6, -0.1): ("8004bae3618b82454dcf9fe206efb08b038a0f378e3bffff7ca27121363d08ae",
                       "1d7da7bbef48f68170a1c991d8ba4946be365c9035ebe3fb2677ec609ea16ed9",
                       "e57a0eab2ad7d539bc662e049f2d662d157abf5f33fc48b3b1714ed0b31bc8fa"),
        (1e6, -0.05): ("3c24d784aec8ea0431bf76453f487efa4097dddfe9e6f39c23abe620f1b8841e",
                        "84604ba21fec59477f870ad011dfa33b855cef611e90368fe3bd43554d1a7357",
                        "6f8b44d2e5c7a98dba400ffd538846ff90688344772d8dcf1f5f17f89c5b6032"),
    }
    for (young, displacement), expected in golden.items():
        request = settings()
        request["material"]["youngs_modulus_pa"], request["top_displacement_m"] = young, displacement
        observed = tuple(mesh.canonical_sha(value) for value in (
            domain.validate_settings(request), domain.model_declaration(request), domain.analytical_reference(request)))
        assert observed == expected
        assert set(domain.validate_settings(request)) == {"case", "material", "top_displacement_m", "limits"}


def test_deterministic_complete_plan_matches_actual_one_shot_native_MED_readback(original, plan):
    before = deepcopy(original)
    assert mesh.subdivide_original_catalog(original) == plan
    assert original == before
    actual = json.loads((ASSETS / "ssnp121a-17.4.0.uniform_quad4_2x.mesh.json").read_text())
    for key in ("coordinates_in_native_order", "levels", "node_groups", "node_name_field"):
        assert actual[key] == plan[key]
    assert len(plan["coordinates_in_native_order"]) == 1154
    assert len(plan["node_parent_map"]) == 1154
    assert sum(row["origin"] == "edge_midpoint" for row in plan["node_parent_map"]) == 576
    assert sum(row["origin"] == "parent_center" for row in plan["node_parent_map"]) == 265
    assert [plan["node_groups"][name]["node_ids"] for name in ("A", "B", "N14")] == [[0], [1], [13]]
    for a, b in zip(plan["coordinates_in_native_order"][:313], original["coordinates_in_native_order"]):
        assert [struct.pack(">d", value) for value in a] == [struct.pack(">d", value) for value in b]
    assert plan["coordinates_in_native_order"][13][0] == 2.98023223876953e-08
    assert len(plan["levels"]["-1"]["groups"]["AB"]["node_ids"]) == 25
    assert len(plan["levels"]["-1"]["groups"]["EF"]["node_ids"]) == 23
    assert set(plan["levels"]["-1"]["groups"]["AB"]["node_ids"]).isdisjoint(plan["levels"]["-1"]["groups"]["EF"]["node_ids"])
    assert len(plan["cell_parent_map"]["0"]) == 1060 and len(plan["cell_parent_map"]["-1"]) == 184
    assert actual["solver_calls"] == 0 and actual["medcoupling_version"] == "9.14.0"


@pytest.mark.parametrize("damage", ["prefix", "midpoint", "center", "node_parent", "cell_parent", "connectivity", "direction", "group", "named"])
def test_generated_fidelity_damage_is_refused_before_native_write(original, plan, damage):
    candidate = deepcopy(plan)
    if damage == "prefix": candidate["coordinates_in_native_order"][13][0] = 0.0
    elif damage == "midpoint": candidate["coordinates_in_native_order"][313][0] += 1e-6
    elif damage == "center": candidate["coordinates_in_native_order"][889][1] += 1e-6
    elif damage == "node_parent": candidate["node_parent_map"][313]["source_edge_node_ids"].reverse()
    elif damage == "cell_parent": candidate["cell_parent_map"]["0"][0]["source_cell_id"] = 1
    elif damage == "connectivity": candidate["levels"]["0"]["cell_connectivity_in_native_order"][0].reverse()
    elif damage == "direction": candidate["levels"]["-1"]["cell_connectivity_in_native_order"][0].reverse()
    elif damage == "group": candidate["levels"]["-1"]["groups"]["AB"]["cell_ids"].pop()
    elif damage == "named": candidate["node_groups"]["A"]["node_ids"] = [4]
    with pytest.raises(ValueError):
        mesh.validate_refined_plan(candidate, original)


def test_generation_parent_must_be_the_sealed_original_not_an_equivalent_coordinate_guess(original):
    original = deepcopy(original)
    original["coordinates_in_native_order"][13][0] = 0.0
    with pytest.raises(ValueError, match="sealed original"):
        mesh.subdivide_original_catalog(original)


def test_profile_asset_and_generator_recipe_pins_bind_genuine_preparation_bytes(tmp_path):
    profile_path = ASSETS / mesh.PROFILE_NAME
    profile = mesh.load_profile(profile_path, worker.REFINED_PROFILE_SHA256)
    selected = mesh.contract(mesh.VARIANT, profile)
    for suffix, key in (("mmed", "mesh_sha256"), ("mesh.json", "catalog_sha256"), ("generation.json", "recipe_sha256")):
        data = (ASSETS / ("ssnp121a-17.4.0.uniform_quad4_2x." + suffix)).read_bytes()
        assert hashlib.sha256(data).hexdigest() == selected[key]
    assert hashlib.sha256(Path(mesh.__file__).read_bytes()).hexdigest() == selected["generator_sha256"]
    changed = tmp_path / "profile.json"
    changed.write_bytes(profile_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="bytes changed"):
        mesh.load_profile(changed, worker.REFINED_PROFILE_SHA256)


@pytest.mark.parametrize("damage", ["shape", "parent", "missing_pin", "extra_pin", "bad_digest", "bool_digest"])
def test_unsealed_or_malformed_profile_cannot_define_a_new_admitted_mesh(damage):
    profile = mesh.load_profile(ASSETS / mesh.PROFILE_NAME, worker.REFINED_PROFILE_SHA256)
    if damage == "shape": profile["shape"]["node_count"] = 313
    elif damage == "parent": profile["parent"]["mesh_sha256"] = "0" * 64
    elif damage == "missing_pin": del profile["pins"]["recipe_sha256"]
    elif damage == "extra_pin": profile["pins"]["arbitrary_path"] = "/tmp/other.mmed"
    elif damage == "bad_digest": profile["pins"]["mesh_sha256"] = "G" * 64
    elif damage == "bool_digest": profile["pins"]["generator_sha256"] = True
    with pytest.raises(ValueError):
        mesh.contract(mesh.VARIANT, profile)


def test_omitted_default_does_not_require_or_read_the_optional_refined_profile(monkeypatch):
    monkeypatch.setattr(mesh, "load_profile", lambda *args: pytest.fail("Default tried to load a refined profile"))
    assert worker.selected_mesh_contract() == mesh.ORIGINAL
    assert worker.mesh_contracts.variant(settings()) is None


def test_reused_native_policy_and_variable_field_math_are_unchanged_from_Main():
    candidate_tree = ast.parse(Path(worker.__file__).read_text())
    # Hashes are of fd41 ASTs without source location attributes.
    original = {"_final_order": "58770727043d632a4e94e73abdebcd9bfbdff86f6e3502b38b2a5325f907dfc4",
                "_nodal": "01026b89555616595454adfadba9987ab7effd81d64103c76fd6a4834db6f62d",
                "_quad_gauss_geometry": "620981b48b69fd14350e1df09ad2510bb12c0bb64780e912a5df69cdd73f9234",
                "_stress": "6415319ce7df15aaadd95bfe8b141806b2d88fc76172e1c31b626205d5cb7fc2",
                "_projected_gaps": "243b8c9aa57f1385d690bddf8e113b8f2ab7f38efc1050615d73993827bb4603"}
    candidate = {node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                 for node in candidate_tree.body if isinstance(node, ast.FunctionDef) and node.name in original}
    assert candidate == original
    assert mesh.canonical_sha(worker.NATIVE_POLICY) == "1203ace0f094fca20ff6614ea8971b7cff7ef83310b2e511586bceaa10e038e5"
