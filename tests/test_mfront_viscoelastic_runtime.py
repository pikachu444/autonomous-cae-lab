"""TEST ONLY runtime/evidence doubles; no compiler, MGIS or MTest is executed."""

from copy import deepcopy
import hashlib
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from caelab import execution_control
from caelab.adapters import mfront_viscoelastic as adapter_module
from caelab.adapters import mfront_viscoelastic_worker as worker
from caelab.storage import load_json, save_json
from plugins.material_point import viscoelastic_reference as ref
from test_mfront_viscoelastic import (clean_environment, fake_runtime,
    install_testonly_executor, no_native, table_text)
from test_viscoelastic_reference import FakeBinding, FakeTransport, make_raw


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(scope="module")
def raw_template(tmp_path_factory):
    return make_raw(tmp_path_factory.mktemp("runtime-TEST-ONLY"))


@pytest.mark.parametrize("ending", ["LF", "CRLF"])
@pytest.mark.parametrize("mode", ["package", "standalone"])
def test_exact_reviewed_transport_variants_load_same_content_bind_actual_bytes(tmp_path, monkeypatch, ending, mode):
    original = adapter_module.transport.WORKER.read_bytes()
    normalized = original.replace(b"\r\n", b"\n")
    data = normalized if ending == "LF" else normalized.replace(b"\n", b"\r\n")
    expected = digest(data)
    assert worker.TRANSPORT_VARIANTS[expected] == len(data)
    path = tmp_path / "mfront_material_worker.py"
    path.write_bytes(data)
    monkeypatch.setattr(worker, "__package__", "TEST_ONLY" if mode == "package" else "")
    monkeypatch.setattr(worker, "__file__", str(tmp_path / "mfront_viscoelastic_worker.py"))
    module = worker._transport(expected, output=tmp_path)
    assert module.COMPILER_POLICY == adapter_module.transport.COMPILER_POLICY
    assert module.sha256(path) == expected and path.read_bytes() == data


@pytest.mark.parametrize("kind", ["extra_newline", "space", "wrong_selected_digest", "unknown_digest"])
def test_transport_unknown_or_wrong_selected_policy_refuses_before_loading(tmp_path, monkeypatch, kind):
    data = adapter_module.transport.WORKER.read_bytes()
    selected = digest(data)
    if kind == "extra_newline":
        data += b"\n"
    elif kind == "space":
        data = data.replace(b"import math", b"import  math", 1)
    elif kind == "wrong_selected_digest":
        selected = next(value for value in worker.TRANSPORT_VARIANTS if value != selected)
    else:
        selected = "f" * 64
    (tmp_path / "mfront_material_worker.py").write_bytes(data)
    monkeypatch.setattr(worker, "__package__", "")
    monkeypatch.setattr(worker, "_checked_module", no_native)
    with pytest.raises(ValueError, match="selected exact reviewed"):
        worker._transport(selected, output=tmp_path)


def test_transport_changed_during_load_is_not_admitted(tmp_path, monkeypatch):
    path = tmp_path / "mfront_material_worker.py"
    path.write_bytes(adapter_module.transport.WORKER.read_bytes())
    expected = worker.sha256(path)
    monkeypatch.setattr(worker, "__package__", "")
    loader = SimpleNamespace(exec_module=lambda module: path.write_bytes(path.read_bytes() + b"\n"))
    monkeypatch.setattr(worker.importlib.util, "spec_from_file_location", lambda *args: SimpleNamespace(loader=loader))
    monkeypatch.setattr(worker.importlib.util, "module_from_spec", lambda spec: SimpleNamespace())
    with pytest.raises(ValueError, match="changed while loading"):
        worker._transport(expected, output=tmp_path)


def test_captured_compiler_helper_requires_exact_selected_source_before_load(tmp_path, monkeypatch):
    path = tmp_path / worker.COMPILER_HELPER_NAME
    path.write_bytes(Path(adapter_module.compiler_helper.__file__).read_bytes())
    expected = worker.sha256(path)
    monkeypatch.setattr(worker, "__package__", "")
    module = worker._compiler_helper(expected, output=tmp_path)
    assert module.BEHAVIOUR == "SaintVenantKirchhoffElasticity"
    assert adapter_module.compiler_helper.BEHAVIOUR == module.BEHAVIOUR
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="selected exact digest"):
        worker._compiler_helper(expected, output=tmp_path)


