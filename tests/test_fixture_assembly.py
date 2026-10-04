"""Focused CAD-only source gate; production admits no mocked happy path."""
from copy import deepcopy
import hashlib
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest


HERE = Path(__file__).resolve()
ROOT = next(p for p in HERE.parents if (p / "PROJECT_SCOPE.md").is_file())
sys.path.insert(0, str(ROOT))
CANDIDATE = HERE.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ad = load("caelab.adapters._assembly_candidate_tests", CANDIDATE / "caelab/adapters/fixture_assembly.py")
worker = load("_assembly_worker_candidate_tests", CANDIDATE / "caelab/adapters/fixture_assembly_worker.py")


@pytest.fixture(scope="module")
def adapter():
    return ad.FixtureAssemblyAdapter()


@pytest.fixture(scope="module")
def default_native(adapter, tmp_path_factory):
    folder = tmp_path_factory.mktemp("actual-default") / "cad"
    outcome = adapter.regenerate(ad.MODEL, {}, folder)
    result = json.loads((folder / "result.json").read_text())
    assert outcome.generated, json.dumps(result.get("checks") + result.get("cad_checks"), indent=2)
    assert outcome.decision == "REVIEW_REQUIRED"
    return folder, result, json.loads((folder / "assembly_catalog.json").read_text()), json.loads((folder / "surface.json").read_text())


@pytest.fixture(scope="module")
def native_bodies(default_native):
    import cadquery as cq
    folder, result, catalog, _ = default_native
    root, native = worker.read_named_step(folder / "assembly.step", cq)
    bodies = {}
    for component in catalog["components"]:
        body = deepcopy(component)
        actual_faces = native[body["id"]]["shape"].Faces()
        body["face_shapes"] = {face["id"]: actual_faces[face["local_ordinal"] - 1] for face in body["faces"]}
        bodies[body["id"]] = body
    return cq, root, native, bodies, result


def test_exact_descriptors_stable_definition(adapter):
    descriptors = adapter.discover(ad.MODEL)
    assert [d.native["path"] for d in descriptors] == list(ad.PARAMETERS)
    assert [d.value for d in descriptors] == [80, 10, 4, 16]
    assert [d.unit for d in descriptors] == ["mm", "mm", "mm", "1"]
    assert all(d.lower is None and d.upper is None for d in descriptors)
    before = adapter.source_fingerprint()
    assert ad.full_input({"specimen.width": 12})["specimen"]["width"] == 12
    assert adapter.source_fingerprint() == before
    assert all(d.source_sha256 == before["source_sha256"] for d in descriptors)
    assert before["commit"] == "UNKNOWN" and before["git_dirty"] is None
    assert before["recorded_upstream_pin"] == ad.RECORDED_UPSTREAM_PIN
    assert "domain/assembly_interfaces.py" in before["files"]


@pytest.mark.parametrize("values", [{"specimen.length": True}, {"specimen.width": None},
    {"specimen.width": "12"}, {"specimen.thickness": math.nan}, {"specimen.span_ratio": math.inf},
    {"specimen.span_ratio": -math.inf}, {"specimen.strength": 90}, {"path": "/tmp/foreign"},
    {"caller_code": "print(1)"}, [], None])
def test_input_shape_fail_before_process(adapter, values, tmp_path):
    folder = tmp_path / "invalid"
    with pytest.raises(ValueError):
        adapter.regenerate(ad.MODEL, values, folder)
    assert not folder.exists()


@pytest.mark.parametrize("method", ["discover", "regenerate", "preflight_effects"])
def test_unsupported_model(adapter, method, tmp_path):
    with pytest.raises(ValueError):
        if method == "discover":
            adapter.discover("other")
        elif method == "regenerate":
            adapter.regenerate("other", {}, tmp_path / "not-exported")
        else:
            adapter.preflight_effects("other", {})


def test_domain_roles_and_interfaces():
    declaration = ad.assembly_declarations()
    assert len(declaration["component_roles"]) == 15
    assert len(declaration["interfaces"]) == 15
    assert sum(i["kind"] == "bolt_head_seat" for i in declaration["interfaces"]) == 8
    assert {i["kind"] for i in declaration["interfaces"]} == {"base_support", "cradle_roller", "roller_specimen", "nose_specimen", "bolt_head_seat"}
    assert all(i["a"] in declaration["component_roles"] and i["b"] in declaration["component_roles"] for i in declaration["interfaces"])


