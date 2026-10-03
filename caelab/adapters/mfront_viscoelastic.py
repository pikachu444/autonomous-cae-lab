"""Fixed-law, exact-local-runtime viscoelastic material-point adapter.

Core owns the append-only declared-model transaction. This adapter owns native
syntax, isolated execution and actual output admission. It reuses only existing
runtime/compiler helpers; neither elasticity nor inverse feedback is executed.
"""

from copy import deepcopy
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil

from plugins.material_point import viscoelastic_reference as material
from ..storage import canonical_hash, save_json
from .. import execution_control
from . import codeaster_elasticity as execution
from .codeaster_elasticity import _process
from . import codeaster_execution as process_policy
from . import mfront_hyperelastic_worker as compiler_helper
from . import mfront_material as transport
from . import mfront_inverse as runtime_helpers
from . import mfront_viscoelastic_worker as worker

ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(worker.__file__).resolve()
LAW = WORKER.with_name(worker.SOURCE_NAME)
PINNED_SIF_SHA256 = runtime_helpers.PINNED_SIF_SHA256
PINNED_SINGULARITY_SHA256 = "994f404350a92a919264e16e1239f409ac550b3fa8118e80cdee1634fc36ff0a"
SEALED_NATIVE_BINARIES = deepcopy(runtime_helpers.SEALED_NATIVE_BINARIES)
CONFIG_KEYS = tuple(key for key in runtime_helpers.CONFIG_KEYS if key != runtime_helpers.PROFILE_ENV) + (
    "CAELAB_CODEASTER_TIME_LIMIT_SECONDS", "CAELAB_CODEASTER_WALL_TIMEOUT_SECONDS")
BOOTSTRAP = "source /opt/activate.sh; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1; exec python3 -B -I /work/mfront_viscoelastic_worker.py"
SOURCE_FILES = [Path(__file__).resolve(), WORKER, LAW, Path(material.__file__).resolve(),
                Path(transport.__file__).resolve(), transport.WORKER.resolve(),
                *runtime_helpers.SOURCE_FILES, Path(compiler_helper.__file__).resolve(),
                Path(execution.__file__).resolve(), Path(process_policy.__file__).resolve(),
                Path(execution_control.__file__).resolve()]
SOURCE_FILES = list(dict.fromkeys(SOURCE_FILES))
SOURCE_BYTES = {str(path): path.read_bytes() for path in SOURCE_FILES}
SOURCE_HASHES = {path.relative_to(ROOT).as_posix(): transport.sha256(path) for path in SOURCE_FILES}
CAPTURE_NAMES = {path.relative_to(ROOT).as_posix(): path.name for path in SOURCE_FILES}
CAPTURE_NAMES["plugins/material_point/reference.py"] = "elastic_reference.py"
LIMITATIONS = [
    "Synthetic infinitesimal 3D standard linear solid; no measured material or spatial solver coupling.",
    "MGIS and MTest share one generated law. The independent Python exact solution is a numerical reference.",
    "Native stored/dissipated energy is mandatory; no missing field or alternative energy is substituted.",
    "Only reliable nominal states advance; every signed FD probe starts from a full independent native clone.",
    "Shared-time refinement checks composition, not a convergence order; tangents depend on each increment dt.",
    "Only the protected exact local SIF is admitted; alternate images and portable runtime qualification are NOT_RUN.",
    "Upstream binary source commits and corporate license/security approval remain UNKNOWN."]

CHECK_CODES = [
    "reliable_integrations", "native_tensor_mapping", "immutable_full_probe_state",
    "native_driver_continuity", "exact_ordered_history", "native_energy_table",
    *["max_" + name + "_error" for name in (
        "stress_physical", "stress_kelvin", "branch_physical", "branch_kelvin",
        "cross_driver_stress", "cross_driver_branch", "stored_energy",
        "dissipated_energy", "prefix_work_closure", "probe_stress", "probe_branch",
        "probe_stored_energy", "probe_dissipated_energy")],
    "analytical_tangent_relative_error",
    *["fd_tangent_relative_error_" + format(h, ".0e") for h in material.FIXED_LIMITS["finite_difference_steps"]],
    "native_stored_energy_nonnegative", "native_dissipation_nondecreasing"]


