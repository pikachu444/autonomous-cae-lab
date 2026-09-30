"""Declared-input contract checks using a TEST ONLY, solver-free adapter.

The quadratic and domain budget below are synthetic bookkeeping examples.
These tests establish no material, numerical-physics or engineering acceptance.
"""

from copy import deepcopy
from pathlib import Path

import pytest

from caelab import Lab
from caelab.contracts import CapabilityUnavailable
from caelab.model_parameters import ModelInputRejected, bind, describe, expected_settings
from caelab.storage import canonical_hash, load_json, save_json


STUDY = "S-model-inputs"


def template_settings():
    return {"inputs": {"x": 1.0, "y": 1.0},
            "mesh": {"cell_count": 4, "degree": 1},
            "load": {"force": 2.0, "source": "TEST ONLY: fixed context"},
            "validation": {"max_error": 0.125},
            "flags": {"audit": True}, "domain_budget": 5.5}


class SyntheticParameterizedModel:
    """TEST ONLY: named inputs, preserved context and synthetic observations."""

    backend = "test.model.parameterized"
    version = "test-only-1"
    domain = "structure"
    physics_domain = "solid_mechanics"
    analysis_type = "linear_static"
    default_metrics = ["synthetic_objective", "synthetic_constraint"]
    input_source_files = [Path(__file__).resolve()]

    def __init__(self, *, metric_overrides=None, check_status="PASS", crash=False):
        self.calls = 0
        self.solved_settings = []
        self.metric_overrides = deepcopy(metric_overrides or {})
        self.check_status = check_status
        self.crash = crash
        self.runtime_version = "1"
        self.solver_version = "TEST-ONLY-1"

    def input_runtime_identity(self):
        return {"test_only": True, "version": self.runtime_version}

    def describe_inputs(self, settings):
        return [
            {"id": "input_x", "label": "Synthetic X", "unit": "1",
             "value": settings["inputs"]["x"], "lower": 0.0, "upper": 4.0,
             "settings_path": ["inputs", "x"],
             "declaration_paths": [["model", "geometry", "values", "x"],
                                   ["model", "materials", 0, "synthetic_x"]]},
            {"id": "input_y", "label": "Synthetic Y", "unit": "1",
             "value": settings["inputs"]["y"], "lower": 0.0, "upper": 4.0,
             "settings_path": ["inputs", "y"],
             "declaration_paths": [["model", "geometry", "values", "y"]]},
        ]

    def describe_model(self, settings):
        x, y = settings["inputs"]["x"], settings["inputs"]["y"]
        if x + y > settings["domain_budget"]:
            raise ValueError("TEST ONLY: domain budget exceeded")
        return {
            "model": {
                "geometry": {"kind": "test_only_declared_inputs", "values": {"x": x, "y": y}},
                "mesh": deepcopy(settings["mesh"]),
                "materials": [{"id": "test-material", "qualified": False, "synthetic_x": x}],
                "sections": [], "interfaces": [], "contact": [], "coordinate_systems": [],
            },
            "loads": [{"type": "force", "region": "test-region", "value": settings["load"]["force"],
                       "unit": "N", "source": settings["load"]["source"]}],
            "boundary_conditions": [{"type": "test_only", "region": "test-region", "value": 0.0}],
            "outputs": {"metrics": deepcopy(self.default_metrics)},
            "reference": {"source": "TEST ONLY: no physical reference"},
            "fixed_context": {"validation": deepcopy(settings["validation"]),
                              "flags": deepcopy(settings["flags"]),
                              "domain_budget": settings["domain_budget"]},
        }

    def bind_inputs(self, settings, values):
        bound = deepcopy(settings)
        for name, value in values.items():
            bound["inputs"][{"input_x": "x", "input_y": "y"}[name]] = value
        return bound

    def solve(self, output, settings):
        # A violated synthetic domain must be rejected before this entry point.
        assert settings["inputs"]["x"] + settings["inputs"]["y"] <= settings["domain_budget"]
        self.calls += 1
        self.solved_settings.append(deepcopy(settings))
        output.mkdir()
        save_json(output / "input.json", settings)
        (output / "raw.log").write_text("TEST ONLY: synthetic observation; no native solver executed\n")
        if self.crash:
            raise RuntimeError("TEST ONLY: synthetic execution failure")
        x, y = settings["inputs"]["x"], settings["inputs"]["y"]
        metrics = {
            "synthetic_objective": {"value": (x - 1.25) ** 2 + (y - 1.75) ** 2,
                                    "unit": "1", "valid": True},
            "synthetic_constraint": {"value": x + y, "unit": "1", "valid": True},
        }
        metrics.update(deepcopy(self.metric_overrides))
        checks = ([] if self.check_status == "MISSING" else
                  [{"code": "synthetic_check", "status": self.check_status,
                    "observed": 0.0, "limit": 0.01}])
        outcome = {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
                   "metrics": metrics, "checks": checks,
                   "pending_validations": ["material_qualification"],
                   "provenance": {"test_only": True, "versions": {"solver": self.solver_version}},
                   "raw_result": "simulation/result.json"}
        save_json(output / "result.json", outcome)
        return outcome