@pytest.mark.parametrize("values", [{"specimen.length": 70}, {"specimen.width": 17},
    {"specimen.span_ratio": 4}, {"specimen.thickness": 20}, {"specimen.length": 2001},
    {"specimen.thickness": 0}, {"specimen.width": -1}])
def test_original_relation_gate_no_build_or_export(values):
    sys.path.insert(0, str(ad.UPSTREAM))
    from fixturelab import core, handcheck
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid original input crossed build/export gate")
    cad = SimpleNamespace(build=forbidden, export_and_check=forbidden)
    try:
        result, parts = worker._build(ad.full_input(values), core, cad, None, handcheck)
    except ValueError:
        return  # Upstream positive/resource validation refuses before CAD.
    assert result["decision"] == "REJECTED" and parts == []
    assert any(c["status"] == "FAIL" for c in result["checks"])


def test_retained_invalid_relation_and_no_native(adapter, tmp_path):
    folder = tmp_path / "actual-rejected"
    outcome = adapter.regenerate(ad.MODEL, {"specimen.length": 70}, folder)
    assert outcome.decision == "REJECTED" and not outcome.generated and outcome.native_revision is None
    assert (folder / "input.json").is_file() and (folder / "result.json").is_file()
    assert json.loads((folder / "input.json").read_text())["specimen"]["length"] == 70
    assert not list(folder.rglob("*.step")) and not list(folder.rglob("*.stl")) and not list(folder.rglob("*.3mf"))
    assert json.loads((folder / "process.json").read_text())["solver_calls"] == 0


def test_retained_positive_validation_failure(adapter, tmp_path):
    folder = tmp_path / "actual-invalid-zero"
    outcome = adapter.regenerate(ad.MODEL, {"specimen.thickness": 0}, folder)
    assert outcome.decision == "COMPUTATION_ERROR" and not outcome.generated
    assert (folder / "input.json").is_file() and (folder / "result.json").is_file()
    assert not list(folder.rglob("*.step"))
    assert any(c["code"] == "assembly_generation_integrity" for c in outcome.checks)


def test_complete_fresh_native_identity(default_native):
    folder, result, catalog, surface = default_native
    ad.verify_result(folder, result, ad.fingerprint())
    assert result["source_fingerprint_before"] == result["source_fingerprint_after"]
    assert result["source_sha256"] == ad.fingerprint()["source_sha256"]
    assert result["runtime"]["python"] == sys.version.split()[0]
    assert result["runtime"]["libraries"]["cadquery"] == importlib.metadata.version("cadquery")
    assert catalog["component_count"] == 15 and catalog["face_count"] == 117
    assert {c["id"] for c in catalog["components"]} == set(worker.REQUIRED)
    assert len(surface["faces"]) == 117
    assert {f["id"] for f in surface["faces"]} == set(range(1, 118))
    assert all(len(t) == 9 and all(math.isfinite(v) for v in t) for f in surface["faces"] for t in f["triangles"])
    assert all(c["xde_product_name"] == c["id"] and c["native_build_to_step_identity"]["relative_symmetric_difference"] < 1e-6 for c in catalog["components"])
    assert sum(c["code"].startswith("bolt_slot_clearance_span_") for c in result["cad_checks"]) == 3
    assert next(c for c in result["cad_checks"] if c["code"] == "pre_export_initial_position_interference")["detail"]["actual_pair_count"] == 105
    assert all(c["status"] == "PASS" for c in result["cad_checks"])
    assert result["specimen_hand_check"]["status"] == "MATCH"
    assert result["production_release"] == "UNKNOWN" and catalog["mechanics"] == "NOT_RUN"
    assert result["pending_validations"] == ad.PENDING
    assert result["native_revision"] == hashlib.sha256(ad.canonical(ad.revision_material(result))).hexdigest()
    assert surface["display_only"] is True and surface["frame"] == catalog["frame"]
    for component in catalog["components"]:
        assert (folder / component["global_step_path"]).is_file()
        if component["role"] == "printed":
            assert (folder / (component["id"] + ".stl")).is_file()
            assert (folder / (component["id"] + ".3mf")).is_file()
            assert "NOT assembled" in component["manufacturing_export_frame"]["meaning"]
    recipe = json.loads((folder / "rebuild_recipe.json").read_text())
    assert recipe["captured_input"] == json.loads((folder / "input.json").read_text())
    assert recipe["portable_rebuild"] == "NOT_VERIFIED" and recipe["freecad_parametric_document"] == "NOT_PROVIDED"


