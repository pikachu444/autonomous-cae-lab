"""One Core API shared by CLI and OpenScience transport."""

from copy import deepcopy
from pathlib import Path
import platform
from typing import Any
import zipfile
from filelock import FileLock

from .adapters.fixture_cadquery import FixtureCadQueryAdapter
from .adapters.fixture_freecad import FixtureFreeCADAdapter
from .contracts import AnalysisAdapter, CADAdapter, DOEAdapter, CapabilityUnavailable
from .registry import register_parameter, validate_assignments
from .schema import validate as validate_schema
from .storage import (artifact_manifest, canonical_hash, check_artifacts, check_id,
                      load_json, save_json, source_identity, utc_now)
import hashlib


class Lab:
    def __init__(self, store: str | Path, *, adapters: dict[str, CADAdapter] | None = None,
                 analysis_adapters: dict[str, AnalysisAdapter] | None = None,
                 doe_adapters: dict[str, DOEAdapter] | None = None):
        self.store = Path(store).resolve()
        self.adapters = adapters if adapters is not None else {
            FixtureCadQueryAdapter.backend: FixtureCadQueryAdapter(),
            FixtureFreeCADAdapter.backend: FixtureFreeCADAdapter(self.store),
        }
        if analysis_adapters is None:
            from .adapters.fixture_calculix import FixtureCalculiXAdapter
            analysis_adapters = {FixtureCalculiXAdapter.backend: FixtureCalculiXAdapter()}
        self.analysis_adapters = analysis_adapters
        if doe_adapters is None:
            from .optimizers.scipy_lhs import ScipyLatinHypercube
            doe_adapters = {ScipyLatinHypercube.engine: ScipyLatinHypercube()}
        self.doe_adapters = doe_adapters

    def create_native_model(self, *, template: str = "roller_support") -> dict[str, Any]:
        return self._adapter("fixture.freecad").create_sample(template)

    def import_native_model(self, source: str | Path) -> dict[str, Any]:
        return self._adapter("fixture.freecad").import_document(Path(source))

    def inspect_native_model(self, model: str) -> dict[str, Any]:
        return self._adapter("fixture.freecad").inspect_model(model)

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

    def registry(self, study_id: str) -> dict[str, Any]:
        return load_json(self.store / "studies" / check_id(study_id) / "parameters.json")

    def discover_parameters(self, backend: str, model: str) -> list[dict[str, Any]]:
        return [deepcopy(candidate.__dict__) for candidate in self._adapter(backend).discover(model)]

    def register_parameter(self, study_id: str, backend: str, model: str, native_path: str,
                           parameter_id: str, display_name: str, lower: float, upper: float,
                           mode: str = "free", kind: str = "continuous",
                           dependencies: list[str] | None = None) -> dict[str, Any]:
        registry_path = self.store / "studies" / check_id(study_id) / "parameters.json"
        with FileLock(str(registry_path) + ".lock", timeout=30):
            registry = load_json(registry_path)
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
            bind = getattr(adapter, "bind", None)
            if bind:
                new_source_hash = bind(model, candidate, parameter_id, display_name, lower, upper)
                entry["source_sha256"] = new_source_hash
                for existing in registry["entries"]:
                    if existing["native"]["document"] == candidate.native["document"]:
                        existing["source_sha256"] = new_source_hash
            registry["entries"].append(entry)
            registry["revision"] += 1
            save_json(registry_path, registry)
            save_json(registry_path.parent / "registry_history" / f"{registry['revision']:04d}.json", registry)
            return entry

    def refresh_registry(self, study_id: str, backend: str, model: str) -> dict[str, Any]:
        """Rebase existing mappings after an engineer edits the native CAD source."""
        registry_path = self.store / "studies" / check_id(study_id) / "parameters.json"
        with FileLock(str(registry_path) + ".lock", timeout=30):
            registry = load_json(registry_path)
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
            save_json(registry_path, refreshed)
            save_json(registry_path.parent / "registry_history" / f"{refreshed['revision']:04d}.json", refreshed)
            return refreshed

    def run_experiment(self, *, study_id: str, experiment_id: str, backend: str,
                       model: str, values: dict[str, Any],
                       hypothesis_id: str | None = None,
                       settings: dict[str, Any] | None = None,
                       campaign_id: str | None = None) -> dict[str, Any]:
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
                    "objectives": [], "constraints": [], "validation_requirements": [],
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
        for kind in outcome.pending_validations if outcome else []:
            validations.append({"type": kind, "validator": "not_executed", "status": "UNKNOWN",
                                "blocking": True, "threshold": None, "expected_range": None,
                                "evidence_ids": [], "cad_revision": revision, "experiment_id": experiment_id,
                                "solver_run_id": None, "timestamp": utc_now(),
                                "notes": "Evidence required before engineering release"})

        rejected = any(v["status"] == "FAIL" for v in validations)
        execution_status = "FAILED_EXECUTION" if execution_error else (
            "REJECTED" if rejected else "COMPLETED_REVIEW_REQUIRED")
        if outcome and outcome.decision not in ("REVIEW_REQUIRED", "REJECTED"):
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
                     backend: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Create a child solver run on a verified, immutable CAD revision."""
        check_id(experiment_id)
        parent_id = check_id(parent_experiment_id)
        if parent_id == experiment_id:
            raise ValueError("An analysis must have a distinct experiment ID")
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
                    "objectives": [], "constraints": [], "validation_requirements": [],
                    "execution": deepcopy(settings),
                    "registry_revision": parent["registry_revision"]}
        if "campaign_id" in parent:
            proposal["campaign_id"] = parent["campaign_id"]
        if "material" in settings:
            proposal["model"]["materials"] = [deepcopy(settings["material"])]
        validate_schema("experiment", proposal)
        canonical_hash(proposal)

        folder = self.store / "experiments" / experiment_id
        folder.mkdir(parents=True, exist_ok=False)
        save_json(folder / "proposal.json", proposal)
        save_json(folder / "registry_snapshot.json", registry)
        parent_result_hash = hashlib.sha256((parent_root / "result.json").read_bytes()).hexdigest()
        save_json(folder / "parent_reference.json", {
            "experiment_id": parent_id, "cad_revision": parent["cad_revision"],
            "result_sha256": parent_result_hash})

        execution_error = False
        outcome = None
        try:
            outcome = adapter.solve(parent, parent_root, folder / "simulation", deepcopy(settings))
            if (not isinstance(outcome, dict) or outcome.get("status") not in ("COMPLETED", "REJECTED") or
                    not isinstance(outcome.get("checks"), list) or
                    not isinstance(outcome.get("metrics"), dict) or
                    not isinstance(outcome.get("provenance"), dict) or
                    not isinstance(outcome.get("solver_status"), str) or
                    not isinstance(outcome.get("pending_validations"), list) or
                    any(not isinstance(k, str) or not k for k in outcome["pending_validations"]) or
                    type(outcome.get("converged")) not in (bool, type(None))):
                raise ValueError("Analysis adapter returned an invalid common outcome")
            if any(not isinstance(check, dict) or
                   check.get("status") not in ("PASS", "FAIL", "UNKNOWN", "WARNING") or
                   not isinstance(check.get("code"), str) or not check["code"]
                   for check in outcome["checks"]):
                raise ValueError("Analysis adapter returned an invalid validation check")
            if any(not isinstance(metric, dict) or
                   not {"value", "unit", "valid"} <= metric.keys() or
                   not isinstance(metric["unit"], str) or
                   type(metric["valid"]) is not bool or
                   (not metric["valid"] and not metric.get("reason"))
                   for metric in outcome["metrics"].values()):
                raise ValueError("Analysis adapter returned an invalid metric")
            if (outcome["status"] == "COMPLETED" and
                    (outcome["converged"] is not True or not outcome["metrics"])):
                raise ValueError("Completed analysis requires convergence and metrics")
            canonical_hash(outcome)  # Reject NaN and non-serializable nested observations.
        except Exception as exc:
            execution_error = True
            outcome = {"status": "REJECTED", "checks": [{"code": "analysis_execution",
                       "status": "FAIL", "observed": f"{type(exc).__name__}: {exc}"}],
                       "metrics": {}, "solver_status": "FAILED_EXECUTION", "converged": None,
                       "pending_validations": [], "provenance": {}, "raw_result": None}
        checks = outcome["checks"]
        if outcome["status"] == "REJECTED" and not any(c["status"] == "FAIL" for c in checks):
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
        status = ("FAILED_EXECUTION" if execution_error else
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

    def research_summary(self, experiment_id: str) -> dict[str, Any]:
        result = self.inspect_experiment(experiment_id)
        return {"experiment_id": result["experiment_id"], "study": result["study"],
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
                "result_ref": f"experiments/{experiment_id}/result.json"}

    def compare(self, experiment_ids: list[str]) -> list[dict[str, Any]]:
        return [self.research_summary(check_id(identifier)) for identifier in experiment_ids]

    def plan_doe(self, *, study_id: str, campaign_id: str, backend: str, model: str,
                 parameter_ids: list[str], sample_count: int, seed: int,
                 analysis_backend: str | None = None,
                 analysis_settings: dict[str, Any] | None = None,
                 engine: str = "scipy.latin_hypercube") -> dict[str, Any]:
        from .campaign import plan_doe
        return plan_doe(self, study_id=study_id, campaign_id=campaign_id,
                        backend=backend, model=model, parameter_ids=parameter_ids,
                        sample_count=sample_count, seed=seed,
                        analysis_backend=analysis_backend, analysis_settings=analysis_settings,
                        engine=engine)

    def run_doe(self, campaign_id: str) -> dict[str, Any]:
        from .campaign import run_doe
        return run_doe(self, campaign_id)

    def inspect_doe(self, campaign_id: str) -> dict[str, Any]:
        from .campaign import inspect_doe
        return inspect_doe(self, campaign_id)