def synthetic_lab(path, adapter=None, *, create_study=True):
    adapter = adapter or SyntheticParameterizedModel()
    lab = Lab(path, adapters={}, analysis_adapters={}, doe_adapters={}, pde_adapters={},
              model_analysis_adapters={adapter.backend: adapter})
    if create_study:
        lab.create_study(STUDY, "TEST ONLY model inputs", "Are declared bindings independently checked?",
                         "Declared-input effects do not qualify physics", "Preserve exact research context")
    return lab, adapter


def register_x(lab, **changes):
    options = {"study_id": STUDY, "backend": SyntheticParameterizedModel.backend,
               "settings": template_settings(), "input_id": "input_x", "parameter_id": "research_x",
               "display_name": "Research X", "lower": 0.0, "upper": 4.0}
    options.update(changes)
    return lab.register_model_parameter(**options)


def test_discovery_and_registration_are_read_only_to_settings_and_never_execute_solver(tmp_path):
    lab, adapter = synthetic_lab(tmp_path)
    settings = template_settings()
    retained = deepcopy(settings)
    found = lab.discover_model_parameters(adapter.backend, settings)
    description = describe(lab, adapter.backend, settings)
    assert [item["native"]["path"] for item in found] == ["input_x", "input_y"]
    assert all(item["native"]["object"] == "declared_inputs" for item in found)
    assert all(item["native"]["document"] == description["revision"] for item in found)
    assert {item["unit"] for item in found} == {"1"}
    found[0]["native"]["path"] = "changed-returned-copy"
    assert lab.discover_model_parameters(adapter.backend, settings)[0]["native"]["path"] == "input_x"
    assert lab.registry(STUDY) == {"revision": 0, "entries": []}
    entry = register_x(lab, settings=settings)
    assert entry["target"] == "model_analysis" and "geometry_effect" not in entry
    effect = entry["input_effect"]
    assert effect["status"] == "PASS" and "UNKNOWN" in effect["scope"]
    assert effect["bound_declaration_sha256"][0] != effect["bound_declaration_sha256"][1]
    assert entry["model_template_revision"] == description["revision"]
    assert entry["input_descriptor_sha256"] == canonical_hash(description["descriptors"])
    assert lab.registry(STUDY) == {"revision": 1, "entries": [entry]}
    assert load_json(lab.store / "studies" / STUDY / "registry_history/0000.json") == {
        "revision": 0, "entries": []}
    assert settings == retained and adapter.calls == 0
    assert not (lab.store / "experiments").exists()