def _configuration():
    if any(key.startswith(runtime_helpers.NATIVE_OVERRIDE_PREFIXES) for key in os.environ):
        raise RuntimeError("Container environment/mount controls are outside the frozen viscoelastic contract")
    return {key: os.environ.get(key) for key in CONFIG_KEYS}


def _assert_sources(output=None):
    actual_transport = SOURCE_HASHES[worker.TRANSPORT_KEY]
    if actual_transport not in worker.TRANSPORT_VARIANTS or transport.WORKER.stat().st_size != worker.TRANSPORT_VARIANTS[actual_transport]:
        raise RuntimeError("Actual transport source is outside the two exact reviewed LF/CRLF forms")
    for path in SOURCE_FILES:
        key = path.relative_to(ROOT).as_posix()
        if path.is_symlink() or not path.is_file() or transport.sha256(path) != SOURCE_HASHES[key]:
            raise RuntimeError("Viscoelastic source/helper identity changed; preserve this checkpoint")
        if output is not None:
            captured = Path(output) / CAPTURE_NAMES[key]
            if captured.is_symlink() or not captured.is_file() or transport.sha256(captured) != SOURCE_HASHES[key]:
                raise RuntimeError("Captured viscoelastic source/helper identity changed")
    if output is not None and _strict_json(Path(output) / "source_inventory.json") != SOURCE_HASHES:
        raise RuntimeError("Captured source inventory differs from the actual producer")


def _strict_json(path, *, maximum=worker.MAX_RAW_BYTES):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > maximum:
        raise ValueError("Required native JSON is absent, a symlink or exceeds the frozen byte bound")
    result = runtime_helpers._json_strict(path.read_text(encoding="utf-8"))
    def finite(item):
        if isinstance(item, dict):
            for value in item.values():
                finite(value)
        elif isinstance(item, list):
            for value in item:
                finite(value)
        elif type(item) in (int, float):
            try:
                good = math.isfinite(item)
            except OverflowError:
                good = False
            if not good:
                raise ValueError("Nonfinite native numeric metadata")
    finite(result)
    return result


def _native_path(value, prefix=None):
    if not isinstance(value, str):
        return False
    path = PurePosixPath(value)
    return path.is_absolute() and str(path) == value and ".." not in path.parts and (
        prefix is None or path.is_relative_to(prefix))


def _frozen_policy(settings, budgets):
    return {"domain_sha256": SOURCE_HASHES[Path(material.__file__).resolve().relative_to(ROOT).as_posix()],
            "source_files": deepcopy(SOURCE_HASHES), "settings_sha256": canonical_hash(settings),
            "limits": deepcopy(settings["limits"]), "behavior": worker.BEHAVIOUR,
            "native_interface": "generic", "native_hypothesis": "Tridimensional",
            "resource_limits": worker.resource_limits(budgets), "process_policy": deepcopy(budgets),
            "compiler_policy": transport.COMPILER_POLICY,
            "transport_sha256": SOURCE_HASHES[worker.TRANSPORT_KEY],
            "compiler_helper_sha256": SOURCE_HASHES[worker.COMPILER_HELPER_KEY],
            "sealed_installed_native_binaries": deepcopy(SEALED_NATIVE_BINARIES),
            "mtest_limits": deepcopy(worker.MTEST_LIMITS),
            "mtest_buffer_mapping": deepcopy(worker.MTEST_BUFFER_MAPPING),
            "mtest_table_mapping": deepcopy(worker.MTEST_TABLE_MAPPING),
            "extra_native_bindings": {"tfel_math": deepcopy(worker.SEALED_MTEST_MATH_BINDING)},
            "sealed_binding_paths": deepcopy(worker.SEALED_BINDING_PATHS)}


