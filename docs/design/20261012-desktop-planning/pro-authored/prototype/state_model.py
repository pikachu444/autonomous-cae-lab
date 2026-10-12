"""Standalone SIMULATED UI state; never computes a fit, physics or provider call."""
from __future__ import annotations
import copy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from uuid import uuid4


class ConflictError(RuntimeError):
    pass


class PendingBufferError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def reference(domain, record):
    return {"document": domain, "revision": record["revision"], "input_sha256": digest(record["value"])}


def initial_document(imports=None):
    material = {"revision": 17, "generation": 42, "value": {
        "law": "compressible_neo_hooke", "mu_MPa": .85, "lmbda_MPa": 12.0,
        "lmbda_basis": "external fixed value; not identified by this fit",
        "protocol": "traction_free_requested_UNSUPPORTED", "stress_measure": "P11"}}
    data = {"revision": 3, "generation": 10, "value": {"imports": imports or {}, "quality_excluded": [],
        "L0_mm": 50.0, "A0_mm2": 20.0}}
    plan = {"revision": 8, "generation": 21, "value": {
        "mu_start_MPa": .85, "mu_min_MPa": .4, "mu_max_MPa": 1.4,
        "lmbda_fixed_MPa": 12.0, "protocol": material["value"]["protocol"],
        "roles": {"A": "train", "B": "holdout"}, "inclusion_excluded": [],
        "source_refs": {"Material": reference("Material", material), "Data": reference("Data", data)}}}
    base = reference("Material", material)
    candidates = [
        {"id": "c017", "mu_MPa": .862, "status": "VALID_FIXTURE", "train_objective": "0.00184 (SIMULATED)",
         "detail": "SIMULATED_RETAINED", "holdout": "SIMULATED_RETAINED", "evaluation_id": "EVAL-fixture-best",
         "base_ref": base, "base_material": copy.deepcopy(material["value"]), "frozen_plan": copy.deepcopy(plan)},
        {"id": "c014", "mu_MPa": .901, "status": "VALID_FIXTURE", "train_objective": "0.07908 (SIMULATED)",
         "detail": "NOT_RETAINED", "holdout": "NOT_EVALUATED", "evaluation_id": None,
         "base_ref": base, "base_material": copy.deepcopy(material["value"]), "frozen_plan": copy.deepcopy(plan)},
        {"id": "c009", "mu_MPa": .401, "status": "FAILED_INCOMPLETE_REQUIRED_RESPONSE", "train_objective": "INVALID",
         "detail": "PARTIAL_FIXTURE_ONLY", "holdout": "NOT_EVALUATED", "evaluation_id": None,
         "base_ref": base, "base_material": copy.deepcopy(material["value"]), "frozen_plan": copy.deepcopy(plan)},
        {"id": "c021", "mu_MPa": .878, "status": "CANCELLED", "train_objective": "INVALID",
         "detail": "PARTIAL_FIXTURE_ONLY", "holdout": "NOT_EVALUATED", "evaluation_id": None,
         "base_ref": base, "base_material": copy.deepcopy(material["value"]), "frozen_plan": copy.deepcopy(plan)},
    ]
    return {"schema_version": "2.0", "kind": "SIMULATED_UI_PLANNING_ONLY", "story": "neo_hooke_mu",
        "domains": {"Data": data, "Material": material, "Plan": plan},
        "candidates": candidates, "evaluations": {"EVAL-fixture-best": {
            "kind": "SIMULATED_DETAIL_FIXTURE", "candidate_id": "c017", "frozen_plan": copy.deepcopy(plan),
            "trials": {"A": {"role": "train", "status": "SIMULATED_RETAINED"},
                       "B": {"role": "holdout", "status": "SIMULATED_RETAINED"}},
            "holdout_RMSE_MPa": .014, "diagnostic": "Illustrative retained fixture only; traction-free solver NOT implemented or run."}},
        "runs": [], "branches": [], "adoption_receipts": []}