def test_binding_applies_only_selected_locations_and_preserves_fixed_types(tmp_path):
    lab, adapter = synthetic_lab(tmp_path)
    settings = template_settings()
    description = describe(lab, adapter.backend, settings)
    assignments = {"input_x": 2.5}
    expected = deepcopy(settings)
    expected["inputs"]["x"] = 2.5
    bound = bind(adapter, settings, assignments)
    assert bound == expected_settings(settings, description["descriptors"], assignments) == expected
    assert settings == template_settings()
    assert type(bound["mesh"]["cell_count"]) is int and type(bound["flags"]["audit"]) is bool
    model = adapter.describe_model(bound)
    assert model["model"]["geometry"]["values"] == {"x": 2.5, "y": 1.0}
    assert model["model"]["materials"][0]["synthetic_x"] == 2.5
    before = adapter.describe_model(settings)
    before["model"]["geometry"]["values"]["x"] = 2.5
    before["model"]["materials"][0]["synthetic_x"] = 2.5
    assert canonical_hash(before) == canonical_hash(model) and adapter.calls == 0


@pytest.mark.parametrize("hidden", ["load", "mesh", "limit", "boolean_type", "integer_type"])
def test_reversible_setter_cannot_hide_changes_to_fixed_context(tmp_path, monkeypatch, hidden):
    lab, adapter = synthetic_lab(tmp_path)
    settings = template_settings()
    original = adapter.bind_inputs

    def reversible_setter(source, values):
        bound = original(source, values)
        delta = bound["inputs"]["x"] - source["inputs"]["x"]
        if hidden == "load":
            bound["load"]["force"] += delta
        elif hidden == "mesh":
            bound["mesh"]["degree"] = int(source["mesh"]["degree"] + delta)
        elif hidden == "limit":
            bound["validation"]["max_error"] += delta
        elif hidden == "boolean_type":
            bound["flags"]["audit"] = 1 if bound["inputs"]["x"] != 1.0 else True
        else:
            bound["mesh"]["cell_count"] = 4.0 if bound["inputs"]["x"] != 1.0 else 4
        return bound

    monkeypatch.setattr(adapter, "bind_inputs", reversible_setter)
    changed = adapter.bind_inputs(settings, {"input_x": 2.0})
    restored = adapter.bind_inputs(changed, {"input_x": 1.0})
    assert canonical_hash(restored) == canonical_hash(settings)
    with pytest.raises(ValueError, match="outside its declared locations"):
        bind(adapter, settings, {"input_x": 2.0})
    with pytest.raises(ValueError, match="outside its declared locations"):
        register_x(lab)
    assert lab.registry(STUDY)["revision"] == 0 and adapter.calls == 0


@pytest.mark.parametrize("hidden", ["load", "mesh", "limit", "boolean_type", "integer_type"])
def test_declaration_changes_outside_selected_inputs_are_rejected(tmp_path, monkeypatch, hidden):
    lab, adapter = synthetic_lab(tmp_path)
    original = adapter.describe_model

    def changed_declaration(settings):
        result = original(settings)
        if settings["inputs"]["x"] != 1.0:
            if hidden == "load":
                result["loads"][0]["value"] = 3.0
            elif hidden == "mesh":
                result["model"]["mesh"]["degree"] = 2
            elif hidden == "limit":
                result["fixed_context"]["validation"]["max_error"] = 0.5
            elif hidden == "boolean_type":
                result["model"]["materials"][0]["qualified"] = 0
            else:
                result["model"]["mesh"]["cell_count"] = 4.0
        return result

    monkeypatch.setattr(adapter, "describe_model", changed_declaration)
    with pytest.raises(ValueError, match="frozen declaration outside selected inputs"):
        bind(adapter, template_settings(), {"input_x": 2.0})
    assert adapter.calls == 0


