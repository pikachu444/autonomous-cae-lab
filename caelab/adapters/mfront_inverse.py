"""Native-response inverse objective over the existing MFront material point.

Numerical candidates and campaign persistence belong to the existing Core
engine. This adapter changes neither the native behavior nor its qualification
checks; the declared target is an explicit synthetic reference.
"""

from copy import deepcopy
import math
from pathlib import Path
import shutil

from plugins.material_point import inverse_reference as domain
from plugins.material_point import reference as material
from ..outcomes import validate_outcome
from ..storage import canonical_hash, save_json
from . import mfront_material as base


PINNED_SIF_SHA256 = "f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64"
ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = [Path(base.__file__).resolve(), base.WORKER.resolve(), Path(material.__file__).resolve(),
                Path(domain.__file__).resolve(), Path(__file__).resolve()]
SOURCE_BYTES = {str(path): path.read_bytes() for path in SOURCE_FILES}
SOURCE_HASHES = {path.relative_to(ROOT).as_posix(): base.sha256(path) for path in SOURCE_FILES}
# Actual installed binary hashes were measured by the clean native08 precursor.
# They are sealed to exactly its SIF bytes, not claimed for another distribution.
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
    version = "1"
    default_metrics = [*base.MFrontMaterialAdapter.default_metrics, domain.METRIC,
                       "normalized_stress_residual", "observed_axial_stress", "target_axial_stress"]
    domain = "material_point"
    physics_domain = "constitutive_material"
    analysis_type = "bounded_synthetic_inverse_prerequisite"
    input_source_files = SOURCE_FILES

    def __init__(self):
        self._base = base.MFrontMaterialAdapter()

    def describe_model(self, settings):
        return domain.model_declaration(settings)

    def describe_inputs(self, settings):
        return domain.describe_inputs(settings)

    def bind_inputs(self, settings, values):
        return domain.bind_inputs(settings, values)

    def input_runtime_identity(self):
        _assert_sources()
        image, digest, runtime = base._runtime_identity()
        if digest != PINNED_SIF_SHA256:
            raise RuntimeError("Inverse prerequisite requires the exact already-verified SIF, not a substituted image")
        executable = Path(runtime).resolve()
        if not executable.is_file():
            raise RuntimeError("Actual Singularity executable/wrapper is unavailable")
        return {"kind": "pinned_mfront_sif", "image_path": str(image), "image_sha256": digest,
                "singularity": {"path": str(executable), "sha256": base.sha256(executable)},
                "sealed_installed_native_binaries": deepcopy(SEALED_NATIVE_BINARIES),
                "binary_inventory_basis": "Actual clean material-point native08 plus identical sealed SIF bytes",
                "behavior_source_sha256": base.SOURCE_SHA256, "compiler_policy": base.COMPILER_POLICY,
                "source_files": deepcopy(SOURCE_HASHES), "upstream_binary_source_commits": "UNKNOWN"}

    def _capture(self, output, settings=None):
        output.mkdir(parents=True, exist_ok=True)
        for key, filename in ((str(Path(domain.__file__).resolve()), "inverse_reference.py"),
                              (str(Path(__file__).resolve()), "mfront_inverse.py")):
            (output / filename).write_bytes(SOURCE_BYTES[key])
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
            if canonical_hash(self.input_runtime_identity()) != canonical_hash(identity):
                raise RuntimeError("SIF/runtime wrapper changed during native inverse evaluation")
            validate_outcome(combined)
            save_json(output / "analysis_raw.json", combined)
            return combined
        except Exception as exc:
            self._capture(output, settings)
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