class PlanningStore:
    """Atomic local JSON writes; CAS is a single-process simulation, not a service."""
    def __init__(self, path, imports=None):
        self.path = Path(path)
        self.recovery_path = self.path.with_name(self.path.stem + ".recovery.json")
        if not self.path.exists():
            self.write(initial_document(imports))
        self.read()

    def read(self):
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if document.get("kind") != "SIMULATED_UI_PLANNING_ONLY" or document.get("story") != "neo_hooke_mu":
            raise ValueError("Expected neo-Hooke planning JSON. Choose a new --state path; older E/yield files are not migrated silently.")
        return document

    @staticmethod
    def atomic_write(path, document):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temp, path)

    def write(self, document):
        self.atomic_write(self.path, document)

    def compare_and_swap(self, domain, expected_revision, value, expected_hash=None, generation=None, adoption_receipt=None):
        document = self.read()
        record = document["domains"][domain]
        if record["revision"] != expected_revision or (expected_hash and digest(record["value"]) != expected_hash):
            raise ConflictError(f"{domain}: expected r{expected_revision}, current r{record['revision']}; no overwrite; draft retained")
        record["revision"] += 1
        record["value"] = copy.deepcopy(value)
        record["generation"] = generation if generation is not None else record["generation"] + 1
        if adoption_receipt is not None:
            receipt = copy.deepcopy(adoption_receipt)
            receipt.update(status="SIMULATED_SAVED_ADOPTION_RECEIPT", destination_ref=reference(domain, record),
                           actual_saved_value=copy.deepcopy(value),
                           proposal_modified_before_save=value != receipt["proposed_value"])
            document["adoption_receipts"].append(receipt)
        self.write(document)
        return copy.deepcopy(record)

    def inject_external_change(self):
        document = self.read()
        record = document["domains"]["Material"]
        record["revision"] += 1
        record["generation"] += 1
        record["value"].update(mu_MPa=.90, protocol="traction_free_requested_UNSUPPORTED_changed_r18")
        self.write(document)
        return record["revision"]


