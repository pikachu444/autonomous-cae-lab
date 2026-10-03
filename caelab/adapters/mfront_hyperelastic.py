"""Bounded SVK declared material point over the existing owned native transport."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shlex

from plugins.hyperelastic import reference as domain
from .. import execution_control
from ..storage import save_json
from . import codeaster_elasticity as execution
from . import codeaster_execution as policy
from . import mfront_material as material
from . import mfront_material_worker as transport
from . import mfront_hyperelastic_worker as worker


_SOURCES = {"domain_reference.py": Path(domain.__file__).resolve(),
    "domain_init.py": Path(domain.__file__).with_name("__init__.py"),
    "mfront_hyperelastic.py": Path(__file__).resolve(), "mfront_hyperelastic_worker.py": Path(worker.__file__).resolve(),
    "mfront_material.py": Path(material.__file__).resolve(), "mfront_material_worker.py": Path(transport.__file__).resolve(),
    "codeaster_elasticity.py": Path(execution.__file__).resolve(), "codeaster_execution.py": Path(policy.__file__).resolve(),
    "execution_control.py": Path(execution_control.__file__).resolve()}
_SOURCE_BYTES = {name: source.read_bytes() for name, source in _SOURCES.items()}
_SOURCE_SHA = {name: hashlib.sha256(data).hexdigest() for name, data in _SOURCE_BYTES.items()}
_SCRIPT = "source /opt/activate.sh; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1; exec python3 -I -B /work/mfront_hyperelastic_worker.py"
_LIMITATIONS = ["Bounded unmodified SVK reference: large proper rotations with small Green strain, not general rubber or large-stretch stability.",
    "Measured PK1/F use nine physical tensor components; stored energy is native per reference volume, MPa.",
    "MGIS and MTest drive the same generated law/library; driver agreement is not cross-solver material physics.",
    "Initial t0 buffers are unprepared; only actual t1 and later reliable endpoints supply numerical observations.",
    "Native dissipation, MTest energy, compiled upstream source equivalence and corporate approval remain UNKNOWN.",
    "No FE constitutive coupling, physical/material/strength/durability qualification, Research promotion or release."]


def _assert_sources(output):
    for name, source in _SOURCES.items():
        captured = output / name
        if (not source.is_file() or worker.sha256(source) != _SOURCE_SHA[name] or captured.is_symlink() or
                not captured.is_file() or worker.sha256(captured) != _SOURCE_SHA[name]):
            raise RuntimeError("Captured material/Domain/owned execution source drifted; retained evidence is unchanged")


def _json(output, relative):
    path = output / relative
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= worker.MAX_FILE_BYTES:
        raise ValueError(f"Missing, linked or unbounded native artifact: {relative}")
    value = json.loads(path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite native JSON: " + value)))
    json.dumps(value, allow_nan=False)
    return value


def _hash(output, relative):
    path = output / relative
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= worker.MAX_FILE_BYTES:
        raise ValueError(f"Missing, linked or unbounded native artifact: {relative}")
    return worker.sha256(path)


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def checked_native(output, input_sha, settings, budgets):
    """Bind actual retained build/package/descriptor bytes before Domain assessment."""
    try:
        raw = _json(output, "native_raw.json")
        captured = _json(output, "input.json")
        if (raw.get("schema_version") != "1" or raw.get("input_sha256") != input_sha or _hash(output, "input.json") != input_sha or
                raw.get("source_sha256") != worker.SOURCE_SHA256 or raw.get("worker_sha256") != _SOURCE_SHA["mfront_hyperelastic_worker.py"] or
                raw.get("captured_source_sha256") != _SOURCE_SHA or captured != {"settings": settings,
                    "captured_source_sha256": _SOURCE_SHA, "process_policy": budgets} or raw.get("process_policy") != budgets or
                _hash(output, f"build/{worker.BEHAVIOUR}.mfront") != worker.SOURCE_SHA256 or
                raw.get("library_sha256") != _hash(output, "build/src/libBehaviour.so")):
            raise ValueError("Native input/source/worker/library/process identity differs from captured producer")
        build = _json(output, "build_identity.json")
        if (build.get("library_path") != "build/src/libBehaviour.so" or build.get("library_sha256") != raw["library_sha256"] or
                build.get("source_sha256") != worker.SOURCE_SHA256 or build.get("generation_arguments") != worker.BUILD_ARGUMENTS or
                build.get("makefile_sha256") != _hash(output, "build/src/Makefile.mfront") or
                build.get("compiler_flags_policy") != worker.COMPILER_POLICY or not build.get("compiler_flags_makefile") or
                build.get("compiler_commands_artifact") != "build/compile.stdout.log" or
                not isinstance(build.get("dependency_sha256"), dict) or not build["dependency_sha256"] or
                any(not name.startswith("/") or not _digest(digest) for name, digest in build["dependency_sha256"].items())):
            raise ValueError("Actual generated compiler/library/dependency evidence is incomplete")
        runtime = raw.get("runtime")
        if (not isinstance(runtime, dict) or runtime != _json(output, "runtime.json") or runtime.get("mgis") != "3.0" or
                not str(runtime.get("tfel", "")).startswith("tfel-config 5.0.0") or
                any(not isinstance(runtime.get(name), str) or not runtime[name] for name in
                    ("python", "numpy", "mfront", "compiler", "make", "mgis_binding_sha256", "mtest_binding_sha256"))):
            raise ValueError("Native runtime identity is absent or inconsistent")
        flags = transport.portable_compiler_flags(runtime["tfel_recommended_oflags0"], runtime["tfel_cpp_compiler_flags"], runtime["tfel_include_path"])
        if build.get("compiler_flags_override") != flags:
            raise ValueError("Actual build did not bind the existing portable compiler flags")
        makefile = (output / "build/src/Makefile.mfront").read_text(encoding="utf-8")
        observed_flags = [line for line in makefile.splitlines() if any(token in line for token in
            ("CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CXX ", "CXX=", "INCLUDES", "-std="))]
        if observed_flags != build["compiler_flags_makefile"]:
            raise ValueError("Makefile flag observation differs from retained actual Makefile")
        _hash(output, "build/compile.stdout.log")
        compiler = runtime["executables"]["g++"]["path"]
        expanded = [line for line in (output / "build/compile.stdout.log").read_text().splitlines()
            if compiler in line and any(token in line for token in (" -c", " -shared", " -M "))]
        if not expanded or build.get("actual_compiler_commands") != expanded:
            raise ValueError("Actual expanded compiler commands are absent or differ from original log")
        for line in expanded:
            tokens = shlex.split(line)
            if (any(token.startswith(("-march", "-mtune")) or token in ("-ffast-math", "-ftree-vectorize") for token in tokens) or
                    not {"-O2", "-fno-fast-math", "-std=c++20"}.issubset(tokens)):
                raise ValueError("Actual compiler command violates portable O2/no-fast-math policy")
        for name, prefix, version, binding_name in (("mgis", worker.MGIS_PREFIX, "3.0", "mgis"),
            ("tfel", worker.TFEL_PREFIX, "5.0.0", "mtest")):
            package = runtime[name + "_package"]
            spec = _json(output, name + "_installed_spec.json")
            nodes = [node for node in spec["spec"]["nodes"] if node.get("name") == name]
            if (len(nodes) != 1 or nodes[0].get("version") != version or nodes[0].get("hash") != package.get("spack_hash") or
                    package.get("name") != name or package.get("version") != version or package.get("package_prefix") != prefix or
                    package.get("spec_sha256") != _hash(output, name + "_installed_spec.json") or
                    not str(package.get("binding_path", "")).startswith(prefix + "/") or
                    package.get("binding_path") != runtime.get(binding_name + "_binding_path") or
                    not _digest(package.get("binding_sha256")) or package["binding_sha256"] != runtime.get(binding_name + "_binding_sha256") or
                    package.get("upstream_binary_source_commit") != "UNKNOWN"):
                raise ValueError("Fixed-prefix actual package/spec/loaded binding identity differs")
        desc = raw.get("behaviour_description")
        if not isinstance(desc, dict) or desc != _json(output, "behaviour_description.json"):
            raise ValueError("Native descriptor differs from retained descriptor artifact")
        expected = {"behaviour": worker.BEHAVIOUR, "hypothesis": "Tridimensional", "behavior_type": "STANDARD_FINITE_STRAIN",
            "kinematic": "F_CAUCHY", "gradients": ["DeformationGradient"], "gradient_sizes": [9],
            "thermodynamic_forces": ["FirstPiolaKirchhoffStress"], "force_sizes": [9],
            "tangent_operator_blocks": [{"force": "FirstPiolaKirchhoffStress", "gradient": "DeformationGradient", "shape": [9, 9]}],
            "material_properties": ["YoungModulus", "PoissonRatio"], "external_state_variables": ["Temperature"],
            "internal_state_variables": [], "computes_stored_energy": True, "computes_dissipated_energy": False,
            "stress_measure": "PK1", "tangent_operator": "DPK1_DF", "component_order": list(worker.F_COMPONENTS),
            "stored_energy_measure": "per_reference_volume", "binary_upstream_source_commit": "UNKNOWN"}
        if (any(desc.get(key) != value for key, value in expected.items()) or not str(desc.get("tfel_version", "")).startswith("5.0.0") or
                raw.get("finite_strain_options") != {"stress_measure": "PK1", "tangent_operator": "DPK1_DF"}):
            raise ValueError("Native finite-strain measures/layout/energy descriptor differ from SVK contract")
        attribution = _json(output, "source_attribution.json")
        if attribution.get("source_sha256") != worker.SOURCE_SHA256 or attribution.get("reference_commit") != worker.TFEL_COMMIT:
            raise ValueError("Pinned native source attribution missing")
        licenses = attribution.get("licenses", [])
        if {row["name"] for row in licenses} != {"LICENCE-GNU-GPL", "LICENCE-CECILL-A-EN", "LICENCE-CECILL-A-FR"} or len(licenses) != 3:
            raise ValueError("Native source license inventory is incomplete")
        for row in licenses:
            if row.get("sha256") != _hash(output, "licenses/" + row["name"]):
                raise ValueError("Native retained license identity drifted")
        if "native_rejection" not in raw and raw.get("mtest", {}).get("library_sha256") != raw["library_sha256"]:
            raise ValueError("MGIS and MTest are not bound to the same generated library")
        return raw, build
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise RuntimeError(f"Malformed native hyperelastic evidence: {error}") from error


def _native_rejection(raw, settings):
    refused = raw["native_rejection"]
    code, index = refused.get("integration_return"), refused.get("history_index")
    if type(code) is not int or code not in (-1, 0) or type(index) is not int or not 1 <= index < len(settings["history"]):
        raise RuntimeError("Malformed actual native reliability rejection")
    steps = raw.get("steps", [])
    if len(steps) != index:
        raise RuntimeError("Native rejection is not bound to retained partial history")
    step = steps[-1]
    if refused.get("driver") != "MGIS":
        raise RuntimeError("Unsupported native rejection driver")
    if refused.get("phase") == "nominal":
        actual = step
    elif refused.get("phase") == "finite_difference":
        matches = [p for fd in step.get("finite_differences", []) if fd.get("h") == refused.get("h") for p in fd["probes"]
            if p["column"] == refused.get("column") and p["sign"] == refused.get("sign")]
        if len(matches) != 1:
            raise RuntimeError("Native rejection is not bound to unique actual signed probe")
        actual = matches[0]
    else:
        raise RuntimeError("Unsupported native rejection phase")
    if actual.get("integration_return") != code:
        raise RuntimeError("Native reliability return differs from retained actual observation")
    return refused


class MFrontHyperelasticAdapter:
    backend = "material.mfront.hyperelastic"
    version = "1"
    domain = "hyperelastic"
    physics_domain = "constitutive_material"
    analysis_type = "finite_strain_material_point"
    default_metrics = ["pk1_stress_error", "cauchy_stress_error", "mtest_stress_error", "analytical_tangent_relative_error",
        "tangent_major_symmetry_relative_error", "native_energy_density_error", "probe_pk1_stress_error", "probe_native_energy_density_error",
        "cross_driver_stress_error", *[prefix + str(h) for h in (1e-7, 1e-8, 1e-9) for prefix in
            ("fd_tangent_vs_native_", "fd_tangent_vs_reference_", "fd_energy_gradient_vs_native_", "fd_energy_gradient_vs_reference_")]]

    def describe_model(self, settings):
        return domain.model_declaration(settings)

    def solve(self, output, settings):
        try:
            settings = domain.validate_settings(settings)
        except ValueError as error:
            return {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                "checks": [{"code": "hyperelastic_preflight", "status": "FAIL", "observed": str(error)}],
                "metrics": {}, "pending_validations": list(domain.PENDING), "raw_result": None,
                "provenance": {"adapter": self.backend, "adapter_version": self.version,
                    "source_snapshot_sha256": dict(_SOURCE_SHA), "source_capture_status": "NOT_RUN",
                    "domain_plugin": {"module": domain.__name__, "version": domain.__version__,
                        "source_sha256": _SOURCE_SHA["domain_reference.py"], "source_artifact": None},
                    "behaviour_source_sha256": worker.SOURCE_SHA256, "behaviour_source_url": worker.SOURCE_URL,
                    "compiled_source_equivalence": "UNKNOWN", "assumptions": list(_LIMITATIONS)},
                "limitations": list(_LIMITATIONS)}
        output = Path(output)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Material output must be new/empty; preserved evidence cannot be overwritten")
        output.mkdir(parents=True, exist_ok=True)
        for name, data in _SOURCE_BYTES.items():
            (output / name).write_bytes(data)
        provenance = {"adapter": self.backend, "adapter_version": self.version, "captured_source_sha256": dict(_SOURCE_SHA),
            "domain_plugin": {"module": domain.__name__, "version": domain.__version__, "source_sha256": _SOURCE_SHA["domain_reference.py"],
                "source_artifact": "simulation/domain_reference.py"}, "behaviour_source_sha256": worker.SOURCE_SHA256,
            "behaviour_source_url": worker.SOURCE_URL, "oci_manifest_sha256": material.OCI_MANIFEST_SHA256,
            "compiled_source_equivalence": "UNKNOWN", "assumptions": list(_LIMITATIONS)}
        try:
            _assert_sources(output)
            return self._execute(output, settings, provenance)
        except BaseException as error:
            cleanup = isinstance(error, execution_control.ExecutionCleanupFailed)
            cancelled = isinstance(error, execution_control.ExecutionCancelled)
            try:
                save_json(output / "execution_failure.json", {"status": "CLEANUP_PENDING" if cleanup else "CANCELLED" if cancelled else "FAILED_EXECUTION",
                    "type": type(error).__name__, "message": str(error), "numerical_verdict": "UNKNOWN", "decision": "NOT_RELEASED",
                    "provenance": provenance, "partial_evidence": "All captured source/build/individual probes/native histories/logs/scratch retained"})
            except OSError:
                # Preserve the ownership/cancellation exception even if failure
                # receipt publication fails. The common token still holds PID.
                pass
            raise

    def _execute(self, output, settings, provenance):
        budgets = policy.process_budgets()
        save_json(output / "input.json", {"settings": settings, "captured_source_sha256": dict(_SOURCE_SHA), "process_policy": budgets})
        save_json(output / "model_declaration.json", self.describe_model(settings))
        save_json(output / "analytical_reference.json", domain.analytical_reference(settings))
        save_json(output / "frozen_execution_policy.json", {"process_policy": budgets, "memory_bytes": 4 * 1024 ** 3,
            "maximum_file_bytes": worker.MAX_FILE_BYTES, "build_arguments": list(worker.BUILD_ARGUMENTS), "compiler_flags_policy": worker.COMPILER_POLICY,
            "stress_measure": "PK1", "tangent_operator": "DPK1_DF", "component_order": list(worker.F_COMPONENTS), "workers": 1,
            "finite_difference_steps": list(settings["limits"]["finite_difference_steps"]), "limits": deepcopy(settings["limits"]),
            "mtest_failure_substep_limit": 1, "initial_phase": "INITIAL_UNPREPARED", "first_native_identity": "t1_with_positive_dt"})
        _assert_sources(output)
        image, image_sha, runtime = material._runtime_identity()
        provenance.update(image_path=str(image), image_sha256=image_sha, input_sha256=worker.sha256(output / "input.json"), process_policy=budgets)
        provenance["versions"] = {"singularity": execution._process([runtime, "--version"], output, "container_version", timeout=10)}
        if not provenance["versions"]["singularity"]:
            raise RuntimeError("Missing actual container runtime version")
        scratch = output / "scratch"
        scratch.mkdir(exist_ok=False)
        command = [runtime, "exec", "--cleanenv", "--containall", "--no-home", "--bind", str(output.resolve()) + ":/work:rw",
            "--bind", str(scratch.resolve()) + ":/tmp:rw", "--pwd", "/work", str(image), "/bin/bash", "--noprofile", "--norc", "-c", _SCRIPT]
        _assert_sources(output)
        if worker.sha256(image) != image_sha:
            raise RuntimeError("Pinned material image drifted before native execution")
        execution._process(command, output, "hyperelastic_worker", timeout=budgets["subprocess_timeout_seconds"])
        _assert_sources(output)
        if worker.sha256(image) != image_sha:
            raise RuntimeError("Pinned material image drifted during native execution")
        raw, build = checked_native(output, provenance["input_sha256"], settings, budgets)
        provenance.update(versions={**provenance["versions"], **raw["runtime"]}, build=build,
            behaviour_description=raw["behaviour_description"], finite_strain_options=raw["finite_strain_options"],
            container_isolation={"cleanenv": True, "containall": True, "no_home": True, "threads": 1, "scratch": "Retained output-owned /tmp"},
            native_library_artifact="simulation/build/src/libBehaviour.so")
        if "native_rejection" in raw:
            refused = _native_rejection(raw, settings)
            result = {"status": "REJECTED", "solver_status": "COMPLETED", "converged": False,
                "checks": [{"code": "reliable_integrations", "status": "FAIL", "observed": deepcopy(refused), "expected": "Every actual integration returns exactly1"}],
                "metrics": {"native_integration_return": {"value": refused["integration_return"], "unit": "1", "valid": False,
                    "reason": "Actual failed/unreliable nominal or probe prevented history advance"}}, "pending_validations": list(domain.PENDING)}
        else:
            assessment = domain.assess(settings, raw)
            result = {"status": "COMPLETED" if assessment["passed"] else "REJECTED", "solver_status": "COMPLETED",
                "converged": assessment["passed"], "checks": assessment["checks"], "metrics": assessment["metrics"],
                "pending_validations": [item["code"] for item in assessment["pending"]], "assessment": assessment}
        _assert_sources(output)
        if worker.sha256(image) != image_sha:
            raise RuntimeError("Pinned image drifted before material result publication")
        result.update(provenance=provenance, raw_result="simulation/analysis_raw.json", native_raw="simulation/native_raw.json", limitations=list(_LIMITATIONS))
        save_json(output / "analysis_raw.json", result)
        return result