def test_all_actual_individual_bolt_seats(default_native):
    _, _, catalog, _ = default_native
    seats = [i for i in catalog["interfaces"] if "_head_to_support_seat" in i["id"]]
    assert len(seats) == 8 and len({i["b"]["face_ids"][0] for i in seats}) == 8
    for seat in seats:
        observation = seat["geometry_observation"]
        assert observation["actual_bolt_xy_mm"] == pytest.approx(observation["actual_seat_xy_mm"], abs=observation["identity_linear_tolerance_mm"])
        assert observation["head_wire_count"] == observation["seat_wire_count"] == 2
        assert observation["coplanar_overlap_area_mm2"] > 0 and observation["normal_dot"] < 0
        assert observation["minimum_distance_mm"] <= observation["identity_linear_tolerance_mm"]
        assert seat["contact_force"] == seat["loaded_contact_gap"] == seat["preload"] == "UNKNOWN"


def test_actual_parameter_effect_without_extra_export(adapter, default_native, tmp_path, monkeypatch):
    monkeypatch.setattr(ad.tempfile, "tempdir", str(tmp_path))
    descriptor = next(c for c in adapter.discover(ad.MODEL) if c.native["path"] == "specimen.width")
    effect = adapter.probe_effect(ad.MODEL, descriptor, 10, 12)
    assert effect["status"] == "PASS" and effect["symmetric_difference_mm3"] == pytest.approx(640)
    assert effect["probe_value"] == 12 and effect["solver_tolerance"] is None
    probe = json.loads((Path(adapter.last_worker_evidence) / "result.json").read_text())
    assert probe["source_fingerprint_before"] == probe["source_fingerprint_after"]
    assert not list(Path(adapter.last_worker_evidence).rglob("*.step"))
    assert probe["source_sha256"] == default_native[1]["source_sha256"]


def test_actual_named_readback_does_not_follow_array_order(native_bodies):
    _, _, native, _, result = native_bodies
    parts = [{"name": name, "kind": worker.REQUIRED[name], "shape": native[name]["shape"]} for name in reversed(list(native))]
    sys.path.insert(0, str(ad.UPSTREAM))
    from fixturelab import functional_checks
    checks = worker.pre_export_parts(parts, result, functional_checks)
    assert all(c["status"] == "PASS" for c in checks)


@pytest.mark.parametrize("problem", ["missing", "duplicate", "role", "multi-solid", "shifted-roller"])
def test_invalid_native_geometry_before_export(native_bodies, problem):
    cq, _, native, _, result = native_bodies
    parts = [{"name": name, "kind": worker.REQUIRED[name], "shape": native[name]["shape"]} for name in native]
    if problem == "missing":
        parts.pop()
    elif problem == "duplicate":
        parts[1]["name"] = parts[0]["name"]
    elif problem == "role":
        parts[0]["kind"] = "foreign"
    elif problem == "multi-solid":
        parts[0]["shape"] = cq.Compound.makeCompound([parts[0]["shape"], parts[0]["shape"].translate(cq.Vector(500, 0, 0))])
    else:
        part = next(p for p in parts if p["name"] == "metal_roller_left")
        part["shape"] = part["shape"].translate(cq.Vector(0, 0, 1))
    sys.path.insert(0, str(ad.UPSTREAM))
    from fixturelab import functional_checks
    if problem == "shifted-roller":
        checks = worker.pre_export_parts(parts, result, functional_checks)
        assert any(c["status"] == "FAIL" for c in checks)
    else:
        with pytest.raises(ValueError):
            worker.pre_export_parts(parts, result, functional_checks)