def checked_native(output, input_sha, settings, budgets):
    """Admit source/build/runtime/native buffers without fabricating fields."""
    output = Path(output)
    _assert_sources(output)
    policy = _frozen_policy(settings, budgets)
    if canonical_hash(_strict_json(output / "frozen_execution_policy.json")) != canonical_hash(policy):
        raise ValueError("Frozen actual transport/compiler/process policy differs from the adapter")
    worker.assert_captures(output, policy)
    raw = _strict_json(output / "native_raw.json")
    build = _strict_json(output / "build_identity.json")
    if canonical_hash(_strict_json(output / "input.json")) != canonical_hash(settings):
        raise ValueError("Original captured input differs from the prescribed settings")
    if (not isinstance(raw, dict) or raw.get("schema_version") != "1" or
            raw.get("input_sha256") != input_sha or transport.sha256(output / "input.json") != input_sha or
            raw.get("worker_sha256") != SOURCE_HASHES[WORKER.relative_to(ROOT).as_posix()] or
            raw.get("source_sha256") != worker.SOURCE_SHA256 or
            raw.get("transport_sha256") != policy["transport_sha256"] or
            raw.get("compiler_helper_sha256") != policy["compiler_helper_sha256"] or
            raw.get("source_files") != SOURCE_HASHES or
            canonical_hash(raw.get("process_policy")) != canonical_hash(budgets) or
            canonical_hash(raw.get("resource_limits")) != canonical_hash(worker.resource_limits(budgets)) or
            transport.sha256(output / worker.SOURCE_NAME) != worker.SOURCE_SHA256 or
            transport.sha256(output / "build" / worker.SOURCE_NAME) != worker.SOURCE_SHA256 or
            raw.get("library_sha256") != transport.sha256(output / "build/src/libBehaviour.so")):
        raise ValueError("Actual input/worker/source/transport/library identity is absent or changed")
    if (not isinstance(build, dict) or build.get("library_path") != "build/src/libBehaviour.so" or
            build.get("library_sha256") != raw["library_sha256"] or build.get("source_sha256") != worker.SOURCE_SHA256 or
            build.get("generation_arguments") != worker.BUILD_ARGUMENTS or
            build.get("makefile_sha256") != transport.sha256(output / "build/src/Makefile.mfront") or
            build.get("compiler_flags_policy") != transport.COMPILER_POLICY or
            build.get("compiler_helper_sha256") != policy["compiler_helper_sha256"] or
            not isinstance(build.get("compiler_flags_override"), list) or
            "-O2" not in build["compiler_flags_override"] or
            any(not isinstance(f, str) or f.startswith(("-march", "-mtune")) or
                f in ("-ffast-math", "-ftree-vectorize") for f in build["compiler_flags_override"]) or
            not all(isinstance(build.get(key), list) and build[key] and all(isinstance(x, str) and x for x in build[key])
                    for key in ("compiler_flags_makefile", "actual_compiler_commands")) or
            not isinstance(build.get("dependency_sha256"), dict) or not build["dependency_sha256"] or
            any(not _native_path(path) or not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)
                for path, digest in build["dependency_sha256"].items())):
        raise ValueError("Actual portable compiler/build/dependency evidence is incomplete")
    runtime = raw.get("runtime")
    if (not isinstance(runtime, dict) or runtime != _strict_json(output / "runtime.json") or
            canonical_hash(runtime.get("process_policy")) != canonical_hash(budgets) or
            canonical_hash(runtime.get("resource_limits")) != canonical_hash(worker.resource_limits(budgets)) or
            runtime.get("mgis") != "3.0" or not str(runtime.get("tfel", "")).startswith("tfel-config 5.0.0") or
            any(not isinstance(runtime.get(name), str) or not runtime[name]
                for name in ("python", "numpy", "compiler", "mfront", "make"))):
        raise ValueError("Actual native package/runtime identity is incomplete")
    runtime_helpers._sealed_runtime(raw)
    extra = runtime.get("extra_native_bindings")
    if (not isinstance(extra, dict) or set(extra) != {"tfel_math"} or
            extra != raw.get("extra_native_bindings") or extra != policy["extra_native_bindings"]):
        raise ValueError("Actual extra converter binding differs from the frozen policy/raw/runtime")
    worker.checked_mtest_math_binding(extra["tfel_math"])
    flags = worker._transport(policy["transport_sha256"]).portable_compiler_flags(
        runtime["tfel_recommended_oflags0"], runtime["tfel_cpp_compiler_flags"], runtime["tfel_include_path"])
    makefile = (output / "build/src/Makefile.mfront").read_text(encoding="utf-8")
    observed_flags = [line for line in makefile.splitlines() if any(token in line for token in
        ("CXXFLAGS", "CPPFLAGS", "LDFLAGS", "CXX", "INCLUDES", "-std="))]
    if (build.get("compiler_flags_override") != flags or build.get("compiler_flags_makefile") != observed_flags or
            build.get("compiler_commands_artifact") != "build/compile.stdout.log" or
            build.get("compiler_commands_sha256") != transport.sha256(output / "build/compile.stdout.log") or
            build.get("compiler_command_policy") != compiler_helper.COMPILER_COMMAND_POLICY or
            build.get("dependency_artifact") != "library_dependencies.stdout.log" or
            build.get("dependency_artifact_sha256") != transport.sha256(output / "library_dependencies.stdout.log")):
        raise ValueError("Original compiler/Makefile/dependency evidence differs from its exact retained bytes")
    for path in (output / "build/compile.stdout.log", output / "library_dependencies.stdout.log"):
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= worker.MAX_FILE_BYTES:
            raise ValueError("Original build log is absent, linked or unbounded")
    compiler = runtime["executables"]["compiler"]["path"]
    if not _native_path(compiler):
        raise ValueError("Actual compiler path is not canonical")
    records = compiler_helper.compiler_command_evidence(
        (output / "build/compile.stdout.log").read_text(encoding="utf-8"), compiler, flags, behaviour=worker.BEHAVIOUR)
    if (build.get("actual_compiler_commands") != [record["command"] for record in records] or
            build.get("compiler_command_evidence") != records):
        raise ValueError("Complete exact five compiler records differ from the original log")
    paths = compiler_helper.library_dependency_paths((output / "library_dependencies.stdout.log").read_text(encoding="utf-8"))
    if set(paths) != set(build["dependency_sha256"]):
        raise ValueError("Complete resolved dependency set differs from the original log")
    for name, prefix, version, binding_key in (
            ("mgis", transport.MGIS_PREFIX, "3.0", "mgis_binding"),
            ("tfel", transport.TFEL_PREFIX, "5.0.0", "mtest_binding")):
        package = runtime.get(name + "_package")
        if (not isinstance(package, dict) or package.get("name") != name or package.get("version") != version or
                package.get("package_prefix") != prefix or
                runtime.get(binding_key + "_loaded_path") != worker.SEALED_BINDING_PATHS[binding_key]["loaded_path"] or
                runtime.get(binding_key + "_path") != worker.SEALED_BINDING_PATHS[binding_key]["resolved_path"] or
                not _native_path(package.get("binding_path"), prefix) or
                package.get("spec_sha256") != transport.sha256(output / (name + "_installed_spec.json")) or
                package.get("binding_sha256") != runtime.get(binding_key + "_sha256") or
                package.get("binding_path") != runtime.get(binding_key + "_path")):
            raise ValueError("Actual installed package and sealed loaded/resolved binding pair are not tied together")
    desc = raw.get("behaviour_description")
    if (not isinstance(desc, dict) or desc.get("behaviour") != worker.BEHAVIOUR or
            desc.get("hypothesis") != "TRIDIMENSIONAL" or desc.get("gradients") != ["Strain"] or
            desc.get("thermodynamic_forces") != ["Stress"] or desc.get("gradient_size") != 6 or
            desc.get("force_size") != 6 or desc.get("internal_state_variables") != ["BranchStress"] or
            desc.get("internal_state_variable_sizes") != [6] or
            desc.get("material_properties") != worker.PROPERTY_NAMES or
            desc.get("external_state_variables") != ["Temperature"] or
            desc.get("computes_stored_energy") is not True or desc.get("computes_dissipated_energy") is not True):
        raise ValueError("Native law/tensor/complete state/energy descriptors are not the fixed 3D law")
    if raw.get("conventions") != {"physical": "xx,yy,zz,xy,xz,yz", "native": "xx,yy,zz,sqrt2*xy,sqrt2*xz,sqrt2*yz",
                                 "strain": "infinitesimal_tensor_not_engineering_shear", "stress_unit": "MPa",
                                 "energy_unit": "MPa = MJ/m^3 per reference volume"}:
        raise ValueError("Actual tensor/energy units and conventions changed")
    attribution = _strict_json(output / "source_attribution.json")
    if (attribution.get("source_sha256") != worker.SOURCE_SHA256 or
            attribution.get("reference_sha256") != worker.REFERENCE_SOURCE_SHA256 or
            attribution.get("reference_commit") != worker.TFEL_COMMIT or
            transport.sha256(output / "upstream_GeneralizedMaxwell.mfront") != worker.REFERENCE_SOURCE_SHA256):
        raise ValueError("Actual fixed upstream source attribution is missing or changed")
    licenses = attribution.get("installed_tfel_license_files")
    if not isinstance(licenses, list) or len(licenses) != 3:
        raise ValueError("Actual installed license evidence is incomplete")
    for record in licenses:
        if not isinstance(record, dict) or record.get("artifact") != "licenses/" + str(record.get("name")) or record.get("name") not in (
                "LICENCE-GNU-GPL", "LICENCE-CECILL-A-EN", "LICENCE-CECILL-A-FR") or record.get("sha256") != transport.sha256(output / record["artifact"]):
            raise ValueError("Installed native license artifact changed")
    if "native_rejection" not in raw:
        mtest = raw.get("mtest")
        if not isinstance(mtest, dict) or not isinstance(mtest.get("states"), list):
            raise ValueError("Complete actual MTest observations are absent")
        material._mtest_imposed_history(settings, mtest)
        copied = deepcopy(mtest["states"])
        metadata = worker.parse_mtest_table(output / "mtest.res", copied)
        if copied != mtest["states"] or metadata != mtest.get("native_output_table"):
            raise ValueError("MTest energy projection differs from its actual strict native output file")
    return raw, build


