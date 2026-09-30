"""Native-response inverse objective over the existing MFront material point.

Numerical candidates and campaign persistence belong to the existing Core
engine. This adapter changes neither the native behavior nor its qualification
checks; the declared target is an explicit synthetic reference.
"""

from copy import deepcopy
import hashlib
import math
import json
import os
import signal
import subprocess
import tempfile
import threading
from pathlib import Path, PurePosixPath
import shutil

from plugins.material_point import inverse_reference as domain
from plugins.material_point import reference as material
from ..outcomes import validate_outcome
from ..storage import canonical_hash, save_json
from . import mfront_material as base


PINNED_SIF_SHA256 = "f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64"
ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PROBE = Path(__file__).with_name("mfront_inverse_runtime_probe.py")
PROFILE_ENV = "CAELAB_MFRONT_INVERSE_RUNTIME_PROFILE"
LOCAL_EXACT = "LOCAL_EXACT_SIF"
SEALED_OCI = "SEALED_OCI"
CONFIG_KEYS = (PROFILE_ENV, "CAELAB_MFRONT_IMAGE", "CAELAB_MFRONT_IMAGE_SHA256",
               "CAELAB_CODEASTER_IMAGE", "CAELAB_CODEASTER_IMAGE_SHA256", "CAELAB_SINGULARITY_COMMAND")
NATIVE_OVERRIDE_PREFIXES = ("SINGULARITY_", "SINGULARITYENV_", "APPTAINER_", "APPTAINERENV_")
OCI_DEFINITION = "bootstrap: docker\nfrom: simvia/code_aster@sha256:" + base.OCI_MANIFEST_SHA256
PROBE_BOOTSTRAP = "source /opt/activate.sh; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1; exec python3 -B -I /probe/mfront_inverse_runtime_probe.py"
ADMISSION_LIMITS = {"address_space_bytes": 4 * 1024 ** 3, "cpu_seconds": 30,
                    "file_bytes": 65536, "stdout_bytes": 32768, "stderr_bytes": 32768,
                    "timeout_seconds": 45, "threads": 1}
SOURCE_FILES = [Path(base.__file__).resolve(), base.WORKER.resolve(), Path(material.__file__).resolve(),
                Path(domain.__file__).resolve(), Path(__file__).resolve(), RUNTIME_PROBE.resolve()]
SOURCE_BYTES = {str(path): path.read_bytes() for path in SOURCE_FILES}
SOURCE_HASHES = {path.relative_to(ROOT).as_posix(): base.sha256(path) for path in SOURCE_FILES}
# Actual installed binary hashes were measured by the clean native08 precursor.
# The default still requires its exact SIF bytes. The opt-in OCI profile must
# remeasure this unchanged inventory; no unmeasured distribution is admitted.
SEALED_NATIVE_BINARIES = {
    "mgis_binding": {"sha256": "60f70796a3d575a678891425d096d2fd5832ed1d4f9f5dcd9a7cd79d926aa8be"},
    "mtest_binding": {"sha256": "88ab5619cc5cbf8ec82ca0f97e0f71f0f6785000f3398c31f64d53028d8a0f21"},
    "compiler": {"sha256": "dd91977c184e327710578363ad93ebb175c3a457b6236b874fd3911b7c055c65"},
    "mfront": {"sha256": "a2131b191d41dcf7bf8b71ecce4e35e61d43713062ead58affd4f1e30468713f"},
    "mtest": {"sha256": "988522d0665c78104ac8ecc714ed158383999fd31b311e81db219328bdb042a6"},
    "tfel_config": {"sha256": "9ed8dd6fcb9b958b4e376ea7c69d2fe2162bbbae46a2b7750f7ac6bcc5e7be9b"}}
LIMITATIONS = ["SYNTHETIC_REFERENCE target; no measured-material fit or physical qualification.",
               "Only E varies; nu, temperature, full history, observations and numerical limits are frozen.",
               "Actual MGIS physical stress supplies the objective after every unchanged material-point gate.",
               "A one-generation search selects a best observed candidate, not a global optimum or qualified identification."]