def tiny_settings(tau):
    settings = ref.canonical_settings(relaxation_time_s=tau)
    settings["history"] = [settings["history"][0],
        {"time_s": math.nextafter(0., 1.), "strain": [.001, -.0002, .0003, .0004, -.0003, .0002]}]
    return ref.validate_settings(settings)


def test_underflowed_native_ratio_blocks_description_export_and_command_domain_limit_survives(tmp_path, monkeypatch):
    clean_environment(monkeypatch)
    settings = tiny_settings(1e6)
    assert settings["history"][1]["time_s"] > 0
    assert settings["history"][1]["time_s"] / settings["material"]["relaxation_time_s"] == 0
    result = ref.analytical_reference(settings)
    assert result["states"][-1]["stored_energy_mpa"] > 0
    monkeypatch.setattr(adapter_module.transport, "_runtime_identity", no_native)
    monkeypatch.setattr(adapter_module, "_process", no_native)
    monkeypatch.setattr(adapter_module.MFrontViscoelasticAdapter, "_capture", no_native)
    adapter = adapter_module.MFrontViscoelasticAdapter()
    with pytest.raises(ValueError, match="native representability"):
        adapter.describe_model(settings)
    outcome = adapter.solve(tmp_path / "refused", settings)
    assert outcome["solver_status"] == "NOT_RUN" and outcome["converged"] is None
    assert "native representability" in outcome["checks"][0]["observed"]
    assert {p.name for p in (tmp_path / "refused").iterdir()} == {"analysis_raw.json"}


def test_positive_subnormal_ratio_has_no_new_scientific_cutoff(monkeypatch):
    clean_environment(monkeypatch)
    settings = tiny_settings(1.)
    assert worker.native_preflight(settings) == settings
    assert adapter_module.MFrontViscoelasticAdapter().describe_model(settings)["model"]["materials"]
    assert ref.FIXED_LIMITS == settings["limits"]


@pytest.mark.parametrize("explicit", [False, True])
def test_actual_default_and_explicit_budgets_bind_command_policy_runtime_raw(tmp_path, monkeypatch, raw_template, explicit):
    calls = install_testonly_executor(monkeypatch, tmp_path, raw_template)
    if explicit:
        monkeypatch.setenv("CAELAB_CODEASTER_TIME_LIMIT_SECONDS", "90123")
        monkeypatch.setenv("CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS", "12345")
    expected_cpu, expected_wall = (90123, 12345) if explicit else (86400, None)
    adapter = adapter_module.MFrontViscoelasticAdapter()
    original_process = adapter_module._process
    waits = []
    def execute(command, folder, label, *, timeout):
        waits.append(timeout)
        return original_process(command, folder, label, timeout)
    monkeypatch.setattr(adapter_module, "_process", execute)
    output = tmp_path / "budget"
    outcome = adapter.solve(output, ref.canonical_settings())
    assert outcome["converged"] is True, outcome
    assert waits == [expected_wall] and f"--cpu={expected_cpu}" in calls[0]
    policy = load_json(output / "frozen_execution_policy.json")
    raw = load_json(output / "native_raw.json")
    assert policy["process_policy"] == adapter._budgets == raw["process_policy"] == raw["runtime"]["process_policy"]
    assert policy["resource_limits"] == raw["resource_limits"] == raw["runtime"]["resource_limits"]
    assert policy["resource_limits"]["cpu_seconds"] == expected_cpu
    assert policy["resource_limits"]["timeout_seconds"] is expected_wall if expected_wall is None else policy["resource_limits"]["timeout_seconds"] == expected_wall
    assert policy["transport_sha256"] == raw["transport_sha256"] == adapter_module.SOURCE_HASHES[worker.TRANSPORT_KEY]
    assert raw["transport_sha256"] in worker.TRANSPORT_VARIANTS
    assert policy["compiler_helper_sha256"] == raw["compiler_helper_sha256"]
    assert raw["source_files"] == adapter_module.SOURCE_HASHES
    assert all(path in raw["source_files"] for path in ("caelab/adapters/codeaster_elasticity.py",
        "caelab/adapters/codeaster_execution.py", "caelab/execution_control.py"))


