"""Bounded material.mfront adapter over common CAD-independent execution."""

from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess

from plugins.material_point import reference as domain
from ..storage import save_json
from .mfront_material_worker import SOURCE_SHA256, SOURCE_URL, BUILD_ARGUMENTS, MGIS_PREFIX, TFEL_PREFIX, COMPILER_POLICY

WORKER = Path(__file__).with_name("mfront_material_worker.py")
_DOMAIN_PATH = Path(domain.__file__).resolve()
_DOMAIN_BYTES = _DOMAIN_PATH.read_bytes()
_DOMAIN_SHA = hashlib.sha256(_DOMAIN_BYTES).hexdigest()
_WORKER_BYTES = WORKER.read_bytes()
_WORKER_SHA = hashlib.sha256(_WORKER_BYTES).hexdigest()
OCI_MANIFEST_SHA256 = "d8d19ea91989eac0d38195bc5795c54c69f530f7196f53d67697ffa57c9106d5"
PROCESS_TIMEOUT_SECONDS = 240
CONTAINER_SCRIPT = "source /opt/activate.sh; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1; exec python3 -I /work/mfront_material_worker.py"
LIMITATIONS = ["Isotropic infinitesimal-strain constitutive point; no mesh or CAD parent.",
               "MGIS and MTest drive the same generated behavior, not independent constitutive laws.",
               "Only reliable nominal states advance; FD probes use independent native buffers.",
               "Elastic energy is postprocessed from measured stress, not native stored-energy output.",
               "No plasticity, finite strain, temperature dependence, solver coupling or physical/material qualification.",
               "Vendor TFEL/MGIS upstream binary commits and corporate license/security approval remain UNKNOWN."]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_sources(output):
    for source, captured, digest in ((_DOMAIN_PATH, output / "domain_reference.py", _DOMAIN_SHA),
                                    (WORKER, output / "mfront_material_worker.py", _WORKER_SHA)):
        if not source.is_file() or sha256(source) != digest or sha256(captured) != digest:
            raise RuntimeError("Material source changed during execution; original captured evidence is preserved")