@pytest.mark.parametrize("problem", ["missing-seat", "ambiguous-seat", "missing-head", "wrong-xy"])
def test_required_native_interface_failclosed(native_bodies, problem):
    cq, _, _, original, _ = native_bodies
    # Retain genuine native Shapes, copy the measured catalog only.
    bodies = {name: {**body, "faces": deepcopy(body["faces"])} for name, body in original.items()}
    bolt = "metal_bolt_left_-10_-12"
    head = next(f for f in bodies[bolt]["faces"] if f["geom_type"] == "PLANE" and f["wire_count"] == 2)
    support = bodies["printed_support_left"]
    seat = next(f for f in support["faces"] if f["geom_type"] == "PLANE" and f["wire_count"] == 2 and abs(f["center_of_mass_mm"][2] - 28) < 1e-7 and max(abs(a-b) for a,b in zip(f["center_of_mass_mm"][:2],head["center_of_mass_mm"][:2])) < 1e-7)
    if problem == "missing-seat":
        support["faces"].remove(seat)
    elif problem == "ambiguous-seat":
        support["faces"].append(deepcopy(seat))
    elif problem == "missing-head":
        bodies[bolt]["faces"].remove(head)
    else:
        seat["center_of_mass_mm"][0] += 1
    with pytest.raises(ValueError, match="Ambiguous or missing"):
        worker.interface_catalog(bodies, cq)


@pytest.mark.parametrize("identity", [0, -1, 0x1000000, 1.5, True, "1"])
def test_display_id_reserved_or_malformed(default_native, identity):
    _, _, catalog, original = default_native
    surface = deepcopy(original)
    surface["faces"][0]["id"] = identity
    with pytest.raises(ValueError, match="24-bit"):
        ad.validate_catalog(catalog, surface)


@pytest.mark.parametrize("problem", ["duplicate-id", "foreign-face", "missing-face", "nonfinite-triangle", "bad-triangle", "foreign-component", "different-frame"])
def test_display_catalog_joins_failclosed(default_native, problem):
    _, _, catalog, original = default_native
    surface = deepcopy(original)
    if problem == "duplicate-id":
        surface["faces"][1]["id"] = surface["faces"][0]["id"]
    elif problem == "foreign-face":
        surface["faces"][0]["catalog_face_id"] = "foreign"
    elif problem == "missing-face":
        surface["faces"].pop()
    elif problem == "nonfinite-triangle":
        surface["faces"][0]["triangles"][0][0] = math.nan
    elif problem == "bad-triangle":
        surface["faces"][0]["triangles"][0].pop()
    elif problem == "foreign-component":
        surface["faces"][0]["component_id"] = "printed_base"
    else:
        surface["bounds"][0][0] += 1
    with pytest.raises(ValueError):
        ad.validate_catalog(catalog, surface)


@pytest.mark.parametrize("problem", ["missing-component", "role", "duplicate-face", "foreign-interface", "native-path"])
def test_catalog_native_joins_failclosed(default_native, problem):
    _, _, original, surface = default_native
    catalog = deepcopy(original)
    if problem == "missing-component":
        catalog["components"].pop()
    elif problem == "role":
        catalog["components"][0]["role"] = "foreign"
    elif problem == "duplicate-face":
        catalog["components"][0]["faces"].append(deepcopy(catalog["components"][0]["faces"][0]))
    elif problem == "foreign-interface":
        catalog["interfaces"][0]["b"]["component_id"] = "specimen"
    else:
        catalog["components"][0]["global_step_path"] = "foreign.step"
    with pytest.raises(ValueError):
        ad.validate_catalog(catalog, surface)


@pytest.mark.parametrize("problem", ["catalog-hash", "surface-hash", "input-hash", "recipe-hash", "native-revision", "source-before", "source-after", "native-size", "native-hash"])
def test_native_revision_and_byte_integrity(default_native, problem):
    folder, original, _, _ = default_native
    result = deepcopy(original)
    if problem.endswith("-hash") and problem.split("-")[0] in {"catalog", "surface", "input", "recipe"}:
        result[problem.split("-")[0] + "_sha256"] = "0" * 64
    elif problem == "native-revision":
        result["native_revision"] = "0" * 64
    elif problem.startswith("source-"):
        result["source_fingerprint_" + problem.split("-")[1]]["files_sha256"] = "0" * 64
    elif problem == "native-size":
        result["native_files"]["assembly.step"]["size_bytes"] += 1
    else:
        result["native_files"]["assembly.step"]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        ad.verify_result(folder, result, ad.fingerprint())