def test_declared_budget_configuration_drift_blocks_before_process(tmp_path, monkeypatch):
    fake_runtime(monkeypatch, tmp_path)
    adapter = adapter_module.MFrontViscoelasticAdapter()
    monkeypatch.setenv("CAELAB_CODEASTER_TIME_LIMIT_SECONDS", "90123")
    monkeypatch.setattr(adapter_module, "_process", no_native)
    outcome = adapter.solve(tmp_path / "drift", ref.canonical_settings())
    assert outcome["solver_status"] == "FAILED_EXECUTION" and outcome["converged"] is None
    assert not (tmp_path / "drift/input.json").exists()


@pytest.mark.parametrize("exception", [execution_control.ExecutionCancelled, execution_control.ExecutionCleanupFailed])
def test_owned_cancellation_and_cleanup_failure_propagate_preserve_unknown_receipt(tmp_path, monkeypatch, exception):
    fake_runtime(monkeypatch, tmp_path)
    def stop(command, output, label, *, timeout):
        (output / "TEST_ONLY.partial.log").write_text("TEST ONLY partial execution retained")
        raise exception("TEST ONLY owned execution stopped")
    monkeypatch.setattr(adapter_module, "_process", stop)
    output = tmp_path / "stopped"
    with pytest.raises(exception):
        adapter_module.MFrontViscoelasticAdapter().solve(output, ref.canonical_settings())
    receipt = load_json(output / "execution_failure.json")
    assert receipt["status"] == ("CANCELLED" if exception is execution_control.ExecutionCancelled else "CLEANUP_PENDING")
    assert receipt["numerical_verdict"] == "UNKNOWN" and receipt["decision"] == "NOT_RELEASED"
    assert (output / "TEST_ONLY.partial.log").exists() and (output / "input.json").exists()
    assert not (output / "analysis_raw.json").exists()


def test_owner_token_cancellation_is_observed_before_source_capture(tmp_path, monkeypatch):
    clean_environment(monkeypatch)
    monkeypatch.setattr(adapter_module.MFrontViscoelasticAdapter, "_capture", no_native)
    token = execution_control.CancellationToken()
    token.request()
    with execution_control.cancellation_scope(token), pytest.raises(execution_control.ExecutionCancelled):
        adapter_module.MFrontViscoelasticAdapter().solve(tmp_path / "cancelled", ref.canonical_settings())
    assert token.observed and not token.cleanup_pending
    assert load_json(tmp_path / "cancelled/execution_failure.json")["numerical_verdict"] == "UNKNOWN"
    assert not (tmp_path / "cancelled/input.json").exists()


def test_actual_process_owner_helper_is_reused_without_alternate_runner():
    assert adapter_module._process is adapter_module.execution._process


@pytest.mark.parametrize("cause", ["wall-time budget exhausted", "native CPU budget exhausted", "process start failed"])
def test_process_and_budget_failure_retains_logs_and_unknown_not_numerical_nonconvergence(tmp_path, monkeypatch, cause):
    fake_runtime(monkeypatch, tmp_path)
    def fail(command, output, label, *, timeout):
        (output / (label + ".stdout.log")).write_text("TEST ONLY partial stdout")
        raise RuntimeError(cause + "; numerical verdict UNKNOWN")
    monkeypatch.setattr(adapter_module, "_process", fail)
    output = tmp_path / "failed"
    outcome = adapter_module.MFrontViscoelasticAdapter().solve(output, ref.canonical_settings())
    assert outcome["solver_status"] == "FAILED_EXECUTION" and outcome["converged"] is None
    assert outcome["pending_validations"] == ref.PENDING
    assert (output / "viscoelastic_worker.stdout.log").exists()
    assert load_json(output / "execution_failure.json")["numerical_verdict"] == "UNKNOWN"


