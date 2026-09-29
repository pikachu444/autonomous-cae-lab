"""One Core API shared by CLI and OpenScience transport."""

from copy import deepcopy
from pathlib import Path
import platform
from typing import Any
import zipfile
from filelock import FileLock

from .adapters.fixture_cadquery import FixtureCadQueryAdapter
from .adapters.fixture_freecad import FixtureFreeCADAdapter
from .contracts import CADAdapter, CapabilityUnavailable
from .registry import register_parameter, validate_assignments
from .schema import validate as validate_schema
from .storage import (artifact_manifest, canonical_hash, check_artifacts, check_id,
                      load_json, save_json, source_identity, utc_now)
import hashlib


class Lab:
    def __init__(self, store: str | Path, *, adapters: dict[str, CADAdapter] | None = None):
        self.store = Path(store).resolve()
        self.adapters = adapters if adapters is not None else {
            FixtureCadQueryAdapter.backend: FixtureCadQueryAdapter(),
            FixtureFreeCADAdapter.backend: FixtureFreeCADAdapter(self.store),
        }

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
                       settings: dict[str, Any] | None = None) -> dict[str, Any]:
        check_id(experiment_id)
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
        thread = {"hypothesis": proposal["hypothesis_id"], "study": study_id,
                  "experiment": experiment_id, "registry_revision": registry["revision"],
                  "cad_revision": revision,
                  "mesh": None, "solver_deck": None, "run": None,
                  "result": "result.json", "evidence": [e["id"] for e in evidence],
                  "decision": result["decision"]}
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
        return result

    def research_summary(self, experiment_id: str) -> dict[str, Any]:
        result = self.inspect_experiment(experiment_id)
        return {"experiment_id": result["experiment_id"], "study": result["study"],
                "status": result["status"], "decision": result["decision"],
                "parameters": result["input_parameters"], "metrics": result["metrics"],
                "failures": [{"type": v["type"], "evidence_ids": v["evidence_ids"]}
                             for v in result["validations"] if v["status"] == "FAIL"],
                "unknown": [v["type"] for v in result["validations"] if v["status"] == "UNKNOWN"],
                "artifact_count": len(result["artifacts"]), "cad_revision": result["cad_revision"],
                "result_ref": f"experiments/{experiment_id}/result.json"}

    def compare(self, experiment_ids: list[str]) -> list[dict[str, Any]]:
        return [self.research_summary(check_id(identifier)) for identifier in experiment_ids]