def _assert_sources():
    current = {path.relative_to(ROOT).as_posix(): base.sha256(path) for path in SOURCE_FILES}
    if current != SOURCE_HASHES:
        raise RuntimeError("Inverse/base adapter, worker or domain source changed; create a new source checkpoint")


def _sealed_runtime(raw):
    runtime = raw.get("runtime", {})
    expected = SEALED_NATIVE_BINARIES
    if (runtime.get("mgis_binding_sha256") != expected["mgis_binding"]["sha256"] or
            runtime.get("mtest_binding_sha256") != expected["mtest_binding"]["sha256"]):
        raise RuntimeError("Loaded MGIS/MTest binding differs from the pinned SIF inventory")
    for name in ("compiler", "mfront", "mtest", "tfel_config"):
        if runtime.get("executables", {}).get(name, {}).get("sha256") != expected[name]["sha256"]:
            raise RuntimeError("Actual native executable differs from the pinned SIF inventory")


def _configuration():
    if any(key.startswith(NATIVE_OVERRIDE_PREFIXES) for key in os.environ):
        # Values may contain credentials; neither execute nor retain them.
        raise RuntimeError("Native environment/bind overrides are not admitted by the inverse runtime contract")
    return {key: os.environ.get(key) for key in CONFIG_KEYS}