def change_build(output, change):
    path = output / "build_identity.json"
    build = load_json(path)
    change(build)
    save_json(path, build)


def corrupt_evidence(output, raw, kind):
    if kind == "compiler_hash":
        change_build(output, lambda b: b.update(compiler_commands_sha256="f" * 64))
    elif kind == "record_tokens":
        change_build(output, lambda b: b["compiler_command_evidence"][0]["tokens"].append("-ffast-math"))
    elif kind == "record_recipe":
        change_build(output, lambda b: b["compiler_command_evidence"][0].update(logical_recipe="foreign recipe"))
    elif kind == "record_stage":
        change_build(output, lambda b: b["compiler_command_evidence"][0].update(stage="COMPILE"))
    elif kind == "record_source":
        change_build(output, lambda b: b["compiler_command_evidence"][0].update(source="foreign.cxx"))
    elif kind == "record_target":
        change_build(output, lambda b: b["compiler_command_evidence"][0].update(target="foreign.o"))
    elif kind == "record_command":
        change_build(output, lambda b: b["compiler_command_evidence"][0].update(command="foreign compiler"))
    elif kind == "record_missing":
        change_build(output, lambda b: b["compiler_command_evidence"].pop())
    elif kind == "makefile_flags":
        change_build(output, lambda b: b["compiler_flags_makefile"].append("foreign flags"))
    elif kind == "dependency_hash":
        change_build(output, lambda b: b.update(dependency_artifact_sha256="f" * 64))
    elif kind == "dependency_foreign_set":
        change_build(output, lambda b: b["dependency_sha256"].update({"/foreign.so": "a" * 64}))
    elif kind == "dependency_noncanonical":
        change_build(output, lambda b: b.update(dependency_sha256={"/x/../foreign.so": "a" * 64}))
    elif kind.startswith("dependency_log_"):
        path = output / "library_dependencies.stdout.log"
        suffix = {"dependency_log_unresolved": "libmissing.so => not found\n",
                  "dependency_log_duplicate": path.read_text(),
                  "dependency_log_unknown": "foreign metadata\n"}[kind]
        path.write_text(path.read_text() + suffix)
        change_build(output, lambda b: b.update(dependency_artifact_sha256=worker.sha256(path)))
    elif kind == "compiler_log_rehashed_foreign":
        path = output / "build/compile.stdout.log"
        path.write_text(path.read_text().replace("-lTFELMath", "-lForeignMath"))
        change_build(output, lambda b: b.update(compiler_commands_sha256=worker.sha256(path)))
    elif kind == "transport_wrong_variant":
        raw["transport_sha256"] = next(value for value in worker.TRANSPORT_VARIANTS if value != raw["transport_sha256"])
    elif kind == "transport_capture_replaced_variant":
        path = output / "mfront_material_worker.py"
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    elif kind == "compiler_helper_capture":
        path = output / worker.COMPILER_HELPER_NAME
        path.write_bytes(path.read_bytes() + b"\n")
    elif kind == "source_inventory":
        save_json(output / "source_inventory.json", {"foreign": "a" * 64})
    elif kind == "raw_process_policy":
        raw["process_policy"]["solver_time_seconds"] += 1
    elif kind == "policy_resource_limits":
        path = output / "frozen_execution_policy.json"
        policy = load_json(path)
        policy["resource_limits"]["timeout_seconds"] = 240
        save_json(path, policy)
    elif kind == "mtest_actual_table":
        path = output / "mtest.res"
        path.write_text(path.read_text() + "0 " * 21 + "\n")
    else:
        raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["compiler_hash", "record_tokens", "record_recipe", "record_stage", "record_source",
    "record_target", "record_command", "record_missing", "makefile_flags", "dependency_hash", "dependency_foreign_set",
    "dependency_noncanonical", "dependency_log_unresolved", "dependency_log_duplicate", "dependency_log_unknown",
    "compiler_log_rehashed_foreign", "transport_wrong_variant", "transport_capture_replaced_variant", "compiler_helper_capture",
    "source_inventory", "raw_process_policy", "policy_resource_limits", "mtest_actual_table"])