BAD_DESCRIPTOR_PATHS = [
    pytest.param("settings_path", [], id="empty"),
    pytest.param("settings_path", ("inputs", "x"), id="tuple-not-list"),
    pytest.param("settings_path", ["inputs", True], id="boolean-key"),
    pytest.param("settings_path", ["inputs", -1], id="negative-index"),
    pytest.param("settings_path", ["inputs", 0], id="integer-in-mapping"),
    pytest.param("settings_path", ["inputs", "absent"], id="missing-leaf"),
    pytest.param("settings_path", ["flags", "audit"], id="boolean-leaf"),
    pytest.param("settings_path", ["load", "source"], id="text-leaf"),
    pytest.param("declaration_paths", [["model", "materials", "0", "synthetic_x"]], id="string-list-index"),
    pytest.param("declaration_paths", [["model", "materials", 99, "synthetic_x"]], id="absent-list-index"),
    pytest.param("declaration_paths", [["model", "materials", 0, "qualified"]], id="boolean-model-leaf"),
]


@pytest.mark.parametrize("field,path", BAD_DESCRIPTOR_PATHS)
def test_discovery_requires_typed_existing_finite_scalar_leaves(tmp_path, monkeypatch, field, path):
    lab, adapter = synthetic_lab(tmp_path)
    original = adapter.describe_inputs

    def malformed(settings):
        descriptors = original(settings)
        descriptors[0][field] = deepcopy(path)
        return descriptors

    monkeypatch.setattr(adapter, "describe_inputs", malformed)
    with pytest.raises(ValueError):
        lab.discover_model_parameters(adapter.backend, template_settings())
    assert lab.registry(STUDY)["revision"] == 0 and adapter.calls == 0


@pytest.mark.parametrize("which", ["settings_repeat", "settings_prefix", "declaration_repeat", "declaration_prefix"])
def test_overlapping_locations_are_rejected_before_binding(tmp_path, monkeypatch, which):
    lab, adapter = synthetic_lab(tmp_path)
    original = adapter.describe_inputs

    def overlapping(settings):
        descriptors = original(settings)
        if which == "settings_repeat":
            descriptors[1]["settings_path"] = deepcopy(descriptors[0]["settings_path"])
        elif which == "settings_prefix":
            descriptors[0]["settings_path"] = ["inputs"]
        elif which == "declaration_repeat":
            descriptors[1]["declaration_paths"] = [deepcopy(descriptors[0]["declaration_paths"][0])]
        else:
            descriptors[0]["declaration_paths"] = [["model", "geometry"]]
        return descriptors

    monkeypatch.setattr(adapter, "describe_inputs", overlapping)
    with pytest.raises(ValueError, match="overlap or repeat"):
        lab.discover_model_parameters(adapter.backend, template_settings())
    assert adapter.calls == 0


