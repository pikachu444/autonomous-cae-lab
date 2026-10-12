"""Pure-stdlib state for the isolated UX prototype, never a production owner.

Only explicit user actions change this fixture state. No solver, provider,
native application, optimization or network operation is present.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

FORMAT = "caelab-ux-review/1"
HERE = Path(__file__).resolve().parent
TOOL_NAMES = {
    "cad": "CAD / FE", "simulation": "Simulation", "thermal": "Simulation",
    "thermoelastic": "Simulation", "post": "Post", "data": "Data",
    "material": "Material", "pde": "PDE", "numerical": "Numerical",
    "runner": "Runner", "expert": "Expert", "study": "Study",
    "evaluation": "Evaluation", "workbench": "Workbench",
}
METHODS = {
    "DOE": ("Design matrix", "Responses", "Effects"),
    "Inverse": ("Observations", "Residuals", "Holdout"),
    "Optimization": ("Candidates", "Objectives", "Constraints"),
    "Sobol sensitivity": ("Sampling design", "First / total order", "Convergence"),
    "UQ": ("Distributions", "Propagation", "Intervals"),
    "RBF surrogate": ("Training cases", "Validation split", "Prediction support"),
    "MOO": ("Candidates", "Pareto front", "Constraints"),
    "MDO": ("Disciplines", "Coupling", "Objectives"),
}


class ReviewError(Exception):
    """A recoverable operation error that must be shown in context."""


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def token(prefix: str) -> str:
    return prefix + "-" + uuid.uuid4().hex[:12]


def atomic_json(path: Path, content: Any) -> None:
    """Write locally, replacing a file only after complete serialization."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False)
    fd, name = tempfile.mkstemp(prefix=".review-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def make_document(key, name, owner, doc_id, revision, payload):
    return {"key": key, "name": name, "owner": owner, "id": doc_id,
            "revision": revision, "generation": 0, "saved": clone(payload),
            "draft": clone(payload), "file": None, "undo": [], "redo": [],
            "history": [{"revision": revision, "payload": clone(payload),
                         "source": "PUBLIC_SYNTHETIC_FIXTURE"}],
            "dirty": False, "buffers": {}}


def initial_documents():
    docs = {}
    def add(*args):
        doc = make_document(*args)
        docs[doc["key"]] = doc
    add("cad", "Clamp fixture", "native_pre", "CAD-01", 13, {
        "thickness": 14.0, "width": 72.0, "height": 28.0, "unit": "mm",
        "material": {"id": "MAT-01", "revision": 18},
        "sketch": {"length_constraint": "72", "fully_constrained": True},
        "joint": {"type": "Revolute", "angle": 15.0, "preview_angle": 15.0},
        "mesh": {"size": 2.0, "quality_limit": .25, "bad_elements": [314, 829]},
        "contact": {"law": "Coulomb", "mu": .15, "gap": .20,
                    "set_a": ["Clamp/Pad/Face6", "Clamp/Pad/Face7"],
                    "set_b": ["Base/Face2"], "resolved": True},
        "capability": "PROTOTYPE_ONLY", "qualification": "UNKNOWN",
        "release": "NOT_RELEASED"})
    add("simulation", "Clamp load", "Simulation", "V-01", 7, {
        "family": "Nonlinear implicit", "model_ref": {"id": "CAD-01", "revision": 13},
        "step": "Load", "duration": 1.0, "increments": 100,
        "geometry": "Large deformation", "force": -250.0, "force_unit": "N",
        "required_response": "U / reaction / contact pressure",
        "failure": "Interface damage", "initial_velocity": -3.43,
        "angular_velocity": 0.0, "time_step": 1e-6,
        "backend": "Code_Aster", "capability": "UNCONNECTED"})
    add("thermal", "Plate heating", "Simulation", "V-02", 4, {
        "family": "Thermal", "backend": "thermal.fenicsx.rectangle",
        "field": "temperature", "unit": "K", "length_unit": "m",
        "mesh": "P1 triangular / same plate", "temperature": 323.15,
        "boundary": "Uniform Dirichlet", "capability": "NOT_EXECUTED"})
    add("thermoelastic", "Plate expansion", "Simulation", "V-03", 6, {
        "family": "Thermoelastic", "backend": "structural.fenicsx.thermoelastic_rectangle",
        "field": "displacement", "unit": "m", "length_unit": "m",
        "mesh": "P1 triangular / same plate", "Tref": 293.15,
        "alpha": 1.2e-5, "state": "Plane stress / free expansion",
        "thermal_ref": {"id": "V-02", "revision": 4}, "capability": "NOT_EXECUTED"})
    samples = [{"id": f"A{i}", "time": i * .01, "extension": i * .004,
                "force": round(195 * (i / 300) ** .82, 5), "temperature": 23.0}
               for i in range(301)]
    add("data", "Tension", "Data", "DATA-01", 4, {
        "columns": [{"key": "time", "name": "Time", "unit": "s", "role": "X", "formula": ""},
                    {"key": "extension", "name": "Extension", "unit": "mm", "role": "Y", "formula": ""},
                    {"key": "force", "name": "Force", "unit": "N", "role": "Y", "formula": ""},
                    {"key": "temperature", "name": "Temperature", "unit": "degC", "role": "None", "formula": ""}],
        "samples": samples, "quality_excluded": [], "exclusion_reasons": {},
        "recipe": {"L0": 50.0, "A0": 20.0, "strain_measure": "engineering",
                   "stress_measure": "first_Piola", "displacement": "gauge extension"},
        "calibration": {"id": "CAL-018", "revision": 2, "file": "Calibration.txt",
                        "locator": "Force channel / calibration row 18",
                        "range": "0–2000 N", "status": "SYNTHETIC / not a certificate"}})
    add("material", "Rubber", "Material", "MAT-01", 18, {
        "law": "Neo-Hookean", "mu": .90, "bulk": 100.0, "unit": "MPa",
        "protocol": "Uniaxial traction-free", "train": "Tension A",
        "holdout": "Tension B", "L0": 50.0, "A0": 20.0,
        "observations": {"id": "DATA-01", "revision": 4},
        "dependencies": [{"id": "TENSION-A", "name": "Tension.csv",
                          "sha256": "", "missing": False}],
        "capability": "UNCONNECTED"})
    add("pde", "Diffusion", "PDE", "PDE-01", 3, {
        "field": "u", "space": "P1", "domain": "Rectangle",
        "equation": "-div(k*grad(u)) = f", "k": 1.0, "f": 1.0,
        "bc": "u = 0", "selection": "Left edge", "mesh": .05,
        "form": "Registered PDE", "capability": "UNCONNECTED"})
    add("numerical", "Clamp trade-off", "Numerical", "N-MOO", 4, {
        "method": "MOO", "evaluator": "Clamp / material response",
        "budget": 40, "seed": 17,
        "sources": {"cad": {"id": "CAD-01", "revision": 12},
                    "material": {"id": "MAT-01", "revision": 17},
                    "data": {"id": "DATA-01", "revision": 4}},
        "observation_snapshot": clone(docs["data"]["saved"]),
        "variables": [{"owner": "cad", "field": "thickness", "unit": "mm", "start": 14.0,
                       "lower": 12.0, "upper": 16.0, "free": True},
                      {"owner": "material", "field": "mu", "unit": "MPa", "start": .85,
                       "lower": .60, "upper": 1.40, "free": True}],
        "responses": [{"name": "Mass", "role": "Minimize", "unit": "kg", "limit": ""},
                      {"name": "Gauge error", "role": "Minimize", "unit": "%", "limit": ""},
                      {"name": "Displacement", "role": "Upper bound", "unit": "mm", "limit": .35},
                      {"name": "Clearance", "role": "Lower bound", "unit": "mm", "limit": .10}],
        "train_samples": [s["id"] for s in samples], "holdout": "Tension B",
        "failure_policy": "Invalid objective; retain diagnostic", "data_source_stale": False})
    add("post", "Clamp result", "native_post", "POST-01", 3, {
        "result": "fixture-result-clamp", "array": "Displacement", "association": "POINTS",
        "unit": "mm", "time": .04, "available_times": [0, .01, .02, .04],
        "filter": "Surface", "pending_filter": "Surface", "mapping": "Unverified",
        "basis": "Global Cartesian", "selection": "Gauge endpoints",
        "deformation_scale": 10, "qualification": "UNKNOWN", "release": "NOT_RELEASED"})
    add("expert", "Clamp compliance", "Discussion", "DISC-01", 2, {
        "question": "지그 유연성이 측정 변위에 얼마나 섞이는가?",
        "provider": "UNCONNECTED", "paused": True, "pending_text": "",
        "reply_to": None,
        "topics": ["지그 강성", "접촉과 마찰", "측정 위치", "판별 시험"],
        "roles": ["구조", "시험", "재료"],
        "turns": [{"id": "question-example", "role": "사용자 예시", "actual": False,
                   "text": "재료 상수와 지그 유연성 중 무엇이 관측 차이를 만드는지 비교하고 싶다.",
                   "topic": "지그 강성", "reply_to": None, "evidence": []}],
        "evidence": [{"id": "fixture-result-clamp", "locator": "Gauge / t = 0.04 s",
                      "label": "Clamp displacement", "synthetic": True}],
        "plan_proposal": {"objective": "Separate fixture compliance from specimen response",
                          "variables": "Thickness, contact friction",
                          "response": "Gauge extension and machine displacement", "budget": 12},
        "study_ref": {"id": "STUDY-01", "revision": 2}})
    add("study", "Clamp compliance", "Study", "STUDY-01", 2, {
        "question": "지그 유연성이 측정 변위에 얼마나 섞이는가?",
        "hypotheses": [{"id": "H1", "text": "지그 유연성이 주요 원인", "judgment": "Undecided"},
                       {"id": "H2", "text": "재료 모델이 주요 원인", "judgment": "Undecided"},
                       {"id": "H3", "text": "계측 위치 또는 영점 영향", "judgment": "Undecided"}],
        "evidence": [{"ref": "fixture-result-clamp", "locator": "Gauge / t = 0.04 s",
                      "hypothesis": "H1", "relation": "Neutral", "synthetic": True}],
        "judgment": "Undecided", "reason": "", "next_research": "Independent gauge measurement",
        "qualification": "UNKNOWN", "release": "NOT_RELEASED"})
    add("evaluation", "Thermal expansion", "Evaluation", "EVAL-01", 5, {
        "stages": [{"stage": "Heat", "ref": {"id": "V-02", "revision": 4}, "operation": "thermal"},
                   {"stage": "Expand", "ref": {"id": "V-03", "revision": 6}, "operation": "thermoelastic"}],
        "transfer": "Temperature [K] / POINTS / exact_same_mesh",
        "static_connection": "Checked in fixture", "actual_field": "PENDING",
        "convergence": "NOT_EVALUATED", "iteration": "Lagged Picard",
        "tolerance": 1e-6, "limit": 25})
    add("workbench", "Clamp research", "Study links", "LINKS-01", 1, {
        "links": [["cad", "simulation"], ["simulation", "runner"], ["runner", "post"],
                  ["post", "numerical"], ["data", "material"], ["expert", "study"]],
        "positions": {}})
    add("runner", "Jobs", "JobManager view", "JOBS-VIEW", 1, {"filter": "All"})
    return docs


class ReviewSession:
    """Small serializable interaction fixture. Production services are not called."""
    def __init__(self, workspace=None):
        self.workspace = Path(workspace or tempfile.mkdtemp(prefix="caelab-ux-"))
        self.documents = initial_documents()
        self.jobs = []
        self.frozen = {}
        self.results = {
            "fixture-result-clamp": {"id": "fixture-result-clamp", "synthetic": True,
                 "source": {"id": "CAD-01", "revision": 12}, "attempt": "fixture-attempt-03",
                 "time": .04, "status": "RETAINED_FIXTURE",
                 "metrics": {"displacement": .31, "mass": .42, "clearance": .12}},
            "fixture-data-A301": {"id": "fixture-data-A301", "synthetic": True,
                 "source": {"id": "DATA-01", "revision": 4}, "included_count": 301,
                 "included_ids": [f"A{i}" for i in range(301)], "status": "RETAINED_FIXTURE"}}
        self.candidates = [
            {"id": "p04", "thickness": 14.6, "mu": .9, "mass": .49, "error": 2.9,
             "displacement": .29, "clearance": .16, "status": "Retained fixture"},
            {"id": "p19", "thickness": 13.7, "mu": 1.12, "mass": .42, "error": 2.1,
             "displacement": .31, "clearance": .12, "status": "Retained fixture"},
            {"id": "p27", "thickness": 12.8, "mu": 1.18, "mass": .38, "error": 4.7,
             "displacement": .41, "clearance": .08, "status": "Constraint violation"},
            {"id": "p31", "thickness": 12.1, "mu": .72, "mass": None, "error": None,
             "displacement": None, "clearance": None, "status": "Failed fixture"}]
        self.groups = {}
        self.relocations = {}
        self.events = []
        self.selected = {"tool": "cad", "candidate": "p19", "samples": [], "topic": "지그 강성"}
        self.paths = {}

    def doc(self, key):
        if key in self.documents:
            return self.documents[key]
        for doc in self.documents.values():
            if doc["id"] == key:
                return doc
        raise ReviewError("Document is not in this review session: " + str(key))

    def resolve(self, ref):
        """Route by document identity AND requested saved revision, never screen label."""
        doc = self.doc(ref["id"])
        for item in doc["history"]:
            if item["revision"] == ref["revision"]:
                return doc["key"], clone(item["payload"])
        raise ReviewError("This exact saved revision is not retained. Current draft was not substituted.")

    def change(self, key, payload, label):
        doc = self.doc(key)
        if payload == doc["draft"]:
            return
        doc["undo"].append({"payload": clone(doc["draft"]), "label": label})
        doc["redo"].clear()
        doc["draft"] = clone(payload)
        doc["generation"] += 1
        doc["dirty"] = doc["draft"] != doc["saved"] or bool(doc["buffers"])
        self.events.append({"action": label, "owner": doc["id"], "kind": "UI_EDIT"})

    def edit(self, key, field, value):
        payload = clone(self.doc(key)["draft"])
        payload[field] = value
        self.change(key, payload, "Edit " + field)

    def history_step(self, key, redo=False):
        doc = self.doc(key)
        src, dst = ("redo", "undo") if redo else ("undo", "redo")
        if not doc[src]:
            return False
        entry = doc[src].pop()
        doc[dst].append({"payload": clone(doc["draft"]), "label": entry["label"]})
        doc["draft"] = entry["payload"]
        doc["generation"] += 1
        doc["dirty"] = doc["draft"] != doc["saved"] or bool(doc["buffers"])
        return True

    def mask(self, sample_ids, exclude=True, reason="Quality exclusion"):
        doc = self.doc("data")
        payload = clone(doc["draft"])
        valid_ids = {s["id"] for s in payload["samples"]}
        if not set(sample_ids) <= valid_ids:
            raise ReviewError("Selection contains an unknown sample.")
        excluded = set(payload["quality_excluded"])
        if exclude:
            excluded.update(sample_ids)
        else:
            excluded.difference_update(sample_ids)
        payload["quality_excluded"] = sorted(excluded, key=lambda x: int(x[1:]))
        for sid in sample_ids:
            if exclude:
                payload["exclusion_reasons"][sid] = reason
            else:
                payload["exclusion_reasons"].pop(sid, None)
        self.change("data", payload, "Exclude selected samples" if exclude else "Restore selected samples")

    def diagnostics(self, key):
        doc, errors = self.doc(key), []
        data = doc["draft"]
        def positive(field, allow_zero=False):
            value = data.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or (
                    value < 0 if allow_zero else value <= 0):
                errors.append((field, "Enter a finite " + ("nonnegative" if allow_zero else "positive") + " value."))
        if key == "cad":
            for field in ("thickness", "width", "height"):
                positive(field)
            if not data["contact"]["resolved"]:
                errors.append(("contact", "Required contact faces are unresolved."))
        elif key == "material":
            for field in ("mu", "bulk", "L0", "A0"):
                positive(field)
            for dep in data["dependencies"]:
                if dep["missing"] and dep["id"] not in self.relocations:
                    errors.append(("dependencies", "Locate the missing original: " + dep["name"]))
        elif key == "pde":
            for field in ("k", "mesh"):
                positive(field)
            if not data["equation"].strip():
                errors.append(("equation", "An equation is required."))
        elif key == "numerical":
            for var in data["variables"]:
                try:
                    vals = [float(var[f]) for f in ("lower", "start", "upper")]
                    if not all(math.isfinite(x) for x in vals) or not vals[0] <= vals[1] <= vals[2]:
                        raise ValueError()
                except (ValueError, TypeError):
                    errors.append((var["field"], "Required bounds must contain the start value."))
        errors.extend((field, "Unfinished input: " + str(value)) for field, value in doc["buffers"].items())
        return errors

    def save_document(self, key, path=None, fail=False):
        doc = self.doc(key)
        if fail:
            raise ReviewError("Simulated write failure. Saved revision and draft are retained.")
        path = Path(path or doc["file"] or self.workspace / (doc["id"] + ".json"))
        if path.exists():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                disk = previous.get("document", {})
                if disk.get("id") != doc["id"]:
                    raise ReviewError("Different document at this path. Choose another file.")
                if disk.get("revision") != doc["revision"] and str(path) == doc["file"]:
                    raise ReviewError("The saved document changed outside this window. Inspect the conflict.")
            except (json.JSONDecodeError, UnicodeError):
                raise ReviewError("The chosen file is not a review document. Original file is unchanged.")
        saved = clone(doc)
        if doc["dirty"]:
            saved["revision"] += 1
            saved["saved"] = clone(doc["draft"])
            saved["history"].append({"revision": saved["revision"], "payload": clone(doc["draft"]),
                                     "source": "EXPLICIT_REVIEW_SAVE"})
        saved["dirty"] = bool(saved["buffers"])
        saved["file"] = str(path)
        atomic_json(path, {"format": FORMAT, "kind": "document", "document": saved,
                           "draft_valid": not self.diagnostics(key)})
        self.documents[doc["key"]] = saved
        self.paths[doc["id"]] = str(path)
        return {"id": saved["id"], "revision": saved["revision"],
                "payload_hash": digest(saved["saved"]), "path": str(path)}

    def refresh_data_source(self):
        data = self.doc("data")
        if data["dirty"]:
            raise ReviewError("Save Data before using its new observations.")
        plan = clone(self.doc("numerical")["draft"])
        plan["sources"]["data"] = {"id": data["id"], "revision": data["revision"]}
        plan["observation_snapshot"] = clone(data["saved"])
        plan["data_source_stale"] = False
        self.change("numerical", plan, "Refresh saved observations")

    def freeze(self, key):
        doc = self.doc(key)
        errors = self.diagnostics(key)
        if errors:
            raise ReviewError("; ".join(x[1] for x in errors))
        if doc["dirty"]:
            raise ReviewError("Save the current document before freezing its input.")
        frozen_id = token("review-input")
        payload = clone(doc["saved"])
        item = {"id": frozen_id, "mode": "UI_REPLAY_ONLY",
                "source": {"id": doc["id"], "revision": doc["revision"]},
                "payload": payload, "hash": digest(payload)}
        if key == "numerical":
            obs = payload["observation_snapshot"]
            mask = set(obs["quality_excluded"])
            keep = set(payload["train_samples"])
            item["included_ids"] = [s["id"] for s in obs["samples"] if s["id"] not in mask and s["id"] in keep]
            item["included_count"] = len(item["included_ids"])
            item["observation_ref"] = clone(payload["sources"]["data"])
        self.frozen[frozen_id] = item
        return clone(item)

    def create_attempt(self, frozen_id):
        item = self.frozen[frozen_id]
        job = {"id": token("review-job"), "attempt": token("review-attempt"),
               "name": self.doc(item["source"]["id"])["name"],
               "input": frozen_id, "source": clone(item["source"]), "result": None,
               "status": "PREPARED", "mode": "UI_REPLAY_ONLY", "executed": False,
               "remote": False, "connected": True,
               "log": ["Review attempt created. No process was submitted."]}
        self.jobs.append(job)
        return job

    def job_event(self, job_id, event):
        job = next(j for j in self.jobs if j["id"] == job_id)
        if event == "cancel":
            if job["status"] in ("CANCELLED", "RETAINED_FIXTURE", "FAILED"):
                raise ReviewError("The selected review attempt is already terminal.")
            job["status"] = "CANCEL_REQUESTED"
        elif event == "terminal":
            if job["status"] != "CANCEL_REQUESTED":
                raise ReviewError("A terminal cancel receipt is only valid after a request.")
            job["status"] = "CANCELLED"
        elif event == "disconnect":
            job["connected"] = False
        elif event == "reconnect":
            job["connected"] = True
        elif event in ("running", "failed"):
            if job["status"] in ("CANCELLED", "RETAINED_FIXTURE", "FAILED"):
                raise ReviewError("A terminal attempt cannot restart. Create a new attempt.")
            job["status"] = "RUNNING_FIXTURE" if event == "running" else "FAILED"
        elif event == "result":
            if job["result"]:
                return job
            result_id = token("review-result")
            self.results[result_id] = {"id": result_id, "synthetic": True,
                "source": clone(job["source"]), "input": job["input"],
                "attempt": job["attempt"], "time": .04, "status": "RETAINED_FIXTURE",
                "metrics": {"displacement": .31, "mass": .42, "clearance": .12}}
            job["result"] = result_id
            # A late retained fixture belongs to the original cancelled attempt.
            if job["status"] not in ("CANCELLED", "CANCEL_REQUESTED"):
                job["status"] = "RETAINED_FIXTURE"
        else:
            raise ReviewError("Unknown review event.")
        job["log"].append("Synthetic review event: " + event)
        return job

    def prepare_adoption(self, candidate_id):
        candidate = next(c for c in self.candidates if c["id"] == candidate_id)
        if candidate["status"] != "Retained fixture":
            raise ReviewError("Only a retained feasible review candidate can be proposed.")
        group_id = token("review-adoption")
        group = {"id": group_id, "candidate": candidate_id, "status": "PROPOSAL",
                 "result": "fixture-result-clamp", "source_plan": {"id": "N-MOO", "revision": 4},
                 "receipt": None, "owners": {}}
        for key, field in (("cad", "thickness"), ("material", "mu")):
            doc = self.doc(key)
            group["owners"][key] = {
                "field": field, "candidate": candidate[field],
                "proposal_base_revision": 12 if key == "cad" else 17,
                "expected_revision": doc["revision"], "expected_generation": doc["generation"],
                "before": doc["saved"][field], "status": "PENDING", "saved_receipt": None}
        self.groups[group_id] = group
        return group

    def apply_owner(self, group_id, key):
        group, doc = self.groups[group_id], self.doc(key)
        row = group["owners"][key]
        if row["status"] in ("APPLIED", "SAVED"):
            return row
        if doc["revision"] != row["expected_revision"] or doc["generation"] != row["expected_generation"]:
            raise ReviewError("The target changed. Inspect and prepare a fresh proposal; current data is unchanged.")
        if doc["dirty"]:
            raise ReviewError("Save or undo this owner's local edits before applying a candidate.")
        payload = clone(doc["draft"])
        payload[row["field"]] = row["candidate"]
        self.change(key, payload, "Apply " + group["candidate"])
        row["applied_hash"] = digest(payload)
        row["status"] = "APPLIED"
        group["status"] = "PARTIAL"
        return row

    def save_adoption_owner(self, group_id, key, path=None, fail=False):
        group, doc = self.groups[group_id], self.doc(key)
        row = group["owners"][key]
        if row["status"] == "SAVED":
            return clone(row["saved_receipt"])
        if row["status"] != "APPLIED":
            raise ReviewError("Apply this owner explicitly before saving it.")
        if digest(doc["draft"]) != row["applied_hash"]:
            raise ReviewError("The applied draft changed. Review the candidate again.")
        receipt = self.save_document(key, path, fail)
        row["saved_receipt"] = receipt
        row["status"] = "SAVED"
        return receipt

    def publish_group(self, group_id):
        group = self.groups[group_id]
        if group["receipt"]:
            return clone(group["receipt"])
        if not all(r["status"] == "SAVED" for r in group["owners"].values()):
            raise ReviewError("Save each applied owner. A partial result is not a published group.")
        for key, row in group["owners"].items():
            doc, receipt = self.doc(key), row["saved_receipt"]
            if doc["dirty"] or doc["revision"] != receipt["revision"] or digest(doc["saved"]) != receipt["payload_hash"]:
                raise ReviewError("A target changed after its save. Re-inspect the group.")
        receipt = {"group": group_id, "candidate": group["candidate"],
                   "source_plan": clone(group["source_plan"]), "result": group["result"],
                   "owners": {k: clone(v["saved_receipt"]) for k, v in group["owners"].items()},
                   "mode": "UI_REPLAY_ONLY"}
        atomic_json(self.workspace / (group_id + ".json"), receipt)
        group["receipt"], group["status"] = receipt, "PUBLISHED"
        return clone(receipt)

    def cancel_adoption(self, group_id):
        group = self.groups[group_id]
        if group["receipt"]:
            raise ReviewError("This group is already published. Open its saved receipt.")
        group["status"] = "CANCELLED"
        # Already-applied drafts and already-saved revisions remain explicitly visible.

    def mark_dependency_missing(self, key="material"):
        doc = self.doc(key)
        if doc["revision"] != 19:
            raise ReviewError("Use the saved Material revision 19 scenario, or finish the p19 save first.")
        dep = doc["saved"]["dependencies"][0]
        dep["missing"] = True
        doc["draft"]["dependencies"][0]["missing"] = True
        for item in doc["history"]:
            if item["revision"] == 19:
                item["payload"]["dependencies"][0]["missing"] = True

    def repair_dependency(self, key, dep_id, candidate_path, changed_branch=False):
        doc = self.doc(key)
        dep = next(d for d in doc["saved"]["dependencies"] if d["id"] == dep_id)
        candidate_path = Path(candidate_path)
        checksum = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        if checksum == dep["sha256"]:
            self.relocations[dep_id] = {"path": str(candidate_path), "sha256": checksum,
                                       "document": doc["id"], "revision": doc["revision"]}
            return {"kind": "IDENTICAL_REPAIR", "id": doc["id"], "revision": doc["revision"]}
        if not changed_branch:
            raise ReviewError("Content changed. Original revision is preserved; create a separate branch.")
        new_doc = clone(doc)
        new_doc["key"] = token("material-branch")
        new_doc["id"] = token("MAT")
        new_doc["revision"], new_doc["file"], new_doc["history"] = 0, None, []
        new_doc["draft"]["dependencies"][0].update(sha256=checksum, missing=False)
        new_doc["draft"]["branch_of"] = {"id": doc["id"], "revision": doc["revision"]}
        new_doc["dirty"], new_doc["undo"], new_doc["redo"] = True, [], []
        self.documents[new_doc["key"]] = new_doc
        self.relocations[new_doc["id"] + "/" + dep_id] = {"path": str(candidate_path), "sha256": checksum}
        return {"kind": "CHANGED_CONTENT_BRANCH", "key": new_doc["key"], "id": new_doc["id"]}

    def append_reply(self, text, topic, reply_to=None):
        if not text.strip():
            raise ReviewError("Write a reply first.")
        payload = clone(self.doc("expert")["draft"])
        turn = {"id": token("user-turn"), "role": "사용자", "actual": True,
                "text": text.strip(), "topic": topic, "reply_to": reply_to, "evidence": []}
        payload["turns"].append(turn)
        payload["pending_text"] = ""
        self.change("expert", payload, "Save user reply")
        return turn

    def material_repair_scenario(self):
        doc = self.doc("material")
        doc["revision"] = 19
        doc["saved"]["mu"] = 1.12
        doc["draft"] = clone(doc["saved"])
        doc["history"].append({"revision": 19, "payload": clone(doc["saved"]), "source": "FIXTURE"})
        self.mark_dependency_missing()

    def dump(self):
        return {"format": FORMAT, "kind": "session", "documents": self.documents,
                "jobs": self.jobs, "frozen": self.frozen, "results": self.results,
                "candidates": self.candidates, "groups": self.groups,
                "relocations": self.relocations, "selected": self.selected,
                "paths": self.paths, "events": self.events,
                "qualification": "UNKNOWN", "release": "NOT_RELEASED",
                "F05": {"value": 3.32295e-6, "tolerance": 1e-6, "verdict": "FAIL"}}

    def save_session(self, path):
        atomic_json(Path(path), self.dump())

    @classmethod
    def open_session(cls, path):
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("format") != FORMAT or raw.get("kind") != "session":
            raise ReviewError("Choose a UX review session file.")
        session = cls(path.parent)
        for field in ("documents", "jobs", "frozen", "results", "candidates", "groups",
                      "relocations", "selected", "paths", "events"):
            setattr(session, field, clone(raw[field]))
        return session

    def open_document(self, path):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("format") != FORMAT or raw.get("kind") != "document":
            raise ReviewError("Choose a UX review document file.")
        doc = raw["document"]
        key = doc["key"]
        if key in self.documents and self.documents[key]["dirty"]:
            raise ReviewError("An unsaved document is open. Save or undo it before reopening.")
        doc["file"] = str(Path(path))
        self.documents[key] = doc
        return key