def test_retained_actual_compiler_dependency_transport_process_and_table_corruption_refuses(tmp_path, monkeypatch, raw_template, kind):
    install_testonly_executor(monkeypatch, tmp_path, raw_template, lambda p, r: corrupt_evidence(p, r, kind))
    output = tmp_path / "corrupted"
    outcome = adapter_module.MFrontViscoelasticAdapter().solve(output, ref.canonical_settings())
    assert outcome["solver_status"] == "FAILED_EXECUTION" and outcome["converged"] is None, kind
    assert outcome["pending_validations"] == ref.PENDING
    assert (output / "native_raw.json").exists() and (output / "build_identity.json").exists()
    assert load_json(output / "execution_failure.json")["numerical_verdict"] == "UNKNOWN"


@pytest.mark.parametrize("value,passes", [(math.nextafter(1e-14, 0.), True), (-math.nextafter(1e-14, 0.), True),
    (1e-14, False), (-1e-14, False), (math.nextafter(1e-14, math.inf), False)])
def test_mtest_actual_imposed_gradient_residual_is_strict_and_keeps_prescribed_reference(raw_template, value, passes):
    raw = deepcopy(raw_template)
    original_reference = ref.analytical_reference(ref.canonical_settings())
    row = raw["mtest"]["states"][3]  # Exact imposed zero on unloading avoids addition rounding.
    row["gradients_kelvin"][3] = value
    row["strain_physical"] = ref.from_kelvin(row["gradients_kelvin"])
    before = ref.state_hash(raw)
    verdict = ref.assess(ref.canonical_settings(), raw)
    mapping = next(c for c in verdict["checks"] if c["code"] == "native_tensor_mapping")
    assert (mapping["status"] == "PASS") is passes
    assert verdict["reference"] == original_reference and ref.state_hash(raw) == before
    assert raw["mtest"]["imposed_history"][3]["gradients_kelvin"] == [0.] * 6
    assert raw["mtest"]["states"][3]["gradients_kelvin"][3] == value
    assert all(m["valid"] is passes for m in verdict["metrics"].values())


@pytest.mark.parametrize("kind", ["missing_history", "changed_history", "boolean_time", "boolean_gradient",
    "wrong_components", "wrong_interpolation", "missing_epsilon", "loose_epsilon", "fake_stress_epsilon",
    "wrong_iterations", "fake_substeps"])
def test_mtest_exact_imposed_metadata_and_existing_driver_limits_are_mandatory(raw_template, kind):
    raw = deepcopy(raw_template)
    mtest = raw["mtest"]
    if kind == "missing_history":
        mtest.pop("imposed_history")
    elif kind == "changed_history":
        mtest["imposed_history"][1]["gradients_kelvin"][0] += 1e-16
    elif kind == "boolean_time":
        mtest["imposed_history"][0]["time_s"] = False
    elif kind == "boolean_gradient":
        mtest["imposed_history"][0]["gradients_kelvin"][0] = False
    elif kind == "wrong_components":
        mtest["imposed_components"][-2:] = reversed(mtest["imposed_components"][-2:])
    elif kind == "wrong_interpolation":
        mtest["imposed_interpolation"] = "constant"
    elif kind == "missing_epsilon":
        mtest.pop("strain_epsilon")
    elif kind == "loose_epsilon":
        mtest["strain_epsilon"] = 1e-13
    elif kind == "fake_stress_epsilon":
        mtest["stress_epsilon_mpa"] = 1e-9
    elif kind == "wrong_iterations":
        mtest["iteration_limit"] = 11
    else:
        mtest["substep_limit"] = True
    with pytest.raises(ValueError):
        ref.assess(ref.canonical_settings(), raw)