def _native_rejection(raw, settings):
    """Bind a typed unreliable return to the retained actual partial endpoint."""
    refused = raw["native_rejection"]
    mgis = raw.get("mgis")
    if not isinstance(refused, dict) or not isinstance(mgis, dict):
        raise ValueError("Actual native rejection and partial driver are mandatory")
    code, index = refused.get("integration_return"), refused.get("step")
    steps = mgis.get("steps")
    if (type(code) is not int or code not in (0, -1) or type(index) is not int or
            not 1 <= index < len(settings["history"]) or not isinstance(steps, list) or len(steps) != index or
            mgis.get("library_sha256") != raw["library_sha256"] or
            canonical_hash(mgis.get("native_rejection")) != canonical_hash(refused)):
        raise ValueError("Actual unreliable return/step/library differs from its retained partial history")
    step = steps[-1]
    if refused.get("phase") == "nominal":
        actual = step
        if step.get("finite_differences") != []:
            raise ValueError("Unreliable nominal state cannot run signed probes")
    elif refused.get("phase") == "finite_difference":
        h, column, sign = refused.get("h"), refused.get("column"), refused.get("sign")
        if (h not in material.FIXED_LIMITS["finite_difference_steps"] or type(column) is not int or
                not 0 <= column < 6 or type(sign) is not int or sign not in (-1, 1)):
            raise ValueError("Actual unreliable probe identity is malformed")
        matches = [probe for fd in step.get("finite_differences", []) if fd.get("h") == h
                   for probe in fd.get("probes", []) if probe.get("column") == column and probe.get("sign") == sign]
        if len(matches) != 1 or step.get("integration_return") != 1:
            raise ValueError("Actual rejection requires its unique signed probe and a reliable nominal endpoint")
        actual = matches[0]
    else:
        raise ValueError("Actual rejection phase is unsupported")
    if (type(actual.get("integration_return")) is not int or actual.get("integration_return") != code or "nominal_after_update" in step or
            not isinstance(actual.get("error_message"), str) or
            any(actual.get(key) != refused.get(key) for key in
                ("time_step_increase_factor", "error_message", "failure_or_unreliable_point_index"))):
        raise ValueError("Actual rejection differs from its retained integration observation or advanced state")
    material.number(actual.get("time_step_increase_factor"), "Actual unreliable dt factor")
    if type(actual.get("failure_or_unreliable_point_index")) is not int:
        raise ValueError("Actual unreliable point index must be a typed integer")
    return refused