def test_no_overwrite_historical_or_completed_output(adapter, default_native):
    folder, _, _, _ = default_native
    prior = {p.relative_to(folder).as_posix(): ad.sha256(p) for p in folder.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="Fresh"):
        adapter.regenerate(ad.MODEL, {}, folder)
    assert prior == {p.relative_to(folder).as_posix(): ad.sha256(p) for p in folder.rglob("*") if p.is_file()}


def test_source_drift_blocks_admission(default_native, monkeypatch):
    folder, result, _, _ = default_native
    expected = ad.fingerprint()
    changed = deepcopy(expected)
    changed["files_sha256"] = "0" * 64
    monkeypatch.setattr(ad, "fingerprint", lambda: changed)
    with pytest.raises(ValueError, match="source changed"):
        ad.verify_result(folder, result, expected)


def test_native_unsafe_paths_reject(default_native):
    folder = default_native[0]
    for path in ("../assembly.step", "/assembly.step", "C:/foreign.step", "a\\b.step", "assembly.step/..", "missing.step"):
        with pytest.raises(ValueError):
            ad._safe_path(folder, path)


def test_actual_corrupt_step_refused(tmp_path):
    import cadquery as cq
    file = tmp_path / "corrupt.step"
    file.write_text("not an ISO STEP document", encoding="utf-8")
    with pytest.raises(ValueError):
        worker.read_named_step(file, cq)


def test_unadmitted_parent_must_not_have_revision():
    source = ad.fingerprint()
    result = {"source_sha256": source["source_sha256"], "source_fingerprint_before": source, "cad_generated": False, "native_revision": "f" * 64}
    with pytest.raises(ValueError, match="Unadmitted"):
        ad.verify_result(Path("."), result, source)


def test_invalid_built_shape_blocks_export(native_bodies, monkeypatch, adapter, tmp_path):
    _, _, native, _, result = native_bodies
    parts = [{"name": name, "kind": worker.REQUIRED[name], "shape": native[name]["shape"]} for name in native]
    next(p for p in parts if p["name"] == "metal_roller_left")["shape"] = next(p for p in parts if p["name"] == "metal_roller_left")["shape"].translate((0, 0, 1))
    sys.path.insert(0, str(ad.UPSTREAM))
    from fixturelab import core, handcheck, functional_checks
    calls = []
    cad = SimpleNamespace(build=lambda _: parts, export_and_check=lambda *args: calls.append(args))
    folder = tmp_path / "actual-negative-orchestration"
    folder.mkdir()
    request = {"action": "regenerate", "model": ad.MODEL, "native_values": {}, "source_fingerprint": worker.ad.fingerprint()}
    worker.ad._save(folder / "request.json", request)
    snapshot = folder / "captured_source"
    (snapshot / "domain").mkdir(parents=True)
    (snapshot / "domain/assembly_interfaces.py").write_bytes(ad.DOMAIN.read_bytes())
    # Only the negative injection is controlled: real readback geometry is
    # shifted, and the production run branch must retain failure without export.
    monkeypatch.setattr(worker, "source_capture", lambda *args: snapshot)
    monkeypatch.setattr(worker, "native_modules", lambda: (None, core, cad, functional_checks, handcheck))
    checked = worker.run(folder / "request.json")
    assert checked["decision"] == "COMPUTATION_ERROR" and any(c["status"] == "FAIL" for c in checked["cad_checks"])
    assert not checked["cad_generated"] and checked["native_revision"] is None and calls == []
    assert (folder / "result.json").is_file() and not list(folder.rglob("*.step"))