def test_mtest_real_returned_buffer_mapping_is_required_even_below_residual_limit(raw_template):
    raw = deepcopy(raw_template)
    row = raw["mtest"]["states"][3]
    row["gradients_kelvin"][3] = math.nextafter(1e-14, 0.)
    # Wrongly projected physical strain still cannot masquerade as its native buffer.
    verdict = ref.assess(ref.canonical_settings(), raw)
    assert next(c for c in verdict["checks"] if c["code"] == "native_tensor_mapping")["status"] == "FAIL"


def test_mtest_initial_unprepared_strain_remains_exact_zero(raw_template):
    raw = deepcopy(raw_template)
    raw["mtest"]["states"][0]["gradients_kelvin"][0] = math.nextafter(0., 1.)
    raw["mtest"]["states"][0]["strain_physical"] = ref.from_kelvin(raw["mtest"]["states"][0]["gradients_kelvin"])
    verdict = ref.assess(ref.canonical_settings(), raw)
    assert next(c for c in verdict["checks"] if c["code"] == "exact_ordered_history")["status"] == "FAIL"


def test_numerical_reference_rejection_preserves_actual_reliable_execution(tmp_path, monkeypatch, raw_template):
    def disagreement(output, raw):
        row = raw["mtest"]["states"][1]
        row["stress_kelvin_mpa"][0] += .1
        row["stress_physical_mpa"] = ref.from_kelvin(row["stress_kelvin_mpa"])
        path = output / "mtest.res"
        path.write_text(table_text(raw["mtest"]["states"]))
        raw["mtest"]["native_output_table"] = worker.parse_mtest_table(path, raw["mtest"]["states"])
    install_testonly_executor(monkeypatch, tmp_path, raw_template, disagreement)
    outcome = adapter_module.MFrontViscoelasticAdapter().solve(tmp_path / "disagreement", ref.canonical_settings())
    assert outcome["status"] == "REJECTED" and outcome["solver_status"] == "COMPLETED"
    assert outcome["converged"] is True
    assert all(check["status"] == "PASS" for check in outcome["checks"][:6])
    assert next(c for c in outcome["checks"] if c["code"] == "max_stress_kelvin_error")["status"] == "FAIL"
    assert all(m["valid"] is False for m in outcome["metrics"].values())


@pytest.mark.parametrize("phase", ["nominal", "finite_difference"])
@pytest.mark.parametrize("code", [0, -1])
def test_actual_typed_partial_unreliable_return_retains_false_and_its_phase(tmp_path, monkeypatch, raw_template, phase, code):
    def unreliable(output, raw):
        class ActualPartial(FakeTransport):
            def _integrate(self, binding, manager, dt):
                self.return_code = code if self.calls == (0 if phase == "nominal" else 1) else 1
                return super()._integrate(binding, manager, dt)
        behaviour = SimpleNamespace(computesStoredEnergy=True, computesDissipatedEnergy=True)
        raw["mgis"] = worker.integrate_history(FakeBinding, behaviour, ref.canonical_settings(), raw["library_sha256"],
                                              output, np, ActualPartial())
        raw["native_rejection"] = deepcopy(raw["mgis"]["native_rejection"])
        raw.pop("mtest")
    install_testonly_executor(monkeypatch, tmp_path, raw_template, unreliable)
    outcome = adapter_module.MFrontViscoelasticAdapter().solve(tmp_path / "unreliable", ref.canonical_settings())
    assert outcome["status"] == "REJECTED" and outcome["solver_status"] == "COMPLETED", outcome
    assert outcome["converged"] is False
    assert outcome["checks"][0]["observed"]["phase"] == phase
    assert outcome["metrics"]["native_integration_return"]["value"] == code
    assert outcome["metrics"]["native_integration_return"]["valid"] is False


@pytest.mark.parametrize("kind", ["unbound_partial", "boolean_code", "wrong_phase"])
def test_unknown_unbound_or_malformed_unreliable_claim_is_not_a_diagnosed_solver_failure(tmp_path, monkeypatch, raw_template, kind):
    def corrupt(output, raw):
        raw["native_rejection"] = {"integration_return": False if kind == "boolean_code" else 0,
                                   "phase": "invented" if kind == "wrong_phase" else "nominal", "step": 1}
    install_testonly_executor(monkeypatch, tmp_path, raw_template, corrupt)
    outcome = adapter_module.MFrontViscoelasticAdapter().solve(tmp_path / "unbound", ref.canonical_settings())
    assert outcome["solver_status"] == "FAILED_EXECUTION" and outcome["converged"] is None