class DraftSession:
    editable = {"Material": {"mu_MPa"}, "Plan": {"mu_start_MPa", "mu_min_MPa", "mu_max_MPa"}}

    def __init__(self, store):
        self.store = store
        self.saved = copy.deepcopy(store.read()["domains"])
        self.draft = {name: copy.deepcopy(record["value"]) for name, record in self.saved.items()}
        self.generations = {name: record["generation"] for name, record in self.saved.items()}
        self.buffer, self.pending_refresh, self.pending_adoption = None, None, None
        self.pending_adoption_receipt = None
        self.undo_stack = []
        self.samples = []
        self.view_hidden = []
        self.last_save_outcomes = {}

    def dirty(self, domain):
        return self.draft[domain] != self.saved[domain]["value"]

    def begin_buffer(self, domain, field, text):
        if field not in self.editable.get(domain, set()):
            raise KeyError((domain, field))
        self.buffer = {"domain": domain, "field": field, "text": str(text)}

    def commit_buffer(self):
        """Enter acknowledges raw invalid text as a recoverable draft, never valid physics."""
        if self.buffer is None:
            return
        text = self.buffer["text"]
        try:
            value = float(text)
            if not math.isfinite(value):
                value = text
        except ValueError:
            value = text
        domain, field = self.buffer["domain"], self.buffer["field"]
        if self.draft[domain][field] != value:
            self.undo_stack.append((domain, field, copy.deepcopy(self.draft[domain][field])))
            self.generations[domain] += 1
        self.draft[domain][field] = value
        self.buffer = None

    def discard_buffer(self):
        self.buffer = None

    def diagnostics(self, domain, value=None):
        value = self.draft[domain] if value is None else value
        errors = []
        for field in self.editable.get(domain, set()):
            number = value.get(field)
            if not isinstance(number, (int, float)) or not math.isfinite(number) or number <= 0:
                errors.append(f"{field}: finite positive number required; raw draft {number!r} retained")
        if domain == "Plan" and not errors:
            if not value["mu_min_MPa"] < value["mu_max_MPa"]:
                errors.append("mu: lower bound must be smaller than upper bound")
            elif not value["mu_min_MPa"] <= value["mu_start_MPa"] <= value["mu_max_MPa"]:
                errors.append("Plan starting mu must lie within its bounds")
        if domain == "Material" and isinstance(value.get("mu_MPa"), (int, float)):
            if value["lmbda_MPa"] + 2 * value["mu_MPa"] / 3 <= 0:
                errors.append("neo-Hooke: lmbda + 2 mu/3 must be positive")
        return errors

    def toggle_mask(self, sample_id, owner="Data", field="quality_excluded"):
        if (owner, field) not in {("Data", "quality_excluded"), ("View", "display_hidden"), ("Plan", "inclusion_excluded")}:
            raise ValueError("Unknown mask owner")
        previous = list(self.view_hidden if owner == "View" else self.draft[owner][field])
        self.undo_stack.append((owner, field, previous))
        changed = set(previous)
        changed.symmetric_difference_update({sample_id})
        if owner == "View":
            self.view_hidden = sorted(changed)
        else:
            self.draft[owner][field] = sorted(changed)
            self.generations[owner] += 1

    def undo_label(self, owner):
        for command_owner, field, previous in reversed(self.undo_stack):
            if command_owner == owner:
                return f"{owner}.{field}"
        return "none"

    def undo(self, owner):
        """Undo latest command for the focused owner; other owners retain history.

        This bounded harness has no Redo. View commands can be undone explicitly
        as View, but document-focused Undo never consumes their history.
        """
        if owner not in {"Data", "Material", "Plan", "View"}:
            raise ValueError("Choose an explicit Undo owner")
        for index in range(len(self.undo_stack) - 1, -1, -1):
            command_owner, field, previous = self.undo_stack[index]
            if command_owner != owner:
                continue
            self.undo_stack.pop(index)
            if owner == "View":
                self.view_hidden = copy.deepcopy(previous)
            else:
                self.draft[owner][field] = copy.deepcopy(previous)
                self.generations[owner] += 1
            return f"{owner}.{field}"
        return "none"

    def undo_mask(self, owner="Data"):
        """Compatibility entry point with an explicit Data default, never global pop."""
        return self.undo(owner)

    def save(self, domain):
        if self.buffer and self.buffer["domain"] == domain:
            raise PendingBufferError(f"{domain}: pending cell buffer; save a recovery capsule or commit/discard it")
        if not self.dirty(domain):
            if domain == "Material":
                self.pending_adoption_receipt = None
            return "unchanged"
        # Structurally valid drafts, including invalid numeric strings, may save.
        receipt = self.pending_adoption_receipt if domain == "Material" else None
        self.saved[domain] = self.store.compare_and_swap(
            domain, self.saved[domain]["revision"], self.draft[domain],
            expected_hash=digest(self.saved[domain]["value"]), generation=self.generations[domain],
            adoption_receipt=receipt)
        if domain == "Material":
            self.pending_adoption_receipt = None
        return "saved INVALID_DRAFT; run blocked" if self.diagnostics(domain) else "saved"

    def save_all(self, simulate_plan_failure=False):
        outcomes = {}
        for domain in ("Data", "Material", "Plan"):
            try:
                if domain == "Plan" and simulate_plan_failure and self.dirty(domain):
                    raise OSError("SIMULATED Plan write failure")
                outcomes[domain] = self.save(domain)
            except (RuntimeError, ValueError, OSError) as exc:
                outcomes[domain] = str(exc)
        self.last_save_outcomes = copy.deepcopy(outcomes)
        return outcomes

    def reload_domain(self, domain, discard_confirmed=False):
        has_buffer = self.buffer is not None and self.buffer["domain"] == domain
        if (self.dirty(domain) or has_buffer) and not discard_confirmed:
            raise ValueError("Reload would discard this domain's draft/buffer")
        record = self.store.read()["domains"][domain]
        self.saved[domain] = copy.deepcopy(record)
        self.draft[domain] = copy.deepcopy(record["value"])
        self.generations[domain] = record["generation"]
        if has_buffer:
            self.buffer = None
        self.undo_stack = [entry for entry in self.undo_stack if entry[0] != domain]
        if domain == "Material":
            self.pending_adoption_receipt = None

    def preview_source_refresh(self):
        current = self.store.read()["domains"]
        if self.diagnostics("Material", current["Material"]["value"]):
            raise ValueError("Saved Material is invalid; source refresh cannot make it executable")
        proposal = copy.deepcopy(self.draft["Plan"])
        proposal["source_refs"] = {name: reference(name, current[name]) for name in ("Material", "Data")}
        proposal["mu_start_MPa"] = current["Material"]["value"]["mu_MPa"]
        proposal["lmbda_fixed_MPa"] = current["Material"]["value"]["lmbda_MPa"]
        proposal["protocol"] = current["Material"]["value"]["protocol"]
        self.pending_refresh = {"old": copy.deepcopy(self.draft["Plan"]), "proposed": proposal}
        return copy.deepcopy(self.pending_refresh)

    def apply_source_refresh(self):
        if not self.pending_refresh:
            raise ValueError("Preview source differences first")
        proposal = self.pending_refresh["proposed"]
        if self.draft["Plan"] != self.pending_refresh["old"] or (self.buffer and self.buffer["domain"] == "Plan"):
            raise ConflictError("Plan changed after refresh preview; preview again; local edits retained")
        current = self.store.read()["domains"]
        for domain in ("Material", "Data"):
            if reference(domain, current[domain]) != proposal["source_refs"][domain]:
                raise ConflictError("Source changed after refresh preview; preview again; old Plan retained")
        self.draft["Plan"] = copy.deepcopy(proposal)
        self.generations["Plan"] += 1
        self.pending_refresh = None

    def cancel_source_refresh(self):
        self.pending_refresh = None

    def frozen_mask(self, data, plan):
        excluded = set(data["quality_excluded"]) | set(plan["inclusion_excluded"])
        known = {sample["id"] for sample in self.samples}
        if excluded - known:
            raise ValueError("Mask identities do not match imported rows; never remap positions implicitly")
        roles = {}
        for source, role in plan["roles"].items():
            selected = [s["id"] for s in self.samples if s["source"] == source and s["operation_valid"] and s["id"] not in excluded]
            if not selected:
                raise ValueError(f"{source}/{role}: empty quality ∩ operation-valid ∩ Plan-inclusion intersection")
            roles[source] = {"role": role, "sample_ids": selected, "count": len(selected)}
        return roles

    def simulate_run(self):
        if self.buffer or self.dirty("Plan"):
            raise ValueError("Resolve buffer and save Plan before a SIMULATED run")
        if self.dirty("Material"):
            raise ConflictError("Material current draft/input hash differs from the saved source; explicitly Save Material, refresh Plan source, and save Plan before a proposed-future SIMULATED run")
        plan = self.saved["Plan"]["value"]
        current = self.store.read()["domains"]
        if self.diagnostics("Plan", plan):
            raise ValueError("Saved Plan has invalid coefficients/bounds; no run created")
        for domain in ("Material", "Data"):
            if plan["source_refs"][domain] != reference(domain, current[domain]):
                raise ConflictError("Plan source reference is stale; preview/apply source refresh and save Plan first")
        actual_imports = {s["source"]: s["source_sha256"] for s in self.samples}
        if actual_imports != current["Data"]["value"]["imports"]:
            raise ValueError("CSV import bytes differ from saved Data; no positional remapping or implicit replacement")
        frozen = self.frozen_mask(current["Data"]["value"], plan)
        run = {"id": "SIM-RUN-" + uuid4().hex[:12], "status": "PROPOSED_FUTURE_SIMULATED_NO_COMPUTATION", "actual_capability": "CURRENT EXECUTION BLOCKED; traction-free solver NOT IMPLEMENTED / NOT RUN",
            "plan_ref": reference("Plan", self.saved["Plan"]), "plan": copy.deepcopy(plan), "observations": frozen}
        document = self.store.read()
        document["runs"].append(run)
        self.store.write(document)
        return copy.deepcopy(run)

    def inspect_candidate(self, candidate_id):
        return copy.deepcopy(next(c for c in self.store.read()["candidates"] if c["id"] == candidate_id))

    def simulate_detail_evaluation(self, candidate_id):
        document = self.store.read()
        candidate = next(c for c in document["candidates"] if c["id"] == candidate_id)
        if candidate["status"] != "VALID_FIXTURE":
            raise ValueError("Incomplete required response: detailed evaluation unavailable; never display zero holdout")
        if len([key for key in document["evaluations"] if key.startswith("SIM-EVAL-")]) >= 3:
            raise ValueError("SIMULATED detail budget exhausted (3); no new evaluation")
        evaluation_id = "SIM-EVAL-" + uuid4().hex[:12]
        evaluation = {"kind": "SIMULATED_DETAIL_FIXTURE", "candidate_id": candidate_id,
            "mu_MPa": candidate["mu_MPa"], "frozen_plan": copy.deepcopy(candidate["frozen_plan"]),
            "trials": {"A": {"role": "train", "status": "SIMULATED_RETAINED"},
                       "B": {"role": "holdout", "status": "SIMULATED_RETAINED"}},
            "diagnostic": "Explicit simulated detail identity; no fit, holdout or physics calculated."}
        document["evaluations"][evaluation_id] = evaluation
        # Explicit detail is a new sidecar identity, not a rewrite of original run retention.
        self.store.write(document)
        return evaluation_id

    def preview_adoption(self, candidate_id):
        if self.dirty("Material") or (self.buffer and self.buffer["domain"] == "Material"):
            raise ValueError("Preserve/save/recover Material draft before adoption preview; no edits overwritten")
        candidate = self.inspect_candidate(candidate_id)
        if candidate["status"] != "VALID_FIXTURE":
            raise ValueError("Incomplete candidate cannot be adopted")
        has_sidecar = any(value["candidate_id"] == candidate_id for key, value in self.store.read()["evaluations"].items() if key.startswith("SIM-EVAL-"))
        if candidate["detail"] == "NOT_RETAINED" and not has_sidecar:
            raise ValueError("Candidate details NOT_RETAINED: explicitly retain a simulated detail evaluation before adoption review")
        current = self.store.read()["domains"]["Material"]
        proposal_value = copy.deepcopy(current["value"])
        proposal_value["mu_MPa"] = candidate["mu_MPa"]
        differences = [{"field": key, "base": candidate["base_material"].get(key),
                        "current": current["value"].get(key), "proposed": proposal_value.get(key)}
                       for key in ("mu_MPa", "lmbda_MPa", "protocol")]
        self.pending_adoption = {"candidate_id": candidate_id, "candidate_base_ref": candidate["base_ref"],
            "current_ref": reference("Material", current), "proposed_value": proposal_value,
            "differences": differences, "phase": "CONFLICT_REVIEW" if candidate["base_ref"] != reference("Material", current) else "REVIEW"}
        return copy.deepcopy(self.pending_adoption)

    def resolve_adoption(self, choice):
        if not self.pending_adoption:
            raise ValueError("Preview adoption differences first")
        proposal = self.pending_adoption
        if choice == "cancel":
            self.pending_adoption = None
            return {"status": "CANCELLED_NO_MUTATION"}
        if self.dirty("Material") or (self.buffer and self.buffer["domain"] == "Material"):
            raise ConflictError("Material local edits changed after preview; preserve/re-review first; no overwrite")
        current = self.store.read()["domains"]["Material"]
        if reference("Material", current) != proposal["current_ref"]:
            raise ConflictError("Material changed after adoption preview; re-review required; no overwrite")
        if choice == "new_proposal":
            proposal["phase"] = "NEW_PROPOSAL_ON_CURRENT_REVIEW"
            return copy.deepcopy(proposal)
        if choice == "apply":
            if proposal["phase"] == "CONFLICT_REVIEW":
                raise ConflictError("Stale candidate: explicitly create a new proposal on current revision or branch/cancel")
            # Apply acknowledges an owner draft; only explicit Save publishes r19.
            self.saved["Material"] = copy.deepcopy(current)
            self.draft["Material"] = copy.deepcopy(proposal["proposed_value"])
            self.generations["Material"] = current["generation"] + 1
            self.undo_stack.append(("Material", "mu_MPa", current["value"]["mu_MPa"]))
            receipt = {"status": "SIMULATED_ACKNOWLEDGED_DIRTY_ADOPTION_DRAFT", **copy.deepcopy(proposal),
                       "draft_generation": self.generations["Material"], "expected_saved_ref": reference("Material", current)}
            self.pending_adoption_receipt = copy.deepcopy(receipt)
        elif choice == "branch":
            receipt = {"status": "SIMULATED_BRANCH_SAVED", "branch_id": "SIM-BRANCH-" + uuid4().hex[:12],
                "revision": 1, **copy.deepcopy(proposal)}
            document = self.store.read()
            document["branches"].append(receipt)
            self.store.write(document)
        else:
            raise ValueError("Choose new_proposal, apply, branch or cancel")
        self.pending_adoption = None
        return copy.deepcopy(receipt)

    def preserve_recovery(self):
        capsule = {"kind": "SIMULATED_RECOVERY_CAPSULE_NOT_SAVED_REVISION", "store_path": str(self.store.path.resolve()),
            "saved_bases": copy.deepcopy(self.saved), "owner_drafts": copy.deepcopy(self.draft),
            "cell_buffer": copy.deepcopy(self.buffer), "undo_stack": copy.deepcopy(self.undo_stack),
            "draft_generations": copy.deepcopy(self.generations),
            "view_hidden": copy.deepcopy(self.view_hidden),
            "pending_save_outcomes": copy.deepcopy(self.last_save_outcomes),
            "acknowledged_adoption_draft_receipt": copy.deepcopy(self.pending_adoption_receipt),
            "retained_evaluation_refs": list(self.store.read()["evaluations"])}
        self.store.atomic_write(self.store.recovery_path, capsule)
        return self.store.recovery_path

    def restore_recovery(self):
        capsule = json.loads(self.store.recovery_path.read_text(encoding="utf-8"))
        if capsule.get("kind") != "SIMULATED_RECOVERY_CAPSULE_NOT_SAVED_REVISION" or capsule["store_path"] != str(self.store.path.resolve()):
            raise ValueError("Recovery capsule belongs to a different planning store")
        self.saved = copy.deepcopy(capsule["saved_bases"])
        self.draft = copy.deepcopy(capsule["owner_drafts"])
        self.buffer = copy.deepcopy(capsule["cell_buffer"])
        self.undo_stack = copy.deepcopy(capsule["undo_stack"])
        self.generations = copy.deepcopy(capsule["draft_generations"])
        self.view_hidden = copy.deepcopy(capsule.get("view_hidden", []))
        self.last_save_outcomes = copy.deepcopy(capsule.get("pending_save_outcomes", {}))
        self.pending_adoption_receipt = copy.deepcopy(capsule.get("acknowledged_adoption_draft_receipt"))
        self.pending_refresh = self.pending_adoption = None
        return capsule