def test_owned_process_cleanup_retains_failure(adapter, tmp_path, monkeypatch):
    from caelab.execution_control import ExecutionCancelled
    class Child:
        def poll(self):
            return -15
    child, stopped = Child(), []
    monkeypatch.setattr(ad.subprocess, "Popen", lambda *args, **kwargs: child)
    def cancel(*args, **kwargs):
        raise ExecutionCancelled("Focused cancellation control")
    monkeypatch.setattr(ad, "wait_for_process", cancel)
    monkeypatch.setattr(ad, "stop_owned_process", lambda process, **kwargs: stopped.append(process))
    folder = tmp_path / "cancelled"
    with pytest.raises(ExecutionCancelled):
        adapter.regenerate(ad.MODEL, {}, folder)
    assert stopped == [child]
    receipt = json.loads((folder / "process.json").read_text())
    assert receipt["owned_process_reaped"] and receipt["wall_timeout_seconds"] is None
    assert (folder / "request.json").is_file() and (folder / "worker.stderr.txt").is_file()


@pytest.mark.parametrize("exit_code", [0, 1, 17, -9])
def test_worker_exit_before_positive_admission(default_native, tmp_path, monkeypatch, exit_code):
    """Retained genuine positive fixture under an explicitly injected source context.

    A controlled owned child transports the same complete positive bytes. It
    runs no CAD. A nonzero process exit must block before result verification
    or Outcome admission, even when every positive payload byte is present.
    """
    source_folder, positive, _, _ = default_native
    expected_context = deepcopy(positive["source_fingerprint_before"])
    assert positive["cad_generated"] is True and positive["decision"] == "REVIEW_REQUIRED"
    assert positive["source_fingerprint_after"] == expected_context
    assert positive["source_sha256"] == expected_context["source_sha256"]
    # CI supplies the existing module fixture; the private correction evaluator
    # supplies the retained original tuple. Neither uses a hardcoded store path.
    monkeypatch.setattr(ad, "fingerprint", lambda: deepcopy(expected_context))
    admitted, launches = [], []
    actual_verifier = ad.verify_result
    def record_verification(*args):
        admitted.append(args[0])
        return actual_verifier(*args)
    monkeypatch.setattr(ad, "verify_result", record_verification)
    source_files = {p.relative_to(source_folder).as_posix(): ad.sha256(p)
                    for p in source_folder.rglob("*") if p.is_file()}
    owned = tmp_path / ("exit-" + str(exit_code))
    class OwnedChild:
        def poll(self):
            return exit_code
    child = OwnedChild()
    def launch(command, **kwargs):
        request_path = Path(command[-1])
        assert request_path.parent == owned
        assert kwargs["cwd"] == ad.ROOT
        launches.append(child)
        # Preserve process/request/log files owned by _call itself. All other
        # native/raw/source bytes are independent copies of the genuine fixture.
        for relative in source_files:
            if relative in {"request.json", "process.json", "worker.stdout.txt", "worker.stderr.txt"}:
                continue
            target = owned / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_folder / relative, target)
        return child
    monkeypatch.setattr(ad.subprocess, "Popen", launch)
    monkeypatch.setattr(ad, "wait_for_process", lambda process, timeout: exit_code)
    adapter = ad.FixtureAssemblyAdapter()
    if exit_code == 0:
        outcome = adapter.regenerate(ad.MODEL, {}, owned)
        assert outcome.generated and outcome.decision == "REVIEW_REQUIRED"
        assert outcome.native_revision == positive["native_revision"]
        assert admitted == [owned]
    else:
        expected_error = f"Assembly worker exited with code {exit_code}; no result admitted; evidence retained at {owned}"
        with pytest.raises(RuntimeError) as failure:
            adapter.regenerate(ad.MODEL, {}, owned)
        assert str(failure.value) == expected_error
        assert admitted == []
    assert launches == [child]
    process = json.loads((owned / "process.json").read_text())
    assert process["exit_code"] == exit_code and process["wall_timeout_seconds"] is None
    assert process["solver_calls"] == process["provider_calls"] == process["git_queries"] == 0
    assert ad.sha256(owned / "result.json") == ad.sha256(source_folder / "result.json")
    for relative, digest in source_files.items():
        assert ad.sha256(source_folder / relative) == digest
        if relative not in {"request.json", "process.json", "worker.stdout.txt", "worker.stderr.txt"}:
            assert ad.sha256(owned / relative) == digest
    assert adapter.last_worker_evidence == str(owned)