def _json_strict(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate native metadata key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite native metadata")))


def _definition(text):
    data = _json_strict(text)
    if (not isinstance(data, dict) or set(data) != {"data", "type"} or data["type"] != "container" or
            not isinstance(data["data"], dict) or set(data["data"]) != {"attributes"} or
            not isinstance(data["data"]["attributes"], dict) or set(data["data"]["attributes"]) != {"deffile"}):
        raise ValueError("Actual Singularity definition metadata has an unsupported structure")
    value = data["data"]["attributes"]["deffile"]
    if not isinstance(value, str) or value.strip() != OCI_DEFINITION:
        raise ValueError("Actual Singularity definition must declare exactly the pinned Docker OCI digest")
    return value


def _checked_probe(text):
    data = _json_strict(text)
    if (not isinstance(data, dict) or set(data) != {"schema_version", "probe_sha256", "python", "bindings", "executables"}
            or data["schema_version"] != "1" or data["probe_sha256"] != SOURCE_HASHES[RUNTIME_PROBE.relative_to(ROOT).as_posix()]):
        raise ValueError("Native preflight probe output/source identity is incomplete or changed")
    if (not isinstance(data["python"], dict) or set(data["python"]) != {"version", "executable"} or
            any(not isinstance(v, str) or not v for v in data["python"].values()) or
            not _native_path(data["python"]["executable"]) or
            not isinstance(data["bindings"], dict) or set(data["bindings"]) != {"mgis_binding", "mtest_binding"} or
            not isinstance(data["executables"], dict) or set(data["executables"]) != {"compiler", "mfront", "mtest", "tfel_config"}):
        raise ValueError("Native preflight probe must retain both loaded bindings and all four tools")
    for name, prefix in (("mgis_binding", base.MGIS_PREFIX), ("mtest_binding", base.TFEL_PREFIX)):
        item = data["bindings"][name]
        if (not isinstance(item, dict) or set(item) != {"loaded_path", "resolved_path", "sha256"} or
                any(not isinstance(v, str) or not v for v in item.values()) or
                not _native_path(item["loaded_path"]) or not _native_path(item["resolved_path"]) or
                not PurePosixPath(item["resolved_path"]).is_relative_to(prefix)):
            raise ValueError("Actual loaded binding must resolve within the fixed installed prefix")
    for name, item in data["executables"].items():
        if (not isinstance(item, dict) or set(item) != {"path", "sha256"} or
                any(not isinstance(v, str) or not v for v in item.values()) or not _native_path(item["path"])):
            raise ValueError("Actual preflight tool identity is malformed")
    for name, expected in SEALED_NATIVE_BINARIES.items():
        group = "bindings" if name.endswith("binding") else "executables"
        if data[group][name]["sha256"] != expected["sha256"]:
            raise ValueError("Actual preflight native binding/tool hash differs from the unchanged sealed inventory")
    return data


def _native_path(value):
    path = PurePosixPath(value)
    return path.is_absolute() and str(path) == value and ".." not in path.parts


def _bounded_command(argv):
    """Drain each pipe with bounded memory and kill the whole group on excess/timeout."""
    limits = ADMISSION_LIMITS
    try:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    except OSError as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc)[:limits["stderr_bytes"]],
                "error": "Native admission command could not start"}
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    excess = threading.Event()
    def stop():
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except (ProcessLookupError, OSError):
            pass
    def drain(name, stream):
        while chunk := stream.read(4096):
            remaining = limits[name + "_bytes"] - len(buffers[name])
            buffers[name].extend(chunk[:remaining])
            if len(chunk) > remaining:
                excess.set()
                stop()
                break
        stream.close()
    threads = [threading.Thread(target=drain, args=(name, stream), daemon=True)
               for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))]
    for thread in threads:
        thread.start()
    reason = None
    try:
        process.wait(timeout=limits["timeout_seconds"])
    except subprocess.TimeoutExpired:
        reason = "Native admission command timed out"
        stop()
        process.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=2)
    if any(thread.is_alive() for thread in threads):
        stop()
        reason = "Native admission pipe did not terminate"
    if excess.is_set():
        reason = "Native admission stdout/stderr exceeded the fixed byte bound"
    decoded = {}
    for name, data in buffers.items():
        try:
            decoded[name] = bytes(data).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            decoded[name] = bytes(data).decode("utf-8", errors="replace")
            reason = "Native admission returned invalid UTF-8; bounded partial output retained"
    result = {"returncode": process.returncode, **decoded, "error": reason}
    if not reason and process.returncode != 0:
        result["error"] = "Native admission command exited " + str(process.returncode)
    return result


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def select_native_observation(raw, settings):
    """Adapter-owned exact raw selection; never use a magnitude or oracle."""
    settings = domain.validate_settings(settings)
    conventions = raw.get("conventions", {})
    if (conventions.get("stress_unit") != "MPa" or
            conventions.get("physical") != "xx,yy,zz,xy,xz,yz"):
        raise ValueError("Native stress units and physical tensor component order must be explicit")
    mgis = raw.get("mgis")
    if not isinstance(mgis, dict) or not isinstance(mgis.get("steps"), list):
        raise ValueError("Complete native MGIS state history is required")
    rows = [mgis.get("initial"), *mgis["steps"]]
    target = settings["observation_dataset"]["observations"][0]
    selected = [row for row in rows if isinstance(row, dict) and type(row.get("time_s")) in (int, float)
                and not isinstance(row.get("time_s"), bool) and row["time_s"] == target["time_s"]]
    if len(selected) != 1:
        raise ValueError("The target time must identify exactly one actual native state")
    row = selected[0]
    values = row.get("stress_physical_mpa")
    if (not isinstance(values, list) or len(values) != 6 or
            any(not _finite(value) for value in values)):
        raise ValueError("All six actual physical stress components must be finite")
    observation = {"quantity": "stress", "component": "xx", "time_s": float(row["time_s"]),
                   "unit": "MPa", "value": float(values[0])}
    return observation, deepcopy(row)