def test_mtest_producer_retains_actual_imposed_api_values_and_actual_returned_strain(tmp_path):
    settings = ref.canonical_settings()
    settings["history"] = [settings["history"][0], settings["history"][1]]
    library = tmp_path / "TEST_ONLY_library.so"
    library.write_bytes(b"TEST ONLY no native library")
    created = []
    class State:
        def __init__(self):
            self.e1 = [0.] * 6
            self.s1, self.iv1 = [0.] * 6, [0.] * 6
            self.mprops1, self.evs0 = [0.] * 5, [0.]
            self.iterations = self.subSteps = 0
    class Driver:
        def __init__(self):
            self.imposed, self.calls, self.properties = {}, {}, {}
            created.append(self)
        def __getattr__(self, name):
            if name in ("setModellingHypothesis", "setBehaviour", "setMaximumNumberOfSubSteps", "setMaximumNumberOfIterations",
                        "setStrainEpsilon", "setStressEpsilon", "setExternalStateVariable", "setStrain", "setStress", "setOutputFileName",
                        "setOutputFilePrecision"):
                return lambda *args: self.calls.__setitem__(name, args)
            if name in ("completeInitialisation", "initializeCurrentState", "initializeWorkSpace", "printOutput"):
                return lambda *args: None
            raise AttributeError(name)
        def setMaterialProperty(self, name, value):
            self.properties[name] = value
        def setImposedStrain(self, name, history):
            self.imposed[name] = deepcopy(history)
        def execute(self, state, workspace, previous, time):
            state.e1 = [self.imposed[name][time] for name in worker.MTEST_COMPONENTS]
            state.e1[0] += 9e-15
            state.mprops1 = list(self.properties.values())
            state.evs0, state.iterations = [settings["temperature_k"]], 1
    module = SimpleNamespace(MTest=Driver, MTestCurrentState=State, MTestWorkSpace=object)
    observed = worker.mtest_history(module, library, settings, tmp_path)
    driver = created[0]
    assert observed["imposed_history"] == [{"time_s": r["time_s"], "gradients_kelvin": ref.to_kelvin(r["strain"])}
                                            for r in settings["history"]]
    for column, name in enumerate(worker.MTEST_COMPONENTS):
        assert driver.imposed[name] == {r["time_s"]: r["gradients_kelvin"][column] for r in observed["imposed_history"]}
    assert driver.calls["setStrainEpsilon"] == (1e-14,) and driver.calls["setStressEpsilon"] == (1e-10,)
    assert driver.calls["setMaximumNumberOfSubSteps"] == (1,) and driver.calls["setMaximumNumberOfIterations"] == (10,)
    assert observed["states"][0]["gradients_kelvin"] == [0.] * 6
    actual = observed["states"][1]["gradients_kelvin"]
    assert actual != observed["imposed_history"][1]["gradients_kelvin"]
    assert observed["states"][1]["strain_physical"] == ref.from_kelvin(actual)
    assert "stored_energy_mpa" not in observed["states"][1]  # Mandatory real table supplies energy separately.
    assert load_json(tmp_path / "mtest.partial.json") == observed


def test_exact_native_law_source_matches_lf_checkout():
    """The real law must match its fixed build identity in a fresh LF checkout."""
    import hashlib
    from pathlib import Path
    from caelab.adapters import mfront_viscoelastic_worker as actual_worker
    law = Path(actual_worker.__file__).with_name(actual_worker.SOURCE_NAME).read_bytes()
    assert b"\r\n" not in law
    assert len(law) == 7417
    assert hashlib.sha256(law).hexdigest() == actual_worker.SOURCE_SHA256 == (
        "8501f6d338d0d58fd9391031274dd0d15ecaf333f6158f0c80a73ffdb99e3d7a")