MAPPINGS = {
    "A": {"time_s": ("time_s", 1.0, 0.0), "force_N": ("force_N", 1.0, 0.0),
          "extension_mm": ("extension_mm", 1.0, 0.0), "temperature_K": ("temperature_C", 1.0, 273.15)},
    "B": {"time_s": ("time_ms", .001, 0.0), "force_N": ("load_kN", 1000.0, 0.0),
          "extension_mm": ("extension_um", .001, 0.0), "temperature_K": ("temperature_K", 1.0, 0.0)},
}


def load_samples(data_dir):
    """Input-unit/geometry mapping only; never a constitutive evaluation."""
    samples, raw = [], {}
    for source in ("A", "B"):
        path = Path(data_dir) / f"tensile_{source}.csv"
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            expected = {spec[0] for spec in MAPPINGS[source].values()}
            if not expected.issubset(reader.fieldnames or []):
                raise ValueError(f"{path.name}: required columns {sorted(expected)}")
            rows = list(reader)
        raw[source] = rows
        for index, row in enumerate(rows):
            values = {key: float(row[column]) * scale + offset for key, (column, scale, offset) in MAPPINGS[source].items()}
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError(f"{path.name} row {index + 2}: non-finite input")
            e = values["extension_mm"] / 50.0
            samples.append({"id": f"{source}:{source_hash[:12]}:{index}", "source": source,
                "source_index": index, "source_row": index + 2, "source_sha256": source_hash,
                "e11": e, "axial_stretch": 1 + e, "P11_MPa": values["force_N"] / 20.0,
                "operation_valid": 1 + e > 0, "temperature_C": values["temperature_K"] - 273.15, **values})
    return samples, raw