class MFrontInverseAdapter:
    backend = "material.mfront.inverse"
    version = "2"
    default_metrics = [*base.MFrontMaterialAdapter.default_metrics, domain.METRIC,
                       "normalized_stress_residual", "observed_axial_stress", "target_axial_stress"]
    domain = "material_point"
    physics_domain = "constitutive_material"
    analysis_type = "bounded_synthetic_inverse_prerequisite"
    input_source_files = SOURCE_FILES

    def __init__(self):
        # Configuration reads only: no subprocess, image hash or native import.
        self._config = _configuration()
        self._profile = self._config[PROFILE_ENV] if self._config[PROFILE_ENV] is not None else LOCAL_EXACT
        if self._profile not in (LOCAL_EXACT, SEALED_OCI):
            raise ValueError("Select only LOCAL_EXACT_SIF or explicit SEALED_OCI in deployment configuration")
        self._base = base.MFrontMaterialAdapter()
        self._admitted_identity = None
        self._admission_evidence = {}

    def _check_configuration(self):
        _assert_sources()
        if self._config != _configuration():
            raise RuntimeError("Inverse deployment profile/image/runtime environment changed; create a new adapter/plan")

    def runtime_admission_evidence(self):
        return deepcopy(self._admission_evidence)

    def runtime_profile_declaration(self):
        """Deployment-only predeclaration; no runtime hashes or native calls."""
        self._check_configuration()
        return {"adapter_version": self.version, "profile": self._profile, "profile_contract_version": "2",
                "deployment_configuration": deepcopy(self._config), "source_files": deepcopy(SOURCE_HASHES),
                "expected_oci_manifest_sha256": base.OCI_MANIFEST_SHA256,
                "local_exact_sif_sha256": PINNED_SIF_SHA256,
                "sealed_installed_native_binaries": deepcopy(SEALED_NATIVE_BINARIES),
                "admission_limits": deepcopy(ADMISSION_LIMITS), "probe_bootstrap": PROBE_BOOTSTRAP}

    def describe_model(self, settings):
        self._check_configuration()
        return domain.model_declaration(settings)

    def describe_inputs(self, settings):
        self._check_configuration()
        return domain.describe_inputs(settings)

    def bind_inputs(self, settings, values):
        self._check_configuration()
        return domain.bind_inputs(settings, values)

    def input_runtime_identity(self):
        self._check_configuration()
        image, digest, runtime = base._runtime_identity()
        if self._profile == LOCAL_EXACT and digest != PINNED_SIF_SHA256:
            raise RuntimeError("Inverse prerequisite requires the exact already-verified SIF, not a substituted image")
        executable = Path(runtime).resolve()
        if not executable.is_file():
            raise RuntimeError("Actual Singularity executable/wrapper is unavailable")
        identity = {"kind": "pinned_mfront_sif" if self._profile == LOCAL_EXACT else "sealed_mfront_oci",
                    "profile": self._profile, "profile_contract_version": "2", "deployment_configuration": deepcopy(self._config),
                    "image_path": str(image), "image_sha256": digest,
                    "singularity": {"path": str(executable), "sha256": base.sha256(executable)},
                    "sealed_installed_native_binaries": deepcopy(SEALED_NATIVE_BINARIES),
                    "binary_inventory_basis": "Unchanged measured native08 inventory; explicit SEALED_OCI remeasures before admission",
                    "behavior_source_sha256": base.SOURCE_SHA256, "compiler_policy": base.COMPILER_POLICY,
                    "source_files": deepcopy(SOURCE_HASHES), "upstream_binary_source_commits": "UNKNOWN"}
        if self._admitted_identity is not None:
            for key in ("profile", "deployment_configuration", "image_path", "image_sha256", "singularity", "source_files"):
                if identity[key] != self._admitted_identity[key]:
                    raise RuntimeError("Admitted inverse SIF/runtime/profile/source identity changed")
        if self._profile == SEALED_OCI:
            location = shutil.which("prlimit")
            if not location:
                raise RuntimeError("SEALED_OCI native admission requires Linux prlimit")
            prlimit = Path(location).resolve()
            identity["prlimit"] = {"path": str(prlimit), "sha256": base.sha256(prlimit)}
            if self._admitted_identity is not None and identity["prlimit"] != self._admitted_identity["prlimit"]:
                raise RuntimeError("Admitted inverse prlimit identity changed")
            prefix = [str(prlimit), "--as=" + str(ADMISSION_LIMITS["address_space_bytes"]),
                      "--cpu=" + str(ADMISSION_LIMITS["cpu_seconds"]), "--fsize=" + str(ADMISSION_LIMITS["file_bytes"])]
            evidence = {"profile": self._profile, "limits": deepcopy(ADMISSION_LIMITS), "commands": {}}
            self._admission_evidence = evidence
            def execute(label, argv):
                result = _bounded_command(argv)
                evidence["commands"][label] = {"argv": argv, **result}
                if result["error"]:
                    raise RuntimeError(result["error"])
                return result["stdout"]
            definition_stdout = execute("definition", prefix + [str(executable), "inspect", "--json", "--deffile", str(image)])
            definition = _definition(definition_stdout)
            with tempfile.TemporaryDirectory(prefix="caelab-inverse-admission-") as directory:
                root = Path(directory)
                script, scratch = root / "probe", root / "scratch"
                script.mkdir()
                scratch.mkdir()
                (script / RUNTIME_PROBE.name).write_bytes(SOURCE_BYTES[str(RUNTIME_PROBE.resolve())])
                command = prefix + [str(executable), "exec", "--cleanenv", "--containall", "--no-home",
                    "--bind", str(script) + ":/probe:ro", "--bind", str(scratch) + ":/tmp:rw",
                    "--pwd", "/probe", str(image), "/bin/bash", "--noprofile", "--norc", "-c", PROBE_BOOTSTRAP]
                probe_stdout = execute("probe", command)
                measurements = _checked_probe(probe_stdout)
            identity.update(oci_definition={"definition": definition, "oci_manifest_sha256": base.OCI_MANIFEST_SHA256,
                                            "stdout_sha256": hashlib.sha256(definition_stdout.encode()).hexdigest()},
                            preflight_probe={"measurements": measurements,
                                             "stdout_sha256": hashlib.sha256(probe_stdout.encode()).hexdigest(),
                                             "limits": deepcopy(ADMISSION_LIMITS), "bootstrap": PROBE_BOOTSTRAP,
                                             "read_only_probe_mount": True, "fresh_scratch": True})
            if (base.sha256(image) != digest or base.sha256(executable) != identity["singularity"]["sha256"] or
                    base.sha256(prlimit) != identity["prlimit"]["sha256"]):
                raise RuntimeError("SIF/runtime/prlimit changed during native runtime admission")
        self._check_configuration()
        if self._admitted_identity is not None and canonical_hash(identity) != canonical_hash(self._admitted_identity):
            raise RuntimeError("Admitted native profile/OCI/probe/runtime identity changed")
        if self._admitted_identity is None:
            self._admitted_identity = deepcopy(identity)
        return identity

    def _capture(self, output, settings=None):
        output.mkdir(parents=True, exist_ok=True)
        for key, filename in ((str(Path(domain.__file__).resolve()), "inverse_reference.py"),
                              (str(Path(__file__).resolve()), "mfront_inverse.py"),
                              (str(RUNTIME_PROBE.resolve()), RUNTIME_PROBE.name)):
            (output / filename).write_bytes(SOURCE_BYTES[key])
        if not (output / "runtime_admission.json").exists():
            save_json(output / "runtime_admission.json", self.runtime_admission_evidence())
        if settings is not None:
            save_json(output / "inverse_settings.json", settings)
            save_json(output / "observation_dataset.json", settings["observation_dataset"])

    def solve(self, output, settings):
        output = Path(output)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Inverse output must be fresh/empty; preserve previous evidence")
        provenance = {"adapter": self.backend, "adapter_version": self.version,
                      "source_files": deepcopy(SOURCE_HASHES), "assumptions": list(LIMITATIONS),
                      "domain_plugin": {"module": "plugins.material_point.inverse_reference", "version": domain.__version__}}
        outcome = None
        try:
            settings = domain.validate_settings(settings)
        except ValueError as exc:
            self._capture(output)
            rejected = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                        "checks": [{"code": "inverse_preflight", "status": "FAIL", "observed": str(exc)}],
                        "metrics": {}, "pending_validations": list(domain.PENDING), "provenance": provenance,
                        "raw_result": "simulation/analysis_raw.json"}
            save_json(output / "analysis_raw.json", rejected)
            return rejected
        try:
            identity = self.input_runtime_identity()
            provenance["input_runtime_identity"] = deepcopy(identity)
            outcome = self._base.solve(output, domain.base_settings(settings))
            validate_outcome(outcome)
            original = output / "analysis_raw.json"
            if not original.is_file():
                raise RuntimeError("Base material-point outcome artifact is missing")
            shutil.copyfile(original, output / "material_point_analysis_raw.json")
            self._capture(output, settings)
            provenance.update(base_adapter=base.MFrontMaterialAdapter.backend,
                              base_adapter_details=deepcopy(outcome["provenance"]),
                              versions=deepcopy(outcome["provenance"].get("versions")),
                              dataset_sha256=settings["observation_dataset"]["sha256"],
                              source_kind="SYNTHETIC_REFERENCE",
                              base_analysis_artifact="simulation/material_point_analysis_raw.json",
                              base_analysis_sha256=base.sha256(output / "material_point_analysis_raw.json"))
            combined = deepcopy(outcome)
            combined.update(provenance=provenance, pending_validations=list(domain.PENDING),
                            raw_result="simulation/analysis_raw.json", limitations=list(LIMITATIONS))
            if outcome["status"] == "COMPLETED":
                codes = {check["code"] for check in outcome["checks"] if check["status"] == "PASS"}
                if (not set(domain.REQUIRED_BASE_CHECKS) <= codes or
                        any(check["status"] != "PASS" for check in outcome["checks"]) or
                        any(not metric["valid"] for metric in outcome["metrics"].values())):
                    raise RuntimeError("Every original native material-point gate must pass before inverse feedback")
                raw, _ = base.checked_native(output, base.sha256(output / "input.json"))
                _sealed_runtime(raw)
                assessment = material.assess(domain.base_settings(settings), raw)
                if (canonical_hash(assessment["checks"]) != canonical_hash(outcome["checks"]) or
                        canonical_hash(assessment["metrics"]) != canonical_hash(outcome["metrics"])):
                    raise RuntimeError("Native fields drifted from the preserved base numerical outcome")
                observation, row = select_native_observation(raw, settings)
                residual = domain.objective_from_observation(settings, observation)
                combined["metrics"].update(residual["metrics"])
                combined["checks"].extend(residual["checks"])
                selection = {"artifact": "simulation/native_raw.json", "driver": "MGIS", "time_s": 1.,
                             "physical_component": "xx", "array": "stress_physical_mpa", "index": 0,
                             "native_raw_sha256": base.sha256(output / "native_raw.json"),
                             "native_library_sha256": raw["library_sha256"]}
                save_json(output / "inverse_observation.json", {"selection": selection, "actual_native_state": row,
                          "observation": observation, "dataset": settings["observation_dataset"],
                          "objective": residual, "source_kind": "SYNTHETIC_REFERENCE"})
                combined["inverse_observation_artifact"] = "simulation/inverse_observation.json"
                provenance["native_observation_selection"] = selection
            else:
                combined["metrics"][domain.METRIC] = {"value": None, "unit": "1", "valid": False,
                    "reason": "Base native material-point execution/numerical gate did not pass; no inverse feedback"}
            _assert_sources()
            try:
                after_identity = self.input_runtime_identity()
            finally:
                save_json(output / "runtime_admission_post.json", self.runtime_admission_evidence())
            if canonical_hash(after_identity) != canonical_hash(identity):
                raise RuntimeError("SIF/runtime/profile changed during native inverse evaluation")
            validate_outcome(combined)
            save_json(output / "analysis_raw.json", combined)
            return combined
        except Exception as exc:
            self._capture(output, settings)
            save_json(output / "runtime_admission_failure.json", self.runtime_admission_evidence())
            if (output / "analysis_raw.json").is_file() and not (output / "material_point_analysis_raw.json").exists():
                shutil.copyfile(output / "analysis_raw.json", output / "material_point_analysis_raw.json")
            if outcome is not None and isinstance(outcome.get("provenance"), dict):
                provenance.setdefault("base_adapter_details", deepcopy(outcome["provenance"]))
            message = f"{type(exc).__name__}: {exc}"
            (output / "inverse_execution_failure.log").write_text(message + "\n", encoding="utf-8")
            failed = {"status": "REJECTED", "solver_status": "FAILED_EXECUTION", "converged": None,
                      "checks": [{"code": "inverse_execution", "status": "FAIL", "observed": message}],
                      "metrics": {}, "pending_validations": list(domain.PENDING), "provenance": provenance,
                      "raw_result": "simulation/analysis_raw.json", "limitations": list(LIMITATIONS)}
            save_json(output / "analysis_raw.json", failed)
            return failed