class MFrontViscoelasticAdapter:
    backend = "material.mfront.viscoelastic"
    version = "1"
    domain = "material_point"
    physics_domain = "constitutive_material"
    analysis_type = "infinitesimal_single_branch_viscoelastic_point"
    default_metrics = [*["max_" + name + "_error" for name in (
        "stress_physical", "stress_kelvin", "branch_physical", "branch_kelvin",
        "cross_driver_stress", "cross_driver_branch", "stored_energy", "dissipated_energy",
        "prefix_work_closure", "probe_stress", "probe_branch", "probe_stored_energy", "probe_dissipated_energy")],
        "analytical_tangent_relative_error",
        *["fd_tangent_relative_error_" + format(h, ".0e") for h in material.FIXED_LIMITS["finite_difference_steps"]],
        "stress_history", "branch_stress_history", "native_energy_history", "reference_work_history"]
    input_source_files = SOURCE_FILES

    def __init__(self):
        self._configuration = _configuration()
        self._budgets = process_policy.process_budgets()
        self._limits = worker.resource_limits(self._budgets)
        self._frozen_runtime = None

    def _check(self, output=None):
        _assert_sources(output)
        if self._configuration != _configuration() or self._budgets != process_policy.process_budgets():
            raise RuntimeError("Frozen deployment environment changed; create a new source/run checkpoint")

    def describe_model(self, settings):
        settings = worker.native_preflight(material.validate_settings(settings))
        self._check()
        return material.model_declaration(settings)

    def input_runtime_identity(self):
        self._check()
        image, digest, executable = transport._runtime_identity()
        if digest != PINNED_SIF_SHA256:
            raise RuntimeError("Viscoelastic acceptance requires the unchanged protected exact local SIF")
        executable = Path(executable).resolve()
        limit = shutil.which("prlimit")
        if not executable.is_file() or not limit:
            raise RuntimeError("Actual trusted Singularity and Linux prlimit are mandatory")
        prlimit = Path(limit).resolve()
        if transport.sha256(executable) != PINNED_SINGULARITY_SHA256:
            raise RuntimeError("Actual Singularity executable differs from the protected local runtime")
        identity = {"profile": "LOCAL_EXACT_SIF", "image_path": str(image), "image_sha256": digest,
                    "singularity": {"path": str(executable), "sha256": transport.sha256(executable)},
                    "prlimit": {"path": str(prlimit), "sha256": transport.sha256(prlimit)},
                    "oci_manifest_sha256": transport.OCI_MANIFEST_SHA256,
                    "deployment_configuration": deepcopy(self._configuration),
                    "source_files": deepcopy(SOURCE_HASHES),
                    "sealed_installed_native_binaries": deepcopy(SEALED_NATIVE_BINARIES),
                    "compiler_policy": transport.COMPILER_POLICY, "resource_limits": deepcopy(self._limits),
                    "process_policy": deepcopy(self._budgets),
                    "transport_sha256": SOURCE_HASHES[worker.TRANSPORT_KEY],
                    "compiler_helper_sha256": SOURCE_HASHES[worker.COMPILER_HELPER_KEY],
                    "upstream_binary_source_commits": "UNKNOWN"}
        self._check()
        if self._frozen_runtime is not None and identity != self._frozen_runtime:
            raise RuntimeError("Actual SIF/wrapper/prlimit/source/runtime identity drifted")
        self._frozen_runtime = deepcopy(identity)
        return identity

    def _capture(self, output):
        for key, name in CAPTURE_NAMES.items():
            (output / name).write_bytes(SOURCE_BYTES[str(ROOT / key)])
        save_json(output / "source_inventory.json", SOURCE_HASHES)

    def solve(self, output, settings):
        output = Path(output)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Viscoelastic output must be fresh/empty; prior evidence is immutable")
        output.mkdir(parents=True, exist_ok=True)
        provenance = {"adapter": self.backend, "adapter_version": self.version,
                      "domain_plugin": {"module": "plugins.material_point.viscoelastic_reference",
                                        "version": material.__version__},
                      "source_files": deepcopy(SOURCE_HASHES), "assumptions": list(LIMITATIONS),
                      "resource_limits": deepcopy(self._limits), "process_policy": deepcopy(self._budgets)}
        def reject(code, message, solver_status, metrics=None):
            outcome = {"status": "REJECTED", "solver_status": solver_status, "converged": None,
                       "checks": [{"code": code, "status": "FAIL", "observed": message}],
                       "metrics": metrics or {}, "pending_validations": list(material.PENDING),
                       "provenance": provenance, "raw_result": "simulation/analysis_raw.json",
                       "limitations": list(LIMITATIONS)}
            save_json(output / "analysis_raw.json", outcome)
            return outcome
        try:
            settings = worker.native_preflight(material.validate_settings(settings))
        except ValueError as exc:
            return reject("viscoelastic_preflight", str(exc), "NOT_RUN")
        try:
            execution_control.check_cancelled()
            self._check()
            self._capture(output)
            self._check(output)
            save_json(output / "input.json", settings)
            input_sha = transport.sha256(output / "input.json")
            save_json(output / "model_declaration.json", self.describe_model(settings))
            save_json(output / "analytical_reference.json", material.analytical_reference(settings))
            identity = self.input_runtime_identity()
            provenance["input_runtime_identity"] = deepcopy(identity)
            policy = _frozen_policy(settings, self._budgets)
            save_json(output / "frozen_execution_policy.json", policy)
            save_json(output / "runtime_identity_before.json", identity)
            scratch = output / "scratch"
            scratch.mkdir(exist_ok=False)
            command = [identity["prlimit"]["path"], "--as=" + str(self._limits["address_space_bytes"]),
                       "--cpu=" + str(self._limits["cpu_seconds"]),
                       "--fsize=" + str(self._limits["maximum_single_artifact_bytes"]),
                       identity["singularity"]["path"], "exec", "--cleanenv", "--containall", "--no-home",
                       "--bind", str(output.resolve()) + ":/work:rw", "--bind", str(scratch.resolve()) + ":/tmp:rw",
                       "--pwd", "/work", identity["image_path"], "/bin/bash", "--noprofile", "--norc", "-c", BOOTSTRAP]
            self._check(output)
            if self.input_runtime_identity() != identity:
                raise RuntimeError("Pre-native frozen runtime changed")
            _process(command, output, "viscoelastic_worker", timeout=self._budgets["subprocess_timeout_seconds"])
            self._check(output)
            save_json(output / "runtime_identity_after.json", self.input_runtime_identity())
            if self._frozen_runtime != identity:
                raise RuntimeError("Post-native frozen runtime changed")
            for path in output.rglob("*"):
                if path.is_symlink() or path.is_file() and path.stat().st_size > self._limits["maximum_single_artifact_bytes"]:
                    raise RuntimeError("Native output contains a symlink or an artifact above its fixed bound")
            raw, build = checked_native(output, input_sha, settings, self._budgets)
            provenance.update(versions=deepcopy(raw["runtime"]), build=build,
                              behaviour_description=deepcopy(raw["behaviour_description"]),
                              native_library_artifact="simulation/build/src/libBehaviour.so",
                              actual_native_raw="simulation/native_raw.json",
                              container_isolation={"cleanenv": True, "containall": True, "no_home": True,
                                                   "fresh_output_bound_tmp": True, "sanitized_host_environment": False,
                                                   "host_execution": "Existing owner-aware runner; native container uses cleanenv"})
            if "native_rejection" in raw:
                failure = _native_rejection(raw, settings)
                code = failure["integration_return"]
                outcome = reject("reliable_integrations", failure, "COMPLETED",
                    {"native_integration_return": {"value": code, "unit": "1", "valid": False,
                        "reason": "Actual native increment was unreliable/failed; nominal history was not advanced"}})
                outcome["converged"] = False
                save_json(output / "analysis_raw.json", outcome)
                return outcome
            assessment = material.assess(settings, raw)
            passed = all(c["status"] == "PASS" for c in assessment["checks"])
            if [c["code"] for c in assessment["checks"]] != CHECK_CODES:
                raise ValueError("Numerical gate inventory differs from the frozen contract")
            self._check(output)
            # A failed independent numerical comparison does not establish
            # native nonconvergence. Full actual execution evidence is separate.
            reliable = all(check["status"] == "PASS" for check in assessment["checks"][:6])
            outcome = {"status": "COMPLETED" if passed else "REJECTED", "solver_status": "COMPLETED",
                       "converged": True if reliable else None, "checks": assessment["checks"], "metrics": assessment["metrics"],
                       "pending_validations": assessment["pending_validations"], "provenance": provenance,
                       "raw_result": "simulation/analysis_raw.json", "native_raw": "simulation/native_raw.json",
                       "assessment": assessment, "limitations": list(LIMITATIONS)}
            save_json(output / "analysis_raw.json", outcome)
            return outcome
        except BaseException as exc:
            cleanup = isinstance(exc, execution_control.ExecutionCleanupFailed)
            cancelled = isinstance(exc, execution_control.ExecutionCancelled)
            try:
                save_json(output / "execution_failure.json", {
                    "status": "CLEANUP_PENDING" if cleanup else "CANCELLED" if cancelled else "FAILED_EXECUTION",
                    "type": type(exc).__name__, "message": str(exc), "numerical_verdict": "UNKNOWN",
                    "decision": "NOT_RELEASED", "provenance": provenance,
                    "partial_evidence": "Captured source/build/native histories/logs/scratch retained"})
            except OSError:
                pass
            if cleanup or cancelled or not isinstance(exc, Exception):
                raise
            # No environment values in errors; accumulated identity/partial native artifacts survive.
            message = f"{type(exc).__name__}: {exc}"
            (output / "execution_failure.log").write_text(message + "\n", encoding="utf-8")
            for filename in ("runtime.json", "build_identity.json", "source_attribution.json"):
                try:
                    provenance[filename.removesuffix(".json")] = _strict_json(output / filename)
                except (OSError, ValueError, TypeError):
                    pass
            return reject("viscoelastic_execution", message, "FAILED_EXECUTION")