@pytest.mark.parametrize("assignment", [
    {"unadvertised_input": 2.0}, {"input_x": True}, {"input_x": -0.01},
    {"input_x": 4.01}, {"input_x": float("nan")}, {"input_x": float("inf")}, {},
])
def test_unadvertised_nonfinite_boolean_and_out_of_domain_assignments_never_call_setter(tmp_path, monkeypatch, assignment):
    _, adapter = synthetic_lab(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid assignment must fail before its setter")

    monkeypatch.setattr(adapter, "bind_inputs", forbidden)
    with pytest.raises(ValueError, match="advertised, finite, in-domain"):
        bind(adapter, template_settings(), assignment)


@pytest.mark.parametrize("change", [
    {"input_id": "unadvertised"}, {"lower": -0.1}, {"upper": 4.1},
    {"lower": 1.5}, {"upper": 0.5}, {"lower": True}, {"upper": float("inf")},
])
def test_invalid_registration_preserves_the_empty_registry(tmp_path, change):
    lab, adapter = synthetic_lab(tmp_path)
    with pytest.raises(ValueError):
        register_x(lab, **change)
    assert lab.registry(STUDY) == {"revision": 0, "entries": []}
    assert not (lab.store / "studies" / STUDY / "registry_history/0001.json").exists()
    assert adapter.calls == 0


@pytest.mark.parametrize("kind", ["empty_sources", "duplicate_sources", "outside_source", "directory_source",
                                "missing_runtime", "empty_runtime", "non_mapping_runtime"])
def test_binding_identity_requires_project_sources_and_callable_nonempty_runtime(tmp_path, monkeypatch, kind):
    lab, adapter = synthetic_lab(tmp_path / "store")
    if kind == "empty_sources":
        monkeypatch.setattr(adapter, "input_source_files", [])
    elif kind == "duplicate_sources":
        monkeypatch.setattr(adapter, "input_source_files", adapter.input_source_files * 2)
    elif kind == "outside_source":
        outside = tmp_path / "outside.py"
        outside.write_text("# TEST ONLY\n")
        monkeypatch.setattr(adapter, "input_source_files", [outside])
    elif kind == "directory_source":
        monkeypatch.setattr(adapter, "input_source_files", [Path(__file__).resolve().parent])
    elif kind == "missing_runtime":
        monkeypatch.setattr(adapter, "input_runtime_identity", None)
    else:
        monkeypatch.setattr(adapter, "input_runtime_identity", lambda: {} if kind == "empty_runtime" else [])
    with pytest.raises(ValueError):
        lab.discover_model_parameters(adapter.backend, template_settings())
    assert adapter.calls == 0


def test_missing_parameter_capability_and_duplicate_registration_are_explicit(tmp_path, monkeypatch):
    lab, adapter = synthetic_lab(tmp_path)
    with pytest.raises(CapabilityUnavailable):
        lab.discover_model_parameters("missing.model", template_settings())
    register_x(lab)
    previous = lab.registry(STUDY)
    with pytest.raises(ValueError, match="already registered"):
        register_x(lab)
    assert lab.registry(STUDY) == previous
    monkeypatch.setattr(adapter, "describe_inputs", None)
    with pytest.raises(CapabilityUnavailable):
        lab.discover_model_parameters(adapter.backend, template_settings())
    assert adapter.calls == 0


@pytest.mark.parametrize("fault", ["extra_key", "missing_unit", "duplicate_id", "unsafe_id",
                                 "boolean_value", "boolean_bound", "infinite_bound", "value_mismatch"])
def test_malformed_input_descriptors_cannot_become_candidates(tmp_path, monkeypatch, fault):
    lab, adapter = synthetic_lab(tmp_path)
    original = adapter.describe_inputs

    def malformed(settings):
        items = original(settings)
        if fault == "extra_key":
            items[0]["expression"] = "arbitrary expression is not an input binding"
        elif fault == "missing_unit":
            items[0].pop("unit")
        elif fault == "duplicate_id":
            items[1]["id"] = items[0]["id"]
        elif fault == "unsafe_id":
            items[0]["id"] = "inputs.x"
        elif fault == "boolean_value":
            items[0]["value"] = True
        elif fault == "boolean_bound":
            items[0]["lower"] = False
        elif fault == "infinite_bound":
            items[0]["upper"] = float("inf")
        else:
            items[0]["value"] = 1.5
        return items

    monkeypatch.setattr(adapter, "describe_inputs", malformed)
    with pytest.raises(ValueError):
        lab.discover_model_parameters(adapter.backend, template_settings())
    assert adapter.calls == 0 and lab.registry(STUDY)["revision"] == 0


@pytest.mark.parametrize("fault", ["registered_bound", "unregistered_research_id", "hidden_setting", "fixed_mode"])
def test_direct_declared_execution_checks_registered_assignments_before_reserving_experiment(tmp_path, fault):
    lab, adapter = synthetic_lab(tmp_path)
    register_x(lab, upper=2.0, mode="fixed" if fault == "fixed_mode" else "free")
    description = describe(lab, adapter.backend, template_settings())
    research_id = "unregistered" if fault == "unregistered_research_id" else "research_x"
    value = 3.0 if fault == "registered_bound" else 1.5
    settings = template_settings()
    settings["inputs"]["x"] = value
    if fault == "hidden_setting":
        settings["load"]["force"] = 999.0
    binding = {"template_settings": template_settings(), "template_revision": description["revision"],
               "input_ids": {research_id: "input_x"}, "source_fingerprint": description["fingerprint"]}
    with pytest.raises(ValueError):
        lab.run_model_analysis(study_id=STUDY, experiment_id="E-invalid-binding", backend=adapter.backend,
                               settings=settings, values={research_id: value}, binding=binding)
    assert adapter.calls == 0 and not (lab.store / "experiments").exists()


def _codeaster_binding_settings(current_modulus):
    # Deliberately retain integer fixed inputs. The pure domain declaration
    # normalizes these, but binding must preserve the requested settings types.
    return {"case": "uniaxial_block", "dimensions_mm": [40, 10, 10],
            "material": {"youngs_modulus_mpa": current_modulus, "poisson_ratio": 0.3},
            "traction_mpa": 10, "mesh_sizes_mm": [5, 3],
            "limits": {"displacement_relative": 1e-8, "displacement_absolute_mm": 1e-12,
                       "stress_relative": 1e-8, "reaction_relative": 1e-8,
                       "mesh_agreement_relative": 1e-8}}


@pytest.mark.parametrize("current_modulus", [210000, 210000.0], ids=["integer-template", "float-template"])
@pytest.mark.parametrize("assigned_modulus", [100000, 250000, 300000], ids=["lower", "interior", "upper"])
def test_codeaster_float_descriptor_admits_integer_modulus_and_registration_bounds(tmp_path, monkeypatch,
                                                                                 current_modulus, assigned_modulus):
    from caelab.adapters.codeaster_elasticity import CodeAsterElasticityAdapter

    adapter = CodeAsterElasticityAdapter()
    # Only runtime fingerprinting is substituted. Real descriptor, declaration
    # and setter methods execute; no solve/native process is requested.
    monkeypatch.setattr(adapter, "input_runtime_identity", lambda: {"test_only": True, "version": "1"})
    lab, _ = synthetic_lab(tmp_path, adapter)
    settings = _codeaster_binding_settings(current_modulus)
    retained = deepcopy(settings)
    descriptors = adapter.describe_inputs(settings)
    assert type(descriptors[0]["value"]) is float
    entry = lab.register_model_parameter(STUDY, adapter.backend, settings, "youngs_modulus_mpa",
                                         "research_E", "Young's modulus", 100000, 300000)
    assert entry["input_effect"]["status"] == "PASS"
    assert type(entry["lower_bound"]) is int and type(entry["upper_bound"]) is int
    bound = bind(adapter, settings, {"youngs_modulus_mpa": assigned_modulus})
    expected = deepcopy(settings)
    expected["material"]["youngs_modulus_mpa"] = assigned_modulus
    assert canonical_hash(bound) == canonical_hash(expected)
    assert type(bound["material"]["youngs_modulus_mpa"]) is int
    assert type(bound["traction_mpa"]) is int and all(type(value) is int for value in bound["mesh_sizes_mm"])
    assert canonical_hash(settings) == canonical_hash(retained)
    assert adapter.describe_inputs(bound)[0]["value"] == float(assigned_modulus)
    actual_model = adapter.describe_model(bound)
    expected_model = adapter.describe_model(settings)
    expected_model["model"]["materials"][0]["youngs_modulus"]["value"] = float(assigned_modulus)
    assert canonical_hash(actual_model) == canonical_hash(expected_model)
    assert not (lab.store / "experiments").exists()


def test_codeaster_integer_normalization_does_not_admit_boolean_modulus(tmp_path, monkeypatch):
    from caelab.adapters.codeaster_elasticity import CodeAsterElasticityAdapter

    adapter = CodeAsterElasticityAdapter()
    monkeypatch.setattr(adapter, "input_runtime_identity", lambda: {"test_only": True, "version": "1"})
    lab, _ = synthetic_lab(tmp_path, adapter)
    settings = _codeaster_binding_settings(210000)
    with pytest.raises(ValueError, match="advertised, finite, in-domain"):
        bind(adapter, settings, {"youngs_modulus_mpa": True})
    with pytest.raises(ValueError):
        lab.register_model_parameter(STUDY, adapter.backend, settings, "youngs_modulus_mpa",
                                     "research_E", "Young's modulus", True, 300000)
    assert lab.registry(STUDY) == {"revision": 0, "entries": []}
    assert not (lab.store / "experiments").exists()


class InteriorMalformedModel(SyntheticParameterizedModel):
    """TEST ONLY: valid template/endpoints, broken metadata at X=2."""

    def __init__(self, fault):
        super().__init__()
        self.fault = fault

    def describe_inputs(self, settings):
        items = super().describe_inputs(settings)
        if settings["inputs"]["x"] == 2.0:
            if self.fault == "missing_unit":
                items[0].pop("unit")
            elif self.fault == "duplicate_id":
                items[1]["id"] = items[0]["id"]
            elif self.fault == "invalid_typed_path":
                items[0]["settings_path"] = ["inputs", True]
        return items

    def describe_model(self, settings):
        model = super().describe_model(settings)
        if settings["inputs"]["x"] == 2.0 and self.fault == "missing_model":
            model.pop("model")
        return model


@pytest.mark.parametrize("fault", ["missing_unit", "duplicate_id", "invalid_typed_path", "missing_model"])
def test_interior_returned_metadata_is_contract_error_not_domain_rejection(tmp_path, fault):
    lab, adapter = synthetic_lab(tmp_path, InteriorMalformedModel(fault))
    entry = register_x(lab)
    assert entry["input_effect"]["status"] == "PASS"
    for endpoint in (0.0, 4.0):
        assert bind(adapter, template_settings(), {"input_x": endpoint})["inputs"]["x"] == endpoint
    with pytest.raises(ValueError) as raised:
        bind(adapter, template_settings(), {"input_x": 2.0})
    assert not isinstance(raised.value, ModelInputRejected)
    assert adapter.calls == 0 and not (lab.store / "experiments").exists()


@pytest.mark.parametrize("context", ["load", "mesh", "empty_return"])
def test_nondeterministic_final_declaration_after_valid_binding_blocks_execution(tmp_path, monkeypatch, context):
    lab, adapter = synthetic_lab(tmp_path)
    register_x(lab)
    description = describe(lab, adapter.backend, template_settings())
    binding = {"template_settings": template_settings(), "template_revision": description["revision"],
               "input_ids": {"research_x": "input_x"}, "source_fingerprint": description["fingerprint"]}
    original = adapter.describe_model
    bound_descriptions = []

    def nondeterministic(settings):
        model = original(settings)
        if settings["inputs"]["x"] == 2.0:
            bound_descriptions.append(deepcopy(model))
            # The first bound description passes bind's context check. The
            # final description changes context without changing settings.
            if len(bound_descriptions) == 2:
                if context == "load":
                    model["loads"][0]["value"] = 3.0
                elif context == "mesh":
                    model["model"]["mesh"]["degree"] = 2
                else:
                    model = {}
        return model

    monkeypatch.setattr(adapter, "describe_model", nondeterministic)
    settings = template_settings()
    settings["inputs"]["x"] = 2.0
    retained = deepcopy(settings)
    with pytest.raises(ValueError, match="Final model declaration changed frozen context") as raised:
        lab.run_model_analysis(study_id=STUDY, experiment_id="E-nondeterministic-declaration",
                               backend=adapter.backend, settings=settings,
                               values={"research_x": 2.0}, binding=binding)
    assert not isinstance(raised.value, ModelInputRejected)
    assert len(bound_descriptions) == 2 and adapter.calls == 0
    assert canonical_hash(settings) == canonical_hash(retained)
    assert not (lab.store / "experiments").exists()
