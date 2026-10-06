"""One Core API shared by CLI and OpenScience transport."""

from copy import deepcopy
from functools import wraps
from pathlib import Path
import json
import platform
from typing import Any
import zipfile
from filelock import FileLock

from .adapters.fixture_cadquery import FixtureCadQueryAdapter
from .adapters.fixture_assembly_conditions_catalog import AssemblyConditionsCADAdapter
from .adapters.fixture_freecad import FixtureFreeCADAdapter
from .contracts import (AnalysisAdapter, CADAdapter, DOEAdapter, OptimizationAdapter,
                        PDEAdapter, ModelAnalysisAdapter, CapabilityUnavailable, FileRevision)
from . import registration_transaction as registration
from .registry import register_parameter, validate_assignments
from .outcomes import validate_outcome
from .execution_control import ExecutionCancelled, ExecutionCleanupFailed, cancelled_outcome
from .schema import validate as validate_schema
from .storage import (artifact_manifest, canonical_hash, check_artifacts, check_id,
                      load_json, save_json, source_identity, utc_now)
import hashlib


def _registration_guard(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._registration_file_lock:
            registration.assert_no_pending(self.store)
            return method(self, *args, **kwargs)
    return guarded


class Lab:
    def __init__(self, store: str | Path, *, adapters: dict[str, CADAdapter] | None = None,
                 analysis_adapters: dict[str, AnalysisAdapter] | None = None,
                 doe_adapters: dict[str, DOEAdapter] | None = None,
                 optimization_adapters: dict[str, OptimizationAdapter] | None = None,
                 pde_adapters: dict[str, PDEAdapter] | None = None,
                 model_analysis_adapters: dict[str, ModelAnalysisAdapter] | None = None,
                 response_field_adapters: dict[str, Any] | None = None,
                 response_history_adapters: dict[str, Any] | None = None):
        self.store = Path(store).resolve()
        # Readers must not create control files inside immutable library stores.
        # Every cooperating Lab instance uses the same external lock identity.
        lock_root = (Path.home() / ".cache" / "autonomous-cae-lab" / "registration-locks").resolve()
        if lock_root.is_relative_to(self.store) or self.store.is_relative_to(lock_root):
            raise ValueError("REGISTRATION_LOCK_PATH_CONFLICT: store and external lock cache must not overlap")
        lock_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        lock_key = hashlib.sha256(self.store.as_posix().casefold().encode("utf-8")).hexdigest()
        self._registration_file_lock = FileLock(str(lock_root / (lock_key + ".lock")), timeout=30)
        self.adapters = adapters if adapters is not None else {
            FixtureCadQueryAdapter.backend: FixtureCadQueryAdapter(),
            AssemblyConditionsCADAdapter.backend: AssemblyConditionsCADAdapter(),
            FixtureFreeCADAdapter.backend: FixtureFreeCADAdapter(self.store),
        }
        if analysis_adapters is None:
            from .adapters.fixture_calculix import FixtureCalculiXAdapter
            from .adapters.native_structural import NativeStructuralAdapter
            analysis_adapters = {FixtureCalculiXAdapter.backend: FixtureCalculiXAdapter(),
                                 NativeStructuralAdapter.backend: NativeStructuralAdapter()}
        self.analysis_adapters = analysis_adapters
        if response_field_adapters is None:
            from .adapters.assembly_response_fields import AssemblyResponseFieldsAdapter
            from .adapters.pde_response_fields import PDEResponseFieldsAdapter, SUPPORTED_BACKENDS
            response_field_adapters = {AssemblyResponseFieldsAdapter.backend: AssemblyResponseFieldsAdapter()}
            response_field_adapters.update({backend: PDEResponseFieldsAdapter(backend) for backend in SUPPORTED_BACKENDS})
        self.response_field_adapters = response_field_adapters
        if response_history_adapters is None:
            from .adapters.openradioss_history import OpenRadiossHistoryAdapter
            response_history_adapters = {OpenRadiossHistoryAdapter.backend: OpenRadiossHistoryAdapter()}
        self.response_history_adapters = response_history_adapters
        if doe_adapters is None:
            from .optimizers.scipy_lhs import ScipyLatinHypercube
            doe_adapters = {ScipyLatinHypercube.engine: ScipyLatinHypercube()}
        self.doe_adapters = doe_adapters
        if optimization_adapters is None:
            from .optimizers.scipy_de import ScipyDifferentialEvolution
            optimization_adapters = {ScipyDifferentialEvolution.engine: ScipyDifferentialEvolution()}
        self.optimization_adapters = optimization_adapters
        if pde_adapters is None:
            from .adapters.fenicsx_pde import FenicsxPDEAdapter
            from .adapters.fenicsx_nonlinear import FenicsxNonlinearPDEAdapter
            from .adapters.fenicsx_rectangle import FenicsxRectanglePDEAdapter
            from .adapters.fenicsx_transient import FenicsxTransientPDEAdapter
            from .adapters.fenicsx_vector import FenicsxVectorPDEAdapter
            from .adapters.fenicsx_coupled import FenicsxCoupledPDEAdapter
            from .adapters.fenicsx_imported import FenicsxImportedPDEAdapter
            pde_adapters = {adapter.backend: adapter() for adapter in
                            (FenicsxPDEAdapter, FenicsxNonlinearPDEAdapter, FenicsxRectanglePDEAdapter,
                             FenicsxTransientPDEAdapter, FenicsxVectorPDEAdapter, FenicsxCoupledPDEAdapter,
                             FenicsxImportedPDEAdapter)}
        self.pde_adapters = pde_adapters
        if model_analysis_adapters is None:
            from .adapters.codeaster_elasticity import CodeAsterElasticityAdapter
            from .adapters.codeaster_plasticity import CodeAsterPlasticityAdapter
            from .adapters.codeaster_geometric import CodeAsterGeometricAdapter
            from .adapters.codeaster_contact import CodeAsterContactPatchAdapter
            from .adapters.structural_family_calculix import StructuralFamilyCalculiXAdapter
            from .adapters.structural_family_codeaster import StructuralFamilyCodeAsterAdapter
            from .adapters.mfront_material import MFrontMaterialAdapter
            from .adapters.mfront_inverse import MFrontInverseAdapter
            from .adapters.mfront_hyperelastic import MFrontHyperelasticAdapter
            from .adapters.mfront_viscoelastic import MFrontViscoelasticAdapter
            from .adapters.openradioss import OpenRadiossAdapter
            model_analysis_adapters = {
                adapter.backend: adapter() for adapter in (
                    CodeAsterElasticityAdapter, CodeAsterPlasticityAdapter, CodeAsterGeometricAdapter,
                    CodeAsterContactPatchAdapter,
                    StructuralFamilyCalculiXAdapter, StructuralFamilyCodeAsterAdapter,
                    MFrontMaterialAdapter, MFrontInverseAdapter, MFrontHyperelasticAdapter,
                    MFrontViscoelasticAdapter, OpenRadiossAdapter)
            }
        self.model_analysis_adapters = model_analysis_adapters

    @_registration_guard
    def create_native_model(self, *, template: str = "roller_support") -> dict[str, Any]:
        return self._adapter("fixture.freecad").create_sample(template)

    @_registration_guard
    def import_native_model(self, source: str | Path) -> dict[str, Any]:
        return self._adapter("fixture.freecad").import_document(Path(source))

    @_registration_guard
    def inspect_native_model(self, model: str) -> dict[str, Any]:
        return self._adapter("fixture.freecad").inspect_model(model)

    @_registration_guard
    def select_native_final(self, model: str, final: str) -> dict[str, Any]:
        return self._adapter("fixture.freecad").select_final(model, final)

    def _adapter(self, backend: str) -> CADAdapter:
        if backend not in self.adapters:
            raise CapabilityUnavailable(f"No executable adapter for {backend}")
        return self.adapters[backend]

    def create_study(self, study_id: str, name: str, research_question: str,
                     hypothesis: str, objective: str) -> dict[str, Any]:
        folder = self.store / "studies" / check_id(study_id)
        folder.mkdir(parents=True, exist_ok=False)
        study = {"schema_version": "1.0", "id": study_id, "name": name,
                 "research_question": research_question, "hypothesis": hypothesis,
                 "objective": objective, "created_utc": utc_now()}
        if not all(isinstance(v, str) and v.strip() for v in
                   (name, research_question, hypothesis, objective)):
            folder.rmdir()
            raise ValueError("Study fields must be nonempty text")
        save_json(folder / "study.json", study)
        initial_registry = {"revision": 0, "entries": []}
        save_json(folder / "parameters.json", initial_registry)
        save_json(folder / "registry_history/0000.json", initial_registry)
        return study

    def inspect_study(self, study_id: str) -> dict[str, Any]:
        return load_json(self.store / "studies" / check_id(study_id) / "study.json")

    def save_response_comparison(self, comparison_id: str, experiment_id: str, purpose: str,
                                 hypothesis: str, observation: dict, response: dict) -> dict[str, Any]:
        from .response_comparison import save_comparison
        return save_comparison(self, comparison_id=comparison_id, experiment_id=experiment_id,
                               purpose=purpose, hypothesis=hypothesis, observation=observation, response=response)

    def inspect_response_comparison(self, comparison_id: str) -> dict[str, Any]:
        from .response_comparison import inspect_comparison
        return inspect_comparison(self, comparison_id)

    def response_comparisons(self, study_id: str) -> list[dict[str, Any]]:
        from .response_comparison import list_comparisons
        return list_comparisons(self, study_id)

    def response_histories(self, experiment_id: str) -> dict[str, Any]:
        from .response_history import history_catalog
        return history_catalog(self, experiment_id)

    def describe_analysis_conditions(self, experiment_id: str) -> dict[str, Any]:
        from .analysis_conditions import describe
        return describe(self, experiment_id)

    def response_fields(self, experiment_id: str) -> dict[str, Any]:
        from .response_field import display_catalog
        return display_catalog(self, check_id(experiment_id))

    def save_analysis_conditions(self, *, conditions_id: str, experiment_id: str,
                                 cad_revision: str, catalog_revision: str,
                                 backend: str, declaration: dict) -> dict[str, Any]:
        from .analysis_conditions import save
        return save(self, conditions_id=conditions_id, experiment_id=experiment_id,
                    cad_revision=cad_revision, catalog_revision=catalog_revision,
                    backend=backend, declaration=declaration)

    def inspect_analysis_conditions(self, conditions_id: str) -> dict[str, Any]:
        from .analysis_conditions import inspect
        return inspect(self, conditions_id)

    def list_analysis_conditions(self, experiment_id: str) -> list[dict[str, Any]]:
        from .analysis_conditions import list_records
        return list_records(self, experiment_id)

    def discover_condition_parameters(self, conditions_id: str) -> dict:
        from .condition_parameters import describe
        return describe(self, conditions_id)

    def register_condition_parameter(self, **arguments) -> dict:
        from .condition_parameters import register
        return register(self, **arguments)

    def plan_condition_optimization(self, **arguments) -> dict:
        from .optimization import plan_condition_optimization
        return plan_condition_optimization(self, **arguments)

    @_registration_guard
    def registry(self, study_id: str) -> dict[str, Any]:
        return load_json(self.store / "studies" / check_id(study_id) / "parameters.json")

    @_registration_guard
    def discover_parameters(self, backend: str, model: str) -> list[dict[str, Any]]:
        return [deepcopy(candidate.__dict__) for candidate in self._adapter(backend).discover(model)]

    def discover_model_parameters(self, backend: str, settings: dict) -> list[dict]:
        from .model_parameters import describe
        return [deepcopy(candidate.__dict__) for candidate in describe(self, backend, settings)["candidates"]]

    def register_model_parameter(self, study_id: str, backend: str, settings: dict,
                                 input_id: str, parameter_id: str, display_name: str,
                                 lower: float, upper: float, mode: str = "free") -> dict:
        from .model_parameters import describe, probe
        self.inspect_study(study_id)
        description = describe(self, backend, settings)
        matches = [item for item in description["candidates"] if item.native["path"] == input_id]
        if len(matches) != 1:
            raise ValueError("Selected model input was not advertised")
        candidate = matches[0]
        effect = probe(description["adapter"], settings, input_id, lower, upper)
        registry_path = self.store / "studies" / check_id(study_id) / "parameters.json"
        with FileLock(str(registry_path) + ".lock", timeout=30), self._registration_file_lock:
            registration.assert_no_pending(self.store)
            registry = load_json(registry_path)
            entry = register_parameter(registry["entries"], candidate, parameter_id=parameter_id,
                                       display_name=display_name, lower=lower, upper=upper,
                                       mode=mode, effect=effect, effect_kind="model_input")
            entry["model_template_revision"] = description["revision"]
            entry["input_descriptor_sha256"] = canonical_hash(description["descriptors"])
            registry["entries"].append(entry)
            registry["revision"] += 1
            save_json(registry_path, registry)
            save_json(registry_path.parent / "registry_history" / f"{registry['revision']:04d}.json", registry)
            return entry

    def register_parameter(self, study_id: str, backend: str, model: str, native_path: str,
                           parameter_id: str, display_name: str, lower: float, upper: float,
                           mode: str = "free", kind: str = "continuous",
                           dependencies: list[str] | None = None) -> dict[str, Any]:
        registry_path = self.store / "studies" / check_id(study_id) / "parameters.json"
        # Preserve the existing campaign lock order: study lock, then store lock.
        with FileLock(str(registry_path) + ".lock", timeout=30), self._registration_file_lock:
            registration.assert_no_pending(self.store)
            original = registry_path.read_bytes()
            registry = json.loads(original)
            adapter = self._adapter(backend)
            discovered = adapter.discover(model)
            current = {tuple(sorted(c.native.items())): c for c in discovered}
            prior = [p for p in registry["entries"] if p["native"]["backend"] == backend and
                     p["native"]["document"] == adapter.document_id(model)]
            if any(tuple(sorted(p["native"].items())) not in current or
                   p["source_sha256"] != current[tuple(sorted(p["native"].items()))].source_sha256
                   for p in prior):
                raise ValueError("CAD source changed; refresh the registry before adding parameters")
            candidates = [c for c in discovered if c.native["path"] == native_path]
            if len(candidates) != 1:
                raise ValueError("Selected native CAD parameter was not discovered")
            candidate = candidates[0]
            effect = adapter.probe_effect(model, candidate, lower, upper)
            entry = register_parameter(registry["entries"], candidate, parameter_id=parameter_id,
                                       display_name=display_name, lower=lower, upper=upper,
                                       mode=mode, kind=kind, dependencies=dependencies,
                                       effect=effect)
            prepare_bind = getattr(adapter, "prepare_bind", None)
            if getattr(adapter, "bind", None) and not prepare_bind:
                raise CapabilityUnavailable("Native registration requires private prepare_bind revisions")
            transaction = registration.RegistrationTransaction(self.store, study_id)
            try:
                if prepare_bind:
                    revision = prepare_bind(model, candidate, parameter_id, display_name, lower, upper,
                                            transaction.work / "native")
                    if not isinstance(revision, FileRevision) or revision.before_sha256 != candidate.source_sha256:
                        raise ValueError("REGISTRATION_IMAGE_INVALID: adapter revision does not match discovered source")
                    transaction.add(revision.target, revision.prepared, revision.before_sha256, revision.after_sha256)
                    entry["source_sha256"] = revision.after_sha256
                    for existing in prior:
                        existing["source_sha256"] = revision.after_sha256
                registry["entries"].append(entry)
                registry["revision"] += 1
                self._publish_registry(transaction, registry_path, registry, registration.digest(original))
            except BaseException as error:
                transaction.abort_preparation(type(error).__name__)
                raise
            return entry

    def _publish_registry(self, transaction, path: Path, value: dict, original_sha: str) -> None:
        prepared = transaction.work / "parameters.json"
        prepared.write_bytes(registration.json_bytes(value))
        after_sha = registration.file_hash(prepared)
        history = path.parent / "registry_history" / f"{value['revision']:04d}.json"
        transaction.add(history, prepared, None, after_sha)
        transaction.add(path, prepared, original_sha, after_sha)
        transaction.prepare()
        transaction.commit()

    def recover_registration(self, study_id: str) -> dict[str, Any]:
        """Restore pending uncommitted CAD registry revisions; conflicts stay blocked."""
        self.inspect_study(study_id)
        path = self.store / "studies" / check_id(study_id) / "parameters.json"
        with FileLock(str(path) + ".lock", timeout=30), self._registration_file_lock:
            recovered = registration.recover(self.store, study_id)
        return {"study_id": study_id, "transactions": recovered, "status": "RECOVERED" if recovered else "NO_PENDING_TRANSACTION"}

    def refresh_registry(self, study_id: str, backend: str, model: str) -> dict[str, Any]:
        """Rebase existing mappings after an engineer edits the native CAD source."""
        registry_path = self.store / "studies" / check_id(study_id) / "parameters.json"
        with FileLock(str(registry_path) + ".lock", timeout=30), self._registration_file_lock:
            registration.assert_no_pending(self.store)
            original = registry_path.read_bytes()
            registry = json.loads(original)
            adapter = self._adapter(backend)
            candidates = {tuple(sorted(c.native.items())): c for c in adapter.discover(model)}
            refreshed = deepcopy(registry)
            touched = 0
            for p in refreshed["entries"]:
                if p["native"]["backend"] != backend or p["native"]["document"] != adapter.document_id(model):
                    continue
                key = tuple(sorted(p["native"].items()))
                if key not in candidates:
                    raise ValueError("Native parameter is missing: " + p["parameter_id"])
                c = candidates[key]
                if not p["lower_bound"] <= c.value <= p["upper_bound"]:
                    raise ValueError("New CAD default lies outside registered bounds: " + p["parameter_id"])
                effect = adapter.probe_effect(model, c, p["lower_bound"], p["upper_bound"])
                if effect.get("status") != "PASS":
                    raise ValueError("Changed CAD parameter has no verified shape effect: " + p["parameter_id"])
                p.update(current_value=c.value, default_value=c.value,
                         source_sha256=c.source_sha256, geometry_effect=effect)
                touched += 1
            if not touched:
                raise ValueError("No registry entries map to this model")
            refreshed["revision"] += 1
            transaction = registration.RegistrationTransaction(self.store, study_id)
            try:
                self._publish_registry(transaction, registry_path, refreshed, registration.digest(original))
            except BaseException as error:
                transaction.abort_preparation(type(error).__name__)
                raise
            return refreshed

    @_registration_guard
    def run_experiment(self, *, study_id: str, experiment_id: str, backend: str,
                       model: str, values: dict[str, Any],
                       hypothesis_id: str | None = None,
                       settings: dict[str, Any] | None = None,
                       campaign_id: str | None = None,
                       objectives: list[dict] | None = None,
                       constraints: list[dict] | None = None) -> dict[str, Any]:
        check_id(experiment_id)
        if campaign_id is not None:
            check_id(campaign_id)
        study = self.inspect_study(study_id)
        registry = self.registry(study_id)
        adapter = self._adapter(backend)
        if not isinstance(values, dict) or (settings is not None and not isinstance(settings, dict)):
            raise ValueError("Values/settings must be mappings")
        # A source edit invalidates the registry's native mappings and effect probe.
        discovered = {tuple(sorted(c.native.items())): c for c in adapter.discover(model)}
        selected = [p for p in registry["entries"]
                    if p["native"]["backend"] == backend and
                    p["native"]["document"] == adapter.document_id(model)]
        stale = [p["parameter_id"] for p in selected
                 if
                 tuple(sorted(p["native"].items())) not in discovered or
                 p["source_sha256"] != discovered[tuple(sorted(p["native"].items()))].source_sha256]
        if stale:
            raise ValueError("CAD source or backend changed; refresh registry: " + ", ".join(stale))

        folder = self.store / "experiments" / experiment_id
        proposal = {"schema_version": "1.0", "id": experiment_id,
                    "study_id": study_id, "hypothesis_id": hypothesis_id or study_id + "-H1",
                    "domain": adapter.domain, "physics": {"domain": adapter.physics_domain,
                                                          "analysis_type": adapter.analysis_type, "backend": None},
                    "model": {"geometry": {"backend": backend, "source": model}},
                    "parameters": deepcopy(values), "outputs": {"metrics": adapter.default_metrics},
                    "objectives": deepcopy(objectives or []),
                    "constraints": deepcopy(constraints or []), "validation_requirements": [],
                    "execution": deepcopy(settings or {}), "registry_revision": registry["revision"]}
        if campaign_id is not None:
            proposal["campaign_id"] = campaign_id
        validate_schema("experiment", proposal)
        canonical_hash(proposal)  # Reject non-JSON values before reserving an experiment ID.
        folder.mkdir(parents=True, exist_ok=False)
        save_json(folder / "proposal.json", proposal)
        save_json(folder / "registry_snapshot.json", registry)
        checks = validate_assignments(selected, values)
        failed = any(c["status"] == "FAIL" for c in checks)
        outcome = None
        execution_error = False
        execution_cancelled = False
        if not failed:
            native_values = {p["native"]["path"]: values.get(p["parameter_id"], p["current_value"])
                             for p in selected}
            try:
                preflight = getattr(adapter, "preflight_effects", None)
                if preflight:
                    for check in preflight(model, native_values):
                        checks.append({**check, "validator": backend,
                                       "evidence_artifact": "proposal.json"})
                if not any(c["status"] == "FAIL" for c in checks):
                    outcome = adapter.regenerate(model, native_values, folder / "cad")
                    checks.extend({**check, "validator": backend} for check in outcome.checks)
                    if outcome.decision == "REJECTED" and not any(c["status"] == "FAIL" for c in checks):
                        checks.append({"code": "adapter_rejected", "status": "FAIL",
                                       "observed": "Backend rejected the design without a detailed check",
                                       "validator": backend})
                    if outcome.decision == "REVIEW_REQUIRED" and not outcome.generated:
                        execution_error = True
                        checks.append({"code": "cad_missing", "status": "FAIL",
                                       "observed": "Backend reported review but produced no valid CAD",
                                       "validator": backend})
                    cad_folder = folder / "cad"
                    if cad_folder.is_dir():
                        with zipfile.ZipFile(cad_folder / "bundle.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
                            for item in sorted(cad_folder.iterdir()):
                                if item.is_file() and item.name != "bundle.zip":
                                    bundle.write(item, item.name)
            except ExecutionCleanupFailed:
                raise
            except ExecutionCancelled as exc:
                execution_cancelled = True
                observed = cancelled_outcome(folder, backend, exc, 'cad')
                checks.extend({**check, 'evidence_artifact': observed['raw_result']}
                              for check in observed['checks'])
            except Exception as exc:
                execution_error = True
                checks.append({"code": "cad_execution", "status": "FAIL",
                               "observed": f"{type(exc).__name__}: {exc}"})

        proposal_revision = canonical_hash({"model": model, "values": values, "registry": registry})
        revision = (canonical_hash({"source": outcome.native_revision, "proposal": proposal_revision})
                    if outcome and outcome.generated else None)
        evidence = []
        validations = []
        for index, check in enumerate(checks, 1):
            evidence_id = f"EV-{experiment_id}-{index:03d}"
            validator = check.get("validator", "caelab.core")
            evidence.append({"id": evidence_id, "type": "script_metric",
                             "method": check["code"], "observation": deepcopy(check),
                             "source": validator,
                             "artifact": check.get("evidence_artifact", outcome.raw_result
                                                   if outcome and validator == backend else "proposal.json"),
                             "recorded_utc": utc_now()})
            validations.append({"type": check["code"], "validator": validator,
                                "status": check["status"], "blocking": True,
                                "threshold": check.get("limit"), "expected_range": check.get("expected"),
                                "evidence_ids": [evidence_id], "cad_revision": revision,
                                "experiment_id": experiment_id, "solver_run_id": None,
                                "timestamp": utc_now(), "notes": check.get("detail")})
        pending_types = list(outcome.pending_validations if outcome else [])
        if execution_cancelled:
            pending_types = list(dict.fromkeys([*pending_types, 'model_qualification', 'physical_validation']))
        for kind in pending_types:
            validations.append({"type": kind, "validator": "not_executed", "status": "UNKNOWN",
                                "blocking": True, "threshold": None, "expected_range": None,
                                "evidence_ids": [], "cad_revision": revision, "experiment_id": experiment_id,
                                "solver_run_id": None, "timestamp": utc_now(),
                                "notes": "Evidence required before engineering release"})

        rejected = any(v["status"] == "FAIL" for v in validations)
        execution_status = "CANCELLED" if execution_cancelled else "FAILED_EXECUTION" if execution_error else (
            "REJECTED" if rejected else "COMPLETED_REVIEW_REQUIRED")
        if not execution_cancelled and outcome and outcome.decision not in ("REVIEW_REQUIRED", "REJECTED"):
            execution_status = "FAILED_EXECUTION"
        artifacts = artifact_manifest(folder, revision=revision or proposal_revision)
        # The artifact reference in evidence is relative to the experiment root.
        for item in evidence:
            if item["artifact"] == "cad/result.json" and not any(a["path"] == item["artifact"] for a in artifacts):
                item["artifact"] = "proposal.json"
        source_commit = getattr(adapter, "source_commit", lambda: "unknown")()
        result = {"schema_version": "1.0", "experiment_id": experiment_id,
                  "study": {"id": study_id, "hypothesis": study["hypothesis"],
                            "hypothesis_id": proposal["hypothesis_id"]},
                  "status": execution_status, "decision": "NOT_RELEASED",
                  "solver_status": "NOT_RUN", "converged": None,
                  "cad_revision": revision, "proposal_revision": proposal_revision,
                  "registry_revision": registry["revision"],
                  "input_parameters": deepcopy(values),
                  "metrics": outcome.metrics if outcome else {},
                  "validations": validations, "evidence": evidence, "artifacts": artifacts,
                  "provenance": {"proposal_sha256": canonical_hash(proposal),
                                 "registry_sha256": canonical_hash(registry),
                                 "cad_source_sha256": outcome.source_sha256 if outcome else None,
                                 "source_commit": source_commit,
                                 "adapter": backend, "adapter_version": adapter.version,
                                 "python": platform.python_version(), "platform": platform.platform(),
                                 "execution_settings": deepcopy(settings or {}),
                                 "random_seed": (settings or {}).get("random_seed"),
                                 "material": None, "mesh": None, "solver": None,
                                 "created_utc": utc_now(), **source_identity(Path(__file__).resolve().parents[1])}}
        if campaign_id is not None:
            result["campaign_id"] = campaign_id
        thread = {"hypothesis": proposal["hypothesis_id"], "study": study_id,
                  "experiment": experiment_id, "registry_revision": registry["revision"],
                  "cad_revision": revision,
                  "mesh": None, "solver_deck": None, "run": None,
                  "result": "result.json", "evidence": [e["id"] for e in evidence],
                  "decision": result["decision"]}
        if campaign_id is not None:
            thread["campaign"] = campaign_id
        validate_schema("result", result)
        save_json(folder / "result.json", result)
        save_json(folder / "thread.json", thread)
        ledger = self.store / "ledger" / f"{experiment_id}.json"
        save_json(ledger, {
            "experiment_id": experiment_id,
            "result_sha256": hashlib.sha256((folder / "result.json").read_bytes()).hexdigest(),
            "thread_sha256": hashlib.sha256((folder / "thread.json").read_bytes()).hexdigest(),
            "created_utc": utc_now(),
        })
        return result

    def run_analysis(self, *, parent_experiment_id: str, experiment_id: str,
                     backend: str, settings: dict[str, Any] | None = None,
                     conditions_id: str | None = None) -> dict[str, Any]:
        """Create a child solver run on a verified, immutable CAD revision."""
        check_id(experiment_id)
        parent_id = check_id(parent_experiment_id)
        if parent_id == experiment_id:
            raise ValueError("An analysis must have a distinct experiment ID")
        conditions_record = conditions_reference = conditions_raw = None
        if conditions_id is not None:
            if settings is not None:
                raise ValueError("Saved conditions and competing settings cannot both define an analysis")
            from .analysis_conditions import execution
            conditions_record, settings, conditions_reference, conditions_raw = execution(
                self, parent_id, backend, conditions_id)
        if not isinstance(settings, dict):
            raise ValueError("Analysis settings must be a mapping")
        if backend not in self.analysis_adapters:
            raise CapabilityUnavailable(f"No executable analysis adapter for {backend}")
        adapter = self.analysis_adapters[backend]
        parent_root = self.store / "experiments" / parent_id
        parent = self.inspect_experiment(parent_id)
        parent_proposal = load_json(parent_root / "proposal.json")
        if (parent_proposal["physics"]["analysis_type"] != "cad_preflight" or
                parent["status"] != "COMPLETED_REVIEW_REQUIRED" or not parent["cad_revision"]):
            raise ValueError("Analysis requires a completed, verified CAD experiment")
        registry = load_json(parent_root / "registry_snapshot.json")
        if canonical_hash(registry) != parent["provenance"]["registry_sha256"]:
            raise ValueError("Parent parameter registry snapshot hash mismatch")

        proposal = {"schema_version": "1.0", "id": experiment_id,
                    "study_id": parent["study"]["id"],
                    "parent_experiment_id": parent_id,
                    "hypothesis_id": parent["study"]["hypothesis_id"],
                    "domain": parent_proposal["domain"],
                    "physics": {"domain": parent_proposal["physics"]["domain"],
                                "analysis_type": adapter.analysis_type, "backend": backend},
                    "model": {"geometry": {"source_experiment_id": parent_id,
                                           "cad_revision": parent["cad_revision"]},
                              "mesh": deepcopy(settings.get("mesh"))},
                    "parameters": deepcopy(parent["input_parameters"]),
                    "loads": [deepcopy(settings["load"])] if "load" in settings else [],
                    "outputs": {"metrics": adapter.default_metrics},
                    "objectives": deepcopy(parent_proposal["objectives"]),
                    "constraints": deepcopy(parent_proposal["constraints"]), "validation_requirements": [],
                    "execution": deepcopy(settings),
                    "registry_revision": parent["registry_revision"]}
        if "campaign_id" in parent:
            proposal["campaign_id"] = parent["campaign_id"]
        if "material" in settings:
            proposal["model"]["materials"] = [deepcopy(settings["material"])]
        if conditions_record is not None:
            declaration = conditions_record["request"]["declaration"]
            if declaration['analysis_type'] != adapter.analysis_type:
                raise ValueError('Declared analysis type differs from the admitted adapter physics')
            proposal["model"]["materials"] = deepcopy(declaration["materials"])
            proposal["model"]["coordinate_systems"] = deepcopy(conditions_record["catalog"]["coordinate_systems"])
            proposal["model"]["contact"] = deepcopy(declaration["contact"].get("pairs", []))
            proposal["model"]["contact_declaration"] = deepcopy(declaration["contact"])
            proposal["model"]["conditions_mesh"] = deepcopy(declaration["mesh"])
            proposal["loads"] = deepcopy(declaration["loads"])
            proposal["boundary_conditions"] = deepcopy(declaration["boundary_conditions"])
            proposal["provenance"] = {"analysis_conditions": deepcopy(conditions_reference)}
        validate_schema("experiment", proposal)
        canonical_hash(proposal)

        folder = self.store / "experiments" / experiment_id
        parent_result_hash = hashlib.sha256((parent_root / "result.json").read_bytes()).hexdigest()
        if conditions_record is not None:
            from .analysis_conditions import _path
            folder = _path(self, f"experiments/{experiment_id}")
            _path(self, f"ledger/{experiment_id}.json")
            if (conditions_record["source"]["result_sha256"] != parent_result_hash
                    or conditions_record["source"]["cad_revision"] != parent["cad_revision"]):
                raise ValueError("Conditions CAD source changed before native execution")
        folder.mkdir(parents=True, exist_ok=False)
        save_json(folder / "proposal.json", proposal)
        save_json(folder / "registry_snapshot.json", registry)
        if conditions_record is not None:
            (folder / "analysis_conditions.json").write_bytes(conditions_raw)
        save_json(folder / "parent_reference.json", {
            "experiment_id": parent_id, "cad_revision": parent["cad_revision"],
            "result_sha256": parent_result_hash})

        execution_error = False
        execution_cancelled = False
        outcome = None
        try:
            outcome = adapter.solve(parent, parent_root, folder / "simulation", deepcopy(settings))
            validate_outcome(outcome)
            execution_error = outcome["solver_status"] == "FAILED_EXECUTION"
        except ExecutionCleanupFailed:
            raise
        except ExecutionCancelled as exc:
            execution_cancelled = True
            outcome = cancelled_outcome(folder, backend, exc, 'analysis')
        except Exception as exc:
            execution_error = True
            outcome = {"status": "REJECTED", "checks": [{"code": "analysis_execution",
                       "status": "FAIL", "observed": f"{type(exc).__name__}: {exc}"}],
                       "metrics": {}, "solver_status": "FAILED_EXECUTION", "converged": None,
                       "pending_validations": [], "provenance": {}, "raw_result": None}
        checks = outcome["checks"]
        if not execution_cancelled and outcome["status"] == "REJECTED" and not any(c["status"] == "FAIL" for c in checks):
            checks.append({"code": "adapter_rejected", "status": "FAIL",
                           "observed": "Analysis adapter rejected without a detailed failure"})
        raw_result = outcome.get("raw_result")
        artifact_path = Path(raw_result) if isinstance(raw_result, str) else None
        evidence_artifact = (raw_result if artifact_path and not artifact_path.is_absolute() and
                             ".." not in artifact_path.parts and
                             (folder / artifact_path).resolve().is_relative_to(folder.resolve()) and
                             (folder / artifact_path).is_file() else "proposal.json")
        evidence, validations = [], []
        for index, check in enumerate(checks, 1):
            evidence_id = f"EV-{experiment_id}-{index:03d}"
            evidence.append({"id": evidence_id, "type": "script_metric",
                             "method": check["code"], "observation": deepcopy(check),
                             "source": backend, "artifact": evidence_artifact,
                             "recorded_utc": utc_now()})
            validations.append({"type": check["code"], "validator": backend,
                                "status": check["status"], "blocking": True,
                                "threshold": check.get("limit"),
                                "expected_range": check.get("expected"),
                                "evidence_ids": [evidence_id],
                                "cad_revision": parent["cad_revision"],
                                "experiment_id": experiment_id,
                                "solver_run_id": experiment_id, "timestamp": utc_now(),
                                "notes": check.get("detail")})
        for kind in outcome.get("pending_validations", []):
            validations.append({"type": kind, "validator": "not_executed",
                                "status": "UNKNOWN", "blocking": True,
                                "threshold": None, "expected_range": None, "evidence_ids": [],
                                "cad_revision": parent["cad_revision"],
                                "experiment_id": experiment_id, "solver_run_id": experiment_id,
                                "timestamp": utc_now(),
                                "notes": "Separate engineering evidence required"})
        # A child solver run cannot erase unresolved CAD/engineering gates.
        # Keep the parent record immutable and link back to it for detail.
        observed_types = {v["type"] for v in validations}
        for prior in parent["validations"]:
            if prior["status"] != "UNKNOWN" or prior["type"] in observed_types:
                continue
            validations.append({"type": prior["type"], "validator": "inherited_parent",
                                "status": "UNKNOWN", "blocking": prior["blocking"],
                                "threshold": prior.get("threshold"),
                                "expected_range": prior.get("expected_range"),
                                "evidence_ids": [], "cad_revision": parent["cad_revision"],
                                "experiment_id": experiment_id, "solver_run_id": experiment_id,
                                "timestamp": utc_now(),
                                "notes": f"Unresolved in parent experiment {parent_id}"})
            observed_types.add(prior["type"])
        status = ("CANCELLED" if execution_cancelled else "FAILED_EXECUTION" if execution_error else
                  "REJECTED" if outcome["status"] == "REJECTED" or
                  any(c["status"] == "FAIL" for c in checks) else
                  "COMPLETED_REVIEW_REQUIRED")
        artifacts = artifact_manifest(folder, revision=parent["cad_revision"])
        result = {"schema_version": "1.0", "experiment_id": experiment_id,
                  "parent_experiment_id": parent_id, "study": deepcopy(parent["study"]),
                  "status": status, "decision": "NOT_RELEASED",
                  "solver_status": outcome.get("solver_status", "NOT_RUN"),
                  "converged": outcome.get("converged"),
                  "cad_revision": parent["cad_revision"],
                  "proposal_revision": canonical_hash(proposal),
                  "registry_revision": parent["registry_revision"],
                  "input_parameters": deepcopy(parent["input_parameters"]),
                  "metrics": outcome["metrics"], "validations": validations,
                  "evidence": evidence, "artifacts": artifacts,
                  "provenance": {"proposal_sha256": canonical_hash(proposal),
                                 "registry_sha256": canonical_hash(registry),
                                 "parent_experiment_id": parent_id,
                                 "parent_result_sha256": parent_result_hash,
                                 "cad_source_sha256": parent["provenance"].get("cad_source_sha256"),
                                 "source_commit": parent["provenance"].get("source_commit"),
                                 "adapter": backend, "adapter_version": adapter.version,
                                 "mesh": outcome["provenance"].get("mesh"),
                                 "material": deepcopy(settings.get("material")),
                                 "solver": {"backend": backend,
                                            "status": outcome.get("solver_status"),
                                            "versions": outcome["provenance"].get("versions")},
                                 "adapter_details": deepcopy(outcome["provenance"]),
                                 "execution_settings": deepcopy(settings),
                                 "created_utc": utc_now(),
                                 **source_identity(Path(__file__).resolve().parents[1])}}
        if "campaign_id" in parent:
            result["campaign_id"] = parent["campaign_id"]
        thread = {"hypothesis": proposal["hypothesis_id"],
                  "study": proposal["study_id"], "experiment": experiment_id,
                  "parent_experiment": parent_id,
                  "parent_result_sha256": parent_result_hash,
                  "registry_revision": parent["registry_revision"],
                  "cad_revision": parent["cad_revision"],
                  "mesh": outcome["provenance"].get("mesh"),
                  "solver_deck": outcome["provenance"].get("solver_deck"),
                  "run": experiment_id, "result": "result.json",
                  "evidence": [e["id"] for e in evidence], "decision": result["decision"]}
        if conditions_reference is not None:
            result["provenance"]["analysis_conditions"] = deepcopy(conditions_reference)
            thread["analysis_conditions"] = deepcopy(conditions_reference)
        if "campaign_id" in parent:
            thread["campaign"] = parent["campaign_id"]
        validate_schema("result", result)
        save_json(folder / "result.json", result)
        save_json(folder / "thread.json", thread)
        save_json(self.store / "ledger" / f"{experiment_id}.json", {
            "experiment_id": experiment_id,
            "result_sha256": hashlib.sha256((folder / "result.json").read_bytes()).hexdigest(),
            "thread_sha256": hashlib.sha256((folder / "thread.json").read_bytes()).hexdigest(),
            "created_utc": utc_now()})
        return result

    def inspect_experiment(self, experiment_id: str, *, verify: bool = True) -> dict[str, Any]:
        folder = self.store / "experiments" / check_id(experiment_id)
        result = load_json(folder / "result.json")
        if verify:
            ledger = load_json(self.store / "ledger" / f"{experiment_id}.json")
            for name in ("result", "thread"):
                actual = hashlib.sha256((folder / f"{name}.json").read_bytes()).hexdigest()
                if actual != ledger[f"{name}_sha256"]:
                    raise ValueError(f"{name}.json hash mismatch")
            corrupt = check_artifacts(folder, result["artifacts"])
            if corrupt:
                raise ValueError("Artifact hash mismatch: " + ", ".join(corrupt))
            if result["provenance"].get("analysis_conditions") is not None:
                from .analysis_conditions import verify_child
                verify_child(folder, result)
            if result.get("model_revision") is not None:
                proposal = load_json(folder / "proposal.json")
                thread = load_json(folder / "thread.json")
                if (proposal.get("model_revision") != result["model_revision"] or
                        thread.get("model_revision") != result["model_revision"]):
                    raise ValueError("Declared model revision mismatch")
            parent_id = result.get("parent_experiment_id")
            if parent_id:
                if parent_id == experiment_id:
                    raise ValueError("Analysis parent cannot be its own experiment")
                parent = self.inspect_experiment(check_id(parent_id))
                parent_file = self.store / "experiments" / parent_id / "result.json"
                if (hashlib.sha256(parent_file.read_bytes()).hexdigest() !=
                        result["provenance"]["parent_result_sha256"] or
                        parent["cad_revision"] != result["cad_revision"]):
                    raise ValueError("Parent CAD revision or result hash mismatch")
        return result

    def _research_result_context(self, result: dict, *, compact_conditions=False) -> dict:
        from .research_context import comparison_context, analysis_conditions_context
        context = comparison_context(self, result)
        conditions = (analysis_conditions_context(self, result, compact=True) if compact_conditions
                      else analysis_conditions_context(self, result))
        backend = result['provenance'].get('adapter')
        adapter = self.analysis_adapters.get(backend)
        semantics_hook = getattr(adapter, 'research_metric_semantics', None)
        if not callable(semantics_hook):
            semantics_hook = getattr(self.response_field_adapters.get(backend), 'research_metric_semantics', None)
        semantics = semantics_hook(result) if callable(semantics_hook) else None
        return {**({"comparison_context": context} if context is not None else {}),
                **({'analysis_conditions_context': conditions} if conditions is not None else {}),
                **({'metric_semantics': semantics} if semantics else {})}

    def research_inspection(self, experiment_id: str) -> dict[str, Any]:
        """Verified full read plus non-persisted research response definitions.

        inspect_experiment remains the unchanged canonical stored result reader.
        This transport response must not replace or be hashed as result.json.
        """
        result = self.inspect_experiment(experiment_id)
        return {**result, **self._research_result_context(result)}

    def research_summary(self, experiment_id: str) -> dict[str, Any]:
        result = self.inspect_experiment(experiment_id)
        return {"experiment_id": result["experiment_id"], "study": result["study"],
                **self._research_result_context(result, compact_conditions=True),
                **({"parent_experiment_id": result["parent_experiment_id"]}
                   if "parent_experiment_id" in result else {}),
                **({"campaign_id": result["campaign_id"]}
                   if "campaign_id" in result else {}),
                "status": result["status"], "decision": result["decision"],
                "parameters": result["input_parameters"], "metrics": result["metrics"],
                "failures": [{"type": v["type"], "evidence_ids": v["evidence_ids"]}
                             for v in result["validations"] if v["status"] == "FAIL"],
                "unknown": [v["type"] for v in result["validations"] if v["status"] == "UNKNOWN"],
                "artifact_count": len(result["artifacts"]), "cad_revision": result["cad_revision"],
                "model_revision": result.get("model_revision"),
                "result_ref": f"experiments/{experiment_id}/result.json"}

    def compare(self, experiment_ids: list[str]) -> list[dict[str, Any]]:
        return [self.research_summary(check_id(identifier)) for identifier in experiment_ids]

    def plan_doe(self, *, study_id: str, campaign_id: str, backend: str, model: str,
                 parameter_ids: list[str], sample_count: int, seed: int,
                 analysis_backend: str | None = None,
                 analysis_settings: dict[str, Any] | None = None,
                 conditions_id: str | None = None,
                 engine: str = "scipy.latin_hypercube") -> dict[str, Any]:
        from .campaign import plan_doe
        return plan_doe(self, study_id=study_id, campaign_id=campaign_id,
                        backend=backend, model=model, parameter_ids=parameter_ids,
                        sample_count=sample_count, seed=seed,
                        analysis_backend=analysis_backend, analysis_settings=analysis_settings,
                        conditions_id=conditions_id,
                        engine=engine)

    def run_doe(self, campaign_id: str) -> dict[str, Any]:
        from .campaign import run_doe
        return run_doe(self, campaign_id)

    def inspect_doe(self, campaign_id: str) -> dict[str, Any]:
        from .campaign import inspect_doe
        return inspect_doe(self, campaign_id)

    def plan_optimization(self, *, study_id: str, campaign_id: str, backend: str,
                          model: str, parameter_ids: list[str], objective: dict,
                          constraints: list[dict], seed: int, max_generations: int = 1,
                          population_size: int = 5, initial_values: dict | None = None,
                          analysis_backend: str | None = None,
                          analysis_settings: dict | None = None,
                          conditions_id: str | None = None,
                          required_validations: dict | None = None,
                          engine: str = "scipy.differential_evolution") -> dict:
        from .optimization import plan_optimization
        return plan_optimization(self, study_id=study_id, campaign_id=campaign_id,
                                 backend=backend, model=model, parameter_ids=parameter_ids,
                                 objective=objective, constraints=constraints, seed=seed,
                                 max_generations=max_generations, population_size=population_size,
                                 initial_values=initial_values, analysis_backend=analysis_backend,
                                 analysis_settings=analysis_settings,
                                 conditions_id=conditions_id,
                                 required_validations=required_validations, engine=engine)

    def run_optimization(self, campaign_id: str) -> dict:
        from .optimization import run_optimization
        return run_optimization(self, campaign_id)

    def plan_model_optimization(self, *, study_id: str, campaign_id: str, backend: str,
                                settings: dict, parameter_ids: list[str], objective: dict,
                                constraints: list[dict], seed: int,
                                max_generations: int = 1, population_size: int = 5,
                                initial_values: dict | None = None,
                                required_validations: dict | None = None,
                                engine: str = "scipy.differential_evolution") -> dict:
        from .optimization import plan_model_optimization
        return plan_model_optimization(self, study_id=study_id, campaign_id=campaign_id,
                                       backend=backend, settings=settings, parameter_ids=parameter_ids,
                                       objective=objective, constraints=constraints, seed=seed,
                                       max_generations=max_generations, population_size=population_size,
                                       initial_values=initial_values, required_validations=required_validations,
                                       engine=engine)

    def inspect_optimization(self, campaign_id: str) -> dict:
        from .optimization import inspect_optimization
        return inspect_optimization(self, campaign_id)

    def run_pde(self, *, study_id: str, experiment_id: str, backend: str,
                settings: dict, hypothesis_id: str | None = None) -> dict:
        from .pde import run_pde
        return run_pde(self, study_id=study_id, experiment_id=experiment_id,
                       backend=backend, settings=settings, hypothesis_id=hypothesis_id)

    def run_model_analysis(self, *, study_id: str, experiment_id: str, backend: str,
                           settings: dict, hypothesis_id: str | None = None,
                           campaign_id: str | None = None, values: dict | None = None,
                           objectives: list | None = None, constraints: list | None = None,
                           binding: dict | None = None) -> dict:
        from .declared_model import run_declared_model
        return run_declared_model(self, study_id=study_id, experiment_id=experiment_id,
                                  backend=backend, settings=settings, hypothesis_id=hypothesis_id,
                                  adapters=self.model_analysis_adapters, namespace="model_analysis",
                                  output_directory="simulation", description=True,
                                  campaign_id=campaign_id, values=values,
                                  objectives=objectives, constraints=constraints, binding=binding)