def _text(value):
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def _process(command, output, label, *, timeout=PROCESS_TIMEOUT_SECONDS):
    save_json(output / (label + ".command.json"), {"argv": command, "timeout_seconds": timeout,
                                               "cwd": str(output.resolve())})
    try:
        result = subprocess.run(command, cwd=output.resolve(), capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        (output / (label + ".stdout.log")).write_text(_text(getattr(exc, "stdout", "")), encoding="utf-8")
        (output / (label + ".stderr.log")).write_text(_text(getattr(exc, "stderr", "")) +
            f"\n{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise RuntimeError(f"{label} failed to complete; partial evidence retained") from exc
    (output / (label + ".stdout.log")).write_text(_text(result.stdout), encoding="utf-8")
    (output / (label + ".stderr.log")).write_text(_text(result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"{label} exited {result.returncode}; native logs retained: " + _text(result.stderr)[-1500:])
    return (_text(result.stdout) + "\n" + _text(result.stderr)).strip()


def _runtime_identity():
    image_value = os.environ.get("CAELAB_MFRONT_IMAGE", os.environ.get("CAELAB_CODEASTER_IMAGE", ""))
    expected = os.environ.get("CAELAB_MFRONT_IMAGE_SHA256", os.environ.get("CAELAB_CODEASTER_IMAGE_SHA256", ""))
    if not image_value or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError("Configure CAELAB_MFRONT_IMAGE and its exact CAELAB_MFRONT_IMAGE_SHA256")
    image = Path(image_value).resolve()
    if not image.is_file() or sha256(image) != expected:
        raise RuntimeError("MFront vendor image is missing or its SIF hash drifted")
    runtime = shutil.which(os.environ.get("CAELAB_SINGULARITY_COMMAND", "singularity"))
    if not runtime:
        raise RuntimeError("Singularity runtime is unavailable")
    return image, expected, runtime


def checked_native(output, input_sha):
    path = output / "native_raw.json"
    if not path.is_file() or path.stat().st_size > 32 * 1024 ** 2:
        raise RuntimeError("Missing or unbounded native material observations")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"),
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON " + value)))
        if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or
                raw.get("input_sha256") != input_sha or raw.get("source_sha256") != SOURCE_SHA256 or
                raw.get("worker_sha256") != _WORKER_SHA or sha256(output / "input.json") != input_sha or
                sha256(output / "build/Elasticity.mfront") != SOURCE_SHA256 or
                raw.get("library_sha256") != sha256(output / "build/src/libBehaviour.so")):
            raise ValueError("Input/worker/behavior source/binary identities are missing or drifted")
        build = json.loads((output / "build_identity.json").read_text())
        if (build.get("library_sha256") != raw["library_sha256"] or build.get("source_sha256") != SOURCE_SHA256 or
                build.get("generation_arguments") != BUILD_ARGUMENTS or
                build.get("makefile_sha256") != sha256(output / "build/src/Makefile.mfront") or
                not isinstance(build.get("compiler_flags_makefile"), list) or not build["compiler_flags_makefile"] or
                not isinstance(build.get("actual_compiler_commands"), list) or not build["actual_compiler_commands"] or
                build.get("compiler_flags_policy") != COMPILER_POLICY or
                not isinstance(build.get("compiler_flags_override"), list) or "-O2" not in build["compiler_flags_override"] or
                any(str(flag).startswith(("-march", "-mtune")) or flag in ("-ffast-math", "-ftree-vectorize")
                    for flag in build["compiler_flags_override"]) or
                not isinstance(build.get("dependency_sha256"), dict) or not build["dependency_sha256"]):
            raise ValueError("Actual compiler/build/dependency identity is incomplete")
        runtime = raw.get("runtime")
        if (not isinstance(runtime, dict) or runtime.get("mgis") != "3.0" or
                not str(runtime.get("tfel", "")).startswith("tfel-config 5.0.0") or
                any(not isinstance(runtime.get(name), str) or not runtime[name]
                    for name in ("python", "numpy", "compiler", "mfront", "make", "mgis_binding_sha256", "mtest_binding_sha256")) or
                json.loads((output / "runtime.json").read_text()) != runtime):
            raise ValueError("Native TFEL/MGIS/Python/compiler identity is incomplete")
        for name, prefix, version in (("mgis", MGIS_PREFIX, "3.0"), ("tfel", TFEL_PREFIX, "5.0.0")):
            package = runtime.get(name + "_package")
            if (not isinstance(package, dict) or package.get("name") != name or package.get("version") != version or
                    package.get("package_prefix") != prefix or
                    not isinstance(package.get("binding_path"), str) or
                    not package["binding_path"].startswith(prefix + "/") or
                    package.get("spec_sha256") != sha256(output / (name + "_installed_spec.json")) or
                    package.get("binding_sha256") != runtime.get("mgis_binding_sha256" if name == "mgis" else "mtest_binding_sha256")):
                raise ValueError("Loaded native binding/package identity is missing or inconsistent")
        descriptor = raw.get("behaviour_description")
        if (not isinstance(descriptor, dict) or descriptor.get("material_properties") != ["YoungModulus", "PoissonRatio"] or
                descriptor.get("external_state_variables") != ["Temperature"] or
                descriptor.get("behaviour") != "Elasticity" or descriptor.get("hypothesis") != "TRIDIMENSIONAL"):
            raise ValueError("Native behavior does not match Elasticity/generic/Tridimensional")
        return raw, build
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RuntimeError(f"Malformed native material observations: {exc}") from exc


class MFrontMaterialAdapter:
    backend = "material.mfront"
    version = "1"
    domain = "material_point"
    physics_domain = "constitutive_material"
    analysis_type = "small_strain_material_point"
    default_metrics = ["max_physical_stress_error", "max_kelvin_stress_error", "analytical_tangent_relative_error",
                       "cross_driver_stress_error", "max_energy_density_error", "stress_history", "energy_density_history",
                       "fd_tangent_relative_error_1e-07", "fd_tangent_relative_error_1e-08", "fd_tangent_relative_error_1e-09"]

    def describe_model(self, settings):
        return domain.model_declaration(settings)

    def solve(self, output, settings):
        output = Path(output)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Material output must be fresh/empty; old evidence cannot be overwritten")
        output.mkdir(parents=True, exist_ok=True)
        (output / "domain_reference.py").write_bytes(_DOMAIN_BYTES)
        (output / "mfront_material_worker.py").write_bytes(_WORKER_BYTES)
        provenance = {"adapter": self.backend, "adapter_version": self.version, "worker_sha256": _WORKER_SHA,
            "domain_plugin": {"module": "plugins.material_point.reference", "version": domain.__version__,
                              "source_sha256": _DOMAIN_SHA, "source_artifact": "simulation/domain_reference.py"},
            "behaviour_source_sha256": SOURCE_SHA256, "behaviour_source_url": SOURCE_URL,
            "oci_manifest_sha256": OCI_MANIFEST_SHA256, "assumptions": list(LIMITATIONS)}
        def execution_failure(exc):
            message = f"{type(exc).__name__}: {exc}"
            (output / "execution_failure.log").write_text(message + "\n", encoding="utf-8")
            outcome = {"status": "REJECTED", "solver_status": "FAILED_EXECUTION", "converged": None,
                "checks": [{"code": "material_execution", "status": "FAIL", "observed": message}],
                "metrics": {}, "pending_validations": list(domain.PENDING), "provenance": provenance,
                "raw_result": "simulation/analysis_raw.json", "limitations": list(LIMITATIONS)}
            save_json(output / "analysis_raw.json", outcome)
            return outcome
        try:
            _assert_sources(output)
        except Exception as exc:
            return execution_failure(exc)
        try:
            settings = domain.validate_settings(settings)
        except ValueError as exc:
            rejected = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                "checks": [{"code": "material_preflight", "status": "FAIL", "observed": str(exc)}],
                "metrics": {}, "pending_validations": list(domain.PENDING), "provenance": provenance,
                "raw_result": "simulation/analysis_raw.json"}
            save_json(output / "analysis_raw.json", rejected)
            return rejected
        try:
            return self._execute(output, settings, provenance)
        except Exception as exc:
            return execution_failure(exc)

    def _execute(self, output, settings, provenance):
        save_json(output / "input.json", settings)
        save_json(output / "model_declaration.json", self.describe_model(settings))
        save_json(output / "analytical_reference.json", domain.analytical_reference(settings))
        save_json(output / "frozen_execution_policy.json", {"finite_difference_steps": settings["limits"]["finite_difference_steps"],
            "limits": settings["limits"], "maximum_states": 32, "maximum_strain_component": .01,
            "interface": "generic", "hypothesis": "Tridimensional", "behavior": "Elasticity",
            "build_arguments": BUILD_ARGUMENTS, "workers": 1, "worker_address_space_bytes": 4 * 1024 ** 3,
            "make_arguments": ["-C", "src", "-f", "Makefile.mfront", "-j1", "--trace", "CXX=<captured vendor compiler path>"],
            "compiler_flags_policy": COMPILER_POLICY,
            "compiler_flags_reason": "Retained GCC12/TFEL Qt immediate-expression probe reproduces erroneous native tangent under oflags arch flags; documented oflags0 keeps O2/no fast math and avoids that path",
            "worker_cpu_seconds": 180, "maximum_single_artifact_bytes": 128 * 1024 ** 2,
            "subprocess_timeout_seconds": PROCESS_TIMEOUT_SECONDS, "mtest_failure_substep_limit": 1,
            "mtest_substep_policy": "Throw on the first failed step before time-step reduction, per TFEL5 GenericSolver",
            "mtest_strain_epsilon": 1e-14, "mtest_stress_epsilon_mpa": 1e-10})
        image, image_sha, runtime = _runtime_identity()
        provenance.update({"image_path": str(image), "image_sha256": image_sha,
                           "input_sha256": sha256(output / "input.json")})
        provenance["versions"] = {"singularity": _process([runtime, "--version"], output, "runtime_version", timeout=10)}
        scratch = output / "scratch"
        scratch.mkdir(exist_ok=False)
        command = [runtime, "exec", "--cleanenv", "--containall", "--no-home", "--bind",
                   str(output.resolve()) + ":/work:rw", "--bind", str(scratch.resolve()) + ":/tmp:rw",
                   "--pwd", "/work", str(image), "/bin/bash", "--noprofile", "--norc", "-c", CONTAINER_SCRIPT]
        _process(command, output, "material_worker")
        _assert_sources(output)
        if sha256(image) != image_sha:
            raise RuntimeError("MFront SIF changed during execution; partial evidence retained")
        raw, build = checked_native(output, provenance["input_sha256"])
        provenance.update({"versions": {**provenance["versions"], **raw["runtime"]},
            "build": build, "behaviour_description": raw["behaviour_description"],
            "container_isolation": {"cleanenv": True, "containall": True, "no_home": True,
                "tmp": "Fresh output-bound disk scratch retained with every run", "threads": 1},
            "native_library_artifact": "simulation/build/src/libBehaviour.so"})
        if "native_rejection" in raw:
            native_rejection = raw["native_rejection"]
            code = native_rejection.get("integration_return")
            if type(code) is not int or code not in (-1, 0):
                raise RuntimeError("Malformed native integration rejection")
            outcome = {"status": "REJECTED", "solver_status": "COMPLETED", "converged": False,
                "checks": [{"code": "reliable_integrations", "status": "FAIL", "observed": native_rejection,
                            "expected": "Every nominal and FD integration returns exactly 1"}],
                "metrics": {"native_integration_return": {"value": code, "unit": "1", "valid": False,
                    "reason": "Native MGIS integration was failed or unreliable; history was not advanced"}},
                "pending_validations": list(domain.PENDING), "provenance": provenance,
                "raw_result": "simulation/analysis_raw.json", "native_raw": "simulation/native_raw.json"}
        else:
            try:
                assessment = domain.assess(settings, raw)
            except (ValueError, TypeError, KeyError) as exc:
                raise RuntimeError(f"Incomplete/malformed native material fields: {exc}") from exc
            passed = all(check["status"] == "PASS" for check in assessment["checks"])
            outcome = {"status": "COMPLETED" if passed else "REJECTED", "solver_status": "COMPLETED",
                "converged": passed, "checks": assessment["checks"], "metrics": assessment["metrics"],
                "pending_validations": assessment["pending_validations"], "provenance": provenance,
                "raw_result": "simulation/analysis_raw.json", "native_raw": "simulation/native_raw.json",
                "assessment": assessment, "limitations": list(LIMITATIONS)}
        _assert_sources(output)
        save_json(output / "analysis_raw.json", outcome)
        return outcome
